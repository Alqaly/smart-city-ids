"""Alert request/response models."""

from pydantic import BaseModel, Field, field_validator
from typing import Dict, List, Any, Optional, Union
from datetime import datetime


class Alert(BaseModel):
    """Incoming security alert from Falco / Suricata / external source."""

    output: str = Field(
        ..., min_length=1, max_length=2048, description="Alert output text"
    )
    priority: str = Field(..., description="Alert priority level")
    rule: str = Field(
        ..., min_length=1, max_length=512, description="Triggered rule"
    )
    time: str = Field(..., description="ISO format timestamp")
    output_fields: Dict[str, Any] = Field(
        default_factory=dict, description="Extra fields"
    )

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v):
        allowed = {
            "Emergency", "Alert", "Critical", "Error",
            "Warning", "Notice", "Informational", "Debug",
        }
        if v not in allowed:
            raise ValueError(f"priority must be one of {allowed}")
        return v

    @field_validator("time")
    @classmethod
    def validate_time(cls, v):
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("time must be ISO format")
        return v

    @field_validator("output_fields")
    @classmethod
    def validate_fields_count(cls, v):
        if len(v) > 50:
            raise ValueError("output_fields cannot have more than 50 items")
        return v


class AlertResponse(BaseModel):
    """Response returned after alert processing."""

    status: str
    alert_id: Union[int, str]
    trace_id: Optional[str] = None
    analysis: Optional[Dict[str, Any]] = None
    actions_taken: Optional[List[str]] = None
    error: Optional[str] = None
    severity: Optional[int] = None
    threat_type: Optional[str] = None
    summary: Optional[str] = None
    llm_engine: Optional[str] = None
    processing_time_ms: Optional[int] = None
