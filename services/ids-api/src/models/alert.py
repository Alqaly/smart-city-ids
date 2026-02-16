"""Alert request and response Pydantic models.

These models define the JSON contract between alert forwarders
(Falco, Suricata, manual submissions) and the IDS API.

Classes:
    Alert          – Incoming security alert (validated on ingestion).
    AlertResponse  – Response returned after processing an alert.

Validation rules:
    * ``priority`` must be one of the 8 syslog severity levels.
    * ``time`` must be ISO 8601 format.
    * ``output_fields`` is limited to 50 keys (DoS protection).
    * ``output`` is capped at 2048 chars, ``rule`` at 512 chars.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Dict, List, Any, Optional, Union
from datetime import datetime


class Alert(BaseModel):
    """Incoming security alert from Falco / Suricata / external source.

    Example JSON payload::

        {
            "output": "Falco rule triggered: shell spawned in container",
            "priority": "Critical",
            "rule": "Terminal_shell_in_container",
            "time": "2025-01-15T12:34:56Z",
            "output_fields": {
                "container.name": "traffic-camera-north",
                "proc.cmdline": "/bin/bash"
            }
        }
    """

    # The raw alert text from the security tool.
    output: str = Field(
        ..., min_length=1, max_length=2048, description="Alert output text"
    )
    # Syslog-style priority level.
    priority: str = Field(..., description="Alert priority level")
    # The rule that triggered this alert (e.g. Falco rule name).
    rule: str = Field(
        ..., min_length=1, max_length=512, description="Triggered rule"
    )
    # ISO 8601 timestamp of when the alert was generated.
    time: str = Field(..., description="ISO format timestamp")
    # Extra fields from the security tool (container name, process info, etc.).
    output_fields: Dict[str, Any] = Field(
        default_factory=dict, description="Extra fields"
    )

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v):
        """Ensure priority is a valid syslog severity level.

        Allowed values follow RFC 5424 severity names used by Falco.
        """
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
        """Ensure the timestamp is valid ISO 8601 format.

        Handles the common ``Z`` suffix by replacing it with ``+00:00``.
        """
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("time must be ISO format")
        return v

    @field_validator("output_fields")
    @classmethod
    def validate_fields_count(cls, v):
        """Limit output_fields to 50 keys to prevent DoS via large payloads."""
        if len(v) > 50:
            raise ValueError("output_fields cannot have more than 50 items")
        return v


class AlertResponse(BaseModel):
    """Response returned after processing an alert through the IDS pipeline.

    Contains the analysis results (severity, threat type, summary),
    any automated actions taken, and performance metadata.
    """

    status: str                                          # "processed", "cached", "error"
    alert_id: Union[int, str]                            # Database ID or trace ID
    trace_id: Optional[str] = None                       # Unique trace for log correlation
    analysis: Optional[Dict[str, Any]] = None            # Full LLM analysis dict
    actions_taken: Optional[List[str]] = None            # e.g. ["isolate_pod", "scale_up"]
    error: Optional[str] = None                          # Error message if processing failed
    severity: Optional[int] = None                       # 1-10 severity from LLM analysis
    threat_type: Optional[str] = None                    # e.g. "Privilege Escalation"
    summary: Optional[str] = None                        # 1-2 sentence summary
    llm_engine: Optional[str] = None                     # Which LLM engine was used
    processing_time_ms: Optional[int] = None             # End-to-end processing time
