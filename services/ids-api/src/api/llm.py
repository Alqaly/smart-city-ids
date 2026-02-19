"""LLM diagnostics, circuit-breaker management, and stats export API router.

This module provides deep observability into the multi-provider LLM subsystem.
The Smart City IDS supports up to six LLM providers simultaneously
(xAI Grok, OpenAI, Anthropic, Google Gemini, Kimi, and a local rule-based
engine).  Each provider can be in one of several states:

    operational     – healthy, accepting requests
    not_configured  – no API key set for this provider
    cooldown        – temporarily paused after an error (auto-recovers)
    error           – last call failed (check diagnostics for cause)
    circuit_open    – circuit breaker tripped after repeated failures
    recovering      – circuit breaker half-open, testing with probe requests

The circuit-breaker pattern prevents cascade failures: when a provider fails
``failure_threshold`` times consecutively, the breaker opens and no further
requests are sent until ``recovery_timeout`` seconds elapse, at which point
a few probe requests test recovery (half-open state).

Endpoints:
    GET  /api/llm/diagnostics       – verbose per-provider health (no auth)
    GET  /api/llm/status            – compact provider list (auth required)
    POST /api/circuit-breaker/reset – manually reset breakers
    GET  /api/circuit-breaker/status – breaker state summary
    GET  /api/rate-limiter/status   – alert-level rate limiter stats
    POST /api/rate-limiter/reset    – reset rate limiter counters
    GET  /api/llm-stats/export      – per-engine latency, cost, token stats
"""

import time

from fastapi import APIRouter, Depends

from config import Config
from infrastructure.auth import verify_token
from api._state import (
    classify_llm_error,              # Map raw error strings to human-readable messages
    update_circuit_breaker_metrics,  # Sync breaker state → Prometheus gauges
)

router = APIRouter(tags=["llm"])


def _deps():
    """Retrieve LLM manager, circuit breaker, and rate limiter from shared state."""
    from api._state import llm_manager, circuit_breaker, alert_rate_limiter
    return llm_manager, circuit_breaker, alert_rate_limiter


# ══════════════════════════════════════════════════════════════════════════════
# SHARED DIAGNOSTIC BUILDER
# ══════════════════════════════════════════════════════════════════════════════

async def _build_llm_diagnostics():
    """Collect verbose per-provider diagnostics for the LLM subsystem.

    This function is reused by both ``GET /api/llm/diagnostics`` and the
    ``GET /health`` endpoint (in ``api/metrics_routes.py``).

    For each of the six known providers, it builds a diagnostic dict with:
        - **status**: one of ``operational``, ``not_configured``, ``cooldown``,
          ``error``, ``circuit_open``, ``recovering``.
        - **reason**: human-readable explanation (powered by
          ``classify_llm_error()`` for error messages).
        - **configured**: whether an API key is present.
        - **key_format_valid**: whether the key passes basic format checks.
        - **model**: the model name configured for this provider.
        - **attempts / successes / failures**: request counters.
        - **last_error**: raw error message from the most recent failure.
        - **cooldown_remaining_seconds**: seconds until cooldown expires.
        - **circuit_breaker_state**: closed / open / half_open.

    The diagnostic state-machine priority:
        1. ``local`` engine → always operational (no API key needed).
        2. Not configured → ``not_configured``.
        3. In cooldown → ``cooldown``.
        4. All requests failed → ``error``.
        5. Circuit breaker open → ``circuit_open``.
        6. Circuit breaker half-open → ``recovering``.
        7. Otherwise → ``operational``.

    Returns:
        Dict[str, dict] keyed by provider name.
    """
    llm_manager, circuit_breaker, _ = _deps()
    all_known = ["xai", "anthropic", "openai", "gemini", "kimi", "local"]
    key_validation = Config.get_valid_engines() if hasattr(Config, "get_valid_engines") else {}
    diags = {}

    if llm_manager:
        status = llm_manager.get_status()
        configured_set = set(status.get("providers", []))
        for prov_name in all_known:
            details = status.get("details", {}).get(prov_name, {})
            cb_stats = circuit_breaker.engine_stats.get(prov_name, {})
            cb_state = cb_stats.get("state", "unknown")
            is_configured = prov_name in configured_set
            key_info = key_validation.get(prov_name, {})
            cooldown_remaining = details.get("cooldown_remaining_seconds", 0)
            last_error = details.get("last_error") or cb_stats.get("last_error")
            attempts = details.get("attempts", 0)
            successes_count = details.get("successes", 0)
            failures_count = details.get("failures", 0)

            # ── Determine diagnostic status (state machine) ──────────────
            if prov_name == "local":
                diag_status = "operational"
                reason = "Rule-based engine, always available (no API key needed)"
            elif not is_configured:
                diag_status = "not_configured"
                if not key_info:
                    reason = f"No API key set — add {prov_name.upper()}_API_KEY environment variable"
                elif not key_info.get("valid_format", True):
                    reason = "API key format invalid — check key prefix and length"
                else:
                    reason = "Provider not initialized"
            elif cooldown_remaining > 0:
                diag_status = "cooldown"
                reason = classify_llm_error(last_error) + f" (cooldown: {cooldown_remaining}s remaining)"
            elif last_error and failures_count > 0 and successes_count == 0:
                diag_status = "error"
                reason = classify_llm_error(last_error)
            elif cb_state == "open":
                diag_status = "circuit_open"
                reason = "Circuit breaker OPEN — too many consecutive failures. " + (
                    classify_llm_error(last_error) if last_error else "Unknown error"
                )
            elif cb_state == "half_open":
                diag_status = "recovering"
                reason = "Circuit breaker half-open — testing recovery"
            else:
                diag_status = "operational"
                reason = "Healthy" if successes_count > 0 else "Ready (no requests yet)"

            diags[prov_name] = {
                "status": diag_status,
                "reason": reason,
                "configured": is_configured,
                "key_format_valid": key_info.get("valid_format", True) if key_info else (prov_name == "local"),
                "model": details.get("model", ""),
                "attempts": attempts,
                "successes": successes_count,
                "failures": failures_count,
                "last_error": last_error,
                "last_latency_ms": details.get("last_latency_ms"),
                "cooldown_remaining_seconds": cooldown_remaining,
                "circuit_breaker_state": cb_state,
            }

    # Fill any missing providers with "not_configured" defaults.
    for name in all_known:
        if name not in diags:
            diags[name] = {
                "status": "not_configured",
                "reason": f"No API key set — add {name.upper()}_API_KEY environment variable",
                "configured": False,
                "key_format_valid": False,
                "model": "",
                "attempts": 0,
                "successes": 0,
                "failures": 0,
                "last_error": None,
                "last_latency_ms": None,
                "cooldown_remaining_seconds": 0,
                "circuit_breaker_state": "unknown",
            }
    return diags


# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/api/llm/diagnostics")
async def llm_diagnostics_endpoint():
    """Verbose LLM provider diagnostics — no authentication required.

    Designed for quick troubleshooting: operators can curl this endpoint
    to see why alerts aren't being analysed.  The ``summary`` section gives
    at-a-glance counts of operational / error / cooldown / unconfigured
    providers.

    Returns:
        {"summary": {…}, "providers": {…}, "circuit_breaker_states": {…}}
    """
    diags = await _build_llm_diagnostics()
    _, circuit_breaker, _ = _deps()
    cb_states = {k: v.get("state", "unknown") for k, v in circuit_breaker.engine_stats.items()}
    summary = {
        "operational": sum(1 for d in diags.values() if d["status"] == "operational"),
        "error": sum(1 for d in diags.values() if d["status"] in ("error", "circuit_open")),
        "cooldown": sum(1 for d in diags.values() if d["status"] == "cooldown"),
        "not_configured": sum(1 for d in diags.values() if d["status"] == "not_configured"),
    }
    return {"summary": summary, "providers": diags, "circuit_breaker_states": cb_states}


@router.get("/api/llm/status")
async def get_llm_status(user: str = Depends(verify_token)):
    """Get LLM provider status (authenticated).

    Returns the same data as ``llm_manager.get_status()`` — provider count,
    list of configured provider names, priority order, and per-provider
    details (model, attempts, successes, failures, cooldown).

    Returns:
        {"provider_count": int, "providers": [...], "details": {…}}
    """
    llm_manager, _, _ = _deps()
    if not llm_manager:
        return {
            "provider_count": 0,
            "providers": [],
            "priority_order": [p.strip() for p in Config.LLM_PRIORITY.split(",") if p.strip()],
            "details": {},
            "error": "No LLM provider configured",
        }
    return llm_manager.get_status()


@router.post("/api/circuit-breaker/reset")
async def reset_circuit_breakers(engine: str = None):
    """Reset circuit breakers to allow LLM engines to retry.

    If ``engine`` is provided, only that engine's breaker is reset.
    Otherwise, all breakers are reset to ``closed`` state with zero
    failure counts.

    This is an administrative action — use after fixing the root cause
    (e.g. adding billing credits, fixing API key) to immediately re-enable
    a provider without waiting for the recovery timeout.

    Args:
        engine: Optional engine name (e.g. "xai", "openai").

    Returns:
        {"status": "success", "results": {engine: "old_state → closed"}, …}
    """
    _, circuit_breaker, _ = _deps()
    engines_to_reset = [engine] if engine else list(circuit_breaker.engine_stats.keys())
    reset_results = {}
    for eng in engines_to_reset:
        if eng in circuit_breaker.engine_stats:
            old_state = circuit_breaker.engine_stats[eng]["state"]
            circuit_breaker.engine_stats[eng] = {"failures": 0, "successes": 0, "state": "closed"}
            reset_results[eng] = f"{old_state} → closed"
        else:
            reset_results[eng] = "not found"
    # Sync Prometheus gauges with the new state.
    update_circuit_breaker_metrics()
    return {
        "status": "success",
        "message": f"Reset {len([r for r in reset_results.values() if 'closed' in r])} circuit breaker(s)",
        "results": reset_results,
        "current_states": {k: v.get("state", "unknown") for k, v in circuit_breaker.engine_stats.items()},
    }


@router.get("/api/circuit-breaker/status")
async def get_circuit_breaker_status():
    """Get detailed circuit breaker status for all LLM engines.

    Returns per-engine failure/success counts, current state, and global
    thresholds.  The ``summary`` section counts how many engines are in
    each state (open/closed/half_open).

    Returns:
        {"engines": {…}, "failure_threshold": int, "recovery_timeout_seconds": int, "summary": {…}}
    """
    _, circuit_breaker, _ = _deps()
    return {
        "engines": circuit_breaker.engine_stats,
        "failure_threshold": circuit_breaker.failure_threshold,
        "recovery_timeout_seconds": circuit_breaker.recovery_timeout,
        "summary": {
            "total_engines": len(circuit_breaker.engine_stats),
            "open": sum(1 for s in circuit_breaker.engine_stats.values() if s.get("state") == "open"),
            "closed": sum(1 for s in circuit_breaker.engine_stats.values() if s.get("state") == "closed"),
            "half_open": sum(1 for s in circuit_breaker.engine_stats.values() if s.get("state") == "half_open"),
        },
    }


@router.get("/api/rate-limiter/status")
async def get_rate_limiter_status():
    """Get alert-level rate limiter status and statistics.

    The alert rate limiter is separate from the HTTP rate limiter — it
    throttles alerts per-rule and per-source to prevent a flood of identical
    alerts from consuming LLM API credits.

    Returns:
        {"config": {…}, "stats": {…}, "status": "healthy" | "high_throttle_rate"}
    """
    _, _, alert_rate_limiter = _deps()
    if not alert_rate_limiter:
        return {"error": "Rate limiter not initialized"}
    stats = alert_rate_limiter.get_stats()
    return {
        "config": {
            "window_seconds": alert_rate_limiter.window_seconds,
            "max_per_rule": alert_rate_limiter.max_per_rule,
            "max_per_source": alert_rate_limiter.max_per_source,
            "max_global": alert_rate_limiter.max_global,
        },
        "stats": {
            "total_received": stats.total_received,
            "total_throttled": stats.total_throttled,
            "total_processed": stats.total_processed,
            "throttle_rate_percent": round(stats.throttle_rate * 100, 2),
            "throttle_reasons": dict(stats.throttle_reasons),
        },
        # Flag unhealthy if more than half of alerts are being throttled.
        "status": "healthy" if stats.throttle_rate < 0.5 else "high_throttle_rate",
    }


@router.post("/api/rate-limiter/reset")
async def reset_rate_limiter():
    """Reset alert rate limiter counters (administrative action).

    Clears all per-rule and per-source counters.  Use this after fixing
    the source of an alert flood.

    Returns:
        {"status": "success", "message": "Rate limiter counters reset"}
    """
    _, _, alert_rate_limiter = _deps()
    if not alert_rate_limiter:
        return {"error": "Rate limiter not initialized"}
    alert_rate_limiter.reset()
    return {"status": "success", "message": "Rate limiter counters reset"}


@router.get("/api/llm-stats/export")
async def export_llm_stats():
    """Export per-engine LLM performance stats for academic paper figures.

    Returns detailed latency percentiles (p50, p95, p99), cost estimates,
    token counts, and success rates for each LLM provider.  Designed to
    be consumed by matplotlib/seaborn for generating performance comparison
    charts in the dissertation.

    Cost estimation uses a fixed per-call cost model defined in
    ``api._state.LLM_COST_PER_CALL`` — these are approximate averages
    based on token usage patterns observed during development.

    Returns:
        {"engines": {…}, "manager_runtime_stats": {…}, "cost_model": {…}}
    """
    import statistics
    from api._state import llm_provider_stats, LLM_COST_PER_CALL, llm_manager

    engines_out = {}
    for engine, s in llm_provider_stats.items():
        lats = s.get("latencies", [])
        n = s["total_requests"]
        succ = s["successes"]
        fail = s["failures"]
        prompt_tokens = int(s.get("prompt_tokens", 0))
        completion_tokens = int(s.get("completion_tokens", 0))
        total_tokens = prompt_tokens + completion_tokens
        total_cost = round(s["total_cost_usd"], 6)
        engines_out[engine] = {
            "total_requests": n,
            "successes": succ,
            "failures": fail,
            "success_rate": round(succ / n, 4) if n else 0,
            # Latency percentiles (seconds).
            "avg_latency_s": round(statistics.mean(lats), 4) if lats else 0,
            "p50_latency_s": round(statistics.median(lats), 4) if lats else 0,
            "p95_latency_s": round(sorted(lats)[int(len(lats) * 0.95)] if len(lats) >= 2 else (lats[0] if lats else 0), 4),
            "p99_latency_s": round(sorted(lats)[int(len(lats) * 0.99)] if len(lats) >= 2 else (lats[0] if lats else 0), 4),
            # Cost estimates (USD).
            "total_estimated_cost_usd": total_cost,
            "cost_per_call_usd": LLM_COST_PER_CALL.get(engine, 0.005),
            # Token estimates.
            "prompt_tokens_total": prompt_tokens,
            "completion_tokens_total": completion_tokens,
            "tokens_total": total_tokens,
            "avg_tokens_per_request": round(total_tokens / n, 2) if n else 0,
            "avg_cost_per_request_usd": round(total_cost / n, 6) if n else 0,
        }

    # Include raw manager runtime stats for additional context.
    mgr_stats = llm_manager.runtime_stats if llm_manager else {}
    return {
        "engines": engines_out,
        "manager_runtime_stats": mgr_stats,
        "cost_model": LLM_COST_PER_CALL,
        "note": "Latencies are in seconds. Cost and tokens are estimated from IDS payload/response size.",
    }


# ══════════════════════════════════════════════════════════════════════════════
# Operator Feedback Endpoint
# ══════════════════════════════════════════════════════════════════════════════

import logging
from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger(__name__)

# In-memory feedback store (persisted to DB when available)
_feedback_store = []


class FeedbackPayload(BaseModel):
    """Operator feedback on an LLM analysis."""
    analysis_id: str
    was_accurate: bool
    comment: Optional[str] = None
    timestamp: Optional[str] = None


@router.post("/api/llm/feedback")
async def submit_feedback(payload: FeedbackPayload):
    """Record operator feedback on an LLM analysis.

    This creates a feedback loop for continuous improvement.  Operators
    can mark analyses as accurate or inaccurate, and optionally add
    comments explaining their assessment.

    The feedback is stored and can be used for:
    - Tracking LLM accuracy over time
    - Identifying patterns in false positives/negatives
    - Informing prompt engineering improvements
    """
    feedback = {
        "analysis_id": payload.analysis_id,
        "was_accurate": payload.was_accurate,
        "comment": payload.comment,
        "timestamp": payload.timestamp or str(time.time()),
    }
    _feedback_store.append(feedback)

    # Try to persist to database
    try:
        from api._state import db
        db.execute_raw(
            "INSERT INTO operator_feedback (analysis_id, was_accurate, comment, created_at) "
            "VALUES (%s, %s, %s, NOW())",
            (payload.analysis_id, payload.was_accurate, payload.comment)
        )
    except Exception as e:
        logger.debug(f"Feedback DB persist skipped (table may not exist): {e}")

    logger.info(
        f"Operator feedback: analysis={payload.analysis_id} "
        f"accurate={payload.was_accurate} comment='{payload.comment or ''}'"
    )

    # Calculate running accuracy
    total = len(_feedback_store)
    accurate = sum(1 for f in _feedback_store if f["was_accurate"])
    accuracy_rate = round(accurate / total * 100, 1) if total > 0 else 0

    return {
        "status": "recorded",
        "total_feedback": total,
        "accuracy_rate": accuracy_rate,
        "message": "Thank you for improving the system."
    }


@router.get("/api/llm/feedback/stats")
async def get_feedback_stats():
    """Return operator feedback statistics."""
    total = len(_feedback_store)
    accurate = sum(1 for f in _feedback_store if f["was_accurate"])
    inaccurate = total - accurate

    return {
        "total_feedback": total,
        "accurate": accurate,
        "inaccurate": inaccurate,
        "accuracy_rate": round(accurate / total * 100, 1) if total > 0 else 0,
        "recent": _feedback_store[-10:] if _feedback_store else [],
    }
