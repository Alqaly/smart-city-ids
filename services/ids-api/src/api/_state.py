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
import json as json_mod      # Aliased to avoid shadowing if a local var is named ``json``
import logging
import time
from collections import OrderedDict  # Available for LRU-style caches elsewhere
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

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
    "local": 0.0,       # Local/self-hosted model — no API cost
}

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
    # Iterate over the configured list of protected service name prefixes
    for protected in Config.PROTECTED_SERVICES:
        if protected.lower() in container_name.lower():
            return True
    return False


def can_execute_action(action: str, container_name: str) -> tuple:
    """Determine whether an automated remediation action is permitted.

    This function implements the **safety-gate logic** that sits between the
    LLM's recommendation and actual Kubernetes execution.  Three levels of
    control are evaluated in order:

    1. **Dry-run mode** — all actions are logged but never executed.
    2. **Approval-required mode** — actions are queued for human approval
       via the operator interface.
    3. **Protected-service check** — even in full-auto mode, actions
       targeting critical infrastructure are blocked.

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
    if Config.AUTOMATION_MODE == "dry-run":
        return False, f"DRY-RUN: Would execute {action} on {container_name}"
    if Config.AUTOMATION_MODE == "approval-required":
        return False, f"APPROVAL-REQUIRED: {action} on {container_name} needs manual approval"
    # Even in auto mode, never touch protected services
    if is_protected_service(container_name):
        return False, f"BLOCKED: {container_name} is a protected service"
    return True, "OK"


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


def compute_human_review_required(severity: int) -> bool:
    """Decide whether a given alert requires human operator review.

    The decision depends on the current **governance / automation mode**:

    - ``"manual"``    — every alert requires human review (return ``True``).
    - ``"autopilot"`` — no alert requires review (return ``False``).
    - ``"assisted"``  — only alerts at or above a configurable severity
      threshold (default 8) require review.

    The ``ASSISTED_THRESHOLD`` environment variable allows operators to
    tune how aggressive the assisted mode is without redeploying the
    service.

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

    mode = get_automation_mode()
    # Configurable severity threshold for the "assisted" mode
    threshold = int(os.getenv("ASSISTED_THRESHOLD", "8"))

    if mode == "manual":
        return True      # All alerts need human eyes
    if mode == "autopilot":
        return False     # Full automation — no human gate
    # "assisted" mode — only high-severity alerts escalate
    return severity >= threshold


def set_automation_mode_metric(mode: str):
    """Update the Prometheus automation-mode gauge to reflect the current mode.

    The gauge ``PROM_AUTOMATION_MODE`` has a ``mode`` label with three
    possible values: ``"autopilot"``, ``"assisted"``, ``"manual"``.
    Exactly one of these is set to ``1`` and the others to ``0``, making
    it easy to build Grafana panels that show the active mode as a
    state-timeline or single-stat.

    Parameters
    ----------
    mode : str
        The currently active automation mode (one of ``"autopilot"``,
        ``"assisted"``, ``"manual"``).
    """
    # Lazy import to avoid circular dependency with the metrics module
    from infrastructure.metrics import PROM_AUTOMATION_MODE

    # Set exactly one label to 1, all others to 0
    for label in ("autopilot", "assisted", "manual"):
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
_iot_metric_cache = {"value": 0, "last_refresh": 0.0}


def refresh_iot_active_metric() -> int:
    """Count active IoT pods via the Kubernetes API, with 120-second caching.

    The count is derived from three complementary sources and the
    **maximum** is used as the authoritative value:

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
                namespace="smart-city", timeout_seconds=5
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

    # Use the highest value to avoid under-reporting
    active_count = max(k8s_count, db_count, mem_count)

    # Update the Prometheus gauge and refresh the TTL cache
    PROM_IOT_DEVICES_ACTIVE.set(active_count)
    _iot_metric_cache["value"] = active_count
    _iot_metric_cache["last_refresh"] = now
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
    from infrastructure.metrics import PROM_LLM_COST_USD

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
        # Look up per-call cost, defaulting to $0.005 for unknown engines
        cost = LLM_COST_PER_CALL.get(engine, 0.005)
        s["total_cost_usd"] += cost
        PROM_LLM_COST_USD.labels(engine=engine).inc(cost)
    else:
        s["failures"] += 1


def record_llm_tokens(engine: str, prompt_payload: Any, completion_payload: Any):
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
    from infrastructure.metrics import PROM_LLM_TOKENS_TOTAL

    # Estimate token counts using the chars/4 heuristic
    prompt_tokens = _estimate_tokens(prompt_payload)
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
    llm_start = time.perf_counter()
    result = await llm_manager.analyze(alert_dict)
    llm_duration = time.perf_counter() - llm_start

    # Extract metadata about which engine was used and which ones failed
    engine_used = result.get("provider") or result.get("engine", "unknown")
    failed_engines = result.get("failed_engines", [])

    # ── Step 3: Handle success ─────────────────────────────────────────
    if result.get("status") == "success":
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
        # Store in cache so subsequent identical alerts skip the LLM
        alert_cache.set(alert_dict, analysis)
        PROM_LLM_CACHE_SIZE.set(len(alert_cache.cache))
        # Record Prometheus metrics for latency, throughput, tokens, cost
        PROM_LLM_REQUESTS_TOTAL.labels(engine=engine_used, result="success").inc()
        PROM_LLM_LATENCY_SECONDS.labels(engine=engine_used).observe(llm_duration)
        record_llm_tokens(engine_used, alert_dict, analysis)
        record_llm_call(engine_used, llm_duration, True)
        return analysis, engine_used, llm_duration

    # ── Step 4: Handle failure ─────────────────────────────────────────
    error_msg = result.get("error", "Unknown error")
    # Record failures in circuit breakers for all attempted engines
    for failed_engine in failed_engines:
        if failed_engine in circuit_breaker.engine_stats:
            circuit_breaker.record_failure(failed_engine)
    if engine_used in circuit_breaker.engine_stats:
        circuit_breaker.record_failure(engine_used)
    update_circuit_breaker_metrics()
    # Record the error in Prometheus counters
    PROM_LLM_REQUESTS_TOTAL.labels(engine=engine_used, result="error").inc()
    record_llm_call(engine_used, llm_duration, False)
    # Raise so the calling router can return an HTTP 5xx response
    raise Exception(f"LLM analysis failed: {error_msg}")
