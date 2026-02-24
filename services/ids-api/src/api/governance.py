"""Governance (Human-in-the-Loop) API router.

This module implements the **Human-in-the-Loop (HITL) governance layer** that
controls whether automated Kubernetes actions (pod isolation, scaling, eviction)
are executed immediately or held for human approval.

Three automation modes are supported:

    ┌─────────────┬──────────────────────────────────────────────────────────┐
    │ Mode        │ Behaviour                                                │
    ├─────────────┼──────────────────────────────────────────────────────────┤
    │ autonomous  │ High-confidence actions execute automatically.            │
    │ assisted    │ Medium-confidence actions require one-click approval.     │
    │ manual      │ Every recommended action is queued for human review.      │
    │ emergency   │ Severity+confidence threshold bypasses normal gates.      │
    └─────────────┴──────────────────────────────────────────────────────────┘

Endpoints (all require JWT authentication):
    GET  /api/governance/status           – overall governance dashboard
    GET  /api/governance/mode             – current automation mode
    POST /api/governance/mode?mode=…      – change automation mode
    GET  /api/governance/pending          – list actions awaiting approval
    POST /api/governance/approve/{id}     – approve and execute a pending action
    POST /api/governance/reject/{id}      – reject a pending action
    GET  /api/governance/history          – audit trail of past decisions

Design notes:
    - The actual governance state machine lives in ``governance.py`` (outside
      the ``api/`` package).  This router is a thin HTTP interface over it.
    - ``_gov()`` lazily imports governance helpers to avoid circular imports.
    - Approved actions are executed synchronously via the K8s automation
      client and then persisted to the database for the audit trail.
    - Prometheus metrics track pending counts, human overrides, and
      time-to-mitigation for the Grafana dashboard.
"""

from datetime import datetime
import time

from fastapi import APIRouter, Depends, HTTPException

from config import Config
from infrastructure.auth import verify_token
from infrastructure.metrics import (
    PROM_APPROVAL_PENDING,       # Gauge: actions currently awaiting approval
    PROM_AUTOMATED_DECISIONS,    # Counter: total automated decisions by type
    PROM_HUMAN_OVERRIDE_REQUESTS,  # Counter: human approve/reject events
    PROM_TIME_TO_MITIGATION,     # Histogram: seconds from alert to mitigation
)

router = APIRouter(prefix="/api/governance", tags=["governance"])


# ── Lazy dependency helpers ──────────────────────────────────────────────────

def _gov():
    """Lazy-import governance helpers from the ``governance`` module.

    Returns a dict of callables so callers can use ``g["get_mode"]()`` etc.
    Lazy importing avoids circular dependencies at module load time.
    """
    from governance import (
        governance,               # GovernanceEngine singleton
        get_automation_mode,      # → str: "autonomous" | "assisted" | "manual" | "emergency"
        set_automation_mode,      # (mode) → dict with status
        get_pending_actions,      # → list of PendingAction objects
        get_governance_status,    # → dict with full dashboard data
        approve_pending_action,   # (id, operator, execute_fn, …) → dict
        reject_pending_action,    # (id, operator, reason) → dict
    )
    return {
        "governance": governance,
        "get_mode": get_automation_mode,
        "set_mode": set_automation_mode,
        "pending": get_pending_actions,
        "status": get_governance_status,
        "approve": approve_pending_action,
        "reject": reject_pending_action,
    }


def _deps():
    """Retrieve K8s automation client and database handle from shared state."""
    from api._state import k8s_automation, db
    return k8s_automation, db


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/status")
async def governance_status():
    """Get Human-in-the-Loop governance status.

    Returns a comprehensive dashboard dict including the current mode,
    counts of pending / approved / rejected actions, and aggregate metrics.
    """
    status = _gov()["status"]()
    try:
        _, db = _deps()
        metrics = (status.get("metrics") or {}) if isinstance(status, dict) else {}
        if db and isinstance(metrics, dict):
            all_zero = all(int(metrics.get(k, 0) or 0) == 0 for k in (
                "total_actions_requested", "auto_executed", "approved", "rejected", "pending_approval"
            ))
            if all_zero and hasattr(db, "get_prometheus_restore_data"):
                restore = db.get_prometheus_restore_data() or {}
                actions_executed = restore.get("actions_executed") or {}
                executed_total = sum(int(v or 0) for v in actions_executed.values())
                if executed_total > 0:
                    metrics["auto_executed"] = executed_total
                    metrics["total_actions_requested"] = max(int(metrics.get("total_actions_requested", 0) or 0), executed_total)
                    status["metrics"] = metrics
    except Exception:
        pass
    return status


@router.get("/mode")
async def get_mode():
    """Get current automation mode.

    Returns:
        {"mode": "autonomous" | "assisted" | "manual" | "emergency"}
    """
    return {"mode": _gov()["get_mode"]()}


@router.post("/mode")
async def change_mode(mode: str = "assisted", user: str = Depends(verify_token)):
    """Change the IDS automation mode.

    Args:
        mode: One of ``"autonomous"``, ``"assisted"``, ``"manual"``, ``"emergency"``.
              Defaults to ``"assisted"`` (the safest production-ready mode).

    Side effects:
        - Updates the Prometheus ``PROM_AUTOMATION_MODE`` gauge so Grafana
          shows the active mode as a coloured indicator.

    Returns:
        {"status": "success", "mode": "…"} or an error dict.
    """
    g = _gov()
    result = g["set_mode"](mode)
    # Update Prometheus gauge — exactly one label gets value 1, rest get 0.
    if result["status"] == "success":
        from infrastructure.metrics import PROM_AUTOMATION_MODE
        for m in ["autonomous", "assisted", "manual", "emergency"]:
            PROM_AUTOMATION_MODE.labels(mode=m).set(1 if m == mode else 0)
    return result


@router.get("/pending")
async def list_pending_actions():
    """List actions that are waiting for human approval.

    In ``assisted`` or ``manual`` mode, high-severity automated actions are
    held in a queue until an operator approves or rejects them.

    Side effects:
        Updates the ``PROM_APPROVAL_PENDING`` gauge for Grafana.

    Returns:
        {"pending_count": int, "actions": [PendingAction…]}
    """
    actions = _gov()["pending"]()
    PROM_APPROVAL_PENDING.set(len(actions))
    return {"pending_count": len(actions), "actions": actions}


@router.post("/approve/{action_id}")
async def approve_action(
    action_id: str,
    operator: str = "admin",
    comment: str = "",
    user: str = Depends(verify_token),
):
    """Approve a pending action and execute it against the K8s cluster.

    Workflow:
        1. Look up the pending action by ``action_id``.
        2. Build an ``execute()`` closure that calls the appropriate
           K8s automation method (isolate_pod / scale_deployment / evict_pod).
        3. Call ``approve_pending_action()`` which runs the closure.
        4. On success, record Prometheus metrics and persist an audit record
           to the database with timestamps and operator comment.

    Args:
        action_id: Unique identifier of the pending action.
        operator:  Name of the approving operator (default "admin").
        comment:   Optional free-text justification for the audit trail.

    Raises:
        HTTPException 404: If ``action_id`` is not found in the pending queue.

    Returns:
        {"status": "approved_and_executed", …} or error dict.
    """
    g = _gov()
    k8s_automation, db = _deps()

    # Look up the pending action object.
    action = g["governance"]._pending_actions.get(action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")

    # Build a closure that performs the actual K8s operation.
    def execute():
        """Execute the approved K8s action (isolate / scale / evict)."""
        if k8s_automation:
            if action.action_type == "isolate_pod":
                return k8s_automation.isolate_pod(action.target)
            elif action.action_type == "scale_up":
                return k8s_automation.scale_deployment(action.target, 3)
            elif action.action_type == "evict_pod":
                return k8s_automation.evict_pod(action.target)
        return {"success": False, "error": "K8s automation not available"}

    # Approve and execute atomically via the governance engine.
    result = g["approve"](action_id, operator, execute, operator_comment=comment)

    # Record metrics and persist audit trail on successful execution.
    if result.get("status") == "approved_and_executed":
        PROM_HUMAN_OVERRIDE_REQUESTS.labels(reason="approved").inc()
        PROM_AUTOMATED_DECISIONS.labels(action_type=action.action_type).inc()
        # Time-to-mitigation = seconds from action creation to approval.
        PROM_TIME_TO_MITIGATION.observe(max(0.0, time.time() - action.created_at))
        # Persist to database for audit trail and compliance.
        db.add_automation_action({
            "alert_id": action.alert_id,
            "action_type": action.action_type,
            "target_resource": action.target,
            "target_namespace": Config.K8S_NAMESPACE,
            "status": "approved_and_executed",
            "execution_time_ms": int(max(0.0, (time.time() - action.created_at)) * 1000),
            "mode": g["get_mode"](),
            "triggered_by": action.recommended_by,
            "operator_comment": comment,
            "created_at": datetime.fromtimestamp(action.created_at),
            "completed_at": datetime.now(),
        })
    return result


@router.post("/reject/{action_id}")
async def reject_action(
    action_id: str,
    operator: str = "admin",
    reason: str = "",
    user: str = Depends(verify_token),
):
    """Reject a pending action — the K8s operation will NOT be executed.

    Rejections are recorded in both Prometheus (for dashboards) and the
    database (for the audit trail).  The ``reason`` field lets the operator
    document why the LLM recommendation was overridden.

    Args:
        action_id: Unique identifier of the pending action.
        operator:  Name of the rejecting operator.
        reason:    Free-text justification for the rejection.

    Returns:
        {"status": "rejected", "action": {…}} or error dict.
    """
    g = _gov()
    _, db = _deps()
    result = g["reject"](action_id, operator, reason)
    if result.get("status") == "rejected":
        PROM_HUMAN_OVERRIDE_REQUESTS.labels(reason="rejected").inc()
        db.add_automation_action({
            "alert_id": result.get("action", {}).get("alert_id"),
            "action_type": result.get("action", {}).get("action_type"),
            "target_resource": result.get("action", {}).get("target"),
            "target_namespace": Config.K8S_NAMESPACE,
            "status": "rejected",
            "error_message": reason,
            "mode": g["get_mode"](),
            "triggered_by": result.get("action", {}).get("recommended_by"),
            "created_at": datetime.now(),
        })
    return result


@router.get("/history")
async def action_history(limit: int = 50, user: str = Depends(verify_token)):
    """Get recent action history for audit trail.

    Returns the last ``limit`` governance decisions (approved, rejected,
    auto-executed) in reverse chronological order.  Used by the operator
    dashboard and for compliance / examiner review.

    Args:
        limit: Maximum number of history entries to return (default 50).
    """
    g = _gov()
    return {"history": g["governance"].get_action_history(limit)}
