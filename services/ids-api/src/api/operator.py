"""Operator interface API router."""

from fastapi import APIRouter, Depends, HTTPException
from typing import Optional

from infrastructure.auth import verify_token

router = APIRouter(prefix="/api/operator", tags=["operator"])


def _oi():
    from api._state import operator_interface
    return operator_interface


@router.get("/incidents")
async def get_incidents_dashboard(limit: int = 50, user: str = Depends(verify_token)):
    """Operator dashboard: recent incidents with summaries and governance info."""
    dashboard = _oi().get_dashboard(limit=limit)
    return dashboard.dict()


@router.get("/incident/{incident_id}")
async def get_incident_detail(incident_id: int, user: str = Depends(verify_token)):
    """Get detailed view of a single incident."""
    incident = _oi().get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    return incident.dict()


@router.get("/evidence/{incident_id}")
async def get_incident_evidence(incident_id: int, user: str = Depends(verify_token)):
    """Get raw evidence for an incident."""
    incident = _oi().get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    return {
        "incident_id": incident_id,
        "timestamp": incident.timestamp.isoformat(),
        "evidence": [e.dict() for e in incident.evidence],
    }


@router.get("/reasoning/{incident_id}")
async def get_incident_reasoning(incident_id: int, user: str = Depends(verify_token)):
    """Get LLM reasoning for an incident."""
    incident = _oi().get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    return {
        "incident_id": incident_id,
        "reasoning": incident.reasoning.dict(),
        "llm_model": incident.llm_model_used,
        "analysis_time_ms": incident.analysis_duration_ms,
    }


@router.get("/metrics")
async def get_operator_metrics(user: str = Depends(verify_token)):
    """Get operator dashboard metrics."""
    m = _oi().get_metrics()
    return m.dict()


@router.get("/dashboard")
async def get_full_operator_dashboard(user: str = Depends(verify_token)):
    """Get comprehensive operator dashboard data."""
    return _oi().get_full_dashboard_data()


@router.get("/search")
async def search_incidents(
    query: str = None,
    severity_min: int = None,
    severity_max: int = None,
    threat_type: str = None,
    limit: int = 50,
    user: str = Depends(verify_token),
):
    """Search and filter incidents."""
    return _oi().search_incidents(
        query=query,
        severity_min=severity_min,
        severity_max=severity_max,
        threat_type=threat_type,
        limit=limit,
    )
