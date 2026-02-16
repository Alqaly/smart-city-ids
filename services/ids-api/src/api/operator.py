"""
Operator Interface API Router
=============================

Provides an **incident-centric** view of security events tailored for
human security analysts.  While the ``/api/alerts`` endpoint focuses on
raw alert ingestion and LLM analysis, the operator interface aggregates
that data into *incidents* — higher-level objects that bundle:

* A concise summary of what happened.
* The raw evidence artefacts (Falco output fields, process trees, etc.).
* The LLM reasoning chain that led to the severity classification.
* Governance metadata (which actions were approved/rejected and by whom).

This separation follows the **NIST SP 800-61** incident-handling model
where raw alerts are *triaged* into incidents and then worked by an
operator through investigation, containment, and recovery stages.

All endpoints require JWT authentication via the ``verify_token``
dependency, ensuring that only authenticated analysts can access the
dashboard data.
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Optional

from infrastructure.auth import verify_token

# ── Router: all paths are prefixed with ``/api/operator`` ──────────────
router = APIRouter(prefix="/api/operator", tags=["operator"])


def _oi():
    """Lazy-import the OperatorInterface singleton from shared state.

    The ``OperatorInterface`` is initialised in ``main.py`` and stored
    in ``api._state``.  It wraps the database and governance layer to
    present incident-level views.
    """
    from api._state import operator_interface
    return operator_interface


@router.get("/incidents")
async def get_incidents_dashboard(limit: int = 50, user: str = Depends(verify_token)):
    """Return a paginated list of recent incidents for the operator dashboard.

    Each incident includes a short summary, severity, threat type,
    governance status (approved / rejected / pending), and timing
    metadata.  The dashboard UI renders these as sortable rows.

    Args:
        limit: Maximum number of incidents to return (default 50).
        user:  Authenticated username injected by ``verify_token``.

    Returns:
        Serialised ``OperatorDashboard`` model with incident summaries.
    """
    dashboard = _oi().get_dashboard(limit=limit)
    return dashboard.dict()


@router.get("/incident/{incident_id}")
async def get_incident_detail(incident_id: int, user: str = Depends(verify_token)):
    """Retrieve the full detail record for a single incident.

    Includes the complete LLM analysis, all evidence items, the
    governance decision trail, and associated automated actions.
    This is the "drill-down" view an analyst opens from the
    dashboard list.

    Args:
        incident_id: Database primary key of the incident.
        user:        Authenticated username.

    Returns:
        Serialised ``IncidentDetail`` Pydantic model.

    Raises:
        HTTPException(404): If no incident with the given ID exists.
    """
    incident = _oi().get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    return incident.dict()


@router.get("/evidence/{incident_id}")
async def get_incident_evidence(incident_id: int, user: str = Depends(verify_token)):
    """Return raw evidence artefacts attached to an incident.

    Evidence items are the unmodified Falco/Suricata output fields,
    process command lines, container metadata, and any IoT sensor
    payloads that were captured at alert time.  Analysts use this
    view for forensic investigation and to verify the LLM's
    reasoning against ground truth.

    Args:
        incident_id: Database primary key of the incident.
        user:        Authenticated username.

    Returns:
        dict with ``incident_id``, ``timestamp``, and a list of
        serialised ``Evidence`` objects.

    Raises:
        HTTPException(404): If the incident does not exist.
    """
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
    """Return the LLM reasoning chain for a given incident.

    Exposes the structured analysis produced by the LLM engine: the
    summary, severity justification, threat classification, and
    recommended actions.  Also reports which LLM model was used and
    the wall-clock analysis latency, enabling the operator to gauge
    confidence in the classification and identify slow providers.

    Args:
        incident_id: Database primary key of the incident.
        user:        Authenticated username.

    Returns:
        dict containing ``reasoning`` (serialised LLM analysis),
        ``llm_model`` (e.g. ``"grok-4"``), and
        ``analysis_time_ms``.

    Raises:
        HTTPException(404): If the incident does not exist.
    """
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
    """Return aggregate metrics for the operator dashboard header.

    Includes totals such as incidents processed, average severity,
    mean analysis latency, approval/rejection ratios, and active
    device counts — the KPIs an analyst needs at-a-glance.

    Returns:
        Serialised ``OperatorMetrics`` Pydantic model.
    """
    m = _oi().get_metrics()
    return m.dict()


@router.get("/dashboard")
async def get_full_operator_dashboard(user: str = Depends(verify_token)):
    """Return the full operator dashboard payload in a single request.

    Combines incident list, aggregate metrics, governance status, and
    LLM provider health into one response, reducing the number of
    round-trips the dashboard UI must make on initial page load.

    Returns:
        dict with keys for incidents, metrics, governance, and system
        health — the complete data contract consumed by the SPA.
    """
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
    """Search and filter the incident database.

    Supports free-text search across summaries and rule names, as well
    as structured filters on severity range and threat type.  This
    enables analysts to quickly locate specific classes of events
    (e.g., all privilege-escalation incidents with severity ≥ 7).

    Args:
        query:        Free-text substring to match against incident
                      summaries and rule names.
        severity_min: Include only incidents with severity ≥ this value.
        severity_max: Include only incidents with severity ≤ this value.
        threat_type:  Exact-match filter on the LLM-assigned threat
                      category (e.g. ``"Privilege Escalation"``).
        limit:        Maximum results to return (default 50).
        user:         Authenticated username.

    Returns:
        dict with matching incidents and result count.
    """
    return _oi().search_incidents(
        query=query,
        severity_min=severity_min,
        severity_max=severity_max,
        threat_type=threat_type,
        limit=limit,
    )
