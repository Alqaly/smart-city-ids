"""Shared mutable application state.

All routers import state from here. Main.py sets values at startup via
``init()``.  This avoids circular imports while still giving routers
access to singletons like ``llm_manager``, ``db``, and ``k8s_automation``.
"""

from __future__ import annotations

import asyncio
import json as json_mod
import logging
import time
from collections import OrderedDict
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from config import Config

logger = logging.getLogger(__name__)

# ─── Globals (set by init()) ─────────────────────────────────────────────────
llm_manager: Any = None
k8s_automation: Any = None
alert_cache: Any = None
rate_limiter: Any = None
circuit_breaker: Any = None
request_queue: Any = None
deduplicator: Any = None
alert_rate_limiter: Any = None
db: Any = None
operator_interface: Any = None
STATIC_DIR: Optional[str] = None

# In-memory caches
alerts_db: List[Dict[str, Any]] = []
metrics_dict: Dict[str, Any] = {
    "total_alerts": 0,
    "critical_alerts": 0,
    "alerts_by_source": {"falco": 0, "suricata": 0},
    "automated_actions": 0,
    "started_at": datetime.now().isoformat(),
    "uptime_seconds": 0,
    "automation_rate": 0,
    "alert_reduction_percentage": 100,
    "avg_response_time_seconds": 3.5,
}

alert_fatigue_stats: Dict[str, int] = {
    "raw_total": 0,
    "after_dedup_total": 0,
    "llm_triaged_total": 0,
    "human_review_required_total": 0,
    "auto_handled_total": 0,
}

# IoT device registry
iot_devices: Dict[str, Dict[str, Any]] = {}
iot_events: List[Dict[str, Any]] = []

# SSE live-event clients
sse_clients: list = []  # list[asyncio.Queue]

# Per-provider LLM stats for /api/llm-stats/export
LLM_COST_PER_CALL = {
    "xai": 0.006,
    "openai": 0.005,
    "anthropic": 0.008,
    "gemini": 0.001,
    "kimi": 0.003,
    "local": 0.0,
}
llm_provider_stats: Dict[str, Dict] = {}


# ─── Init function — called once from main.py ──────────────────────────────
def init(
    *,
    _llm_manager=None,
    _k8s_automation=None,
    _alert_cache=None,
    _rate_limiter=None,
    _circuit_breaker=None,
    _request_queue=None,
    _deduplicator=None,
    _alert_rate_limiter=None,
    _db=None,
    _operator_interface=None,
    _static_dir=None,
):
    """Populate module-level globals so routers can import them."""
    global llm_manager, k8s_automation, alert_cache, rate_limiter
    global circuit_breaker, request_queue, deduplicator, alert_rate_limiter
    global db, operator_interface, STATIC_DIR

    llm_manager = _llm_manager
    k8s_automation = _k8s_automation
    alert_cache = _alert_cache
    rate_limiter = _rate_limiter
    circuit_breaker = _circuit_breaker
    request_queue = _request_queue
    deduplicator = _deduplicator
    alert_rate_limiter = _alert_rate_limiter
    db = _db
    operator_interface = _operator_interface
    STATIC_DIR = _static_dir


# ─── Helper functions (used by multiple routers) ────────────────────────────

async def sse_broadcast(event: dict):
    """Push an event to all connected SSE clients."""
    dead = []
    for q in sse_clients:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        sse_clients.remove(q)


def classify_llm_error(error_msg: str) -> str:
    """Classify an LLM error into a human-readable diagnostic reason."""
    if not error_msg:
        return "Unknown error"
    msg = error_msg.lower()
    if "invalid api key" in msg or "incorrect api key" in msg or "api error 401" in msg:
        return "Invalid API key — check your key is correct and not expired"
    if "unauthorized" in msg or "authentication" in msg or "api error 403" in msg:
        return "Authentication failed — API key rejected by provider"
    if "insufficient_quota" in msg or "quota" in msg or "api error 429" in msg:
        return "Insufficient credits / quota exceeded — add billing or wait for reset"
    if "resource has been exhausted" in msg or "used all available credits" in msg:
        return "Credits exhausted — provider account has no remaining balance"
    if "monthly spending limit" in msg:
        return "Monthly spending limit reached — increase limit in provider settings"
    if "exhausted" in msg:
        return "Resource exhausted — provider capacity limit reached"
    if "timeout" in msg:
        return "Request timeout — provider too slow or network issue"
    if "connection" in msg or "connect" in msg:
        return "Connection failed — network error or provider is down"
    if "rate limit" in msg or "rate_limit" in msg:
        return "Rate limited — too many requests, will retry after cooldown"
    if "model not found" in msg or "model_not_found" in msg:
        return "Model not found — configured model is unavailable on this provider"
    if "api error" in msg:
        return f"API error — {error_msg}"
    if "cooldown" in msg:
        return error_msg
    return f"Error: {error_msg}"


def is_protected_service(container_name: str) -> bool:
    """Check if a service is protected from automated actions."""
    if not container_name:
        return False
    for protected in Config.PROTECTED_SERVICES:
        if protected.lower() in container_name.lower():
            return True
    return False


def can_execute_action(action: str, container_name: str) -> tuple:
    """Check if an automated action can be executed based on safety controls."""
    if Config.AUTOMATION_MODE == "dry-run":
        return False, f"DRY-RUN: Would execute {action} on {container_name}"
    if Config.AUTOMATION_MODE == "approval-required":
        return False, f"APPROVAL-REQUIRED: {action} on {container_name} needs manual approval"
    if is_protected_service(container_name):
        return False, f"BLOCKED: {container_name} is a protected service"
    return True, "OK"


def classify_decision_outcome(severity: int) -> str:
    """Map severity score to LLM decision outcome label."""
    if severity >= 8:
        return "malicious"
    if severity >= 5:
        return "suspicious"
    return "benign"


def alert_trace_id(alert_id) -> str:
    return f"alert-{alert_id}"


def detect_alert_source(alert) -> str:
    """Determine alert source using robust fields."""
    rule = (alert.rule or "").lower()
    output = (alert.output or "").lower()
    fields = alert.output_fields or {}
    container = str(fields.get("container.name", "")).lower()
    event_type = str(fields.get("event_type", "")).lower()
    if (
        "suricata" in rule
        or "suricata" in output
        or "suricata" in container
        or event_type == "alert"
    ):
        return "suricata"
    return "falco"


def compute_human_review_required(severity: int) -> bool:
    """Approximate analyst-touch requirement from governance mode."""
    from governance import get_automation_mode
    import os

    mode = get_automation_mode()
    threshold = int(os.getenv("ASSISTED_THRESHOLD", "8"))
    if mode == "manual":
        return True
    if mode == "autopilot":
        return False
    return severity >= threshold


def set_automation_mode_metric(mode: str):
    """Set automation mode gauge with normalized labels."""
    from infrastructure.metrics import PROM_AUTOMATION_MODE

    for label in ("autopilot", "assisted", "manual"):
        PROM_AUTOMATION_MODE.labels(mode=label).set(1 if label == mode else 0)


def update_circuit_breaker_metrics():
    """Update Prometheus metrics for circuit breaker states."""
    from infrastructure.metrics import PROM_CIRCUIT_BREAKER_STATE

    state_map = {"closed": 0, "half_open": 1, "open": 2, "unconfigured": 3}
    configured = set(circuit_breaker.engine_stats.keys()) if circuit_breaker else set()
    all_engines = ["xai", "anthropic", "openai", "gemini", "kimi"]
    for engine in all_engines:
        if engine in configured:
            stats = circuit_breaker.engine_stats.get(engine, {})
            state_val = state_map.get(stats.get("state", "closed"), 0)
        else:
            state_val = state_map["unconfigured"]
        PROM_CIRCUIT_BREAKER_STATE.labels(engine=engine).set(state_val)


# IoT metric cache
_iot_metric_cache = {"value": 0, "last_refresh": 0.0}


def refresh_iot_active_metric() -> int:
    """Count real IoT pods via K8s API (cached 120s)."""
    from infrastructure.metrics import PROM_IOT_DEVICES_ACTIVE

    now = time.time()
    if now - _iot_metric_cache["last_refresh"] < 120:
        return _iot_metric_cache["value"]

    k8s_count = 0
    if k8s_automation:
        try:
            pod_list = k8s_automation.core_v1.list_namespaced_pod(
                namespace="smart-city", timeout_seconds=5
            )
            iot_prefixes = [
                "traffic-camera", "healthcare-api", "parking-system",
                "iot-devices-enhanced", "iot-device-high",
                "iot-device-medium", "iot-device-burst", "mqtt-broker",
                "env-sensor", "street-lighting", "iot-simulator",
            ]
            for p in pod_list.items:
                name = p.metadata.name
                phase = (p.status.phase or "").lower()
                if phase == "running" and any(name.startswith(pfx) for pfx in iot_prefixes):
                    k8s_count += 1
        except Exception:
            pass

    db_count = db.get_iot_device_count() if db else 0
    mem_count = len(iot_devices)
    active_count = max(k8s_count, db_count, mem_count)
    PROM_IOT_DEVICES_ACTIVE.set(active_count)
    _iot_metric_cache["value"] = active_count
    _iot_metric_cache["last_refresh"] = now
    return active_count


def _estimate_tokens(payload: Any) -> int:
    """Estimate tokens with a conservative chars/4 heuristic."""
    try:
        text = payload if isinstance(payload, str) else json_mod.dumps(payload, ensure_ascii=False)
    except Exception:
        text = str(payload)
    return max(1, int(len(text) / 4))


def record_llm_call(engine: str, latency_s: float, success: bool):
    """Track per-provider stats for latency histograms and cost."""
    from infrastructure.metrics import PROM_LLM_COST_USD

    s = llm_provider_stats.setdefault(engine, {
        "total_requests": 0, "successes": 0, "failures": 0,
        "latencies": [], "total_cost_usd": 0.0,
    })
    s["total_requests"] += 1
    if success:
        s["successes"] += 1
        s["latencies"].append(latency_s)
        if len(s["latencies"]) > 500:
            s["latencies"] = s["latencies"][-500:]
        cost = LLM_COST_PER_CALL.get(engine, 0.005)
        s["total_cost_usd"] += cost
        PROM_LLM_COST_USD.labels(engine=engine).inc(cost)
    else:
        s["failures"] += 1


def record_llm_tokens(engine: str, prompt_payload: Any, completion_payload: Any):
    """Track estimated prompt/completion tokens for observability."""
    from infrastructure.metrics import PROM_LLM_TOKENS_TOTAL

    prompt_tokens = _estimate_tokens(prompt_payload)
    completion_tokens = _estimate_tokens(completion_payload)
    PROM_LLM_TOKENS_TOTAL.labels(engine=engine, kind="prompt").inc(prompt_tokens)
    PROM_LLM_TOKENS_TOTAL.labels(engine=engine, kind="completion").inc(completion_tokens)
    s = llm_provider_stats.setdefault(engine, {
        "total_requests": 0, "successes": 0, "failures": 0,
        "latencies": [], "total_cost_usd": 0.0,
        "prompt_tokens": 0, "completion_tokens": 0,
    })
    s["prompt_tokens"] = s.get("prompt_tokens", 0) + prompt_tokens
    s["completion_tokens"] = s.get("completion_tokens", 0) + completion_tokens


async def analyze_with_fallback(alert_dict: dict) -> tuple:
    """Analyze alert using unified LLM Manager with caching."""
    from infrastructure.metrics import (
        PROM_LLM_CACHE_OPERATIONS,
        PROM_LLM_CACHE_SIZE,
        PROM_LLM_REQUESTS_TOTAL,
        PROM_LLM_LATENCY_SECONDS,
    )

    cached = alert_cache.get(alert_dict)
    if cached:
        PROM_LLM_CACHE_OPERATIONS.labels(operation="hit").inc()
        PROM_LLM_CACHE_SIZE.set(len(alert_cache.cache))
        return cached, "cache", 0.0

    PROM_LLM_CACHE_OPERATIONS.labels(operation="miss").inc()

    llm_start = time.perf_counter()
    result = await llm_manager.analyze(alert_dict)
    llm_duration = time.perf_counter() - llm_start

    engine_used = result.get("provider") or result.get("engine", "unknown")
    failed_engines = result.get("failed_engines", [])

    if result.get("status") == "success":
        for failed_engine in failed_engines:
            if failed_engine in circuit_breaker.engine_stats:
                circuit_breaker.record_failure(failed_engine)
        if engine_used in circuit_breaker.engine_stats:
            circuit_breaker.record_success(engine_used)
        update_circuit_breaker_metrics()

        analysis = result.get("analysis", {})
        alert_cache.set(alert_dict, analysis)
        PROM_LLM_CACHE_SIZE.set(len(alert_cache.cache))
        PROM_LLM_REQUESTS_TOTAL.labels(engine=engine_used, result="success").inc()
        PROM_LLM_LATENCY_SECONDS.labels(engine=engine_used).observe(llm_duration)
        record_llm_tokens(engine_used, alert_dict, analysis)
        record_llm_call(engine_used, llm_duration, True)
        return analysis, engine_used, llm_duration

    error_msg = result.get("error", "Unknown error")
    for failed_engine in failed_engines:
        if failed_engine in circuit_breaker.engine_stats:
            circuit_breaker.record_failure(failed_engine)
    if engine_used in circuit_breaker.engine_stats:
        circuit_breaker.record_failure(engine_used)
    update_circuit_breaker_metrics()
    PROM_LLM_REQUESTS_TOTAL.labels(engine=engine_used, result="error").inc()
    record_llm_call(engine_used, llm_duration, False)
    raise Exception(f"LLM analysis failed: {error_msg}")
