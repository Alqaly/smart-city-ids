"""Governance (Human-in-the-Loop) API router.

This module implements the **Human-in-the-Loop (HITL) governance layer** that
controls whether automated Kubernetes actions (pod isolation, scaling, eviction)
are executed immediately or held for human approval.

Three user-selectable automation modes are supported, plus an API-only
emergency bypass:

    ┌─────────────┬──────────────────────────────────────────────────────────┐
    │ Mode        │ Behaviour                                                │
    ├─────────────┼──────────────────────────────────────────────────────────┤
    │ autonomous  │ High-confidence actions execute automatically.            │
    │ assisted    │ Medium-confidence actions require one-click approval.     │
    │ manual      │ Every recommended action is queued for human review.      │
    ├─────────────┼──────────────────────────────────────────────────────────┤
    │ emergency   │ API-only: sev 10 + conf ≥ 0.85 bypasses all gates.       │
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
        set_autonomous_force_execution,  # (enabled) -> dict
    )
    return {
        "governance": governance,
        "get_mode": get_automation_mode,
        "set_mode": set_automation_mode,
        "pending": get_pending_actions,
        "status": get_governance_status,
        "approve": approve_pending_action,
        "reject": reject_pending_action,
        "set_force_autonomy": set_autonomous_force_execution,
    }


def _deps():
    """Retrieve K8s automation client and database handle from shared state."""
    from api._state import k8s_automation, db
    return k8s_automation, db


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/status")
async def governance_status(user: str = Depends(verify_token)):
    """Get Human-in-the-Loop governance status.

    Returns a comprehensive dashboard dict including the current mode,
    counts of pending / approved / rejected actions, and aggregate metrics.
    Merges in-process runtime counters with persisted DB lifetime totals
    so counters survive pod restarts.
    """
    status = _gov()["status"]()
    # Merge lifetime DB counts so counters survive restarts.
    try:
        _, db = _deps()
        db_counts = db.get_automation_action_counts()
        rt = status.get("metrics", {})
        rt["auto_executed"] = max(rt.get("auto_executed", 0), db_counts.get("auto_executed", 0) + db_counts.get("executed", 0))
        approved_db = db_counts.get("approved_and_executed", 0)
        rt["approved"] = max(rt.get("approved", 0), approved_db)
        rt["manual_approved"] = max(rt.get("manual_approved", 0), approved_db)
        rt["rejected"] = max(rt.get("rejected", 0), db_counts.get("rejected", 0))
        rt["expired"] = max(rt.get("expired", 0), db_counts.get("expired", 0))
        total_db = db_counts.get("total", 0)
        rt["total_actions_requested"] = max(rt.get("total_actions_requested", 0), total_db)
        status["metrics"] = rt
    except Exception:
        pass  # graceful: return runtime-only if DB is unreachable
    return status


@router.get("/mode")
async def get_mode(user: str = Depends(verify_token)):
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


@router.post("/autonomy/force")
async def set_autonomy_force(enabled: bool = False, user: str = Depends(verify_token)):
    """Enable/disable full LLM autonomous force-execution profile.

    When enabled, autonomous mode executes all recommended actions without
    confidence gating (protected targets are still gated unless emergency
    bypass criteria are met).
    """
    return _gov()["set_force_autonomy"](enabled)


@router.get("/pending")
async def list_pending_actions(user: str = Depends(verify_token)):
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

    # Approve in governance engine, then execute asynchronously in this route.
    result = g["approve"](action_id, operator, None, operator_comment=comment)

    # Record metrics and persist audit trail on successful execution.
    if result.get("status") == "approved_and_executed":
        execution_result = {"success": False, "error": "not_executed"}
        if not k8s_automation:
            execution_result = {"success": False, "error": "K8s automation not available"}
        else:
            try:
                if action.action_type == "isolate_pod":
                    await k8s_automation.isolate_pod(action.target, Config.K8S_NAMESPACE)
                    execution_result = {"success": True}
                elif action.action_type == "scale_up":
                    await k8s_automation.scale_deployment(action.target, 3, Config.K8S_NAMESPACE)
                    execution_result = {"success": True}
                elif action.action_type == "block_ip":
                    target_workload = None
                    try:
                        if isinstance(action.context, dict):
                            target_workload = action.context.get("target_workload")
                    except Exception:
                        target_workload = None
                    await k8s_automation.block_ip(
                        action.target,
                        Config.K8S_NAMESPACE,
                        target_workload=target_workload,
                    )
                    execution_result = {"success": True}
                elif action.action_type == "cordon_node":
                    await k8s_automation.cordon_node(action.target)
                    execution_result = {"success": True}
                else:
                    execution_result = {"success": False, "error": f"Unsupported action type: {action.action_type}"}
            except Exception as exc:
                execution_result = {"success": False, "error": str(exc)}

        result["execution_result"] = execution_result
        if execution_result.get("success"):
            PROM_AUTOMATED_DECISIONS.labels(action_type=action.action_type).inc()
            # Time-to-mitigation = seconds from action creation to approval/execution.
            PROM_TIME_TO_MITIGATION.observe(max(0.0, time.time() - action.created_at))
        else:
            result["status"] = "approved_execution_failed"

        PROM_HUMAN_OVERRIDE_REQUESTS.labels(reason="approved").inc()
        # Persist to database for audit trail and compliance.
        db.add_automation_action({
            "alert_id": action.alert_id,
            "action_type": action.action_type,
            "target_resource": action.target,
            "target_namespace": Config.K8S_NAMESPACE,
            "status": "approved_and_executed" if execution_result.get("success") else "approved_execution_failed",
            "error_message": execution_result.get("error"),
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
async def action_history(limit: int = 100, user: str = Depends(verify_token)):
    """Get recent action history for audit trail.

    Returns the last ``limit`` governance decisions (approved, rejected,
    auto-executed) in reverse chronological order.  Reads from the
    persistent database audit_logs table so history survives pod restarts.

    Args:
        limit: Maximum number of history entries to return (default 100).
    """
    _, db = _deps()
    if db:
        rows = db.get_governance_audit_logs(limit=limit)
        history = []
        for r in rows:
            details = r.get("details") or {}
            if isinstance(details, str):
                import json as _json
                try:
                    details = _json.loads(details)
                except Exception:
                    details = {}
            inner = details.get("details", {}) if isinstance(details.get("details"), dict) else {}
            event = details.get("event", r.get("action", ""))
            mode = details.get("mode", "")
            ts = r.get("created_at")
            if hasattr(ts, "isoformat"):
                ts = ts.isoformat()
            # Build target and status based on event type
            if event == "mode_change":
                target = f"{inner.get('old', '?')} → {inner.get('new', '?')}"
                status = "completed"
                operator = r.get("actor") or "system"
            elif event == "autonomous_force_toggle":
                enabled = inner.get("enabled")
                target = f"force_autonomy={'on' if enabled else 'off'}"
                status = "toggled"
                operator = r.get("actor") or "system"
            else:
                target = inner.get("target", inner.get("resource_id", r.get("resource_id", ""))) or ""
                status = inner.get("status", r.get("status", "")) or event
                operator = inner.get("approved_by", r.get("actor", "")) or "system"
            history.append({
                "timestamp": ts or details.get("timestamp", ""),
                "action_type": event,
                "target": target,
                "status": status,
                "operator": operator,
                "mode": mode,
            })
        # Get total count from DB for display purposes
        total_count = len(history)
        try:
            with db._cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM audit_logs WHERE resource_type = 'governance'")
                total_count = cur.fetchone()[0]
        except Exception:
            pass
        return {"total": total_count, "history": history}
    g = _gov()
    return {"total": 0, "history": g["governance"].get_action_history(limit)}
