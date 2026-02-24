"""LLM diagnostics, circuit-breaker management, and stats export API router.

This module provides deep observability into the multi-provider LLM subsystem.
The Smart City IDS supports up to five LLM providers simultaneously
(xAI Grok, OpenAI, Anthropic, Google Gemini, and Kimi).  Each provider can be
in one of several states:

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

import asyncio
import time
import os
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from config import Config
from infrastructure.auth import verify_token
from api._state import (
    classify_llm_error,              # Map raw error strings to human-readable messages
    update_circuit_breaker_metrics,  # Sync breaker state → Prometheus gauges
)

router = APIRouter(tags=["llm"])


def _mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "***"
    return f"{key[:3]}...{key[-4:]}"


class ForceProviderPayload(BaseModel):
    provider: str | None = None


class LLMTestPayload(BaseModel):
    provider: str | None = None
    prompt: str = "Respond with: OK"


class PriorityPayload(BaseModel):
    providers: list[str] | None = None
    order: str | None = None


class RoutingStrategyPayload(BaseModel):
    mode: str | None = None
    cost_ceiling_usd: float | None = None
    ab_enabled: bool | None = None
    provider_a: str | None = None
    provider_b: str | None = None
    split_percent_a: int | None = None


class LLMQuickTestPayload(BaseModel):
    prompt: str = "Respond with: OK"


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

    For each known provider, it builds a diagnostic dict with:
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
        1. Not configured → ``not_configured``.
        2. In cooldown → ``cooldown``.
        3. All requests failed → ``error``.
        4. Circuit breaker open → ``circuit_open``.
        5. Circuit breaker half-open → ``recovering``.
        6. Otherwise → ``operational``.

    Returns:
        Dict[str, dict] keyed by provider name.
    """
    llm_manager, circuit_breaker, _ = _deps()
    all_known = ["xai", "anthropic", "openai", "gemini", "kimi"]
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
            auth_failed = bool(details.get("auth_failed"))
            auth_failed_reason = details.get("auth_failed_reason")
            last_error = details.get("last_error") or cb_stats.get("last_error")
            attempts = details.get("attempts", 0)
            successes_count = details.get("successes", 0)
            failures_count = details.get("failures", 0)

            # ── Determine diagnostic status (state machine) ──────────────
            if auth_failed:
                diag_status = "auth_failed"
                reason = auth_failed_reason or "Invalid API key"
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
                "key_format_valid": key_info.get("valid_format", True) if key_info else False,
                "model": details.get("model", ""),
                "attempts": attempts,
                "successes": successes_count,
                "failures": failures_count,
                "success_rate": details.get("success_rate", 0.0),
                "last_error": last_error,
                "last_latency_ms": details.get("last_latency_ms"),
                "p95_latency_ms": details.get("p95_latency_ms"),
                "cooldown_remaining_seconds": cooldown_remaining,
                "auth_failed": auth_failed,
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


@router.post("/api/llm/reset-cooldown")
async def reset_llm_cooldowns(user: str = Depends(verify_token)):
    """Manually clear provider cooldown/auth-disable timers.

    This is used after fixing API keys/billing so providers become eligible
    immediately without waiting for long cooldown windows.
    """
    llm_manager, circuit_breaker, _ = _deps()
    out = {"status": "success"}
    if llm_manager and hasattr(llm_manager, "reset_cooldowns"):
        out["llm_manager"] = llm_manager.reset_cooldowns()
    # Also reset circuit breaker state to avoid a stale OPEN state.
    if circuit_breaker and hasattr(circuit_breaker, "reset"):
        circuit_breaker.reset()
        update_circuit_breaker_metrics(circuit_breaker)
        out["circuit_breaker"] = "reset"
    return out


@router.post("/api/llm/retry-all")
async def retry_all_providers(user: str = Depends(verify_token)):
    """
    Clears all auth_failed states and cooldowns, allowing all providers to be retried.
    This is a convenience endpoint for the UI 'Retry All' button.
    """
    llm_manager, circuit_breaker, _ = _deps()
    out = {"status": "success", "message": "All provider states reset."}

    if llm_manager:
        if hasattr(llm_manager, "reset_all_provider_states"):
            out["providers"] = llm_manager.reset_all_provider_states()
        elif hasattr(llm_manager, "reset_cooldowns"): # Fallback for older manager versions
            llm_manager.reset_cooldowns()

    if circuit_breaker and hasattr(circuit_breaker, "reset"):
        circuit_breaker.reset()
        update_circuit_breaker_metrics(circuit_breaker)
        out["circuit_breaker"] = "reset"

    return out


@router.post("/api/llm/providers/{provider}/enable")
async def enable_llm_provider(provider: str, user: str = Depends(verify_token)):
    """Manually re-enable a provider after auth_failed.

    This does not change the API key; it only clears the auth_failed latch
    so the next probe/call can retry.
    """
    llm_manager, _, _ = _deps()
    if not llm_manager or not hasattr(llm_manager, "enable_provider"):
        return {"status": "error", "error": "llm_manager_unavailable"}
    return llm_manager.enable_provider(provider.strip().lower())


@router.get("/api/llm/key-status")
async def llm_key_status(remote_probe: bool = False, user: str = Depends(verify_token)):
    """Return API key diagnostics without exposing secrets.

    - Masks keys as "sk-...last4".
    - Validates format using Config.is_valid_api_key().
    - Optionally performs a cheap remote probe (GET /models) when remote_probe=true.
    """
    llm_manager, _, _ = _deps()
    status = llm_manager.get_status() if llm_manager else {"details": {}}
    details = status.get("details", {}) or {}

    providers = [
        ("xai", "XAI_API_KEY"),
        ("openai", "OPENAI_API_KEY"),
        ("anthropic", "ANTHROPIC_API_KEY"),
        ("gemini", "GEMINI_API_KEY"),
        ("kimi", "KIMI_API_KEY"),
    ]

    out = {
        "observed_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "providers": {},
    }

    # Key age: env-provided keys have no reliable issuance timestamp.
    # We provide an operator-meaningful proxy: how long this process has been running.
    try:
        from api._state import metrics_dict

        out["process_started_at"] = metrics_dict.get("started_at")
        out["process_uptime_seconds"] = int(metrics_dict.get("uptime_seconds") or 0)
    except Exception:
        out["process_started_at"] = None
        out["process_uptime_seconds"] = None

    async def _probe_models(name: str, key: str) -> dict:
        # Remote probe is intentionally NOT an analysis call.
        import httpx

        try:
            timeout = 6.0
            if name in ("openai", "xai", "kimi"):
                base = os.getenv(f"{name.upper()}_BASE_URL", "")
                if not base:
                    # fall back to provider defaults used elsewhere
                    base = {
                        "openai": "https://api.openai.com/v1",
                        "xai": "https://api.x.ai/v1",
                        "kimi": "https://api.moonshot.ai/v1",
                    }[name]
                url = f"{base.rstrip('/')}/models"
                headers = {"Authorization": f"Bearer {key}"}
            elif name == "anthropic":
                url = "https://api.anthropic.com/v1/models"
                headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
            elif name == "gemini":
                url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
                headers = {}
            else:
                return {"ok": False, "error": "unknown provider"}

            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.get(url, headers=headers)
                remaining = r.headers.get("X-RateLimit-Remaining") or r.headers.get("x-ratelimit-remaining")
                limit = r.headers.get("X-RateLimit-Limit") or r.headers.get("x-ratelimit-limit")
                if r.status_code == 200:
                    return {"ok": True, "http": 200, "rate_limit_remaining": remaining, "rate_limit_limit": limit}
                return {"ok": False, "http": r.status_code, "error": r.text[:200], "rate_limit_remaining": remaining, "rate_limit_limit": limit}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    for name, env_key in providers:
        raw = os.getenv(env_key, "")
        configured = bool(raw)
        valid_format = bool(configured and hasattr(Config, "is_valid_api_key") and Config.is_valid_api_key(raw, name))
        d = details.get(name, {}) or {}

        entry = {
            "configured": configured,
            "valid_format": valid_format,
            "masked_key": _mask_key(raw) if configured else None,
            "env_var": env_key,
            "last_error": d.get("last_error"),
            "cooldown_remaining_seconds": int(d.get("cooldown_remaining_seconds") or 0),
            "auth_disabled_remaining_seconds": int(d.get("auth_disabled_remaining_seconds") or 0),
        }

        if remote_probe and configured and valid_format:
            entry["remote_probe"] = await _probe_models(name, raw)
        elif remote_probe and configured and not valid_format:
            entry["remote_probe"] = {"ok": False, "error": "format_invalid"}

        out["providers"][name] = entry

    return out


@router.get("/api/llm/key-status/{provider}")
async def llm_key_status_for_provider(
    provider: str,
    remote_probe: bool = True,
    user: str = Depends(verify_token),
):
    """Return key diagnostics for a single provider.

    This is used by the dashboard per-provider "Test key" button.
    When ``remote_probe=true`` (default), performs a cheap remote probe
    (models list) for ONLY the requested provider.
    """
    llm_manager, _, _ = _deps()
    status = llm_manager.get_status() if llm_manager else {"details": {}}
    details = status.get("details", {}) or {}

    provider = (provider or "").strip().lower()
    env_map = {
        "xai": "XAI_API_KEY",
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "kimi": "KIMI_API_KEY",
    }
    if provider not in env_map:
        return {"status": "error", "error": "unknown_provider", "provider": provider}

    async def _probe_models(name: str, key: str) -> dict:
        import httpx

        try:
            timeout = 6.0
            if name in ("openai", "xai", "kimi"):
                base = os.getenv(f"{name.upper()}_BASE_URL", "")
                if not base:
                    base = {
                        "openai": "https://api.openai.com/v1",
                        "xai": "https://api.x.ai/v1",
                        "kimi": "https://api.moonshot.ai/v1",
                    }[name]
                url = f"{base.rstrip('/')}/models"
                headers = {"Authorization": f"Bearer {key}"}
            elif name == "anthropic":
                url = "https://api.anthropic.com/v1/models"
                headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
            elif name == "gemini":
                url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
                headers = {}
            else:
                return {"ok": False, "error": "unknown provider"}

            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.get(url, headers=headers)
                remaining = r.headers.get("X-RateLimit-Remaining") or r.headers.get("x-ratelimit-remaining")
                limit = r.headers.get("X-RateLimit-Limit") or r.headers.get("x-ratelimit-limit")
                if r.status_code == 200:
                    return {"ok": True, "http": 200, "rate_limit_remaining": remaining, "rate_limit_limit": limit}
                return {
                    "ok": False,
                    "http": r.status_code,
                    "error": r.text[:200],
                    "rate_limit_remaining": remaining,
                    "rate_limit_limit": limit,
                }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    env_key = env_map[provider]
    raw = os.getenv(env_key, "")
    configured = bool(raw)
    valid_format = bool(configured and hasattr(Config, "is_valid_api_key") and Config.is_valid_api_key(raw, provider))
    d = details.get(provider, {}) or {}

    entry = {
        "configured": configured,
        "valid_format": valid_format,
        "masked_key": _mask_key(raw) if configured else None,
        "env_var": env_key,
        "last_error": d.get("last_error"),
        "cooldown_remaining_seconds": int(d.get("cooldown_remaining_seconds") or 0),
        "auth_disabled_remaining_seconds": int(d.get("auth_disabled_remaining_seconds") or 0),
    }

    if remote_probe and configured and valid_format:
        entry["remote_probe"] = await _probe_models(provider, raw)
    elif remote_probe and configured and not valid_format:
        entry["remote_probe"] = {"ok": False, "error": "format_invalid"}
    elif remote_probe and not configured:
        entry["remote_probe"] = {"ok": False, "error": "not_configured"}

    return {
        "observed_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "provider": provider,
        "entry": entry,
    }


@router.get("/api/llm/retry-queue")
async def get_llm_retry_queue(user: str = Depends(verify_token)):
    """Return queued alerts that failed all provider attempts and await retry orchestration."""
    from api._state import llm_retry_queue
    items = list(llm_retry_queue)
    return {"queued": len(items), "items": items[-200:]}


@router.post("/api/llm/retry-queue/clear")
async def clear_llm_retry_queue(user: str = Depends(verify_token)):
    """Clear queued failed-analysis items."""
    from api._state import llm_retry_queue
    cleared = len(llm_retry_queue)
    llm_retry_queue.clear()
    return {"status": "success", "cleared": cleared}


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
    stats = alert_rate_limiter.get_stats() or {}
    total_received = int(stats.get("total_received", 0))
    total_throttled = int(stats.get("total_throttled", 0))
    total_processed = int(stats.get("total_processed", 0))
    throttle_rate = float(stats.get("throttle_rate_percent", 0.0))
    return {
        "config": {
            "window_seconds": alert_rate_limiter.window_seconds,
            "max_per_rule": alert_rate_limiter.max_per_rule,
            "max_per_source": alert_rate_limiter.max_per_source,
            "max_global": alert_rate_limiter.max_global,
        },
        "stats": {
            "total_received": total_received,
            "total_throttled": total_throttled,
            "total_processed": total_processed,
            "throttle_rate_percent": throttle_rate,
            "throttle_reasons": stats.get("throttle_reasons", {}),
            "current_windows": stats.get("current_windows", {}),
        },
        # Flag unhealthy if more than half of alerts are being throttled.
        "status": "healthy" if throttle_rate < 50.0 else "high_throttle_rate",
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
    if hasattr(alert_rate_limiter, "clear_all"):
        alert_rate_limiter.clear_all()
        return {"status": "success", "message": "Rate limiter counters and windows reset"}
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
    from api._state import llm_provider_stats, LLM_COST_PER_CALL, LLM_COST_PER_1K_TOKENS, llm_manager

    engines_out = {}
    valid_engines = {"xai", "openai", "anthropic", "gemini", "kimi", "custom"}
    for engine, s in llm_provider_stats.items():
        if engine not in valid_engines:
            continue
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
            "cost_per_1k_tokens_usd": LLM_COST_PER_1K_TOKENS.get(engine, 0.0),
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
        "token_cost_model": LLM_COST_PER_1K_TOKENS,
        "note": "Latencies are in seconds. Cost is token-based estimate when token usage is available and fallback token estimates otherwise.",
    }


async def _build_provider_comparison_payload():
    stats = await export_llm_stats()
    diagnostics = await _build_llm_diagnostics()
    usage_totals_by_provider: dict[str, dict] = {}

    # Runtime counters reset on pod restart. Merge DB-backed usage totals so
    # the dashboard comparison remains meaningful across restarts.
    try:
        from api._state import db, LLM_COST_PER_1K_TOKENS
        usage = None
        if db and hasattr(db, "get_llm_usage_today"):
            usage = db.get_llm_usage_today()
        for row in (usage or {}).get("providers", []) or []:
            prov = str(row.get("provider") or "").strip().lower()
            if not prov:
                continue
            prompt_tokens = int(row.get("prompt_tokens") or 0)
            completion_tokens = int(row.get("completion_tokens") or 0)
            tokens_total = prompt_tokens + completion_tokens
            rate = float(LLM_COST_PER_1K_TOKENS.get(prov, 0.0))
            usage_totals_by_provider[prov] = {
                "calls": int(row.get("calls") or 0),
                "prompt_tokens_total": prompt_tokens,
                "completion_tokens_total": completion_tokens,
                "tokens_total": tokens_total,
                "total_estimated_cost_usd": round((tokens_total / 1000.0) * rate, 6) if rate > 0 else 0.0,
            }
    except Exception:
        usage_totals_by_provider = {}

    engines = stats.get("engines", {})
    names = sorted(set(engines.keys()) | set(diagnostics.keys()) | set(usage_totals_by_provider.keys()))

    rows = []
    totals = {
        "providers": len(names),
        "calls": 0,
        "tokens": 0,
        "cost_usd": 0.0,
        "successes": 0,
    }

    for name in names:
        engine = engines.get(name, {})
        diag = diagnostics.get(name, {})
        usage = usage_totals_by_provider.get(name, {})
        calls = int(engine.get("total_requests", 0)) or int(usage.get("calls", 0))
        successes = int(engine.get("successes", 0))
        failures = int(engine.get("failures", 0))
        success_rate = engine.get("success_rate")
        if success_rate is None:
            success_rate = (successes / calls) if calls else 0.0

        prompt_tokens = int(engine.get("prompt_tokens_total", 0)) or int(usage.get("prompt_tokens_total", 0))
        completion_tokens = int(engine.get("completion_tokens_total", 0)) or int(usage.get("completion_tokens_total", 0))
        total_tokens = int(engine.get("tokens_total", prompt_tokens + completion_tokens)) or int(usage.get("tokens_total", 0))
        total_cost_usd = float(engine.get("total_estimated_cost_usd", 0.0)) or float(usage.get("total_estimated_cost_usd", 0.0))

        totals["calls"] += calls
        totals["tokens"] += total_tokens
        totals["cost_usd"] += total_cost_usd
        totals["successes"] += successes

        rows.append({
            "provider": name,
            "configured": bool(diag.get("configured", False)),
            "status": diag.get("status", "unknown"),
            "model": diag.get("model") or "",
            "calls": calls,
            "attempts": int(diag.get("attempts", 0)),
            "successes": successes,
            "failures": failures,
            "success_rate": round(float(success_rate), 4),
            "last_latency_ms": diag.get("last_latency_ms"),
            "avg_latency_s": float(engine.get("avg_latency_s", 0.0)),
            "p95_latency_s": float(engine.get("p95_latency_s", 0.0)),
            "prompt_tokens_total": prompt_tokens,
            "completion_tokens_total": completion_tokens,
            "tokens_total": total_tokens,
            "total_estimated_cost_usd": round(total_cost_usd, 6),
            "avg_cost_per_request_usd": float(engine.get("avg_cost_per_request_usd", 0.0)),
            "cooldown_remaining_seconds": int(diag.get("cooldown_remaining_seconds", 0) or 0),
            "circuit_breaker_state": diag.get("circuit_breaker_state", "unknown"),
            "last_error": diag.get("last_error"),
            "reason": diag.get("reason", ""),
        })

    totals["cost_usd"] = round(totals["cost_usd"], 6)
    totals["success_rate"] = round((totals["successes"] / totals["calls"]) if totals["calls"] else 0.0, 4)
    totals["operational"] = sum(1 for row in rows if row.get("status") == "operational")

    return {
        "summary": totals,
        "providers": rows,
        "generated_at": int(time.time()),
    }


@router.get("/api/llm/providers/comparison")
async def llm_provider_comparison():
    """Normalized provider comparison payload for dashboard tables/cards."""
    return await _build_provider_comparison_payload()


@router.get("/api/llm/providers/health-summary")
async def llm_provider_health_summary():
    """Compact provider health summary for dashboard KPI cards."""
    comparison = await _build_provider_comparison_payload()
    summary = comparison.get("summary", {})
    providers = comparison.get("providers", [])

    active = [p for p in providers if p.get("configured")]
    fastest = min(
        [p for p in active if p.get("avg_latency_s", 0) > 0],
        key=lambda p: p.get("avg_latency_s", 0),
        default=None,
    )

    return {
        "operational": summary.get("operational", 0),
        "providers": summary.get("providers", len(providers)),
        "calls": summary.get("calls", 0),
        "tokens": summary.get("tokens", 0),
        "cost_usd": summary.get("cost_usd", 0.0),
        "success_rate": summary.get("success_rate", 0.0),
        "fastest_provider": fastest.get("provider") if fastest else None,
        "fastest_avg_latency_s": fastest.get("avg_latency_s") if fastest else None,
        "generated_at": comparison.get("generated_at"),
    }


@router.get("/api/llm/providers")
async def llm_providers_matrix(probe: bool = False):
    """Real-time provider matrix for LLM control center cards."""
    status = await llm_control_status(probe=probe)
    comparison = await _build_provider_comparison_payload()
    return {
        "generated_at": comparison.get("generated_at"),
        "active_provider": status.get("active_provider"),
        "effective_provider": status.get("effective_provider"),
        "fallback_chain": status.get("fallback_chain", []),
        "providers": comparison.get("providers", []),
    }


@router.post("/api/llm/test/{provider}")
async def llm_test_provider_by_name(
    provider: str,
    payload: LLMQuickTestPayload | None = None,
    _=Depends(verify_token),
):
    """Interactive single-provider test endpoint for operator console."""
    llm_manager, _, _ = _deps()
    provider = (provider or "").strip().lower()
    if not llm_manager:
        return {"status": "error", "message": "LLM manager unavailable", "provider": provider}

    status = llm_manager.get_status() if hasattr(llm_manager, "get_status") else {}
    available = set(status.get("providers", []))
    if provider not in available:
        return {"status": "error", "message": f"Unknown provider: {provider}", "provider": provider}

    prompt = (payload.prompt if payload else None) or "Analyze: suspicious outbound connection"
    test_alert = {
        "output": prompt,
        "rule": "operator-llm-test",
        "priority": "Notice",
        "time": str(time.time()),
        "output_fields": {"container.name": "ids-api", "interactive_test": "true"},
    }
    started = time.perf_counter()
    result = await llm_manager.analyze(test_alert, preferred_engine=provider)
    latency_ms = int((time.perf_counter() - started) * 1000)
    analysis = result.get("analysis") or {}
    usage = result.get("usage") or {}
    total_tokens = int(usage.get("total_tokens") or (usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0) or 0))
    estimated_cost = 0.0
    try:
        from api._state import _estimate_cost_from_tokens
        estimated_cost = float(_estimate_cost_from_tokens(provider, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)))
    except Exception:
        estimated_cost = 0.0

    return {
        "status": result.get("status", "unknown"),
        "provider": result.get("provider") or result.get("engine") or provider,
        "latency_ms": latency_ms,
        "summary": analysis.get("summary"),
        "severity": analysis.get("severity"),
        "usage": usage,
        "tokens": total_tokens,
        "estimated_cost_usd": round(estimated_cost, 6),
        "error": result.get("error"),
        "failed_engines": result.get("failed_engines", []),
    }


# ══════════════════════════════════════════════════════════════════════════════
# LLM Provider Combat — supervisor demo: all providers race the same threat
# ══════════════════════════════════════════════════════════════════════════════

class CombatPayload(BaseModel):
    prompt: str = "Suspicious outbound connection from IoT sensor device to unknown external IP. Large data transfer detected."
    scenario: str = "iot-exfiltration"
    priority: str = "High"
    timeout_seconds: float = 15.0


@router.post("/api/llm/combat")
async def llm_provider_combat(payload: CombatPayload | None = None):
    """Run the same threat scenario through ALL configured providers simultaneously.

    Returns a ranked comparison showing which provider is fastest, most accurate,
    and most cost-efficient — ideal for live supervisor demo / provider selection.

    No auth required so the dashboard can call it without a token.
    """
    llm_manager, _, _ = _deps()
    if not llm_manager:
        return {"status": "error", "message": "LLM manager unavailable"}

    p = payload or CombatPayload()
    test_alert = {
        "output": p.prompt,
        "rule": f"combat-{p.scenario}",
        "priority": p.priority,
        "time": str(time.time()),
        "output_fields": {
            "container.name": "ids-api",
            "scenario": p.scenario,
            "combat_test": "true",
        },
    }

    # Discover all configured providers
    manager_status = llm_manager.get_status() if hasattr(llm_manager, "get_status") else {}
    providers = manager_status.get("providers", [])
    if not providers:
        return {"status": "error", "message": "No providers configured"}

    async def _race_one(provider_name: str) -> dict:
        started = time.perf_counter()
        try:
            result = await asyncio.wait_for(
                llm_manager.analyze(test_alert, preferred_engine=provider_name),
                timeout=p.timeout_seconds,
            )
            latency_ms = int((time.perf_counter() - started) * 1000)
            analysis = result.get("analysis") or {}
            usage = result.get("usage") or {}
            prompt_toks = int(usage.get("prompt_tokens", 0))
            completion_toks = int(usage.get("completion_tokens", 0))
            total_toks = int(usage.get("total_tokens") or (prompt_toks + completion_toks))
            cost = 0.0
            try:
                from api._state import _estimate_cost_from_tokens
                cost = float(_estimate_cost_from_tokens(provider_name, prompt_toks, completion_toks))
            except Exception:
                pass
            return {
                "provider": provider_name,
                "status": result.get("status", "unknown"),
                "latency_ms": latency_ms,
                "severity": analysis.get("severity"),
                "threat_type": analysis.get("threat_type"),
                "summary": analysis.get("summary"),
                "recommendations": analysis.get("recommendations", [])[:2],
                "tokens": total_toks,
                "estimated_cost_usd": round(cost, 6),
                "error": result.get("error"),
            }
        except asyncio.TimeoutError:
            return {
                "provider": provider_name,
                "status": "timeout",
                "latency_ms": int(p.timeout_seconds * 1000),
                "severity": None,
                "threat_type": None,
                "summary": None,
                "recommendations": [],
                "tokens": 0,
                "estimated_cost_usd": 0.0,
                "error": f"Timed out after {p.timeout_seconds}s",
            }
        except Exception as exc:
            return {
                "provider": provider_name,
                "status": "error",
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "severity": None,
                "threat_type": None,
                "summary": None,
                "recommendations": [],
                "tokens": 0,
                "estimated_cost_usd": 0.0,
                "error": str(exc),
            }

    overall_start = time.perf_counter()
    results = await asyncio.gather(*[_race_one(p_name) for p_name in providers])
    total_wall_ms = int((time.perf_counter() - overall_start) * 1000)

    # Rank providers
    successful = [r for r in results if r["status"] == "success"]
    fastest = min(successful, key=lambda r: r["latency_ms"], default=None)
    cheapest = min(successful, key=lambda r: r["estimated_cost_usd"], default=None) if any(r["estimated_cost_usd"] > 0 for r in successful) else None
    quality_scored = [r for r in successful if r.get("severity") and r.get("summary")]
    best_quality = quality_scored[0] if quality_scored else (successful[0] if successful else None)

    # Determine winner (fastest + quality beats cheap alone for security workloads)
    winner = None
    winner_reason = ""
    if fastest and best_quality and fastest["provider"] == best_quality["provider"]:
        winner = fastest["provider"]
        winner_reason = "fastest response with complete analysis"
    elif best_quality:
        winner = best_quality["provider"]
        winner_reason = "most complete threat analysis (severity + summary + recommendations)"
    elif fastest:
        winner = fastest["provider"]
        winner_reason = "only provider that responded successfully"

    # Assign per-result ranks
    rank_map = {}
    for idx, r in enumerate(sorted(successful, key=lambda x: x["latency_ms"]), 1):
        rank_map[r["provider"]] = {"speed_rank": idx}
    for idx, r in enumerate(sorted(successful, key=lambda x: x["estimated_cost_usd"]), 1):
        rank_map.setdefault(r["provider"], {})["cost_rank"] = idx

    for r in results:
        ranks = rank_map.get(r["provider"], {})
        r["speed_rank"] = ranks.get("speed_rank")
        r["cost_rank"] = ranks.get("cost_rank")
        r["is_winner"] = (r["provider"] == winner)

    return {
        "status": "ok",
        "scenario": p.scenario,
        "prompt": p.prompt,
        "providers_raced": len(providers),
        "successful": len(successful),
        "total_wall_ms": total_wall_ms,
        "winner": winner,
        "winner_reason": winner_reason,
        "fastest_provider": fastest["provider"] if fastest else None,
        "fastest_latency_ms": fastest["latency_ms"] if fastest else None,
        "cheapest_provider": cheapest["provider"] if cheapest else None,
        "best_quality_provider": best_quality["provider"] if best_quality else None,
        "results": sorted(results, key=lambda r: (r["status"] != "success", r["latency_ms"])),
        "generated_at": int(time.time()),
    }


@router.post("/api/llm/force/{provider}")
async def force_provider_path(provider: str, _=Depends(verify_token)):
    """Force selected provider using path-style endpoint for operator UI."""
    chosen = (provider or "").strip().lower()
    payload = ForceProviderPayload(provider=chosen if chosen != "auto" else None)
    return await set_forced_provider(payload)


@router.get("/api/llm/metrics/24h")
async def llm_metrics_24h(_=Depends(verify_token)):
    """24h-shaped metrics payload for comparison table (uses current in-memory runtime window)."""
    comparison = await _build_provider_comparison_payload()
    rows = []
    for row in comparison.get("providers", []):
        rows.append({
            "provider": row.get("provider"),
            "calls": int(row.get("attempts") or 0),
            "tokens": int(row.get("tokens_total") or 0),
            "cost_usd": float(row.get("total_estimated_cost_usd") or 0.0),
            "success_rate": float(row.get("success_rate") or 0.0),
            "p95_latency_s": float(row.get("p95_latency_s") or 0.0),
            "status": row.get("status"),
        })
    return {
        "window_hours": 24,
        "generated_at": comparison.get("generated_at"),
        "summary": comparison.get("summary", {}),
        "providers": rows,
        "note": "Runtime in-memory metrics snapshot in 24h schema.",
    }


@router.get("/api/llm/routing/strategy")
async def get_llm_routing_strategy(_=Depends(verify_token)):
    """Get active LLM routing strategy and recent routing decisions."""
    try:
        from api._state import db
        cost_cfg = db.get_system_config('llm_cost_ceiling', {
            "max_daily_usd": 10.0,
            "current_daily_usd": 0.0,
            "last_reset": None
        })
        routing_cfg = db.get_system_config('llm_routing_strategy', {
            "mode": "priority",
            "ab_enabled": False,
            "provider_a": None,
            "provider_b": None,
            "split_percent_a": 50,
        })
        return {
            "status": "ok",
            "routing": {
                "mode": routing_cfg.get("mode", "priority"),
                "ab_enabled": bool(routing_cfg.get("ab_enabled", False)),
                "provider_a": routing_cfg.get("provider_a"),
                "provider_b": routing_cfg.get("provider_b"),
                "split_percent_a": int(routing_cfg.get("split_percent_a", 50) or 50),
                "cost_ceiling_usd": cost_cfg.get("max_daily_usd"),
            },
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.post("/api/llm/routing/strategy")
async def set_llm_routing_strategy(payload: RoutingStrategyPayload, _=Depends(verify_token)):
    """Update runtime LLM routing strategy (priority/cost_optimized/ab_test/severity_adaptive)."""
    try:
        from api._state import db
        cost_cfg = db.get_system_config('llm_cost_ceiling', {
            "max_daily_usd": 10.0,
            "current_daily_usd": 0.0,
            "last_reset": None
        })
        routing_cfg = db.get_system_config('llm_routing_strategy', {
            "mode": "priority",
            "ab_enabled": False,
            "provider_a": None,
            "provider_b": None,
            "split_percent_a": 50,
        })
        
        if payload.cost_ceiling_usd is not None:
            cost_cfg["max_daily_usd"] = payload.cost_ceiling_usd
            db.set_system_config('llm_cost_ceiling', cost_cfg)
        if payload.mode:
            routing_cfg["mode"] = str(payload.mode)
        if payload.ab_enabled is not None:
            routing_cfg["ab_enabled"] = bool(payload.ab_enabled)
        if payload.provider_a is not None:
            routing_cfg["provider_a"] = payload.provider_a
        if payload.provider_b is not None:
            routing_cfg["provider_b"] = payload.provider_b
        if payload.split_percent_a is not None:
            routing_cfg["split_percent_a"] = int(payload.split_percent_a)
        db.set_system_config('llm_routing_strategy', routing_cfg)

        return {
            "status": "ok",
            "routing": {
                "mode": routing_cfg.get("mode", "priority"),
                "ab_enabled": bool(routing_cfg.get("ab_enabled", False)),
                "provider_a": routing_cfg.get("provider_a"),
                "provider_b": routing_cfg.get("provider_b"),
                "split_percent_a": int(routing_cfg.get("split_percent_a", 50) or 50),
                "cost_ceiling_usd": cost_cfg.get("max_daily_usd"),
            },
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.get("/api/llm/predictive-risk")
async def get_llm_predictive_risk(limit: int = 100, _=Depends(verify_token)):
    """Predictive risk snapshot based on recent alert severity trend and LLM failure pressure."""
    from api._state import get_predictive_risk_snapshot
    return get_predictive_risk_snapshot(limit=limit)


async def _probe_provider_live(provider_name: str, llm_manager) -> dict:
    """Actively probe provider health with a lightweight test request."""
    test_alert = {
        "output": "LLM health probe event",
        "rule": "llm-health-probe",
        "priority": "Notice",
        "time": str(time.time()),
        "output_fields": {"container.name": "ids-api", "probe": "true"},
    }
    started = time.perf_counter()
    try:
        res = await asyncio.wait_for(llm_manager.analyze(test_alert, preferred_engine=provider_name), timeout=8.0)
        latency_ms = int((time.perf_counter() - started) * 1000)
        if res.get("status") == "success":
            return {"status": "operational", "latency_ms": latency_ms, "error": None}
        return {"status": "error", "latency_ms": latency_ms, "error": res.get("error", "probe failed")}
    except Exception as exc:
        return {
            "status": "error",
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "error": str(exc),
        }


@router.get("/api/llm/control/status")
async def llm_control_status(probe: bool = False):
    """LLM Control Center status with optional live health probes."""
    from api._state import (
        get_llm_forced_provider,
        llm_last_provider_ts,
        llm_last_provider_used,
    )

    llm_manager, _, _ = _deps()
    diagnostics = await _build_llm_diagnostics()
    forced_provider = get_llm_forced_provider()
    live_probe = {}
    manager_status = llm_manager.get_status() if llm_manager else {}
    configured_providers = manager_status.get("providers", [])

    if llm_manager and hasattr(llm_manager, "get_priority_order"):
        runtime_priority = llm_manager.get_priority_order() or []
    else:
        runtime_priority = [p.strip() for p in Config.LLM_PRIORITY.split(",") if p.strip()]

    if not runtime_priority:
        runtime_priority = configured_providers[:]

    if llm_manager and probe:
        for provider_name in configured_providers:
            live_probe[provider_name] = await _probe_provider_live(provider_name, llm_manager)

    credits = {}
    try:
        from llm_credit_checker import credit_checker
        cred_info = await credit_checker.check_all_providers()
        credits = {name: info.to_dict() for name, info in cred_info.items()}
    except Exception:
        credits = {}

    provider_names = sorted(diagnostics.keys())
    selectable_providers = [p for p in runtime_priority if p in configured_providers]
    active_provider = forced_provider if forced_provider in configured_providers else llm_last_provider_used
    effective_provider = active_provider or (selectable_providers[0] if selectable_providers else None)
    active_provider = active_provider or effective_provider

    active_stats = {}
    try:
        stats = await export_llm_stats()
        active_stats = (stats.get("engines", {}) or {}).get(active_provider or "", {})
    except Exception:
        active_stats = {}

    return {
        "providers": diagnostics,
        "provider_names": provider_names,
        "active_provider": active_provider,
        "effective_provider": effective_provider,
        "active_provider_details": {
            "provider": active_provider,
            "p95_latency_s": active_stats.get("p95_latency_s"),
            "success_rate": active_stats.get("success_rate"),
            "total_requests": active_stats.get("total_requests", 0),
        },
        "active_provider_last_seen": llm_last_provider_ts,
        "forced_provider": forced_provider,
        "configured_providers": configured_providers,
        "selectable_providers": selectable_providers,
        "live_probe": live_probe,
        "credits": credits,
        "fallback_chain": runtime_priority,
    }


@router.post("/api/llm/control/force")
async def set_forced_provider(payload: ForceProviderPayload, _=Depends(verify_token)):
    """Force a provider for analysis pipeline; null clears to auto-failover."""
    from api._state import set_llm_forced_provider

    llm_manager, _, _ = _deps()
    provider = (payload.provider or "").strip() or None
    available_providers = []
    if llm_manager:
        if hasattr(llm_manager, "get_available_providers"):
            available_providers = llm_manager.get_available_providers()
        elif hasattr(llm_manager, "get_available_engines"):
            available_providers = llm_manager.get_available_engines()
        elif hasattr(llm_manager, "get_status"):
            available_providers = llm_manager.get_status().get("providers", [])

    if provider and (not llm_manager or provider not in available_providers):
        return {"status": "error", "message": f"Unknown provider: {provider}"}

    current = set_llm_forced_provider(provider)
    return {
        "status": "ok",
        "forced_provider": current,
        "mode": "forced" if current else "auto-failover",
    }


@router.post("/api/llm/control/priority")
async def set_provider_priority(payload: PriorityPayload, _=Depends(verify_token)):
    """Update runtime provider priority order for alert analysis failover chain."""
    llm_manager, _, _ = _deps()
    if not llm_manager:
        return {"status": "error", "message": "LLM manager unavailable"}

    if not hasattr(llm_manager, "set_priority_order"):
        return {"status": "error", "message": "Runtime priority control is not supported by this manager"}

    requested: list[str] = []
    if payload.providers:
        requested.extend(payload.providers)
    if payload.order:
        requested.extend([part.strip() for part in payload.order.split(",") if part.strip()])

    if not requested:
        return {"status": "error", "message": "Provide providers list or comma-separated order"}

    updated_chain = llm_manager.set_priority_order(requested)

    manager_status = llm_manager.get_status() if hasattr(llm_manager, "get_status") else {}
    configured = manager_status.get("providers", [])
    return {
        "status": "ok",
        "fallback_chain": updated_chain,
        "configured_providers": configured,
        "selectable_providers": [p for p in updated_chain if p in configured],
    }


@router.post("/api/llm/control/test")
async def test_provider(payload: LLMTestPayload, _=Depends(verify_token)):
    """Run a live test prompt against a selected provider or auto routing."""
    llm_manager, _, _ = _deps()
    if not llm_manager:
        return {"status": "error", "message": "LLM manager unavailable"}

    test_alert = {
        "output": payload.prompt,
        "rule": "operator-llm-test",
        "priority": "Notice",
        "time": str(time.time()),
        "output_fields": {"container.name": "ids-api", "interactive_test": "true"},
    }
    started = time.perf_counter()
    result = await llm_manager.analyze(test_alert, preferred_engine=payload.provider)
    latency_ms = int((time.perf_counter() - started) * 1000)
    return {
        "status": result.get("status", "unknown"),
        "provider": result.get("provider") or result.get("engine"),
        "latency_ms": latency_ms,
        "analysis": result.get("analysis"),
        "error": result.get("error"),
        "failed_engines": result.get("failed_engines", []),
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
