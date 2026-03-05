"""
Human-in-the-Loop Governance System
Capstone II Integration Plan - TASK 4

Implements three automation modes:
- AUTONOMOUS: High-confidence actions auto-execute
- ASSISTED: Medium-confidence actions require quick operator approval
- MANUAL: Human-only execution
- EMERGENCY: Catastrophic high-confidence events bypass gates

Each mode provides IEEE-defensible trade-offs between response time and safety.
"""

import os
import time
import json
import logging
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime
import threading
from collections import deque

logger = logging.getLogger(__name__)

try:
    from database import db
except Exception:
    db = None

try:
    from config import Config
except Exception:
    Config = None


class AutomationMode(Enum):
    """
    Human-in-the-Loop automation modes.
    
    AUTONOMOUS: High-confidence autonomous execution
    
    ASSISTED: Balanced automation
    - Medium confidence actions require 1-click approval
    
    MANUAL: Human-controlled
    - All actions require explicit operator action

    EMERGENCY: Catastrophic threat response
    - Severity + confidence threshold bypasses normal gates
    """
    AUTONOMOUS = "autonomous"
    ASSISTED = "assisted"
    MANUAL = "manual"
    EMERGENCY = "emergency"
    
    # Legacy compatibility
    AUTOPILOT = "autonomous"
    LIVE = "autonomous"     # Map old "live" to autonomous
    DRY_RUN = "manual"     # Map old "dry-run" to manual


@dataclass(frozen=True)
class AutoDecision:
    """Compatibility wrapper for auto-execution decisions.

    Behaves like:
    - a boolean (`if decision:`) using `allowed`
    - a 2-tuple (`allowed, reason = decision`) for existing code paths
    """
    allowed: bool
    reason: str

    def __bool__(self) -> bool:
        return bool(self.allowed)

    def __iter__(self):
        yield self.allowed
        yield self.reason


@dataclass
class PendingAction:
    """An action awaiting human approval."""
    id: str
    action_type: str
    target: str
    severity: int
    reason: str
    recommended_by: str  # LLM engine that recommended it
    alert_id: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    status: str = "pending"  # pending, approved, rejected, expired, auto_executed
    approved_by: Optional[str] = None
    approved_at: Optional[float] = None
    execution_result: Optional[Dict] = None
    operator_comment: Optional[str] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for API responses."""
        return {
            **asdict(self),
            "operator_comment": self.operator_comment,
            "created_at_iso": datetime.fromtimestamp(self.created_at).isoformat(),
            "expires_at_iso": datetime.fromtimestamp(self.expires_at).isoformat() if self.expires_at else None,
            "age_seconds": time.time() - self.created_at
        }


class GovernanceController:
    """
    Central governance controller for Human-in-the-Loop automation.
    
    Thread-safe singleton that manages:
    - Automation mode selection
    - Pending action queue
    - Approval workflow
    - Audit logging
    """
    
    _instance = None
    _lock = threading.Lock()
    
    # Configuration defaults
    DEFAULT_MODE = AutomationMode.ASSISTED
    AUTONOMOUS_MIN_CONFIDENCE = 0.90
    ASSISTED_MIN_CONFIDENCE = 0.70
    EMERGENCY_MIN_CONFIDENCE = 0.85
    EMERGENCY_SEVERITY = 10
    AUTONOMOUS_FORCE_EXECUTION = False
    ACTION_EXPIRY_SECONDS = 300  # 5 minutes
    MAX_PENDING_ACTIONS = 100
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        
        # Load configuration
        mode_str = os.getenv("AUTOMATION_MODE", "assisted").lower()
        self._mode = self._parse_mode(mode_str)
        self._autonomous_min_confidence = float(os.getenv("AUTONOMOUS_MIN_CONFIDENCE", str(self.AUTONOMOUS_MIN_CONFIDENCE)))
        self._assisted_min_confidence = float(os.getenv("ASSISTED_MIN_CONFIDENCE", str(self.ASSISTED_MIN_CONFIDENCE)))
        self._emergency_min_confidence = float(os.getenv("EMERGENCY_MIN_CONFIDENCE", str(self.EMERGENCY_MIN_CONFIDENCE)))
        self._emergency_severity = int(os.getenv("EMERGENCY_SEVERITY_THRESHOLD", str(self.EMERGENCY_SEVERITY)))
        self._autonomous_force_execution = (
            str(os.getenv("AUTONOMOUS_FORCE_EXECUTION", str(self.AUTONOMOUS_FORCE_EXECUTION))).strip().lower()
            in ("1", "true", "yes", "on")
        )
        self._action_expiry = int(os.getenv("ACTION_EXPIRY_SECONDS", str(self.ACTION_EXPIRY_SECONDS)))
        
        # State
        self._pending_actions: Dict[str, PendingAction] = {}
        self._action_history: deque = deque(maxlen=1000)
        self._action_counter = 0
        self._state_lock = threading.Lock()
        
        # Callbacks
        self._on_approval_callbacks: List[Callable] = []
        self._on_rejection_callbacks: List[Callable] = []
        
        # Metrics
        self._metrics = {
            "total_actions_requested": 0,
            "auto_executed": 0,
            "pending_approval": 0,
            "approved": 0,
            "rejected": 0,
            "expired": 0,
            "blocked_dry_run": 0,
        }
        
        logger.info(
            "GovernanceController initialized: "
            f"mode={self._mode.value}, autonomous={self._autonomous_min_confidence}, "
            f"assisted={self._assisted_min_confidence}, emergency=sev{self._emergency_severity}/conf{self._emergency_min_confidence}, "
            f"autonomous_force_execution={self._autonomous_force_execution}"
        )
    
    def _parse_mode(self, mode_str: str) -> AutomationMode:
        """Parse mode string with legacy compatibility."""
        mode_map = {
            "autonomous": AutomationMode.AUTONOMOUS,
            "autopilot": AutomationMode.AUTONOMOUS,
            "assisted": AutomationMode.ASSISTED,
            "manual": AutomationMode.MANUAL,
            "emergency": AutomationMode.EMERGENCY,
            "live": AutomationMode.AUTONOMOUS,
            "dry-run": AutomationMode.MANUAL,
            "approval-required": AutomationMode.ASSISTED,
        }
        return mode_map.get(mode_str, self.DEFAULT_MODE)
    
    @property
    def mode(self) -> AutomationMode:
        """Current automation mode."""
        return self._mode
    
    @mode.setter
    def mode(self, value: AutomationMode):
        """Change automation mode (requires appropriate permissions in production)."""
        old_mode = self._mode
        self._mode = value
        logger.warning(f"Automation mode changed: {old_mode.value} → {value.value}")
        self._log_audit("mode_change", {"old": old_mode.value, "new": value.value})

    # Backward-compatible helper used by legacy tests/scripts.
    def set_mode(self, value: AutomationMode | str):
        if isinstance(value, str):
            self.mode = self._parse_mode(value)
        else:
            self.mode = value
        return self._mode
    
    def should_auto_execute(
        self,
        action_type: str,
        severity: int,
        confidence: Optional[float] = None,
        target: Optional[str] = None,
    ) -> AutoDecision:
        """
        Determine if an action should execute automatically.
        
        Returns:
            (should_execute, reason)
        """
        # Legacy behavior for older callers/tests that pass only severity:
        # make a severity-based decision when confidence is omitted.
        if confidence is None:
            if self._mode == AutomationMode.MANUAL:
                return AutoDecision(False, "MANUAL mode: all actions require human approval")
            if self._mode == AutomationMode.ASSISTED:
                # Legacy behavior: lower severity auto, high severity approval.
                if int(severity or 0) < 8:
                    return AutoDecision(True, "ASSISTED mode (legacy severity path): low severity auto-execute")
                return AutoDecision(False, "ASSISTED mode (legacy severity path): high severity requires approval")
            if self._mode == AutomationMode.EMERGENCY:
                return AutoDecision(int(severity or 0) >= int(self._emergency_severity), "EMERGENCY mode (legacy severity path)")
            return AutoDecision(True, "AUTONOMOUS mode (legacy severity path)")

        conf = float(confidence or 0.0)

        if (
            self._mode == AutomationMode.EMERGENCY
            and severity >= self._emergency_severity
            and conf >= self._emergency_min_confidence
        ):
            return AutoDecision(True, "EMERGENCY mode: severity/confidence threshold met")
        
        if self._mode == AutomationMode.AUTONOMOUS:
            if self._autonomous_force_execution:
                return AutoDecision(True, "AUTONOMOUS mode: force execution profile enabled")
            if conf >= self._autonomous_min_confidence:
                return AutoDecision(True, f"AUTONOMOUS mode: confidence {conf:.2f} >= {self._autonomous_min_confidence:.2f}")
            return AutoDecision(False, f"AUTONOMOUS mode: confidence {conf:.2f} below threshold")
        
        elif self._mode == AutomationMode.ASSISTED:
            if conf >= self._autonomous_min_confidence:
                return AutoDecision(True, "ASSISTED mode: high confidence auto-execute")
            elif conf >= self._assisted_min_confidence:
                return AutoDecision(False, (
                    f"ASSISTED mode: confidence {conf:.2f} in approval band "
                    f"[{self._assisted_min_confidence:.2f}, {self._autonomous_min_confidence:.2f})"
                ))
            else:
                return AutoDecision(False, f"ASSISTED mode: confidence {conf:.2f} below assisted threshold")
        
        elif self._mode == AutomationMode.MANUAL:
            return AutoDecision(False, "MANUAL mode: all actions require human approval")

        return AutoDecision(False, "Unknown mode")

    @property
    def autonomous_force_execution(self) -> bool:
        """Whether autonomous mode force-executes all LLM-recommended actions."""
        return bool(self._autonomous_force_execution)

    def set_autonomous_force_execution(self, enabled: bool) -> bool:
        """Toggle full autonomous force-execution profile at runtime."""
        with self._state_lock:
            self._autonomous_force_execution = bool(enabled)
        self._log_audit(
            "autonomous_force_toggle",
            {"enabled": bool(enabled), "mode": self._mode.value},
        )
        logger.warning("Autonomous force execution toggled: %s", bool(enabled))
        return self._autonomous_force_execution
    
    def request_action(self, action_type: str, target: str, severity: int,
                      reason: str, recommended_by: str = "llm",
                      confidence: float = 0.0,
                      alert_id: Optional[str] = None,
                      context: Optional[Dict[str, Any]] = None,
                      execute_callback: Optional[Callable] = None) -> Dict:
        """
        Request an automated action through the governance system.
        
        Args:
            action_type: Type of action (isolate_pod, scale_up, evict_pod, etc.)
            target: Target resource (pod name, service name, etc.)
            severity: Severity score (1-10)
            reason: Why this action is recommended
            recommended_by: LLM engine that recommended the action
            alert_id: Associated alert ID
            execute_callback: Function to call if action is approved/auto-executed
            
        Returns:
            Dict with status and action details
        """
        with self._state_lock:
            self._metrics["total_actions_requested"] += 1

        mode_name = self._mode.value
        target_lower = str(target or "").lower()
        protected_services = []
        if Config is not None:
            try:
                protected_services = [str(s).strip().lower() for s in (Config.PROTECTED_SERVICES or []) if str(s).strip()]
            except Exception:
                protected_services = []
        is_protected_target = any(ps and ps in target_lower for ps in protected_services)
        emergency_bypass = (
            mode_name == "emergency"
            and int(severity or 0) >= int(self._emergency_severity)
            and float(confidence or 0.0) >= float(self._emergency_min_confidence)
        )

        if is_protected_target and not emergency_bypass:
            should_execute = False
            explanation = "Protected target requires operator approval"
        else:
            should_execute, explanation = self.should_auto_execute(action_type, severity, confidence, target)
        
        if should_execute:
            with self._state_lock:
                self._metrics["auto_executed"] += 1
            # Execute immediately
            result = None
            if execute_callback:
                try:
                    result = execute_callback()
                except Exception as e:
                    logger.error(f"Action execution failed: {e}")
                    result = {"success": False, "error": str(e)}
            
            action_record = PendingAction(
                id=self._generate_action_id(),
                action_type=action_type,
                target=target,
                severity=severity,
                reason=reason,
                recommended_by=recommended_by,
                alert_id=alert_id,
                context=context or {},
                status="auto_executed",
                execution_result=result
            )
            self._action_history.append(action_record)
            self._log_audit("auto_execute", action_record.to_dict())
            
            return {
                "status": "executed",
                "mode": self._mode.value,
                "action": action_record.to_dict(),
                "explanation": explanation
            }
        
        else:
            # Queue for approval
            action = PendingAction(
                id=self._generate_action_id(),
                action_type=action_type,
                target=target,
                severity=severity,
                reason=reason,
                recommended_by=recommended_by,
                alert_id=alert_id,
                context=context or {},
                expires_at=time.time() + self._action_expiry
            )
            
            with self._state_lock:
                if len(self._pending_actions) >= self.MAX_PENDING_ACTIONS:
                    # Remove oldest expired action
                    self._cleanup_expired()
                    if len(self._pending_actions) >= self.MAX_PENDING_ACTIONS:
                        return {
                            "status": "rejected",
                            "reason": "Pending action queue full",
                            "mode": self._mode.value
                        }
                
                self._pending_actions[action.id] = action
                self._metrics["pending_approval"] += 1
            
            self._log_audit("pending_approval", action.to_dict())
            
            return {
                "status": "pending_approval",
                "mode": self._mode.value,
                "action": action.to_dict(),
                "explanation": explanation,
                "expires_in_seconds": self._action_expiry
            }
    
    def approve_action(self, action_id: str, approved_by: str = "operator",
                      execute_callback: Optional[Callable] = None,
                      operator_comment: Optional[str] = None) -> Dict:
        """
        Approve a pending action.
        
        Args:
            action_id: ID of the action to approve
            approved_by: Who approved the action
            execute_callback: Function to execute the action
            
        Returns:
            Dict with approval status and execution result
        """
        with self._state_lock:
            if action_id not in self._pending_actions:
                return {"status": "error", "reason": "Action not found or already processed"}
            
            action = self._pending_actions.pop(action_id)
            if self._metrics["pending_approval"] > 0:
                self._metrics["pending_approval"] -= 1
            
            if action.expires_at and time.time() > action.expires_at:
                action.status = "expired"
                self._action_history.append(action)
                self._metrics["expired"] += 1
                return {"status": "error", "reason": "Action expired"}
            
            action.status = "approved"
            action.approved_by = approved_by
            action.approved_at = time.time()
            action.operator_comment = operator_comment
            self._metrics["approved"] += 1
        
        # Execute the action
        if execute_callback:
            try:
                result = execute_callback()
                action.execution_result = result
            except Exception as e:
                logger.error(f"Action execution failed after approval: {e}")
                action.execution_result = {"success": False, "error": str(e)}
        
        self._action_history.append(action)
        self._log_audit("approved", action.to_dict())
        
        # Trigger callbacks
        for callback in self._on_approval_callbacks:
            try:
                callback(action)
            except Exception as e:
                logger.error(f"Approval callback failed: {e}")
        
        return {
            "status": "approved_and_executed",
            "action": action.to_dict()
        }
    
    def reject_action(self, action_id: str, rejected_by: str = "operator",
                     reason: Optional[str] = None) -> Dict:
        """
        Reject a pending action.
        
        Args:
            action_id: ID of the action to reject
            rejected_by: Who rejected the action
            reason: Optional rejection reason
            
        Returns:
            Dict with rejection status
        """
        with self._state_lock:
            if action_id not in self._pending_actions:
                return {"status": "error", "reason": "Action not found or already processed"}
            
            action = self._pending_actions.pop(action_id)
            if self._metrics["pending_approval"] > 0:
                self._metrics["pending_approval"] -= 1
            action.status = "rejected"
            action.approved_by = rejected_by  # Reuse field for rejector
            action.approved_at = time.time()
            self._metrics["rejected"] += 1
        
        self._action_history.append(action)
        self._log_audit("rejected", {**action.to_dict(), "rejection_reason": reason})
        
        # Trigger callbacks
        for callback in self._on_rejection_callbacks:
            try:
                callback(action, reason)
            except Exception as e:
                logger.error(f"Rejection callback failed: {e}")
        
        return {
            "status": "rejected",
            "action": action.to_dict(),
            "rejection_reason": reason
        }
    
    def get_pending_actions(self) -> List[Dict]:
        """Get all pending actions awaiting approval."""
        self._cleanup_expired()
        with self._state_lock:
            return [a.to_dict() for a in self._pending_actions.values()]
    
    def get_action_history(self, limit: int = 50) -> List[Dict]:
        """Get recent action history."""
        return [a.to_dict() for a in list(self._action_history)[-limit:]]
    
    def get_status(self) -> Dict:
        """Get governance system status."""
        self._cleanup_expired()
        metrics = self._metrics.copy()
        metrics["pending_approval"] = len(self._pending_actions)
        return {
            "mode": self._mode.value,
            "autonomous_min_confidence": self._autonomous_min_confidence,
            "autonomous_force_execution": self._autonomous_force_execution,
            "assisted_min_confidence": self._assisted_min_confidence,
            "emergency_min_confidence": self._emergency_min_confidence,
            "emergency_severity": self._emergency_severity,
            "action_expiry_seconds": self._action_expiry,
            "pending_count": len(self._pending_actions),
            "metrics": metrics
        }
    
    def _generate_action_id(self) -> str:
        """Generate unique action ID."""
        with self._state_lock:
            self._action_counter += 1
            return f"action-{int(time.time())}-{self._action_counter}"
    
    def _cleanup_expired(self):
        """Remove expired actions from pending queue."""
        now = time.time()
        with self._state_lock:
            expired_ids = [
                aid for aid, action in self._pending_actions.items()
                if action.expires_at and now > action.expires_at
            ]
            for aid in expired_ids:
                action = self._pending_actions.pop(aid)
                action.status = "expired"
                self._action_history.append(action)
                if self._metrics["pending_approval"] > 0:
                    self._metrics["pending_approval"] -= 1
                self._metrics["expired"] += 1
                logger.info(f"Action {aid} expired")
    
    def _log_audit(self, event_type: str, details: Dict):
        """Log audit event for compliance."""
        audit_entry = {
            "timestamp": datetime.now().isoformat(),
            "event": event_type,
            "mode": self._mode.value,
            "details": details
        }
        logger.info(f"AUDIT: {json.dumps(audit_entry)}")
        if db:
            db.add_audit_log({
                "action": event_type,
                "resource_type": "governance",
                "resource_id": details.get("id") if isinstance(details, dict) else None,
                "details": audit_entry,
                "status": details.get("status") if isinstance(details, dict) else None,
                "actor": details.get("approved_by") if isinstance(details, dict) else None,
                "created_at": datetime.now()
            })
    
    def on_approval(self, callback: Callable):
        """Register callback for action approvals."""
        self._on_approval_callbacks.append(callback)
    
    def on_rejection(self, callback: Callable):
        """Register callback for action rejections."""
        self._on_rejection_callbacks.append(callback)


# Singleton instance
governance = GovernanceController()


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_automation_mode() -> str:
    """Get current automation mode as string."""
    return governance.mode.value

def set_automation_mode(mode: str) -> Dict:
    """Set automation mode. Returns status."""
    try:
        governance.mode = AutomationMode(mode)
        return {"status": "success", "mode": mode}
    except ValueError:
        return {"status": "error", "reason": f"Invalid mode: {mode}. Use: autonomous, assisted, manual, emergency"}

def request_automated_action(action_type: str, target: str, severity: int,
                            reason: str, execute_fn: Optional[Callable] = None,
                            confidence: float = 0.0,
                            recommended_by: str = "llm",
                            alert_id: Optional[str] = None,
                            context: Optional[Dict[str, Any]] = None) -> Dict:
    """Request an automated action through governance."""
    return governance.request_action(
        action_type=action_type,
        target=target,
        severity=severity,
        reason=reason,
        recommended_by=recommended_by,
        alert_id=alert_id,
        confidence=confidence,
        context=context,
        execute_callback=execute_fn
    )

def approve_pending_action(action_id: str, operator: str = "admin",
                          execute_fn: Optional[Callable] = None,
                          operator_comment: Optional[str] = None) -> Dict:
    """Approve a pending action (convenience wrapper)."""
    return governance.approve_action(action_id, operator, execute_fn, operator_comment)

def reject_pending_action(action_id: str, operator: str = "admin",
                         reason: Optional[str] = None) -> Dict:
    """Reject a pending action."""
    return governance.reject_action(action_id, operator, reason)

def get_pending_actions() -> List[Dict]:
    """Get all pending actions."""
    return governance.get_pending_actions()

def get_governance_status() -> Dict:
    """Get governance system status."""
    return governance.get_status()

def set_autonomous_force_execution(enabled: bool) -> Dict:
    """Enable/disable force-execution profile for autonomous mode."""
    value = governance.set_autonomous_force_execution(bool(enabled))
    return {"status": "success", "autonomous_force_execution": value}
