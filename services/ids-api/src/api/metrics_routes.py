"""Metrics, safety, production status, and Prometheus exposition API router.

This module provides the observability layer of the Smart City IDS.
It aggregates data from every subsystem — database, LLM providers,
circuit breakers, deduplication cache, rate limiters, request queue,
and governance engine — and exposes it through REST and Prometheus
endpoints.

Endpoint overview:
    GET  /health                   – deep component health check
    GET  /api/safety               – automation-mode, thresholds, cache
    GET  /api/production-status    – rate-limiter/cb/queue health booleans
    GET  /api/pipeline-overview    – 5-stage pipeline strip for dashboard
    GET  /api/metrics              – aggregate JSON metrics blob
    GET  /api/db/stats             – database storage statistics
    GET  /api/deduplicator-stats   – dedup cache hit-rate and cost savings
    POST /api/deduplicator/clear   – flush dedup cache (auth required)
    GET  /metrics                  – Prometheus text exposition format

Design notes:
    * ``_deps()`` lazily imports all shared-state objects and returns them
      in a dict to avoid circular imports at module load time.
    * ``/health`` reuses ``_build_llm_diagnostics()`` from ``api.llm``
      to give a single-call view of the entire system.
    * ``/api/pipeline-overview`` computes per-stage throughput in
      alerts/minute — intended for the React dashboard's horizontal
      pipeline strip.
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from config import Config
from infrastructure.auth import verify_token
from infrastructure.metrics import PROM_UPTIME_SECONDS

router = APIRouter(tags=["metrics"])

_PSEUDO_LLM_PROVIDERS = {"none", "unknown", "cache", "cached", "rule", "rule_based", "rule-based"}


# ══════════════════════════════════════════════════════════════════════════════
# LAZY DEPENDENCY INJECTION
# ══════════════════════════════════════════════════════════════════════════════

def _deps():
    """Lazily import all shared-state objects to avoid circular imports.

    Returns a dict with short keys mapped to the singleton instances
    initialised in ``main.py`` and stored in ``api._state``.

    Returns:
        dict with keys: cache, fatigue, db, dedup, metrics, rate_limiter,
        rq, cb, refresh_iot, update_cb.
    """
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
        get_iot_metric_metadata,
        update_circuit_breaker_metrics,
    )
    return {
        "cache": alert_cache,            # AlertCache — LRU + TTL dedup for SSE
        "fatigue": alert_fatigue_stats,  # dict — alert fatigue reduction counters
        "db": db,                        # DatabaseManager — async DB wrapper
        "dedup": deduplicator,           # AlertDeduplicator — fingerprint-based dedup
        "metrics": metrics_dict,         # dict — in-memory aggregate metrics
        "rate_limiter": rate_limiter,    # RateLimiter — HTTP-level token bucket
        "rq": request_queue,            # RequestQueue — bounded async queue
        "cb": circuit_breaker,          # CircuitBreaker — per-engine LLM breakers
        "refresh_iot": refresh_iot_active_metric,      # callable → int (active device count)
        "iot_meta": get_iot_metric_metadata,           # callable → source/degraded metadata
        "update_cb": update_circuit_breaker_metrics,   # callable — sync breaker state → Prometheus
    }


# ══════════════════════════════════════════════════════════════════════════════
# HEALTH CHECK
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/health")
async def health():
    """Deep component health check — used by Kubernetes liveness/readiness probes.

    Checks every subsystem (LLM providers, K8s connection, database,
    Falco, Suricata) and returns a unified status object.  The response
    includes the full LLM diagnostics from ``api.llm._build_llm_diagnostics``
    so that a single GET can reveal the operational state of all six
    LLM providers.

    Returns:
        {
            "status": "healthy",
            "components": { … per-subsystem status strings … },
            "llm_diagnostics": { … per-provider diagnostic dicts … },
            "uptime_seconds": float,
            "total_alerts_processed": int,
            …
        }
    """
    d = _deps()

    # ── Compute uptime and update Prometheus gauge ────────────────────────
    uptime = (datetime.now() - datetime.fromisoformat(d["metrics"]["started_at"])).total_seconds()
    PROM_UPTIME_SECONDS.set(uptime)

    # ── LLM provider diagnostics (reused from api.llm) ───────────────────
    from api.llm import _build_llm_diagnostics
    from api._state import llm_manager, k8s_automation

    llm_diagnostics = await _build_llm_diagnostics()

    # Build a compact one-line status string per provider for the
    # ``components`` section (full diagnostics are in ``llm_diagnostics``).
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

    # ── Database and optional subsystem status ────────────────────────────
    # Database status: connected (green), memory-fallback (yellow), or error (red)
    try:
        db_stats = d["db"].get_stats()
        if getattr(d["db"], "use_memory", False):
            db_status = "memory-fallback"  # Memory fallback functional but not persistent
        else:
            db_status = "connected"  # PostgreSQL is connected
    except Exception as e:
        db_status = "error"
    
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


# ══════════════════════════════════════════════════════════════════════════════
# SAFETY & PRODUCTION STATUS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/api/safety")
async def get_safety_status():
    """Get safety controls status — used for demo pre-flight verification.

    Returns the current automation mode (``autonomous`` | ``assisted`` |
    ``manual`` | ``emergency``), the list of protected services, alert
    cache statistics, and severity thresholds.

    Operators should check this before a live demo: if ``automation_mode``
    is not ``dry-run``, Kubernetes actions may actually execute.

    Returns:
        {"automation_mode": str, "protected_services": list, "cache_stats": dict, …}
    """
    d = _deps()
    return {
        "automation_mode": Config.AUTOMATION_MODE,
        "protected_services": Config.PROTECTED_SERVICES,
        "cache_stats": d["cache"].stats(),
        "thresholds": {
            "critical_severity": Config.CRITICAL_SEVERITY_THRESHOLD,
            "high_severity": Config.HIGH_SEVERITY_THRESHOLD,
        },
        "note": "Use AUTOMATION_MODE=manual for approval-only demos",
    }


@router.get("/api/production-status")
async def get_production_status():
    """Get production health indicators — consumed by Grafana dashboards.

    Aggregates rate-limiter, circuit-breaker, request-queue, and cache
    stats with boolean health flags:
        - ``rate_limit_healthy``: fewer than 10% of requests rejected.
        - ``circuit_breakers_healthy``: no engine in ``open`` state.
        - ``queue_healthy``: queue fill level below 80%.

    Returns:
        {"rate_limiter": {…}, "circuit_breaker": {…}, "health": {…}, …}
    """
    d = _deps()
    return {
        "rate_limiter": d["rate_limiter"].stats(),
        "circuit_breaker": d["cb"].get_stats(),
        "request_queue": d["rq"].stats(),
        "cache": d["cache"].stats(),
        "protected_services": Config.PROTECTED_SERVICES,
        "automation_mode": Config.AUTOMATION_MODE,
        "health": {
            # Rate-limiter healthy if rejection rate < 10%.
            "rate_limit_healthy": (
                d["rate_limiter"].rejected_requests < d["rate_limiter"].total_requests * 0.1
                if d["rate_limiter"].total_requests > 0
                else True
            ),
            # All circuit breakers must be closed or half-open.
            "circuit_breakers_healthy": all(
                s["state"] != "open" for s in d["cb"].engine_stats.values()
            ),
            # Queue healthy if below 80% capacity.
            "queue_healthy": d["rq"].queue_size < d["rq"].max_queue_size * 0.8,
        },
    }


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE OVERVIEW  (5-stage dashboard strip)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/api/pipeline-overview")
async def pipeline_overview():
    """Compact stage-by-stage operational view for the React dashboard pipeline strip.

    Computes real-time throughput (alerts/minute) and latency for each of
    the five processing stages:

        1. **Falco Alerts** — runtime security alerts from Falco.
        2. **Suricata Alerts** — network IDS alerts from Suricata.
        3. **IDS Ingest + Dedup** — combined ingest with dedup hit-rate.
        4. **LLM / Rule-Based Analysis** — analysis engine throughput and p95.
        5. **Governance + K8s Actions** — human-review vs auto-handled count.

    Also includes an ``alert_fatigue`` section showing how many raw alerts
    were reduced to human-review items (the core metric for the dissertation's
    alert-fatigue-reduction claim).

    Returns:
        {"stages": [{…}, …], "alert_fatigue": {…}}
    """
    from governance import get_governance_status
    from api.llm import export_llm_stats

    d = _deps()

    # ── Gather raw counts from the database ───────────────────────────────
    db_stats = d["db"].get_stats()
    total_alerts = db_stats.get("total_alerts", 0)
    by_source = db_stats.get("alerts_by_source", {})

    # Total runtime in minutes (min 1.0 to avoid division by zero).
    total_minutes = max(
        1.0,
        (datetime.now() - datetime.fromisoformat(d["metrics"]["started_at"])).total_seconds() / 60.0,
    )

    # ── LLM engine stats for Stage 4 ─────────────────────────────────────
    llm_stats = await export_llm_stats()
    engine_stats = llm_stats.get("engines", {})
    llm_requests = sum(v.get("total_requests", 0) for v in engine_stats.values())
    llm_p95 = max((v.get("p95_latency_s", 0.0) for v in engine_stats.values()), default=0.0)

    # ── Deduplication stats for Stage 3 ───────────────────────────────────
    dedup_stats = d["dedup"].get_stats() if d["dedup"] else {"hit_rate_percent": 0}

    # ── Governance stats for Stage 5 ──────────────────────────────────────
    gov = get_governance_status()
    human_review = d["fatigue"]["human_review_required_total"]
    auto_handled = d["fatigue"]["auto_handled_total"]
    actions_total = gov.get("metrics", {}).get("approved", 0) + gov.get("metrics", {}).get("auto_executed", 0)
    falco_count = by_source.get("falco", 0)
    suricata_count = by_source.get("suricata", 0)

    def _stage_state(count: int, label: str) -> tuple[str, str]:
        if count > 0:
            return "green", f"{label} active"
        return "idle", f"{label} idle (no recent events)"

    return {
        "stages": [
            # Stage 1: Falco runtime security alerts.
            {
                "id": "falco",
                "label": "Falco Alerts",
                "rate_per_minute": round(falco_count / total_minutes, 2),
                "p95_latency_ms": 0,
                "status": _stage_state(falco_count, "Falco")[0],
                "status_text": _stage_state(falco_count, "Falco")[1],
            },
            # Stage 2: Suricata network IDS alerts.
            {
                "id": "suricata",
                "label": "Suricata Alerts",
                "rate_per_minute": round(suricata_count / total_minutes, 2),
                "p95_latency_ms": 0,
                "status": _stage_state(suricata_count, "Suricata")[0],
                "status_text": _stage_state(suricata_count, "Suricata")[1],
            },
            # Stage 3: Ingest and fingerprint-based deduplication.
            {
                "id": "ingest",
                "label": "IDS Ingest + Dedup",
                "rate_per_minute": round(total_alerts / total_minutes, 2),
                "p95_latency_ms": 0,
                "status": "green" if total_alerts > 0 else "idle",
                "status_text": "Ingest active" if total_alerts > 0 else "Waiting for alerts",
                "dedup_hit_rate_percent": dedup_stats.get("hit_rate_percent", 0),
            },
            # Stage 4: LLM or rule-based analysis.
            {
                "id": "llm",
                "label": "LLM / Rule-Based Analysis",
                "rate_per_minute": round(llm_requests / total_minutes, 2),
                "p95_latency_ms": int(llm_p95 * 1000),
                "status": "green" if llm_requests > 0 else "idle",
                "status_text": "Analysis active" if llm_requests > 0 else "No LLM analyses yet",
            },
            # Stage 5: HITL governance decisions and K8s automated actions.
            {
                "id": "gov",
                "label": "Governance + K8s Actions",
                "rate_per_minute": round(actions_total / total_minutes, 2),
                "p95_latency_ms": 0,
                "status": "green" if (actions_total > 0 or human_review > 0 or auto_handled > 0) else "idle",
                "status_text": "Actions/approvals recorded" if (actions_total > 0 or human_review > 0 or auto_handled > 0) else "No actions yet",
                "human_review_required": human_review,
                "auto_handled": auto_handled,
            },
        ],
        # Alert fatigue reduction metrics — core dissertation contribution.
        "alert_fatigue": {
            "raw_total": d["fatigue"]["raw_total"],
            "after_dedup_total": d["fatigue"]["after_dedup_total"],
            "llm_triaged_total": d["fatigue"]["llm_triaged_total"],
            "human_review_required_total": human_review,
            "auto_handled_total": auto_handled,
            # Reduction percentage: how many raw alerts were handled
            # without human intervention.
            "reduction_percent": round((1 - (human_review / max(1, d["fatigue"]["raw_total"]))) * 100, 2),
        },
    }


# ══════════════════════════════════════════════════════════════════════════════
# AGGREGATE METRICS & DATABASE STATS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/api/metrics")
async def get_metrics():
    """Get aggregate JSON metrics blob — consumed by the React dashboard.

    Merges in-memory counters with database statistics and Prometheus
    restore data (alerts-by-threat-type, alerts-by-severity histograms).
    Also refreshes the ``iot_devices_active`` gauge.

    Returns:
        dict with keys: total_alerts, uptime_seconds, alerts_by_source,
        alerts_by_threat_type, alerts_by_severity, iot_devices_active, …
    """
    d = _deps()
    uptime = (datetime.now() - datetime.fromisoformat(d["metrics"]["started_at"])).total_seconds()
    d["metrics"]["uptime_seconds"] = uptime

    # Merge latest database stats into the metrics dict.
    db_stats = d["db"].get_stats()
    d["metrics"]["total_alerts"] = db_stats["total_alerts"]
    d["metrics"]["alerts_by_source"] = db_stats["alerts_by_source"]
    d["metrics"]["storage_type"] = db_stats["storage_type"]

    # Attempt to restore histogram data from persistent storage.
    try:
        restore_data = d["db"].get_prometheus_restore_data()
        d["metrics"]["alerts_by_threat_type"] = restore_data.get("alerts_by_threat_type", {})
        d["metrics"]["alerts_by_severity"] = restore_data.get("alerts_by_severity", {})
        # Restore critical_alerts from DB — the in-memory counter resets on
        # restart but the DB always has the true count of severity >= 8 alerts.
        db_critical = restore_data.get("critical_alerts", 0)
        if db_critical > d["metrics"]["critical_alerts"]:
            d["metrics"]["critical_alerts"] = db_critical
    except Exception:
        pass  # Non-critical — dashboard will show partial data.

    PROM_UPTIME_SECONDS.set(uptime)
    d["metrics"]["iot_devices_active"] = d["refresh_iot"]()
    d["metrics"]["iot_devices_active_meta"] = d["iot_meta"]()
    return d["metrics"]


@router.get("/api/metrics/llm-usage")
async def llm_usage(window: str = "today"):
    """DB-backed LLM usage summary.

    Purpose: give the operator a "today" view of:
      - total calls
      - prompt/completion tokens
      - estimated cost (token-based model)
      - per-provider breakdown

        Query params:
            - window: "today" (default) or "week" (last 7 days).
    """
    from api._state import LLM_COST_PER_1K_TOKENS, llm_last_provider_used, llm_manager

    d = _deps()
    db = d["db"]

    w = (window or "today").strip().lower()

    usage = None
    if w == "today":
        if hasattr(db, "get_llm_usage_today"):
            usage = db.get_llm_usage_today()
    elif w in ("week", "weekly", "7d", "last7d"):
        if hasattr(db, "get_llm_usage_window"):
            end = datetime.utcnow()
            start = end - timedelta(days=7)
            usage = db.get_llm_usage_window(start, end)
            w = "week"
    else:
        w = "today"
        if hasattr(db, "get_llm_usage_today"):
            usage = db.get_llm_usage_today()

    if not usage:
        usage = {
            "start_utc": "",
            "end_utc": "",
            "totals": {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "tokens": 0},
            "providers": [],
        }

    # Estimate cost from token totals (provider-specific per-1k token rate).
    providers_out = []
    seen_providers = set()
    total_cost = 0.0
    for row in usage.get("providers", []) or []:
        prov = (row.get("provider") or "unknown").strip().lower() or "unknown"
        if prov in _PSEUDO_LLM_PROVIDERS:
            continue
        prompt_tokens = int(row.get("prompt_tokens") or 0)
        completion_tokens = int(row.get("completion_tokens") or 0)
        tokens_total = prompt_tokens + completion_tokens
        rate = float(LLM_COST_PER_1K_TOKENS.get(prov, 0.0))
        cost = round((tokens_total / 1000.0) * rate, 6) if rate > 0 else 0.0
        total_cost += cost
        providers_out.append({
            "provider": prov,
            "calls": int(row.get("calls") or 0),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "tokens": tokens_total,
            "estimated_cost_usd": cost,
            "rate_per_1k_tokens_usd": rate,
        })
        seen_providers.add(prov)

    # Ensure the dashboard always shows all configured providers, even if
    # they had zero calls in the selected window.
    try:
        from api._state import llm_manager
        configured = []
        if llm_manager and hasattr(llm_manager, "get_status"):
            configured = list((llm_manager.get_status() or {}).get("providers", []) or [])
        for prov in configured:
            key = str(prov or "").strip().lower()
            if not key or key in seen_providers:
                continue
            providers_out.append({
                "provider": key,
                "calls": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "tokens": 0,
                "estimated_cost_usd": 0.0,
                "rate_per_1k_tokens_usd": float(LLM_COST_PER_1K_TOKENS.get(key, 0.0)),
            })
            seen_providers.add(key)
    except Exception:
        pass

    providers_out.sort(key=lambda r: str(r.get("provider", "")))

    totals = usage.get("totals", {}) or {}
    out_totals = {
        "calls": int(totals.get("calls") or 0),
        "prompt_tokens": int(totals.get("prompt_tokens") or 0),
        "completion_tokens": int(totals.get("completion_tokens") or 0),
        "tokens": int(totals.get("tokens") or 0),
        "estimated_cost_usd": round(float(total_cost), 6),
    }

    return {
        "window": w,
        "start_utc": usage.get("start_utc"),
        "end_utc": usage.get("end_utc"),
        "totals": out_totals,
        "providers": providers_out,
        "cost_values_are_estimated": True,
        "cost_estimation_method": "token_based_rate_per_1k",
        "active_provider": (llm_last_provider_used or (llm_manager.get_status().get("active_provider") if llm_manager else None)),
        "cost_threshold_usd": 5.0,
        "generated_at": int(datetime.utcnow().timestamp()),
    }


@router.get("/api/db/stats")
async def get_db_stats():
    """Get raw database storage statistics (table row counts, storage type).

    Returns:
        dict from ``DatabaseManager.get_stats()`` — includes total_alerts,
        alerts_by_source, storage_type, and table-level counts.
    """
    from api._state import db
    return db.get_stats()


# ══════════════════════════════════════════════════════════════════════════════
# DEDUPLICATION CACHE
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/api/deduplicator-stats")
async def get_dedup_stats():
    """Get alert deduplication cache statistics with cost-savings estimates.

    The deduplicator uses SHA-256 fingerprints of (rule + source + key fields)
    to detect duplicate alerts.  Cache hits skip LLM analysis entirely,
    saving API call costs.

    Cost model: assumes $0.005 per LLM API call.  The ``cost_saved_usd``
    field shows how much was saved by deduplication.

    Returns:
        {…cache stats…, "hit_rate_percent": float, "cost_saved_usd": float, …}
    """
    d = _deps()
    if not d["dedup"]:
        return {"error": "Deduplicator not initialized"}
    stats = d["dedup"].get_stats()
    total = stats.get("total_alerts", 0)
    hits = stats.get("hits", 0)
    misses = stats.get("misses", 0)

    # Estimated cost per LLM API call (average across providers).
    cost_per_call = 0.005

    if total > 0:
        cost_without = total * cost_per_call      # Cost if every alert hit LLM.
        cost_with = misses * cost_per_call         # Actual cost (only misses hit LLM).
        cost_saved = cost_without - cost_with      # Savings from dedup cache hits.
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
    """Clear alert deduplication cache — requires authentication.

    Removes all cached fingerprints so that previously-seen alerts will
    be re-analysed by the LLM on next occurrence.  Use after changing
    LLM prompts or analysis logic.

    Returns:
        {"status": "success", "cleared_fingerprints": int, "previous_hit_rate": str}
    """
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


# ══════════════════════════════════════════════════════════════════════════════
# PROMETHEUS EXPOSITION
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/metrics")
async def prometheus_metrics():
    """Prometheus text exposition endpoint — scraped by Prometheus every 15s.

    Before generating the text output, this endpoint refreshes three sets
    of gauges to ensure Prometheus sees current values:
        1. ``PROM_UPTIME_SECONDS`` — application uptime.
        2. Circuit-breaker state gauges (via ``update_cb``).
        3. IoT active-device count (via ``refresh_iot``).

    Returns:
        HTTP 200 with ``text/plain; version=0.0.4`` content type
        (Prometheus exposition format).
    """
    d = _deps()
    uptime = (datetime.now() - datetime.fromisoformat(d["metrics"]["started_at"])).total_seconds()
    PROM_UPTIME_SECONDS.set(uptime)
    d["update_cb"]()    # Sync circuit-breaker states → Prometheus gauges.
    
    # Run the synchronous refresh_iot in a thread pool to avoid blocking the event loop
    import asyncio
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, d["refresh_iot"])
    
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
