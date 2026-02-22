"""Enterprise audit/event timeline endpoints for SOC investigations."""

from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse

from api._state import get_audit_events

router = APIRouter(tags=["audit"])


@router.get("/api/audit/events")
async def list_audit_events(
    event_type: Optional[str] = None,
    min_severity: Optional[int] = None,
    user: Optional[str] = None,
    trace_id: Optional[str] = None,
    limit: int = Query(default=500, ge=1, le=5000),
):
    rows = get_audit_events(
        event_type=event_type,
        min_severity=min_severity,
        user=user,
        trace_id=trace_id,
        limit=limit,
    )
    return {"total": len(rows), "events": rows}


@router.get("/api/audit/trace/{trace_id}")
async def get_trace(trace_id: str):
    rows = get_audit_events(trace_id=trace_id, limit=2000)
    rows.sort(key=lambda r: r.get("timestamp", ""))
    return {"trace_id": trace_id, "steps": rows, "step_count": len(rows)}


@router.get("/api/audit/export")
async def export_audit_events(
    format: str = Query(default="json", pattern="^(json|csv)$"),
    event_type: Optional[str] = None,
    min_severity: Optional[int] = None,
    user: Optional[str] = None,
    trace_id: Optional[str] = None,
    limit: int = Query(default=2000, ge=1, le=5000),
):
    rows = get_audit_events(
        event_type=event_type,
        min_severity=min_severity,
        user=user,
        trace_id=trace_id,
        limit=limit,
    )
    if format == "json":
        return {"exported_at": datetime.now().isoformat(), "total": len(rows), "events": rows}

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["timestamp", "event_type", "trace_id", "severity", "user", "status", "payload"])
    for row in rows:
        writer.writerow([
            row.get("timestamp", ""),
            row.get("event_type", ""),
            row.get("trace_id", ""),
            row.get("severity", ""),
            row.get("user", ""),
            row.get("status", ""),
            str(row.get("payload", {})),
        ])
    return PlainTextResponse(buf.getvalue(), media_type="text/csv")
