"""Unified SOC logs endpoints (alerts + audit timeline).

This module provides a unified view of security-relevant logs:
- Falco runtime security alerts (container syscalls)
- Suricata network IDS alerts (network traffic)
- Audit events (system actions and governance decisions)

Note: Only Falco and Suricata security alerts are sent to the LLM for analysis.
System logs and application logs are excluded from LLM processing to reduce
costs and focus on actionable security events.
"""

from __future__ import annotations

from typing import Optional, List

from fastapi import APIRouter, Depends, Query

from infrastructure.auth import verify_token
from api._state import db, get_audit_events

router = APIRouter(tags=["logs"])

# Security log sources that are sent to LLM
SECURITY_LOG_SOURCES = {"falco", "suricata"}


def _severity_to_level(severity: Optional[int]) -> str:
    if severity is None:
        return "info"
    if severity >= 8:
        return "critical"
    if severity >= 6:
        return "high"
    if severity >= 4:
        return "medium"
    return "low"


def _detect_alert_source(alert: dict) -> str:
    """Detect if alert is from Falco or Suricata."""
    raw = alert.get("raw_alert") or {}
    rule = str(raw.get("rule") or alert.get("rule", "")).lower()
    output = str(raw.get("output") or "").lower()
    output_fields = raw.get("output_fields") or alert.get("output_fields") or {}
    
    # Suricata indicators
    if "suricata" in rule or "suricata" in output:
        return "suricata"
    if output_fields.get("event_type") == "alert":
        return "suricata"
    
    # Default to Falco (most runtime alerts come from Falco)
    return "falco"


@router.get("/api/logs/events")
async def get_logs_events(
    source: str = Query(default="all", pattern="^(all|audit|alerts|falco|suricata)$"),
    level: Optional[str] = Query(default=None),
    search: Optional[str] = None,
    trace_id: Optional[str] = None,
    llm_analyzed_only: bool = Query(default=False, description="Only include logs sent to LLM (Falco/Suricata)"),
    limit: int = Query(default=500, ge=1, le=5000),
    _=Depends(verify_token),
):
    """
    Get unified SOC logs with filtering options.
    
    Source filtering:
    - "all": Include all log sources
    - "audit": System audit events only
    - "alerts": All security alerts
    - "falco": Falco runtime security alerts only
    - "suricata": Suricata network IDS alerts only
    
    When llm_analyzed_only=true, only Falco and Suricata alerts are returned
    (these are the only logs sent to the LLM for analysis).
    """
    from api._state import deduplicator
    
    events = []

    if source in ("all", "audit"):
        audit_rows = get_audit_events(trace_id=trace_id, limit=limit)
        for row in audit_rows:
            status = (row.get("status") or "ok").lower()
            row_level = "warn" if status == "blocked" else "error" if status in ("error", "failed") else "info"
            payload = row.get("payload") or {}
            events.append(
                {
                    "timestamp": row.get("timestamp"),
                    "source": "audit",
                    "event_type": row.get("event_type", "EVENT"),
                    "trace_id": row.get("trace_id"),
                    "level": row_level,
                    "message": payload.get("summary") or payload.get("rule") or row.get("event_type", "EVENT"),
                    "llm_analyzed": False,  # Audit events are not sent to LLM
                    "details": row,
                }
            )

    # Handle alert sources (falco/suricata/alerts)
    alert_sources = []
    if source == "falco":
        alert_sources = ["falco"]
    elif source == "suricata":
        alert_sources = ["suricata"]
    elif source in ("all", "alerts"):
        alert_sources = ["falco", "suricata"]
    
    if alert_sources:
        try:
            alert_rows = db.get_alerts(limit=limit * 2)  # Get more to filter
        except Exception:
            alert_rows = []

        for alert in alert_rows:
            raw = alert.get("raw_alert") or {}
            this_trace = alert.get("trace_id") or raw.get("trace_id")
            if trace_id and this_trace != trace_id:
                continue
            
            # Detect the actual source (falco vs suricata)
            alert_source = _detect_alert_source(alert)
            
            # Skip if source filtering doesn't match
            if alert_source not in alert_sources:
                continue
            
            # Skip if llm_analyzed_only and not a security source
            if llm_analyzed_only and alert_source not in SECURITY_LOG_SOURCES:
                continue
            
            sev = alert.get("severity")
            events.append(
                {
                    "timestamp": alert.get("timestamp"),
                    "source": alert_source,  # Use detected source, not generic "alerts"
                    "event_type": "ALERT",
                    "trace_id": this_trace,
                    "level": _severity_to_level(sev),
                    "message": alert.get("summary") or alert.get("rule") or raw.get("output") or "Alert",
                    "severity": sev,
                    "rule": alert.get("rule"),
                    "llm_analyzed": True,  # Security alerts are sent to LLM
                    "deduplicated": alert.get("llm_engine") == "cached",  # Was this a cache hit?
                    "details": alert,
                }
            )

    if level:
        level_norm = level.lower().strip()
        events = [e for e in events if str(e.get("level", "")).lower() == level_norm]

    if search:
        q = search.lower().strip()
        events = [
            e
            for e in events
            if q in str(e.get("message", "")).lower()
            or q in str(e.get("event_type", "")).lower()
            or q in str(e.get("trace_id", "")).lower()
            or q in str(e.get("rule", "")).lower()
            or q in str(e.get("source", "")).lower()
        ]

    events.sort(key=lambda e: str(e.get("timestamp", "")), reverse=True)
    events = events[:limit]
    
    # Calculate deduplication statistics for the returned events
    dedup_stats = None
    security_events = [e for e in events if e.get("llm_analyzed")]
    if security_events:
        dedup_count = sum(1 for e in security_events if e.get("deduplicated"))
        dedup_stats = {
            "total_security_events": len(security_events),
            "deduplicated_count": dedup_count,
            "analyzed_count": len(security_events) - dedup_count,
            "dedup_rate_percent": round((dedup_count / len(security_events)) * 100, 1) if security_events else 0,
        }
    
    return {
        "total": len(events),
        "events": events,
        "dedup_stats": dedup_stats,
        "filters_applied": {
            "source": source,
            "llm_analyzed_only": llm_analyzed_only,
        }
    }


@router.get("/api/logs/security-only")
async def get_security_logs_only(
    source: str = Query(default="all", pattern="^(all|falco|suricata)$"),
    limit: int = Query(default=100, ge=1, le=1000),
    _=Depends(verify_token),
):
    """
    Get only security logs that are sent to LLM (Falco and Suricata).
    
    This endpoint is optimized for the LLM analysis pipeline view,
    showing only the alerts that consume LLM credits.
    """
    return await get_logs_events(
        source=source if source != "all" else "alerts",
        llm_analyzed_only=True,
        limit=limit,
    )
