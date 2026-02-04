"""
Operator Interface Data Models - PhD-Level Human-in-the-Loop Governance

These models represent the complete picture for security operators:
- What happened (incident summary in plain language)
- Why it matters (evidence from Falco + Suricata)
- How confident we are (confidence scores and reasoning)
- What happens next (allowed actions with governance constraints)
- Why automation did/didn't happen (transparency for trust)

This is NOT a chatbot - it's a Tier-1 SOC analyst decision interface.
The human is Tier-2/authority with full control and visibility.
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum


class ConfidenceLevel(str, Enum):
    """Confidence level for LLM analysis"""
    VERY_LOW = "very_low"      # < 40%
    LOW = "low"                  # 40-60%
    MEDIUM = "medium"            # 60-75%
    HIGH = "high"                # 75-90%
    VERY_HIGH = "very_high"      # > 90%


class ThreatType(str, Enum):
    """Standardized threat type classification"""
    DDOS = "DDoS"
    PRIVILEGE_ESCALATION = "Privilege Escalation"
    DATA_EXFILTRATION = "Data Exfiltration"
    MALWARE = "Malware"
    POLICY_VIOLATION = "Policy Violation"
    RECONNAISSANCE = "Reconnaissance"
    UNKNOWN = "Unknown"


class ActionType(str, Enum):
    """Types of automated actions"""
    ISOLATE_POD = "isolate_pod"
    SCALE_UP = "scale_up"
    EVICT_POD = "evict_pod"
    BLOCK_IP = "block_ip"
    CORDON_NODE = "cordon_node"
    ALERT_TEAM = "alert_team"
    NO_ACTION = "no_action"


class ActionStatus(str, Enum):
    """Status of an action"""
    APPROVED = "approved"
    REJECTED = "rejected"
    PENDING = "pending"
    EXECUTED = "executed"
    BLOCKED = "blocked"
    BLOCKED_PROTECTED_SERVICE = "blocked_protected_service"
    BLOCKED_DRY_RUN = "blocked_dry_run"


class EvidenceItem(BaseModel):
    """Single piece of evidence from IDS source"""
    source: str = Field(..., description="falco or suricata")
    rule: str = Field(..., description="The rule that triggered")
    timestamp: str = Field(..., description="ISO format timestamp")
    container: Optional[str] = Field(None, description="Container name if applicable")
    process: Optional[str] = Field(None, description="Process command line if applicable")
    excerpt: str = Field(..., description="Plain language excerpt from the alert")
    severity_indicator: str = Field(..., description="What aspect of this triggers concern: syscall | network | behavior | pattern")


class AnalysisReasoning(BaseModel):
    """The LLM's reasoning chain - why this threat assessment"""
    threat_type: str = Field(..., description="What kind of threat")
    key_indicators: List[str] = Field(..., description="Top 3-5 signals that led to this assessment")
    mitigating_factors: Optional[List[str]] = Field(None, description="Why this might be false positive")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="0.0-1.0 confidence")
    confidence_level: ConfidenceLevel = Field(..., description="Semantic label for confidence")
    reasoning_summary: str = Field(..., description="Plain English explanation of the analysis")


class RecommendedAction(BaseModel):
    """An action the LLM recommends"""
    action_type: str = Field(..., description="Type of action")
    target: str = Field(..., description="What to act on (pod name, service, IP, etc)")
    priority: int = Field(..., ge=1, le=3, description="1=critical, 2=high, 3=medium")
    rationale: str = Field(..., description="Why this action is recommended")
    estimated_impact: str = Field(..., description="Expected outcome if executed")
    reversible: bool = Field(..., description="Can this action be easily reversed?")


class AutomationGovernance(BaseModel):
    """Governance decision: what happens automatically vs needs approval"""
    automation_mode: str = Field(..., description="autopilot | assisted | manual")
    requires_approval: bool = Field(..., description="Does this action need human approval?")
    approval_reason: Optional[str] = Field(None, description="Why approval is needed")
    why_automated: Optional[str] = Field(None, description="Why this is automated (if applies)")
    why_blocked: Optional[str] = Field(None, description="Why automation is blocked (if applies)")
    protected_service: bool = Field(..., description="Is target a protected service?")


class OperatorIncident(BaseModel):
    """Complete incident summary for operator dashboard"""
    incident_id: int = Field(..., description="Alert ID in database")
    timestamp: datetime = Field(..., description="When alert was received")
    
    # SUMMARY: Plain language incident description
    incident_summary: str = Field(..., description="1-2 sentence plain English summary")
    severity: int = Field(..., ge=1, le=10, description="1-10 severity scale")
    
    # EVIDENCE: What the security tools saw
    evidence: List[EvidenceItem] = Field(..., description="Falco and Suricata excerpts")
    
    # REASONING: Why the LLM reached this conclusion
    reasoning: AnalysisReasoning = Field(..., description="LLM analysis chain")
    
    # ACTIONS: What can be done
    recommended_actions: List[RecommendedAction] = Field(..., description="Available actions")
    
    # GOVERNANCE: What happens automatically
    automation_governance: AutomationGovernance = Field(..., description="Approval flow")
    
    # BUSINESS CONTEXT: Why operators should care
    business_impact: str = Field(..., description="How this affects Smart City operations")
    
    # AUDIT TRAIL: For IEEE defensibility
    llm_model_used: str = Field(..., description="xai-grok-4 or openai")
    analysis_duration_ms: int = Field(..., description="How long LLM analysis took")
    analysis_timestamp: datetime = Field(..., description="When analysis was performed")


class OperatorActionRequest(BaseModel):
    """Operator requesting to execute an action"""
    incident_id: int = Field(..., description="Which incident")
    action_index: int = Field(..., description="Index from recommended_actions list")
    operator_id: str = Field(..., description="Who is approving")
    operator_comment: Optional[str] = Field(None, description="Why the operator is approving/rejecting")


class OperatorActionResponse(BaseModel):
    """Result of operator action"""
    status: str = Field(..., description="executed | rejected | error")
    action_type: str = Field(..., description="What was done")
    target: str = Field(..., description="What it was done to")
    message: str = Field(..., description="Result message")
    execution_time_ms: Optional[int] = Field(None, description="How long it took to execute")


class IncidentDashboard(BaseModel):
    """Operator dashboard view: list of incidents"""
    total_incidents: int = Field(..., description="Total incidents today")
    critical_incidents: int = Field(..., description="Severity >= 8")
    pending_approval: int = Field(..., description="Awaiting operator approval")
    incidents: List[OperatorIncident] = Field(..., description="Recent incidents")


class OperatorMetrics(BaseModel):
    """Metrics for operator dashboard"""
    avg_analysis_time_ms: int = Field(..., description="Average LLM analysis duration")
    avg_confidence_score: float = Field(..., description="Average LLM confidence")
    approval_rate: float = Field(..., description="% of recommended actions approved by operators")
    rejection_rate: float = Field(..., description="% of recommended actions rejected by operators")
    override_rate: float = Field(..., description="% of automated actions rejected by operator override")
    incident_volume_trend: str = Field(..., description="increasing | stable | decreasing")
