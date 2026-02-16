"""LLM diagnostics & circuit-breaker API router."""

import time

from fastapi import APIRouter, Depends

from config import Config
from infrastructure.auth import verify_token
from api._state import (
    classify_llm_error,
    update_circuit_breaker_metrics,
)

router = APIRouter(tags=["llm"])


def _deps():
    from api._state import llm_manager, circuit_breaker, alert_rate_limiter
    return llm_manager, circuit_breaker, alert_rate_limiter


# ─── Health helper (reused by diagnostics) ───────────────────────────────
async def _build_llm_diagnostics():
    """Collect verbose LLM provider diagnostics."""
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

    # Fill any missing providers
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


@router.get("/api/llm/diagnostics")
async def llm_diagnostics_endpoint():
    """Verbose LLM provider diagnostics. No auth required."""
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
    """Get LLM provider status."""
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
    """Reset circuit breakers to allow LLM engines to retry."""
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
    update_circuit_breaker_metrics()
    return {
        "status": "success",
        "message": f"Reset {len([r for r in reset_results.values() if 'closed' in r])} circuit breaker(s)",
        "results": reset_results,
        "current_states": {k: v.get("state", "unknown") for k, v in circuit_breaker.engine_stats.items()},
    }


@router.get("/api/circuit-breaker/status")
async def get_circuit_breaker_status():
    """Get detailed circuit breaker status for all LLM engines."""
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
    """Get alert rate limiter status and statistics."""
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
        "status": "healthy" if stats.throttle_rate < 0.5 else "high_throttle_rate",
    }


@router.post("/api/rate-limiter/reset")
async def reset_rate_limiter():
    """Reset rate limiter counters (admin use only)."""
    _, _, alert_rate_limiter = _deps()
    if not alert_rate_limiter:
        return {"error": "Rate limiter not initialized"}
    alert_rate_limiter.reset()
    return {"status": "success", "message": "Rate limiter counters reset"}


@router.get("/api/llm-stats/export")
async def export_llm_stats():
    """Export per-engine LLM performance stats for paper figures."""
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
            "avg_latency_s": round(statistics.mean(lats), 4) if lats else 0,
            "p50_latency_s": round(statistics.median(lats), 4) if lats else 0,
            "p95_latency_s": round(sorted(lats)[int(len(lats) * 0.95)] if len(lats) >= 2 else (lats[0] if lats else 0), 4),
            "p99_latency_s": round(sorted(lats)[int(len(lats) * 0.99)] if len(lats) >= 2 else (lats[0] if lats else 0), 4),
            "total_estimated_cost_usd": total_cost,
            "cost_per_call_usd": LLM_COST_PER_CALL.get(engine, 0.005),
            "prompt_tokens_total": prompt_tokens,
            "completion_tokens_total": completion_tokens,
            "tokens_total": total_tokens,
            "avg_tokens_per_request": round(total_tokens / n, 2) if n else 0,
            "avg_cost_per_request_usd": round(total_cost / n, 6) if n else 0,
        }

    mgr_stats = llm_manager.runtime_stats if llm_manager else {}
    return {
        "engines": engines_out,
        "manager_runtime_stats": mgr_stats,
        "cost_model": LLM_COST_PER_CALL,
        "note": "Latencies are in seconds. Cost and tokens are estimated from IDS payload/response size.",
    }
