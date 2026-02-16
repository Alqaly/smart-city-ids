"""Metrics, safety, and system status API router."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from config import Config
from infrastructure.auth import verify_token
from infrastructure.metrics import PROM_UPTIME_SECONDS

router = APIRouter(tags=["metrics"])


def _deps():
    from api._state import (
        alert_cache,
        alert_fatigue_stats,
        db,
        deduplicator,
        metrics_dict,
        rate_limiter,
        request_queue,
        circuit_breaker,
        refresh_iot_active_metric,
        update_circuit_breaker_metrics,
    )
    return {
        "cache": alert_cache,
        "fatigue": alert_fatigue_stats,
        "db": db,
        "dedup": deduplicator,
        "metrics": metrics_dict,
        "rate_limiter": rate_limiter,
        "rq": request_queue,
        "cb": circuit_breaker,
        "refresh_iot": refresh_iot_active_metric,
        "update_cb": update_circuit_breaker_metrics,
    }


@router.get("/health")
async def health():
    """Health check with component status."""
    d = _deps()
    uptime = (datetime.now() - datetime.fromisoformat(d["metrics"]["started_at"])).total_seconds()
    PROM_UPTIME_SECONDS.set(uptime)

    from api.llm import _build_llm_diagnostics
    from api._state import llm_manager, k8s_automation

    llm_diagnostics = await _build_llm_diagnostics()
    llm_status = {}
    for prov_name, diag in llm_diagnostics.items():
        from api._state import circuit_breaker
        cb_stats = circuit_breaker.engine_stats.get(prov_name, {})
        cb_state = cb_stats.get("state", "unknown")
        cb_successes = cb_stats.get("successes", 0)
        cb_failures = cb_stats.get("failures", 0)
        llm_status[prov_name] = (
            f"configured (circuit: {cb_state}, ok={cb_successes}, fail={cb_failures})"
            if diag["configured"]
            else "not configured"
        )

    db_status = "postgresql" if not d["db"].use_memory else "memory-fallback"
    suricata_status = "enabled" if Config.SURICATA_ENABLED else "disabled"

    return {
        "status": "healthy",
        "components": {
            "llm_providers": llm_status,
            "kubernetes": "connected" if k8s_automation else "disconnected",
            "database": db_status,
            "falco": "enabled" if Config.FALCO_ENABLED else "disabled",
            "suricata": suricata_status,
        },
        "llm_provider_count": llm_manager.get_status()["provider_count"] if llm_manager else 0,
        "llm_diagnostics": llm_diagnostics,
        "circuit_breaker_states": {k: v.get("state", "unknown") for k, v in d["cb"].engine_stats.items()},
        "uptime_seconds": uptime,
        "total_alerts_processed": d["metrics"]["total_alerts"],
        "storage_type": db_status,
    }


@router.get("/api/safety")
async def get_safety_status():
    """Get safety controls status — for demo verification."""
    d = _deps()
    return {
        "automation_mode": Config.AUTOMATION_MODE,
        "protected_services": Config.PROTECTED_SERVICES,
        "cache_stats": d["cache"].stats(),
        "thresholds": {
            "critical_severity": Config.CRITICAL_SEVERITY_THRESHOLD,
            "high_severity": Config.HIGH_SEVERITY_THRESHOLD,
        },
        "note": "Set AUTOMATION_MODE=dry-run for safe demos",
    }


@router.get("/api/production-status")
async def get_production_status():
    """Get production controls status — for monitoring and Grafana."""
    d = _deps()
    return {
        "rate_limiter": d["rate_limiter"].stats(),
        "circuit_breaker": d["cb"].get_stats(),
        "request_queue": d["rq"].stats(),
        "cache": d["cache"].stats(),
        "protected_services": Config.PROTECTED_SERVICES,
        "automation_mode": Config.AUTOMATION_MODE,
        "health": {
            "rate_limit_healthy": (
                d["rate_limiter"].rejected_requests < d["rate_limiter"].total_requests * 0.1
                if d["rate_limiter"].total_requests > 0
                else True
            ),
            "circuit_breakers_healthy": all(
                s["state"] != "open" for s in d["cb"].engine_stats.values()
            ),
            "queue_healthy": d["rq"].queue_size < d["rq"].max_queue_size * 0.8,
        },
    }


@router.get("/api/pipeline-overview")
async def pipeline_overview():
    """Compact stage-by-stage operational view for dashboard pipeline strip."""
    from governance import get_governance_status
    from api.llm import export_llm_stats

    d = _deps()
    db_stats = d["db"].get_stats()
    total_alerts = db_stats.get("total_alerts", 0)
    by_source = db_stats.get("alerts_by_source", {})
    total_minutes = max(
        1.0,
        (datetime.now() - datetime.fromisoformat(d["metrics"]["started_at"])).total_seconds() / 60.0,
    )
    llm_stats = await export_llm_stats()
    engine_stats = llm_stats.get("engines", {})
    llm_requests = sum(v.get("total_requests", 0) for v in engine_stats.values())
    llm_p95 = max((v.get("p95_latency_s", 0.0) for v in engine_stats.values()), default=0.0)
    dedup_stats = d["dedup"].get_stats() if d["dedup"] else {"hit_rate_percent": 0}
    gov = get_governance_status()
    human_review = d["fatigue"]["human_review_required_total"]
    auto_handled = d["fatigue"]["auto_handled_total"]
    actions_total = gov.get("metrics", {}).get("approved", 0) + gov.get("metrics", {}).get("auto_executed", 0)

    return {
        "stages": [
            {"id": "falco", "label": "Falco Alerts", "rate_per_minute": round(by_source.get("falco", 0) / total_minutes, 2), "p95_latency_ms": 0, "status": "green"},
            {"id": "suricata", "label": "Suricata Alerts", "rate_per_minute": round(by_source.get("suricata", 0) / total_minutes, 2), "p95_latency_ms": 0, "status": "green" if by_source.get("suricata", 0) > 0 else "yellow"},
            {"id": "ingest", "label": "IDS Ingest + Dedup", "rate_per_minute": round(total_alerts / total_minutes, 2), "p95_latency_ms": 0, "status": "green", "dedup_hit_rate_percent": dedup_stats.get("hit_rate_percent", 0)},
            {"id": "llm", "label": "LLM / Local Analysis", "rate_per_minute": round(llm_requests / total_minutes, 2), "p95_latency_ms": int(llm_p95 * 1000), "status": "green" if llm_requests > 0 else "yellow"},
            {"id": "gov", "label": "Governance + K8s Actions", "rate_per_minute": round(actions_total / total_minutes, 2), "p95_latency_ms": 0, "status": "green", "human_review_required": human_review, "auto_handled": auto_handled},
        ],
        "alert_fatigue": {
            "raw_total": d["fatigue"]["raw_total"],
            "after_dedup_total": d["fatigue"]["after_dedup_total"],
            "llm_triaged_total": d["fatigue"]["llm_triaged_total"],
            "human_review_required_total": human_review,
            "auto_handled_total": auto_handled,
            "reduction_percent": round((1 - (human_review / max(1, d["fatigue"]["raw_total"]))) * 100, 2),
        },
    }


@router.get("/api/metrics")
async def get_metrics():
    """Get aggregate metrics."""
    d = _deps()
    uptime = (datetime.now() - datetime.fromisoformat(d["metrics"]["started_at"])).total_seconds()
    d["metrics"]["uptime_seconds"] = uptime
    db_stats = d["db"].get_stats()
    d["metrics"]["total_alerts"] = db_stats["total_alerts"]
    d["metrics"]["alerts_by_source"] = db_stats["alerts_by_source"]
    d["metrics"]["storage_type"] = db_stats["storage_type"]
    try:
        restore_data = d["db"].get_prometheus_restore_data()
        d["metrics"]["alerts_by_threat_type"] = restore_data.get("alerts_by_threat_type", {})
        d["metrics"]["alerts_by_severity"] = restore_data.get("alerts_by_severity", {})
    except Exception:
        pass
    PROM_UPTIME_SECONDS.set(uptime)
    d["metrics"]["iot_devices_active"] = d["refresh_iot"]()
    return d["metrics"]


@router.get("/api/db/stats")
async def get_db_stats():
    """Get database statistics."""
    from api._state import db
    return db.get_stats()


@router.get("/api/deduplicator-stats")
async def get_dedup_stats():
    """Get alert deduplication cache statistics."""
    d = _deps()
    if not d["dedup"]:
        return {"error": "Deduplicator not initialized"}
    stats = d["dedup"].get_stats()
    total = stats.get("total_alerts", 0)
    hits = stats.get("hits", 0)
    misses = stats.get("misses", 0)
    cost_per_call = 0.005
    if total > 0:
        cost_without = total * cost_per_call
        cost_with = misses * cost_per_call
        cost_saved = cost_without - cost_with
        hit_rate = round((hits / total) * 100, 1)
    else:
        cost_without = cost_with = cost_saved = 0
        hit_rate = 0
    return {
        **stats,
        "hit_rate_percent": hit_rate,
        "cost_saved_usd": round(cost_saved, 4),
        "estimated_cost_without_dedup": round(cost_without, 4),
        "estimated_cost_with_dedup": round(cost_with, 4),
    }


@router.post("/api/deduplicator/clear")
async def clear_dedup_cache(token=Depends(verify_token)):
    """Clear alert deduplication cache (administrative)."""
    d = _deps()
    if not d["dedup"]:
        return {"error": "Deduplicator not initialized"}
    stats_before = d["dedup"].get_stats()
    d["dedup"].clear_cache()
    return {
        "status": "success",
        "cleared_fingerprints": stats_before["cache_size"],
        "previous_hit_rate": f"{stats_before['hit_rate_percent']}%",
    }


@router.get("/metrics")
async def prometheus_metrics():
    """Prometheus exposition endpoint."""
    d = _deps()
    uptime = (datetime.now() - datetime.fromisoformat(d["metrics"]["started_at"])).total_seconds()
    PROM_UPTIME_SECONDS.set(uptime)
    d["update_cb"]()
    d["refresh_iot"]()
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
