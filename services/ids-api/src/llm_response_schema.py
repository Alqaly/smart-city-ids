"""
LLM Response Schema Validation
Ensures all LLM engines return consistent, valid responses.

This module provides:
1. Pydantic models for response validation
2. Fallback response generation
3. Response normalization

Used by all LLM engines to ensure IEEE-defensible consistency.
"""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field, field_validator
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# RESPONSE SCHEMA (Pydantic v2)
# =============================================================================

class LLMAnalysisResponse(BaseModel):
    """
    Validated LLM analysis response.
    
    All LLM engines must return data conforming to this schema.
    This ensures consistent behavior regardless of which engine responds.
    Extra fields (e.g. mitre_technique, analysis_engine) are preserved.
    """
    model_config = {"extra": "allow"}
    
    summary: str = Field(
        ...,
        min_length=10,
        max_length=500,
        description="1-2 sentence explanation of the security event"
    )
    
    severity: int = Field(
        ...,
        ge=1,
        le=10,
        description="Threat severity (1=benign, 10=critical)"
    )
    
    threat_type: Literal[
        "DDoS",
        "Denial of Service",
        "Privilege Escalation", 
        "Data Exfiltration",
        "Credential Access",
        "Malware",
        "Policy Violation",
        "Reconnaissance",
        "Lateral Movement",
        "Initial Access",
        "Command and Control",
        "Unauthorized Access",
        "Configuration Error",
        "Unclassified",
        "Unknown"
    ] = Field(
        default="Unknown",
        description="Categorized threat type"
    )
    
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Analysis confidence (0.0-1.0)"
    )
    
    key_indicators: List[str] = Field(
        default_factory=list,
        max_length=10,
        description="Evidence supporting the assessment"
    )
    
    mitigating_factors: List[str] = Field(
        default_factory=list,
        max_length=5,
        description="Reasons this might be a false positive"
    )
    
    business_impact: str = Field(
        default="Unknown impact",
        max_length=800,
        description="Effect on Smart City operations"
    )
    
    reasoning: str = Field(
        default="",
        max_length=2000,
        description="Detailed explanation of threat assessment"
    )
    
    recommendations: List[str] = Field(
        default_factory=list,
        max_length=10,
        description="Recommended human actions"
    )
    
    automated_actions: List[Literal[
        "isolate_pod",
        "scale_up",
        "scale_down", 
        "block_ip",
        "cordon_node",
        "restart_service",
        "alert_team",
        "collect_logs",
        "none"
    ]] = Field(
        default_factory=list,
        max_length=5,
        description="Suggested Kubernetes automation actions"
    )
    
    @field_validator('severity', mode='before')
    @classmethod
    def clamp_severity(cls, v):
        """Ensure severity is within valid range"""
        if isinstance(v, (int, float)):
            return max(1, min(10, int(v)))
        return 5  # Default if invalid
    
    @field_validator('confidence', mode='before')
    @classmethod
    def clamp_confidence(cls, v):
        """Ensure confidence is within valid range"""
        if isinstance(v, (int, float)):
            return max(0.0, min(1.0, float(v)))
        return 0.5  # Default if invalid
    
    @field_validator('threat_type', mode='before')
    @classmethod
    def normalize_threat_type(cls, v):
        """Normalize threat type to valid enum value"""
        if not v or not isinstance(v, str):
            return "Unknown"
        
        # Normalize common variations
        v_lower = v.lower().strip()
        mapping = {
            "ddos": "DDoS",
            "dos": "DDoS",
            "privilege escalation": "Privilege Escalation",
            "priv esc": "Privilege Escalation",
            "data exfiltration": "Data Exfiltration",
            "exfiltration": "Data Exfiltration",
            "data theft": "Data Exfiltration",
            "malware": "Malware",
            "virus": "Malware",
            "trojan": "Malware",
            "policy violation": "Policy Violation",
            "compliance": "Policy Violation",
            "reconnaissance": "Reconnaissance",
            "scanning": "Reconnaissance",
            "port scan": "Reconnaissance",
            "unauthorized access": "Unauthorized Access",
            "unauthorized": "Unauthorized Access",
            "config error": "Configuration Error",
            "misconfiguration": "Configuration Error",
            "denial of service": "DDoS",
            "credential access": "Credential Access",
            "credential theft": "Credential Access",
            "lateral movement": "Lateral Movement",
            "initial access": "Initial Access",
            "command and control": "Command and Control",
            "c2": "Command and Control",
            "c&c": "Command and Control",
        }
        
        for key, value in mapping.items():
            if key in v_lower:
                return value
        
        # Check if already valid
        valid_types = [
            "DDoS", "Privilege Escalation", "Data Exfiltration",
            "Malware", "Policy Violation", "Reconnaissance",
            "Unauthorized Access", "Configuration Error",
            "Denial of Service", "Credential Access",
            "Lateral Movement", "Initial Access",
            "Command and Control", "Unclassified", "Unknown",
        ]
        if v in valid_types:
            return v
        
        return "Unknown"


def validate_llm_response(response_dict: dict) -> LLMAnalysisResponse:
    """
    Validate and normalize LLM response.
    
    Args:
        response_dict: Raw dict from LLM JSON parsing
        
    Returns:
        Validated LLMAnalysisResponse
        
    Raises:
        ValueError: If response cannot be validated even with defaults
    """
    try:
        return LLMAnalysisResponse(**response_dict)
    except Exception as e:
        logger.warning(f"LLM response validation failed, using defaults: {e}")
        # Return with defaults for missing fields
        return LLMAnalysisResponse(
            summary=response_dict.get("summary", "Security event detected - requires investigation"),
            severity=response_dict.get("severity", 5),
            threat_type=response_dict.get("threat_type", "Unknown"),
        )


def create_fallback_response(
    raw_content: str = "",
    error_reason: str = "LLM parsing failed"
) -> dict:
    """
    Create a safe fallback response when LLM parsing fails.
    
    Args:
        raw_content: Raw LLM output (for summary)
        error_reason: Why fallback was triggered
        
    Returns:
        Valid response dict
    """
    summary = raw_content[:200] if raw_content else "Alert requires manual review"
    
    return LLMAnalysisResponse(
        summary=summary,
        severity=5,
        threat_type="Unknown",
        confidence=0.3,
        key_indicators=["Automated analysis failed", "Manual review required"],
        mitigating_factors=[f"Analysis error: {error_reason}"],
        business_impact="Unknown - automated analysis inconclusive",
        reasoning=f"Fallback response generated because: {error_reason}. Manual investigation recommended.",
        recommendations=[
            "Review alert details manually",
            "Check related system logs",
            "Escalate if suspicious activity confirmed"
        ],
        automated_actions=["alert_team"]
    ).model_dump()


# =============================================================================
# RESPONSE METRICS
# =============================================================================

class ResponseMetrics:
    """Track LLM response quality metrics for observability."""
    
    def __init__(self):
        self.total_responses = 0
        self.valid_responses = 0
        self.fallback_responses = 0
        self.validation_errors = 0
    
    def record_valid(self):
        self.total_responses += 1
        self.valid_responses += 1
    
    def record_fallback(self):
        self.total_responses += 1
        self.fallback_responses += 1
    
    def record_error(self):
        self.total_responses += 1
        self.validation_errors += 1
    
    @property
    def success_rate(self) -> float:
        if self.total_responses == 0:
            return 1.0
        return self.valid_responses / self.total_responses
    
    def to_dict(self) -> dict:
        return {
            "total_responses": self.total_responses,
            "valid_responses": self.valid_responses,
            "fallback_responses": self.fallback_responses,
            "validation_errors": self.validation_errors,
            "success_rate": round(self.success_rate, 3)
        }


# Global metrics instance
response_metrics = ResponseMetrics()
