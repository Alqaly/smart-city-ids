"""Governance (Human-in-the-Loop) API router."""

from datetime import datetime
import time

from fastapi import APIRouter, Depends, HTTPException

from config import Config
from infrastructure.auth import verify_token
from infrastructure.metrics import (
    PROM_APPROVAL_PENDING,
    PROM_AUTOMATED_DECISIONS,
    PROM_HUMAN_OVERRIDE_REQUESTS,
    PROM_TIME_TO_MITIGATION,
)

router = APIRouter(prefix="/api/governance", tags=["governance"])


def _gov():
    """Lazy-import governance helpers."""
    from governance import (
        governance,
        get_automation_mode,
        set_automation_mode,
        get_pending_actions,
        get_governance_status,
        approve_pending_action,
        reject_pending_action,
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
    from api._state import k8s_automation, db
    return k8s_automation, db


@router.get("/status")
async def governance_status(user: str = Depends(verify_token)):
    """Get Human-in-the-Loop governance status."""
    return _gov()["status"]()


@router.get("/mode")
async def get_mode(user: str = Depends(verify_token)):
    """Get current automation mode."""
    return {"mode": _gov()["get_mode"]()}


@router.post("/mode")
async def change_mode(mode: str = "assisted", user: str = Depends(verify_token)):
    """Change automation mode (autopilot / assisted / manual)."""
    g = _gov()
    result = g["set_mode"](mode)
    if result["status"] == "success":
        from infrastructure.metrics import PROM_AUTOMATION_MODE
        for m in ["autopilot", "assisted", "manual"]:
            PROM_AUTOMATION_MODE.labels(mode=m).set(1 if m == mode else 0)
    return result


@router.get("/pending")
async def list_pending_actions(user: str = Depends(verify_token)):
    """List actions pending human approval."""
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
    """Approve a pending action and execute it."""
    g = _gov()
    k8s_automation, db = _deps()
    action = g["governance"]._pending_actions.get(action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")

    def execute():
        if k8s_automation:
            if action.action_type == "isolate_pod":
                return k8s_automation.isolate_pod(action.target)
            elif action.action_type == "scale_up":
                return k8s_automation.scale_deployment(action.target, 3)
            elif action.action_type == "evict_pod":
                return k8s_automation.evict_pod(action.target)
        return {"success": False, "error": "K8s automation not available"}

    result = g["approve"](action_id, operator, execute, operator_comment=comment)

    if result.get("status") == "approved_and_executed":
        PROM_HUMAN_OVERRIDE_REQUESTS.labels(reason="approved").inc()
        PROM_AUTOMATED_DECISIONS.labels(action_type=action.action_type).inc()
        PROM_TIME_TO_MITIGATION.observe(max(0.0, time.time() - action.created_at))
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
    """Reject a pending action."""
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
    """Get recent action history for audit trail."""
    g = _gov()
    return {"history": g["governance"].get_action_history(limit)}
