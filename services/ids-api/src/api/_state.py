"""Shared mutable application state for the Smart City IDS API.

This module acts as a **centralised state registry** for the entire FastAPI
application.  It follows the "module-as-singleton" pattern: every router
(alerts, IoT, LLM stats, operator, etc.) imports the globals it needs
directly from ``api._state``, and those globals are populated exactly once
during application startup by ``main.py`` calling :func:`init`.

Why a dedicated state module?
    FastAPI routers are defined in separate files, and many of them need
    access to the same heavyweight objects (the LLM manager, the Kubernetes
    automation client, the database handle, etc.).  Passing these through
    dependency-injection or app-state would work but creates tight coupling
    to the framework.  Using a plain Python module avoids circular-import
    problems — ``main.py`` imports ``_state`` and writes to it, routers
    import ``_state`` and read from it, but neither imports the other.

In addition to hosting singleton references, the module provides a
collection of **shared helper functions** that are used by multiple routers
(SSE broadcast, LLM error classification, safety-gate checks, metric
bookkeeping, etc.).  Keeping these here rather than in the routers
eliminates code duplication and keeps the router modules focused on
HTTP-layer concerns.

Architectural note (academic context):
    This module is a key element of the *separation-of-concerns* design
    described in the capstone report.  The dependency graph is strictly:

        main.py  ──writes──►  _state  ◄──reads──  routers/*

    No router ever writes to the singleton slots, and ``main.py`` never
    reads back from them after init.  This one-directional data flow makes
    the system easier to reason about, test (mocks can be injected via
    ``init()``), and extend with new routers.

Typical lifecycle:
    1. ``main.py`` creates concrete instances (LLMManager, K8sAutomation,
       DatabaseManager, …).
    2. ``main.py`` calls ``_state.init(…)`` with those instances.
    3. Each router file does ``from api._state import llm_manager, db, …``
       and uses the objects during request handling.
"""

from __future__ import annotations

import asyncio
import hashlib
import json as json_mod      # Aliased to avoid shadowing if a local var is named ``json``
import logging
import os
import time
from collections import OrderedDict, deque  # Available for LRU-style caches elsewhere
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional, Union

from config import Config  # Project-level configuration (thresholds, modes, protected services)

# Module-level logger — all log messages from helpers in this file are tagged
# with the ``api._state`` logger name, making them easy to filter in
# structured-logging pipelines or Grafana/Loki dashboards.
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — Singleton references (set once by ``init()``)
# ═══════════════════════════════════════════════════════════════════════════════
# These module-level variables start as ``None`` and are assigned concrete
# objects during application startup.  Using ``Any`` as the type annotation
# is intentional — it avoids importing the heavy implementation classes at
# module-load time, which would re-introduce the circular imports this
# module exists to prevent.
#
# Each variable maps to a well-known subsystem:
#   llm_manager       — orchestrates multi-provider LLM analysis (xAI, OpenAI, …)
#   k8s_automation    — executes Kubernetes remediation actions (isolate, scale, …)
#   alert_cache       — LRU cache that deduplicates identical alert payloads
#   rate_limiter      — global API rate limiter (protects the /api/* endpoints)
#   circuit_breaker   — per-engine circuit breaker (prevents cascading LLM failures)
#   request_queue     — bounded async queue for back-pressure on alert ingestion
#   deduplicator      — content-hash based deduplication for incoming alerts
#   alert_rate_limiter — secondary rate limiter scoped to the alert endpoint
#   db                — async database handle (PostgreSQL via asyncpg)
#   operator_interface — human-in-the-loop (HITL) approval/notification manager
#   STATIC_DIR        — filesystem path to the built front-end assets (if any)
# ───────────────────────────────────────────────────────────────────────────────

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


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — In-memory caches and counters
# ═══════════════════════════════════════════════════════════════════════════════
# These data structures accumulate operational statistics entirely in memory.
# They are exposed through the ``/api/metrics`` and ``/api/status`` endpoints
# so the operator dashboard and Prometheus scraper can visualise system health.
# Because they live in process memory, they reset on every restart; persistent
# storage is handled by the ``db`` object above.
# ───────────────────────────────────────────────────────────────────────────────

# ``alerts_db`` — full list of processed alert records kept in RAM.
# Each entry is a dict that mirrors the database row shape, allowing the
# ``/api/alerts/history`` endpoint to serve results without a DB round-trip
# for small deployments.
alerts_db: List[Dict[str, Any]] = []
MAX_ALERTS_MEMORY = max(100, int(os.getenv("MAX_ALERTS_MEMORY", "10000")))


def append_alert_memory(alert_record: Dict[str, Any]) -> None:
    """Append alert to in-memory cache with bounded growth.

    This cache is only for fast dashboard/API reads. Durable history remains in DB.
    """
    alerts_db.append(alert_record)
    overflow = len(alerts_db) - MAX_ALERTS_MEMORY
    if overflow > 0:
        del alerts_db[:overflow]

# ``metrics_dict`` — aggregate counters shown on the operator dashboard.
# ``started_at`` is captured at module-load time so uptime can be derived.
# ``avg_response_time_seconds`` is seeded with a reasonable default (3.5 s)
# and updated as real alerts are processed.
metrics_dict: Dict[str, Any] = {
    "total_alerts": 0,                  # Cumulative alerts received since startup
    "critical_alerts": 0,               # Subset with severity >= 8
    "alerts_by_source": {               # Breakdown by originating security tool
        "falco": 0,                     #   Falco  — runtime syscall-level alerts
        "suricata": 0,                  #   Suricata — network-level IDS alerts
    },
    "automated_actions": 0,             # How many K8s actions were auto-executed
    "started_at": datetime.now().isoformat(),  # ISO-8601 boot timestamp
    "uptime_seconds": 0,               # Recomputed on each metrics read
    "automation_rate": 0,               # Fraction of alerts that triggered automation
    "alert_reduction_percentage": 100,  # Dedup effectiveness (100 = no duplicates yet)
    "avg_response_time_seconds": 3.5,   # Rolling average end-to-end response time
}

# ``alert_fatigue_stats`` — tracks how effectively the pipeline reduces
# operator workload (a key metric in the capstone evaluation).
# The flow is:  raw → deduplicated → LLM-triaged → auto-handled | human-review.
alert_fatigue_stats: Dict[str, int] = {
    "raw_total": 0,                    # Total raw alerts received before any filtering
    "after_dedup_total": 0,            # Remaining after content-hash deduplication
    "llm_triaged_total": 0,            # Successfully analysed by the LLM engine
    "human_review_required_total": 0,  # Escalated to an operator for manual review
    "auto_handled_total": 0,           # Fully automated (no human intervention needed)
}


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — IoT device registry
# ═══════════════════════════════════════════════════════════════════════════════
# The IDS monitors IoT devices deployed in the smart-city K8s cluster.
# ``iot_devices`` maps device-id → metadata dict (type, status, last-seen).
# ``iot_events``  stores recent telemetry/lifecycle events from IoT pods.
# Both are populated by the IoT router when devices register or send heartbeats.
# ───────────────────────────────────────────────────────────────────────────────

iot_devices: Dict[str, Dict[str, Any]] = {}
iot_events: List[Dict[str, Any]] = []


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — Server-Sent Events (SSE) client registry
# ═══════════════════════════════════════════════════════════════════════════════
# Each connected SSE client is represented by an ``asyncio.Queue``.  When a
# new alert or action occurs, ``sse_broadcast()`` pushes the event into every
# queue.  The SSE endpoint generator yields items from its own queue.
# This provides real-time push updates to the operator dashboard without
# polling.
# ───────────────────────────────────────────────────────────────────────────────

sse_clients: list = []  # list[asyncio.Queue]

# Enterprise audit/event timeline (in-memory ring buffer).
audit_events: Deque[Dict[str, Any]] = deque(maxlen=5000)
llm_retry_queue: Deque[Dict[str, Any]] = deque(maxlen=10000)

# LLM runtime control knobs/state.
llm_forced_provider: Optional[str] = None
llm_last_provider_used: Optional[str] = None
llm_last_provider_ts: Optional[str] = None
llm_routing_mode: str = os.getenv("LLM_ROUTING_MODE", "priority").strip().lower() or "priority"
llm_routing_cost_ceiling_usd: float = float(os.getenv("LLM_ROUTING_COST_CEILING_USD", "0.005"))
llm_ab_config: Dict[str, Any] = {
    "enabled": False,
    "provider_a": "xai",
    "provider_b": "openai",
    "split_percent_a": 50,
    "salt": os.getenv("LLM_AB_SALT", "smart-city-ids-ab"),
}
llm_routing_decisions: Deque[Dict[str, Any]] = deque(maxlen=500)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — LLM provider cost model and per-provider statistics
# ═══════════════════════════════════════════════════════════════════════════════
# ``LLM_COST_PER_CALL`` stores the *estimated* USD cost per single LLM API
# call for each supported provider.  These are rough averages used for the
# cost-tracking dashboard; they do not reflect exact token-based billing.
# ``llm_provider_stats`` accumulates runtime metrics (request counts,
# latency samples, cumulative cost) per engine, powering the
# ``/api/llm-stats/export`` endpoint.
# ───────────────────────────────────────────────────────────────────────────────

LLM_COST_PER_CALL = {
    "xai": 0.006,       # xAI Grok-4 — slightly higher due to larger context window
    "openai": 0.005,    # OpenAI GPT-4o-mini baseline
    "anthropic": 0.008, # Anthropic Claude — highest per-call estimate
    "gemini": 0.001,    # Google Gemini — lowest commercial cost
    "kimi": 0.003,      # Moonshot Kimi — mid-range
}

LLM_COST_PER_1K_TOKENS = {
    "xai": 0.012,
    "openai": 0.010,
    "anthropic": 0.016,
    "gemini": 0.002,
    "kimi": 0.006,
}


def _is_trackable_engine(engine: str) -> bool:
    normalized = str(engine or "").strip().lower()
    if not normalized:
        return False
    if normalized in {"unknown", "none", "cache", "n/a", "null"}:
        return False
    return normalized in {"xai", "openai", "anthropic", "gemini", "kimi", "custom"}


def _estimate_cost_from_tokens(engine: str, prompt_tokens: int, completion_tokens: int) -> float:
    total_tokens = max(0, int(prompt_tokens or 0)) + max(0, int(completion_tokens or 0))
    if total_tokens <= 0:
        return 0.0
    rate_per_1k = float(LLM_COST_PER_1K_TOKENS.get(engine, 0.0))
    return round((total_tokens / 1000.0) * rate_per_1k, 8)

# Populated lazily by ``record_llm_call()`` — keys are engine names, values
# are dicts with ``total_requests``, ``successes``, ``failures``,
# ``latencies`` (list, capped at 500 samples), and ``total_cost_usd``.
llm_provider_stats: Dict[str, Dict] = {}


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — Initialisation function
# ═══════════════════════════════════════════════════════════════════════════════


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
    """Populate module-level singleton globals so that routers can import them.

    This function is called **exactly once** during FastAPI application
    startup (inside ``main.py``'s ``lifespan`` context manager).  All
    parameters are keyword-only (enforced by the bare ``*``) to prevent
    accidental positional mis-ordering when the argument list is long.

    Parameters
    ----------
    _llm_manager : LLMManager, optional
        The unified multi-provider LLM analysis orchestrator.
    _k8s_automation : K8sAutomation, optional
        Client for executing Kubernetes remediation actions (pod isolation,
        service scaling, etc.).
    _alert_cache : AlertCache, optional
        LRU cache that maps alert content-hashes to previous LLM results,
        avoiding redundant API calls for duplicate alerts.
    _rate_limiter : RateLimiter, optional
        Global token-bucket rate limiter protecting all ``/api/*`` routes.
    _circuit_breaker : CircuitBreaker, optional
        Per-engine circuit breaker that opens after repeated LLM failures,
        preventing cascading timeouts across providers.
    _request_queue : asyncio.Queue, optional
        Bounded async queue providing back-pressure on alert ingestion
        when the LLM pipeline is saturated.
    _deduplicator : Deduplicator, optional
        Content-hash based deduplication filter for incoming alerts.
    _alert_rate_limiter : RateLimiter, optional
        Secondary rate limiter scoped specifically to the alert-ingestion
        endpoint (``POST /api/alerts``).
    _db : DatabaseManager, optional
        Async PostgreSQL database handle for persistent alert and metric
        storage.
    _operator_interface : OperatorInterface, optional
        Human-in-the-loop (HITL) manager that queues actions requiring
        manual operator approval before execution.
    _static_dir : str, optional
        Absolute filesystem path to the directory containing built
        front-end static assets served by the dashboard route.

    Notes
    -----
    After ``init()`` returns, every module that has already imported these
    names will see the updated values because Python module-level variables
    are shared references — the ``global`` statement rebinds the names in
    this module's namespace, and all importers access the same namespace.
    """
    # Declare all globals that will be rebound
    global llm_manager, k8s_automation, alert_cache, rate_limiter
    global circuit_breaker, request_queue, deduplicator, alert_rate_limiter
    global db, operator_interface, STATIC_DIR

    # Assign each singleton from the caller-provided instances
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


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 7 — Helper functions (shared across multiple routers)
# ═══════════════════════════════════════════════════════════════════════════════
# The functions below are intentionally co-located in the state module
# because they depend on the singleton globals above (``circuit_breaker``,
# ``k8s_automation``, ``db``, etc.) and are consumed by more than one router.
# ───────────────────────────────────────────────────────────────────────────────


async def sse_broadcast(event: dict):
    """Push a real-time event to every connected Server-Sent Events client.

    Each SSE client is represented by an ``asyncio.Queue`` stored in the
    module-level ``sse_clients`` list.  This function iterates over all
    queues and attempts a **non-blocking** put.  If a queue is full (i.e.
    the client is consuming events too slowly), the queue is marked as dead
    and removed after iteration to avoid memory leaks.

    Parameters
    ----------
    event : dict
        JSON-serialisable event payload to broadcast.  Typically contains
        keys like ``type`` (e.g. ``"alert"``, ``"action"``), ``data``, and
        ``timestamp``.

    Side Effects
    ------------
    - Enqueues ``event`` into each live client queue.
    - Removes any queues that are full (client presumed disconnected or
      lagging).
    """
    # Collect references to queues that are full so we can remove them
    # *after* iteration (mutating a list while iterating is unsafe).
    dead = []
    for q in sse_clients:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            # Client is not consuming fast enough; mark for removal
            dead.append(q)
    # Clean up stale / slow clients
    for q in dead:
        sse_clients.remove(q)


def set_llm_forced_provider(provider: Optional[str]) -> Optional[str]:
    """Set (or clear) forced LLM provider used by the analysis pipeline."""
    global llm_forced_provider
    llm_forced_provider = provider if provider else None
    return llm_forced_provider


def get_llm_forced_provider() -> Optional[str]:
    """Get currently forced LLM provider, if any."""
    return llm_forced_provider


def get_llm_routing_config() -> Dict[str, Any]:
    """Return current runtime routing strategy configuration."""
    try:
        config = db.get_system_config('llm_cost_ceiling', {
            "max_daily_usd": 10.0,
            "current_daily_usd": 0.0,
            "last_reset": None
        })
        ceiling = config.get("max_daily_usd", llm_routing_cost_ceiling_usd)
    except Exception:
        ceiling = llm_routing_cost_ceiling_usd
        
    return {
        "mode": llm_routing_mode,
        "cost_ceiling_usd": ceiling,
        "ab_test": dict(llm_ab_config),
        "recent_decisions": list(llm_routing_decisions)[-30:],
    }


def update_llm_routing_config(
    *,
    mode: Optional[str] = None,
    cost_ceiling_usd: Optional[float] = None,
    ab_enabled: Optional[bool] = None,
    provider_a: Optional[str] = None,
    provider_b: Optional[str] = None,
    split_percent_a: Optional[int] = None,
):
    """Update runtime routing strategy (A/B and cost-aware modes)."""
    global llm_routing_mode, llm_routing_cost_ceiling_usd

    allowed_modes = {"priority", "cost_optimized", "ab_test", "severity_adaptive"}
    if mode is not None:
        normalized = str(mode).strip().lower()
        if normalized in allowed_modes:
            llm_routing_mode = normalized

    if cost_ceiling_usd is not None:
        llm_routing_cost_ceiling_usd = max(0.0001, float(cost_ceiling_usd))
        try:
            config = db.get_system_config('llm_cost_ceiling', {
                "max_daily_usd": 10.0,
                "current_daily_usd": 0.0,
                "last_reset": None
            })
            config["max_daily_usd"] = llm_routing_cost_ceiling_usd
            db.set_system_config('llm_cost_ceiling', config)
        except Exception as e:
            logger.warning(f"Could not save cost ceiling to DB: {e}")

    if ab_enabled is not None:
        llm_ab_config["enabled"] = bool(ab_enabled)
    if provider_a:
        llm_ab_config["provider_a"] = str(provider_a).strip().lower()
    if provider_b:
        llm_ab_config["provider_b"] = str(provider_b).strip().lower()
    if split_percent_a is not None:
        llm_ab_config["split_percent_a"] = max(0, min(100, int(split_percent_a)))

    return get_llm_routing_config()


def set_llm_last_provider_used(provider: Optional[str]) -> None:
    """Track last provider (or fallback engine) used for analysis."""
    global llm_last_provider_used, llm_last_provider_ts
    llm_last_provider_used = provider
    llm_last_provider_ts = datetime.now().isoformat()


def _ab_bucket_for_alert(alert_dict: Dict[str, Any]) -> int:
    """Deterministic 0..99 bucket for A/B assignment per alert signature."""
    material = {
        "rule": alert_dict.get("rule"),
        "priority": alert_dict.get("priority"),
        "output": alert_dict.get("output"),
        "container": (alert_dict.get("output_fields") or {}).get("container.name"),
        "salt": llm_ab_config.get("salt", "smart-city-ids-ab"),
    }
    key = json_mod.dumps(material, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100


def _estimate_engine_call_cost(engine: str) -> float:
    return float(LLM_COST_PER_CALL.get(engine, 0.005))


def check_cost_ceiling() -> bool:
    """Check if the daily cost ceiling has been reached."""
    try:
        from infrastructure.metrics import PROM_LLM_BUDGET_REMAINING_USD, PROM_LLM_BUDGET_CEILING_USD
        config = db.get_system_config('llm_cost_ceiling', {
            "max_daily_usd": 10.0,
            "current_daily_usd": 0.0,
            "last_reset": None
        })

        # Reset daily counter if it's a new day
        today = datetime.now().strftime('%Y-%m-%d')
        if config.get("last_reset") != today:
            config["current_daily_usd"] = 0.0
            config["last_reset"] = today
            db.set_system_config('llm_cost_ceiling', config)

        ceiling = float(config.get("max_daily_usd") or 0.0)
        spent = float(config.get("current_daily_usd") or 0.0)

        # Treat ceiling=0 as "no ceiling configured" — use env-based fallback.
        # This prevents a zero-valued DB entry from silently blocking all LLM calls.
        if ceiling <= 0.0:
            ceiling = max(float(os.getenv("LLM_ROUTING_COST_CEILING_USD", "10.0")), 0.01)

        PROM_LLM_BUDGET_CEILING_USD.set(ceiling)
        PROM_LLM_BUDGET_REMAINING_USD.set(max(0.0, ceiling - spent))
        return spent >= ceiling
    except Exception as e:
        logger.warning(f"Error checking cost ceiling: {e}")
        return False


def update_cost_tracking(cost_usd: float):
    """Update the daily cost tracking and Prometheus budget gauges."""
    if cost_usd <= 0:
        return

    try:
        from infrastructure.metrics import PROM_LLM_BUDGET_REMAINING_USD, PROM_LLM_BUDGET_CEILING_USD
        config = db.get_system_config('llm_cost_ceiling', {
            "max_daily_usd": 10.0,
            "current_daily_usd": 0.0,
            "last_reset": None
        })
        
        today = datetime.now().strftime('%Y-%m-%d')
        if config.get("last_reset") != today:
            config["current_daily_usd"] = cost_usd
            config["last_reset"] = today
        else:
            config["current_daily_usd"] = config.get("current_daily_usd", 0.0) + cost_usd

        db.set_system_config('llm_cost_ceiling', config)

        ceiling = float(config.get("max_daily_usd", 10.0))
        spent = float(config.get("current_daily_usd", 0.0))
        PROM_LLM_BUDGET_CEILING_USD.set(ceiling)
        PROM_LLM_BUDGET_REMAINING_USD.set(max(0.0, ceiling - spent))
    except Exception as e:
        logger.warning(f"Error updating cost tracking: {e}")


def select_preferred_provider(alert_dict: Dict[str, Any]) -> Optional[str]:
    """Select preferred provider based on forced override or routing strategy."""
    forced = get_llm_forced_provider()
    if forced:
        llm_routing_decisions.append({
            "ts": datetime.now().isoformat(),
            "mode": "forced",
            "chosen": forced,
            "reason": "forced_provider_override",
        })
        return forced

    if not llm_manager or not hasattr(llm_manager, "get_available_providers"):
        return None

    available = llm_manager.get_available_providers() or []
    if not available:
        return None

    mode = llm_routing_mode
    severity = int((alert_dict or {}).get("severity") or 0)
    chosen: Optional[str] = None
    reason = mode

    if mode == "ab_test" and llm_ab_config.get("enabled"):
        bucket = _ab_bucket_for_alert(alert_dict or {})
        threshold = int(llm_ab_config.get("split_percent_a", 50))
        candidate = llm_ab_config.get("provider_a") if bucket < threshold else llm_ab_config.get("provider_b")
        if candidate in available:
            chosen = candidate
            reason = f"ab_bucket:{bucket}"

    elif mode == "cost_optimized":
        cheap = [p for p in available if _estimate_engine_call_cost(p) <= llm_routing_cost_ceiling_usd]
        pool = cheap or available
        chosen = min(pool, key=_estimate_engine_call_cost)
        reason = f"cost_ceiling:{llm_routing_cost_ceiling_usd}"

    elif mode == "severity_adaptive":
        if severity >= 8:
            premium = [p for p in available if p in ("xai", "anthropic", "openai")]
            chosen = premium[0] if premium else available[0]
            reason = "severity_high_quality"
        else:
            chosen = min(available, key=_estimate_engine_call_cost)
            reason = "severity_cost_efficiency"

    if not chosen:
        chosen = available[0]
        reason = f"{reason}_fallback_priority"

    llm_routing_decisions.append({
        "ts": datetime.now().isoformat(),
        "mode": mode,
        "chosen": chosen,
        "reason": reason,
        "severity": severity,
    })
    return chosen


def get_predictive_risk_snapshot(limit: int = 100) -> Dict[str, Any]:
    """Build lightweight predictive risk indicators from recent alerts and LLM behavior."""
    window = max(20, min(500, int(limit or 100)))
    rows = list(alerts_db)[-window:]
    # After restart, the in-memory alert cache may be empty even though the DB
    # has a long alert history. Fall back to recent persisted alerts so the
    # dashboard risk forecast is available immediately.
    if not rows:
        try:
            recent = db.get_alerts(limit=window)
            if isinstance(recent, list):
                rows = recent
        except Exception:
            rows = []
    severities = [int(r.get("severity", 0) or 0) for r in rows if r.get("severity") is not None]
    if not severities:
        return {
            "risk_score": 0.0,
            "trend": "stable",
            "critical_rate": 0.0,
            "avg_severity": 0.0,
            "recommendation": "Insufficient data",
            "window_size": len(rows),
        }

    avg_severity = sum(severities) / len(severities)
    critical_rate = sum(1 for s in severities if s >= 8) / len(severities)

    mid = max(1, len(severities) // 2)
    older = severities[:mid]
    newer = severities[mid:]
    older_avg = (sum(older) / len(older)) if older else avg_severity
    newer_avg = (sum(newer) / len(newer)) if newer else avg_severity
    delta = newer_avg - older_avg

    if delta >= 1.0:
        trend = "rising"
    elif delta <= -1.0:
        trend = "falling"
    else:
        trend = "stable"

    error_pressure = 0.0
    total_req = 0
    total_fail = 0
    for engine_stats in llm_provider_stats.values():
        total_req += int(engine_stats.get("total_requests", 0))
        total_fail += int(engine_stats.get("failures", 0))
    if total_req > 0:
        error_pressure = total_fail / total_req

    risk_score = min(100.0, max(0.0, (avg_severity * 8.0) + (critical_rate * 30.0) + (error_pressure * 20.0)))
    recommendation = (
        "Switch to assisted/manual review and prioritize high-quality provider"
        if risk_score >= 70
        else "Keep assisted mode with active monitoring" if risk_score >= 45
        else "Current posture acceptable; continue automated handling"
    )

    return {
        "risk_score": round(risk_score, 2),
        "trend": trend,
        "critical_rate": round(critical_rate, 4),
        "avg_severity": round(avg_severity, 3),
        "llm_failure_rate": round(error_pressure, 4),
        "recommendation": recommendation,
        "window_size": len(severities),
    }


def add_audit_event(
    event_type: str,
    *,
    trace_id: Optional[str] = None,
    severity: Optional[int] = None,
    user: Optional[str] = None,
    status: str = "ok",
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Append an event to the in-memory SOC audit timeline."""
    ev = {
        "id": f"ev-{int(time.time() * 1000)}-{len(audit_events)}",
        "timestamp": datetime.now().isoformat(),
        "event_type": event_type,
        "trace_id": trace_id,
        "severity": severity,
        "user": user,
        "status": status,
        "payload": payload or {},
    }
    audit_events.append(ev)
    return ev


def get_audit_events(
    *,
    event_type: Optional[str] = None,
    min_severity: Optional[int] = None,
    user: Optional[str] = None,
    trace_id: Optional[str] = None,
    limit: int = 500,
) -> List[Dict[str, Any]]:
    """Read filtered audit events newest-first."""
    rows = list(audit_events)
    if event_type:
        rows = [r for r in rows if str(r.get("event_type", "")).lower() == event_type.lower()]
    if min_severity is not None:
        rows = [r for r in rows if isinstance(r.get("severity"), int) and r["severity"] >= min_severity]
    if user:
        rows = [r for r in rows if str(r.get("user", "")).lower() == user.lower()]
    if trace_id:
        rows = [r for r in rows if r.get("trace_id") == trace_id]
    rows.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
    return rows[: max(1, min(limit, 5000))]


def classify_llm_error(error_msg: str) -> str:
    """Classify a raw LLM error string into a human-readable diagnostic reason.

    The multi-provider LLM pipeline can surface errors from five or more
    different API providers, each with its own error format.  This function
    normalises those into consistent, actionable messages that appear on the
    operator dashboard and in structured logs.

    The classification order matters — more specific patterns (e.g.
    ``"invalid api key"``) are tested before broad catch-alls (e.g.
    ``"api error"``).

    Parameters
    ----------
    error_msg : str
        The raw error message string returned by the LLM engine or HTTP
        client.

    Returns
    -------
    str
        A human-readable diagnostic string suitable for display in the
        operator UI or inclusion in a log record.
    """
    if not error_msg:
        return "Unknown error"

    # Case-insensitive matching against known error patterns
    msg = error_msg.lower()

    # --- Authentication / authorisation errors ---
    if "invalid api key" in msg or "incorrect api key" in msg or "api error 401" in msg:
        return "Invalid API key — check your key is correct and not expired"
    if "unauthorized" in msg or "authentication" in msg or "api error 403" in msg:
        return "Authentication failed — API key rejected by provider"

    # --- Quota / billing errors ---
    if "insufficient_quota" in msg or "quota" in msg or "api error 429" in msg:
        return "Insufficient credits / quota exceeded — add billing or wait for reset"
    if "resource has been exhausted" in msg or "used all available credits" in msg:
        return "Credits exhausted — provider account has no remaining balance"
    if "monthly spending limit" in msg:
        return "Monthly spending limit reached — increase limit in provider settings"
    if "exhausted" in msg:
        return "Resource exhausted — provider capacity limit reached"

    # --- Connectivity / timeout errors ---
    if "timeout" in msg:
        return "Request timeout — provider too slow or network issue"
    if "connection" in msg or "connect" in msg:
        return "Connection failed — network error or provider is down"

    # --- Rate-limiting (distinct from quota exhaustion) ---
    if "rate limit" in msg or "rate_limit" in msg:
        return "Rate limited — too many requests, will retry after cooldown"

    # --- Model availability ---
    if "model not found" in msg or "model_not_found" in msg:
        return "Model not found — configured model is unavailable on this provider"

    # --- Generic API errors ---
    if "api error" in msg:
        return f"API error — {error_msg}"

    # --- Circuit-breaker cooldown (internal) ---
    if "cooldown" in msg:
        return error_msg

    # Fallback — echo the original message with a prefix
    return f"Error: {error_msg}"


def is_protected_service(container_name: str) -> bool:
    """Check whether a Kubernetes service is on the protected-services list.

    Protected services (defined in ``Config.PROTECTED_SERVICES``) are
    critical infrastructure components that must **never** be automatically
    isolated or restarted by the IDS, regardless of alert severity.
    Examples include the IDS API itself, the database, and monitoring
    stack components.

    The check is case-insensitive and uses substring matching so that
    partial container names (e.g. ``"ids-api-6f8b9"`` matching ``"ids-api"``)
    are correctly caught.

    Parameters
    ----------
    container_name : str
        The ``container.name`` value extracted from the alert's
        ``output_fields``.

    Returns
    -------
    bool
        ``True`` if the container belongs to a protected service and should
        **not** be subject to automated remediation actions.
    """
    if not container_name:
        return False
    configured = [str(s).strip().lower() for s in getattr(Config, "PROTECTED_SERVICES", []) if str(s).strip()]
    # Keep a safety baseline so test/runtime behavior does not depend on
    # accidental mutation of Config.PROTECTED_SERVICES.
    baseline = ["healthcare-api", "ids-api", "postgres"]
    protected_services = list(dict.fromkeys(configured + baseline))

    # Iterate over the protected service name prefixes
    for protected in protected_services:
        if protected.lower() in container_name.lower():
            return True
    return False


def can_execute_action(
    action: str,
    container_name: str,
    severity: Optional[int] = None,
    confidence: Optional[float] = None,
) -> tuple:
    """Determine whether an automated remediation action is permitted.

    This function implements the **safety-gate logic** that sits between the
    LLM's recommendation and actual Kubernetes execution.  Three levels of
    control are evaluated in order:

    1. **SOAR mode policy** — autonomous / assisted / manual / emergency.
    2. **Protected-service check** — for non-emergency modes.

    Parameters
    ----------
    action : str
        The action verb (e.g. ``"isolate_pod"``, ``"scale_up"``).
    container_name : str
        The target container / service name.

    Returns
    -------
    tuple[bool, str]
        A 2-tuple of ``(allowed, reason)``.  ``allowed`` is ``True`` only
        when the action may proceed; ``reason`` provides an explanation
        suitable for logging and dashboard display.
    """
    # Check global automation mode from project configuration
    sev = int(severity or 0)
    conf = float(confidence or 0.0)
    raw_mode = str(Config.AUTOMATION_MODE or "assisted").strip().lower()
    mode = raw_mode

    # Import governance controller to update metrics
    try:
        from governance import governance
    except Exception:
        governance = None

    # Backward-compatible mode aliases
    if mode in {"live", "autopilot"}:
        mode = "autonomous"
    elif mode in {"dry-run", "approval-required"}:
        mode = "manual"

    # Explicit dry-run semantics for legacy tests/scripts:
    # never execute actions and always return a DRY-RUN reason.
    if raw_mode == "dry-run":
        if governance:
            governance._metrics["blocked_dry_run"] += 1
        return False, f"DRY-RUN mode: {action} on {container_name} blocked"

    # Emergency mode: bypass confidence and approval gates for catastrophic events
    if (
        mode == "emergency"
        and sev >= int(Config.EMERGENCY_SEVERITY_THRESHOLD)
        and conf >= float(Config.EMERGENCY_MIN_CONFIDENCE)
    ):
        if governance:
            governance._metrics["auto_executed"] += 1
        return True, "EMERGENCY mode: severity/confidence threshold met"

    # Protected services are never auto-acted on outside emergency bypass
    if is_protected_service(container_name):
        if governance:
            governance._metrics["rejected"] += 1
        return False, f"BLOCKED: {container_name} is a protected service"

    if mode == "manual":
        if governance:
            governance._metrics["pending_approval"] += 1
        return False, f"MANUAL mode: {action} on {container_name} requires human action"

    if mode == "assisted":
        if conf >= float(Config.AUTONOMOUS_MIN_CONFIDENCE):
            # High confidence can execute immediately in assisted mode.
            if governance:
                governance._metrics["auto_executed"] += 1
            return True, "ASSISTED mode: high-confidence action auto-approved"
        if conf >= float(Config.ASSISTED_MIN_CONFIDENCE):
            if governance:
                governance._metrics["pending_approval"] += 1
            return False, (
                f"ASSISTED mode: confidence {conf:.2f} requires 1-click approval "
                f"for {action} on {container_name}"
            )
        if governance:
            governance._metrics["rejected"] += 1
        return False, (
            f"ASSISTED mode: confidence {conf:.2f} below threshold; manual handling required"
        )

    # Default autonomous mode
    if conf >= float(Config.AUTONOMOUS_MIN_CONFIDENCE):
        if governance:
            governance._metrics["auto_executed"] += 1
        return True, "AUTONOMOUS mode: confidence threshold met"
    if governance:
        governance._metrics["rejected"] += 1
    return False, (
        f"AUTONOMOUS mode: confidence {conf:.2f} below {float(Config.AUTONOMOUS_MIN_CONFIDENCE):.2f}"
    )


def enqueue_llm_retry(alert_dict: Dict[str, Any], error: str, attempt: int = 1) -> Dict[str, Any]:
    """Queue a failed analysis payload for retry with exponential backoff metadata."""
    base = max(0.1, float(Config.BACKOFF_BASE_SECONDS))
    delay = base * (2 ** max(0, attempt - 1))
    item = {
        "id": f"retry-{int(time.time() * 1000)}",
        "queued_at": datetime.now().isoformat(),
        "attempt": attempt,
        "next_retry_after_seconds": delay,
        "error": str(error),
        "alert": alert_dict,
    }
    llm_retry_queue.append(item)
    return item


def classify_decision_outcome(severity: int) -> str:
    """Map a numeric severity score (1–10) to a categorical decision label.

    These labels are used in Prometheus metrics and the operator dashboard
    to summarise the LLM's assessment at a glance:

    - ``"malicious"``  — severity 8–10, high-confidence threat
    - ``"suspicious"`` — severity 5–7, warrants investigation
    - ``"benign"``     — severity 1–4, likely false positive

    Parameters
    ----------
    severity : int
        The LLM-assigned severity score (1 = informational, 10 = critical).

    Returns
    -------
    str
        One of ``"malicious"``, ``"suspicious"``, or ``"benign"``.
    """
    if severity >= 8:
        return "malicious"
    if severity >= 5:
        return "suspicious"
    return "benign"


def alert_trace_id(alert_id) -> str:
    """Generate a deterministic trace identifier for correlating log entries.

    The trace ID follows the format ``"alert-<id>"`` and is attached to
    every log message emitted during the processing of a single alert.
    This enables end-to-end tracing from ingestion through LLM analysis
    to automated action execution in log aggregation tools (e.g. Loki,
    ELK).

    Parameters
    ----------
    alert_id : str or int
        The unique identifier of the alert (typically a UUID or DB row ID).

    Returns
    -------
    str
        A prefixed trace string, e.g. ``"alert-42"`` or ``"alert-abc123"``.
    """
    return f"alert-{alert_id}"


def detect_alert_source(alert) -> str:
    """Determine the originating security tool for an incoming alert.

    The IDS ingests alerts from two primary sources:

    - **Falco** — a runtime security tool that monitors Linux syscalls
      inside containers and fires rule-based alerts.
    - **Suricata** — a network-level intrusion detection engine that
      inspects packet payloads against signature rules.

    Because the JSON schema of forwarded alerts varies slightly, this
    function uses a heuristic approach — checking the ``rule`` name,
    ``output`` text, ``container.name``, and ``event_type`` fields for
    the substring ``"suricata"``.  If none match, the alert is assumed
    to originate from Falco (the default / most common source in this
    deployment).

    Parameters
    ----------
    alert : object
        An alert model instance with attributes ``rule``, ``output``,
        and ``output_fields`` (dict).

    Returns
    -------
    str
        Either ``"suricata"`` or ``"falco"``.
    """
    # Normalise all searchable fields to lowercase for comparison
    rule = (alert.rule or "").lower()
    output = (alert.output or "").lower()
    fields = alert.output_fields or {}
    container = str(fields.get("container.name", "")).lower()
    event_type = str(fields.get("event_type", "")).lower()

    # If any field contains a Suricata indicator, classify accordingly
    if (
        "suricata" in rule
        or "suricata" in output
        or "suricata" in container
        or event_type == "alert"  # Suricata uses ``event_type: "alert"``
    ):
        return "suricata"
    # Default assumption: alert originated from Falco
    return "falco"


def compute_human_review_required(severity: int, confidence: float = 0.0) -> bool:
    """Decide whether a given alert requires human operator review.

    The decision depends on the current **governance / automation mode**:

    - ``"manual"``      — every alert requires human review.
    - ``"assisted"``    — medium confidence requires one-click approval.
    - ``"autonomous"``  — high-confidence auto execute, otherwise review.
    - ``"emergency"``   — catastrophic severity + confidence bypass review.

    Parameters
    ----------
    severity : int
        The LLM-assigned severity score (1–10).

    Returns
    -------
    bool
        ``True`` if a human operator must review and approve any
        recommended actions before they are executed.
    """
    # Lazy imports to avoid circular dependency — governance module may
    # import from _state indirectly.
    from governance import get_automation_mode
    import os

    mode = str(get_automation_mode() or "assisted").strip().lower()
    if mode in {"live", "autopilot"}:
        mode = "autonomous"
    elif mode in {"dry-run", "approval-required"}:
        mode = "manual"

    autonomous_conf = float(os.getenv("AUTONOMOUS_MIN_CONFIDENCE", str(Config.AUTONOMOUS_MIN_CONFIDENCE)))
    assisted_conf = float(os.getenv("ASSISTED_MIN_CONFIDENCE", str(Config.ASSISTED_MIN_CONFIDENCE)))
    emergency_conf = float(os.getenv("EMERGENCY_MIN_CONFIDENCE", str(Config.EMERGENCY_MIN_CONFIDENCE)))
    emergency_sev = int(os.getenv("EMERGENCY_SEVERITY_THRESHOLD", str(Config.EMERGENCY_SEVERITY_THRESHOLD)))

    if mode == "manual":
        return True      # All alerts need human eyes
    if mode == "emergency" and severity >= emergency_sev and confidence >= emergency_conf:
        return False
    if mode == "autonomous":
        return confidence < autonomous_conf
    if mode == "assisted":
        if confidence >= autonomous_conf:
            return False
        if confidence >= assisted_conf:
            return True
        return True
    return True


def set_automation_mode_metric(mode: str):
    """Update the Prometheus automation-mode gauge to reflect the current mode.

    The gauge ``PROM_AUTOMATION_MODE`` has a ``mode`` label across
    ``"autonomous"``, ``"assisted"``, ``"manual"``, ``"emergency"``.
    Exactly one of these is set to ``1`` and the others to ``0``, making
    it easy to build Grafana panels that show the active mode as a
    state-timeline or single-stat.

    Parameters
    ----------
    mode : str
        The currently active automation mode (one of ``"autonomous"``,
        ``"assisted"``, ``"manual"``, ``"emergency"``).
    """
    # Lazy import to avoid circular dependency with the metrics module
    from infrastructure.metrics import PROM_AUTOMATION_MODE

    # Set exactly one label to 1, all others to 0
    for label in ("autonomous", "assisted", "manual", "emergency"):
        PROM_AUTOMATION_MODE.labels(mode=label).set(1 if label == mode else 0)


def update_circuit_breaker_metrics():
    """Synchronise Prometheus gauges with the current circuit-breaker states.

    Each LLM engine has an independent circuit breaker that can be in one
    of four states:

    - ``closed``      (0) — healthy, requests flow normally.
    - ``half_open``   (1) — testing recovery with a single probe request.
    - ``open``        (2) — tripped, all requests are short-circuited.
    - ``unconfigured`` (3) — engine is not provisioned / no API key.

    This function iterates over all known engines and writes the current
    numeric state into ``PROM_CIRCUIT_BREAKER_STATE``, which powers the
    circuit-breaker health panel on the Grafana dashboard.
    """
    # Lazy import — metrics module may not be available during unit tests
    from infrastructure.metrics import PROM_CIRCUIT_BREAKER_STATE

    # Map state names to numeric values for the Prometheus gauge
    state_map = {"closed": 0, "half_open": 1, "open": 2, "unconfigured": 3}

    # Determine which engines are actually configured (have API keys)
    configured = set(circuit_breaker.engine_stats.keys()) if circuit_breaker else set()

    # All engines we want to report on, regardless of configuration
    all_engines = ["xai", "anthropic", "openai", "gemini", "kimi"]

    for engine in all_engines:
        if engine in configured:
            # Engine is configured — read its actual state
            stats = circuit_breaker.engine_stats.get(engine, {})
            state_val = state_map.get(stats.get("state", "closed"), 0)
        else:
            # Engine is not configured — report as "unconfigured"
            state_val = state_map["unconfigured"]
        PROM_CIRCUIT_BREAKER_STATE.labels(engine=engine).set(state_val)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 8 — IoT device metric helpers
# ═══════════════════════════════════════════════════════════════════════════════
# The smart-city deployment runs heterogeneous IoT pods (traffic cameras,
# environmental sensors, healthcare APIs, etc.).  The metric
# ``PROM_IOT_DEVICES_ACTIVE`` tracks how many are currently running.
# Because querying the K8s API on every Prometheus scrape would be too
# expensive, the result is cached for 120 seconds.
# ───────────────────────────────────────────────────────────────────────────────

# Simple TTL cache: ``value`` is the last known active-device count,
# ``last_refresh`` is the Unix timestamp of the last K8s API query.
_iot_metric_cache = {
    "value": 0,
    "last_refresh": 0.0,
    "k8s_count": 0,
    "db_count": 0,
    "mem_count": 0,
    "authoritative_source": "none",
    "degraded": True,
}


def get_iot_metric_metadata() -> Dict[str, Any]:
    """Return metadata for the cached IoT active-count metric."""
    return {
        "k8s_count": int(_iot_metric_cache.get("k8s_count", 0) or 0),
        "db_count": int(_iot_metric_cache.get("db_count", 0) or 0),
        "mem_count": int(_iot_metric_cache.get("mem_count", 0) or 0),
        "authoritative_source": str(_iot_metric_cache.get("authoritative_source", "none")),
        "degraded": bool(_iot_metric_cache.get("degraded", True)),
        "cache_age_seconds": max(0, int(time.time() - float(_iot_metric_cache.get("last_refresh", 0.0) or 0.0))),
    }


def refresh_iot_active_metric() -> int:
    """Count active IoT pods via the Kubernetes API, with 120-second caching.

    The count is derived from three complementary sources and the
    **maximum observed value** is used as the authoritative value:

    1. **K8s API** — list running pods in the ``smart-city`` namespace
       whose name starts with a known IoT-service prefix.
    2. **Database** — ``db.get_iot_device_count()`` returns the number of
       registered devices in persistent storage.
    3. **In-memory registry** — ``len(iot_devices)`` counts devices that
       have registered via the ``/api/iot/register`` endpoint during this
       process's lifetime.

    Taking the maximum avoids under-reporting when one source is
    temporarily stale (e.g. the DB hasn't been updated yet, but pods are
    already running).

    Important:
        This function no longer fabricates an expected fallback value.
        If Kubernetes/DB/registry sources are unavailable, the metric may
        legitimately return 0 and should be treated as degraded telemetry,
        not as a guaranteed fleet inventory count.

    Returns
    -------
    int
        The number of active IoT devices / pods.

    Side Effects
    ------------
    - Updates the ``PROM_IOT_DEVICES_ACTIVE`` Prometheus gauge.
    - Refreshes the module-level ``_iot_metric_cache``.
    """
    from infrastructure.metrics import PROM_IOT_DEVICES_ACTIVE

    now = time.time()
    # Return cached value if it is still fresh (< 120 seconds old)
    if now - _iot_metric_cache["last_refresh"] < 120:
        return _iot_metric_cache["value"]

    # --- Source 1: live Kubernetes pod listing ---
    k8s_count = 0
    if k8s_automation:
        try:
            pod_list = k8s_automation.core_v1.list_namespaced_pod(
                namespace="smart-city",
                timeout_seconds=2,
                _request_timeout=(1, 2),
            )
            # Known pod-name prefixes for IoT-related services in this deployment
            iot_prefixes = [
                "traffic-camera", "healthcare-api", "parking-system",
                "iot-devices-enhanced", "iot-simulator-high",
                "iot-simulator-medium", "iot-simulator-burst",
                "iot-mqtt", "mqtt-broker",
                "env-sensor", "street-lighting",
            ]
            for p in pod_list.items:
                name = p.metadata.name
                phase = (p.status.phase or "").lower()
                # Only count pods that are actually running and match an IoT prefix
                if phase == "running" and any(name.startswith(pfx) for pfx in iot_prefixes):
                    k8s_count += 1
        except Exception:
            # Silently degrade — K8s may be unreachable in dev/test environments
            pass

    # --- Source 2: persistent database count ---
    db_count = db.get_iot_device_count() if db else 0

    # --- Source 3: in-memory device registry ---
    mem_count = len(iot_devices)

    # Use the highest value across real sources to avoid under-reporting
    # when one source is temporarily stale.
    active_count = max(k8s_count, db_count, mem_count)
    source_counts = {
        "k8s_pods": k8s_count,
        "device_registry_db": db_count,
        "device_registry_memory": mem_count,
    }
    authoritative_source = "none"
    for name, count in source_counts.items():
        if count == active_count and count > 0:
            authoritative_source = name
            break
    degraded = (k8s_count == 0 and db_count == 0 and mem_count == 0)

    # Update the Prometheus gauge and refresh the TTL cache
    PROM_IOT_DEVICES_ACTIVE.set(active_count)
    _iot_metric_cache["value"] = active_count
    _iot_metric_cache["last_refresh"] = now
    _iot_metric_cache["k8s_count"] = k8s_count
    _iot_metric_cache["db_count"] = db_count
    _iot_metric_cache["mem_count"] = mem_count
    _iot_metric_cache["authoritative_source"] = authoritative_source
    _iot_metric_cache["degraded"] = degraded
    return active_count


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 9 — LLM observability helpers (tokens, cost, latency)
# ═══════════════════════════════════════════════════════════════════════════════
# These functions support the cost-tracking and token-usage dashboards by
# estimating per-call metrics and recording them in both the in-memory
# ``llm_provider_stats`` dict and Prometheus counters.
# ───────────────────────────────────────────────────────────────────────────────


def _estimate_tokens(payload: Any) -> int:
    """Estimate the token count of an arbitrary payload using a chars/4 heuristic.

    Most LLM tokenisers produce roughly 1 token per 4 characters of
    English text.  This is a *conservative* (over-) estimate that is
    acceptable for cost dashboards; exact token counting would require
    importing provider-specific tokeniser libraries (tiktoken, etc.),
    adding significant dependency weight for marginal accuracy gains.

    Parameters
    ----------
    payload : Any
        The data to estimate.  If it is not already a string, it is
        serialised to JSON first.

    Returns
    -------
    int
        Estimated token count (minimum 1).
    """
    try:
        # Convert dicts / lists to a JSON string for character counting
        text = payload if isinstance(payload, str) else json_mod.dumps(payload, ensure_ascii=False)
    except Exception:
        # Fallback for non-serialisable objects
        text = str(payload)
    # Floor at 1 to avoid zero-token entries in metrics
    return max(1, int(len(text) / 4))


def record_llm_call(engine: str, latency_s: float, success: bool):
    """Record a single LLM API call in per-provider statistics and Prometheus.

    This function maintains a **rolling window** of latency samples (capped
    at 500 entries per engine) and a cumulative cost counter.  It is called
    by ``analyze_with_fallback()`` after every LLM invocation, whether
    successful or failed.

    Parameters
    ----------
    engine : str
        Identifier of the LLM provider that handled the call (e.g.
        ``"xai"``, ``"openai"``).
    latency_s : float
        Wall-clock duration of the LLM API call in seconds.
    success : bool
        ``True`` if the call returned a usable analysis result.

    Side Effects
    ------------
    - Increments ``PROM_LLM_COST_USD`` Prometheus counter on success.
    - Updates the in-memory ``llm_provider_stats[engine]`` dict.
    """
    if not _is_trackable_engine(engine):
        return

    # Lazily initialise stats dict for this engine if not already present
    s = llm_provider_stats.setdefault(engine, {
        "total_requests": 0, "successes": 0, "failures": 0,
        "latencies": [], "total_cost_usd": 0.0,
    })
    s["total_requests"] += 1

    if success:
        s["successes"] += 1
        s["latencies"].append(latency_s)
        # Cap the latency sample buffer at 500 to bound memory usage
        if len(s["latencies"]) > 500:
            s["latencies"] = s["latencies"][-500:]
    else:
        s["failures"] += 1


def record_llm_tokens(engine: str, prompt_payload: Any, completion_payload: Any, usage: Any = None):
    """Estimate and record prompt/completion token counts for a single LLM call.

    Token counts are tracked in two places:
    - **Prometheus** — ``PROM_LLM_TOKENS_TOTAL`` counter with ``engine``
      and ``kind`` (``"prompt"`` / ``"completion"``) labels.
    - **In-memory** — ``llm_provider_stats[engine]`` dict for the
      ``/api/llm-stats/export`` endpoint.

    Parameters
    ----------
    engine : str
        Identifier of the LLM provider.
    prompt_payload : Any
        The request payload sent to the LLM (dict or string).
    completion_payload : Any
        The response payload returned by the LLM (dict or string).

    Side Effects
    ------------
    - Increments ``PROM_LLM_TOKENS_TOTAL`` for both prompt and completion.
    - Updates ``prompt_tokens`` and ``completion_tokens`` in
      ``llm_provider_stats[engine]``.
    """
    from infrastructure.metrics import PROM_LLM_TOKENS_TOTAL, PROM_LLM_COST_USD

    if not _is_trackable_engine(engine):
        return 0, 0, 0.0

    # Use provider-reported usage when available; fallback to chars/4 estimates.
    prompt_tokens = None
    completion_tokens = None
    if isinstance(usage, dict):
        raw_prompt = usage.get("prompt_tokens")
        raw_completion = usage.get("completion_tokens")
        if raw_prompt is not None:
            prompt_tokens = max(0, int(raw_prompt))
        if raw_completion is not None:
            completion_tokens = max(0, int(raw_completion))

    if prompt_tokens is None:
        prompt_tokens = _estimate_tokens(prompt_payload)
    if completion_tokens is None:
        completion_tokens = _estimate_tokens(completion_payload)

    # Update Prometheus counters (separate series for prompt vs completion)
    PROM_LLM_TOKENS_TOTAL.labels(engine=engine, kind="prompt").inc(prompt_tokens)
    PROM_LLM_TOKENS_TOTAL.labels(engine=engine, kind="completion").inc(completion_tokens)

    # Update in-memory stats (used by /api/llm-stats/export)
    s = llm_provider_stats.setdefault(engine, {
        "total_requests": 0, "successes": 0, "failures": 0,
        "latencies": [], "total_cost_usd": 0.0,
        "prompt_tokens": 0, "completion_tokens": 0,
    })
    s["prompt_tokens"] = s.get("prompt_tokens", 0) + prompt_tokens
    s["completion_tokens"] = s.get("completion_tokens", 0) + completion_tokens

    token_cost = _estimate_cost_from_tokens(engine, prompt_tokens, completion_tokens)
    if token_cost > 0:
        s["total_cost_usd"] = round(float(s.get("total_cost_usd", 0.0)) + token_cost, 8)
        PROM_LLM_COST_USD.labels(engine=engine).inc(token_cost)

    return int(prompt_tokens), int(completion_tokens), float(token_cost)


def record_llm_usage(
    engine: str,
    *,
    latency_s: float,
    success: bool,
    prompt_payload: Any,
    completion_payload: Any,
    usage: Any = None,
    purpose: str = "alerts",
    model: Optional[str] = None,
    error_message: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Record a single LLM call in memory/Prometheus AND persist token usage to DB.

    This is the preferred entry-point for usage tracking because it captures:
    - calls, successes/failures, latency samples
    - prompt/completion tokens (provider-reported when available, else estimated)
    - a DB row for "today" usage dashboards across restarts

    Returns:
        dict with prompt_tokens, completion_tokens, tokens_total, estimated_cost_usd
    """
    prompt_tokens, completion_tokens, token_cost = record_llm_tokens(
        engine,
        prompt_payload,
        completion_payload,
        usage=usage,
    )
    record_llm_call(engine, float(latency_s or 0.0), bool(success))

    # Best-effort DB persistence (never break alert processing if DB write fails).
    try:
        if db and hasattr(db, "log_llm_api_call"):
            latency_ms = int(max(0.0, float(latency_s or 0.0)) * 1000)
            safe_meta = dict(meta or {})
            if token_cost:
                safe_meta.setdefault("estimated_cost_usd", float(token_cost))
            if usage is not None and isinstance(usage, dict):
                safe_meta.setdefault("provider_usage", usage)
            db.log_llm_api_call(
                engine,
                int(prompt_tokens),
                int(completion_tokens),
                purpose=str(purpose or "alerts"),
                model=model,
                success=bool(success),
                latency_ms=latency_ms,
                error_message=error_message,
                meta=safe_meta,
            )
    except Exception:
        pass

    return {
        "prompt_tokens": int(prompt_tokens),
        "completion_tokens": int(completion_tokens),
        "tokens_total": int(prompt_tokens) + int(completion_tokens),
        "estimated_cost_usd": float(token_cost or 0.0),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 10 — Core LLM analysis pipeline
# ═══════════════════════════════════════════════════════════════════════════════
# The ``analyze_with_fallback`` coroutine is the single entry point for
# submitting an alert to the LLM analysis pipeline.  It handles caching,
# provider fallback (via ``llm_manager``), circuit-breaker bookkeeping,
# and Prometheus metric recording in one place.
# ───────────────────────────────────────────────────────────────────────────────


async def analyze_with_fallback(alert_dict: dict) -> tuple:
    """Analyse a security alert through the unified LLM pipeline with caching.

    This is the **primary analysis entry point** used by the alert-ingestion
    router.  The execution flow is:

    1. **Cache check** — if an identical alert was already analysed, return
       the cached result immediately (cache hit).
    2. **LLM invocation** — delegate to ``llm_manager.analyze()``, which
       internally handles multi-provider fallback and circuit-breaker
       logic.
    3. **Success path** — cache the result, update Prometheus metrics
       (latency histogram, request counter, token estimates, cost), record
       circuit-breaker successes/failures, and return the analysis.
    4. **Failure path** — record failures in circuit breakers and metrics,
       then raise an ``Exception`` so the caller can return an appropriate
       HTTP error response.

    Parameters
    ----------
    alert_dict : dict
        The normalised alert payload (must be JSON-serialisable for cache
        hashing).

    Returns
    -------
    tuple[dict, str, float]
        A 3-tuple of:
        - ``analysis`` — the LLM's structured analysis result (dict with
          ``severity``, ``summary``, ``threat_type``, etc.).
        - ``engine_used`` — identifier of the provider that produced the
          result (``"xai"``, ``"openai"``, ``"cache"``, etc.).
        - ``llm_duration`` — wall-clock seconds spent on the LLM call
          (``0.0`` for cache hits).

    Raises
    ------
    Exception
        If all LLM providers fail and no cached result is available.
    """
    # Lazy imports — these Prometheus metrics are only needed inside this
    # function and importing at module level would create circular deps.
    from infrastructure.metrics import (
        PROM_LLM_CACHE_OPERATIONS,
        PROM_LLM_CACHE_SIZE,
        PROM_LLM_REQUESTS_TOTAL,
        PROM_LLM_LATENCY_SECONDS,
    )

    # ── Step 0: LLM manager availability ───────────────────────────────
    if not llm_manager:
        enqueue_llm_retry(alert_dict, "llm_manager_unavailable", attempt=1)
        raise Exception("LLM manager unavailable; alert queued for retry")

    # ── Step 1: Check the alert cache ──────────────────────────────────
    cached = alert_cache.get(alert_dict)
    if cached:
        # Cache hit — skip the expensive LLM call entirely
        PROM_LLM_CACHE_OPERATIONS.labels(operation="hit").inc()
        PROM_LLM_CACHE_SIZE.set(len(alert_cache.cache))
        return cached, "cache", 0.0

    # Cache miss — we must call the LLM
    PROM_LLM_CACHE_OPERATIONS.labels(operation="miss").inc()

    # ── Step 2: Invoke the LLM manager ─────────────────────────────────
    preferred = select_preferred_provider(alert_dict)
    max_attempts = max(1, int(Config.MAX_RETRY_ATTEMPTS))
    llm_duration = 0.0
    result = None
    engine_used = "unknown"
    failed_engines = []
    last_error = "unknown"

    for attempt in range(1, max_attempts + 1):
        llm_start = time.perf_counter()
        try:
            result = await llm_manager.analyze(alert_dict, preferred_engine=preferred)
        except Exception as exc:
            result = {"status": "error", "error": str(exc), "engine": preferred or "unknown"}
        llm_duration += time.perf_counter() - llm_start

        engine_used = (result or {}).get("provider") or (result or {}).get("engine", "unknown")
        failed_engines = (result or {}).get("failed_engines", [])

        if (result or {}).get("status") == "success":
            break

        last_error = (result or {}).get("error", "unknown error")
        if attempt < max_attempts:
            backoff = max(0.1, float(Config.BACKOFF_BASE_SECONDS)) * (2 ** (attempt - 1))
            await asyncio.sleep(backoff)

    # Extract metadata about which engine was used and which ones failed
    engine_used = (result or {}).get("provider") or (result or {}).get("engine", "unknown")
    failed_engines = (result or {}).get("failed_engines", [])

    # ── Step 3: Handle success ─────────────────────────────────────────
    if (result or {}).get("status") == "success":
        # Record circuit-breaker failures for engines that were tried and failed
        for failed_engine in failed_engines:
            if failed_engine in circuit_breaker.engine_stats:
                circuit_breaker.record_failure(failed_engine)
        # Record success for the engine that ultimately succeeded
        if engine_used in circuit_breaker.engine_stats:
            circuit_breaker.record_success(engine_used)
        # Push updated breaker states into Prometheus
        update_circuit_breaker_metrics()

        analysis = result.get("analysis", {})
        # Preserve a full per-alert LLM trace (prompt + raw completion + usage)
        # for UI transparency/debugging. Stored inside analysis JSON so no DB
        # schema change is required.
        if isinstance(analysis, dict):
            llm_trace = result.get("llm_trace")
            if isinstance(llm_trace, dict):
                analysis["_llm_trace"] = llm_trace
            analysis["_llm_engine"] = engine_used
        # Store in cache so subsequent identical alerts skip the LLM
        alert_cache.set(alert_dict, analysis)
        PROM_LLM_CACHE_SIZE.set(len(alert_cache.cache))
        # Record Prometheus + DB metrics for latency, throughput, tokens, cost
        PROM_LLM_REQUESTS_TOTAL.labels(engine=engine_used, result="success").inc()
        PROM_LLM_LATENCY_SECONDS.labels(engine=engine_used).observe(llm_duration)
        record_llm_usage(
            engine_used,
            latency_s=llm_duration,
            success=True,
            prompt_payload=alert_dict,
            completion_payload=analysis,
            usage=result.get("usage"),
            purpose="alerts",
            model=(result.get("model") or None),
            meta={"failed_engines": failed_engines} if failed_engines else None,
        )
        set_llm_last_provider_used(engine_used)
        return analysis, engine_used, llm_duration

    # ── Step 4: Handle failure ─────────────────────────────────────────
    error_msg = (result or {}).get("error", "Unknown error")
    # Record failures in circuit breakers for all attempted engines
    for failed_engine in failed_engines:
        if failed_engine in circuit_breaker.engine_stats:
            circuit_breaker.record_failure(failed_engine)
    if engine_used in circuit_breaker.engine_stats:
        circuit_breaker.record_failure(engine_used)
    update_circuit_breaker_metrics()
    # Record the error in Prometheus counters
    PROM_LLM_REQUESTS_TOTAL.labels(engine=engine_used, result="error").inc()
    # Best-effort usage record for failures (prompt tokens estimated, completion=0)
    record_llm_usage(
        engine_used,
        latency_s=llm_duration,
        success=False,
        prompt_payload=alert_dict,
        completion_payload="",
        usage=None,
        purpose="alerts",
        model=(result.get("model") or None) if isinstance(result, dict) else None,
        error_message=error_msg or last_error,
        meta={"failed_engines": failed_engines} if failed_engines else None,
    )
    set_llm_last_provider_used(engine_used)
    enqueue_llm_retry(alert_dict, error_msg or last_error, attempt=max_attempts)
    # Raise so the calling router can return an HTTP 5xx response
    raise Exception(f"LLM analysis failed after retries; queued for retry: {error_msg}")
