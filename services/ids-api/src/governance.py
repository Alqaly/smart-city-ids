"""
Human-in-the-Loop Governance System
Capstone II Integration Plan - TASK 4

Implements three automation modes:
- AUTOPILOT: Full automation, all LLM-recommended actions execute immediately
- ASSISTED: Actions with severity >= 8 require human approval
- MANUAL: All actions require human approval, system only recommends

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


class AutomationMode(Enum):
    """
    Human-in-the-Loop automation modes.
    
    AUTOPILOT: Maximum automation
    - All LLM-recommended actions execute immediately
    - Fastest response time (seconds)
    - Best for: Known threat patterns, high-confidence scenarios
    
    ASSISTED: Balanced automation
    - Low/medium severity actions execute automatically
    - High severity (>= 8) requires human approval
    - Moderate response time (seconds to minutes)
    - Best for: Production environments with SOC oversight
    
    MANUAL: Human-controlled
    - All actions require explicit approval
    - System provides recommendations only
    - Longest response time (depends on operator)
    - Best for: Testing, compliance-sensitive environments
    """
    AUTOPILOT = "autopilot"
    ASSISTED = "assisted"
    MANUAL = "manual"
    
    # Legacy compatibility
    LIVE = "autopilot"     # Map old "live" to autopilot
    DRY_RUN = "manual"     # Map old "dry-run" to manual


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
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    status: str = "pending"  # pending, approved, rejected, expired, auto_executed
    approved_by: Optional[str] = None
    approved_at: Optional[float] = None
    execution_result: Optional[Dict] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for API responses."""
        return {
            **asdict(self),
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
    ASSISTED_THRESHOLD = 8  # Severity at which ASSISTED mode requires approval
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
        self._assisted_threshold = int(os.getenv("ASSISTED_THRESHOLD", str(self.ASSISTED_THRESHOLD)))
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
        
        logger.info(f"GovernanceController initialized: mode={self._mode.value}, threshold={self._assisted_threshold}")
    
    def _parse_mode(self, mode_str: str) -> AutomationMode:
        """Parse mode string with legacy compatibility."""
        mode_map = {
            "autopilot": AutomationMode.AUTOPILOT,
            "assisted": AutomationMode.ASSISTED,
            "manual": AutomationMode.MANUAL,
            "live": AutomationMode.AUTOPILOT,
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
    
    def should_auto_execute(self, action_type: str, severity: int, 
                           target: Optional[str] = None) -> tuple[bool, str]:
        """
        Determine if an action should execute automatically.
        
        Returns:
            (should_execute, reason)
        """
        self._metrics["total_actions_requested"] += 1
        
        if self._mode == AutomationMode.AUTOPILOT:
            self._metrics["auto_executed"] += 1
            return True, "AUTOPILOT mode: all actions auto-execute"
        
        elif self._mode == AutomationMode.ASSISTED:
            if severity < self._assisted_threshold:
                self._metrics["auto_executed"] += 1
                return True, f"ASSISTED mode: severity {severity} < threshold {self._assisted_threshold}"
            else:
                return False, f"ASSISTED mode: severity {severity} >= threshold {self._assisted_threshold}, requires approval"
        
        elif self._mode == AutomationMode.MANUAL:
            return False, "MANUAL mode: all actions require human approval"
        
        return False, "Unknown mode"
    
    def request_action(self, action_type: str, target: str, severity: int,
                      reason: str, recommended_by: str = "llm",
                      alert_id: Optional[str] = None,
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
        should_execute, explanation = self.should_auto_execute(action_type, severity, target)
        
        if should_execute:
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
                      execute_callback: Optional[Callable] = None) -> Dict:
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
            
            if action.expires_at and time.time() > action.expires_at:
                action.status = "expired"
                self._action_history.append(action)
                self._metrics["expired"] += 1
                return {"status": "error", "reason": "Action expired"}
            
            action.status = "approved"
            action.approved_by = approved_by
            action.approved_at = time.time()
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
        return {
            "mode": self._mode.value,
            "assisted_threshold": self._assisted_threshold,
            "action_expiry_seconds": self._action_expiry,
            "pending_count": len(self._pending_actions),
            "metrics": self._metrics.copy()
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
        return {"status": "error", "reason": f"Invalid mode: {mode}. Use: autopilot, assisted, manual"}

def request_automated_action(action_type: str, target: str, severity: int,
                            reason: str, execute_fn: Optional[Callable] = None) -> Dict:
    """Request an automated action through governance."""
    return governance.request_action(
        action_type=action_type,
        target=target,
        severity=severity,
        reason=reason,
        execute_callback=execute_fn
    )

def approve_pending_action(action_id: str, operator: str = "admin",
                          execute_fn: Optional[Callable] = None) -> Dict:
    """Approve a pending action."""
    return governance.approve_action(action_id, operator, execute_fn)

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
