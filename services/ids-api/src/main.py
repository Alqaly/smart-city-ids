"""Smart City IDS — Main Application Entry-Point.

This module is the single orchestration point for the entire IDS FastAPI
application.  It was refactored from a monolithic 3 105-line file into a
slim ~370-line entry-point that delegates all business logic to dedicated
sub-packages:

    api/             – 8 FastAPI APIRouter modules (alerts, auth, governance, …)
    models/          – Pydantic request / response schemas
    infrastructure/  – cross-cutting concerns (auth, metrics, middleware, DB)
    services/        – (future) domain service layer

Architecture overview:
    1. Create the FastAPI ``app`` instance.
    2. Mount static files for the security-analyst dashboard UI.
    3. Initialise heavyweight singletons (LLM manager, K8s client, DB, …).
    4. Populate the shared-state module ``api._state`` so all routers can
       import references to those singletons without circular imports.
    5. Register the 8 API routers.
    6. Restore Prometheus counters from PostgreSQL so Grafana keeps showing
       historical data across restarts.
    7. Define ``startup`` / ``shutdown`` lifecycle hooks.

Design rationale (why a shared-state module?):
    FastAPI routers are stateless by convention, but this IDS needs access to
    several long-lived singletons (LLM client, K8s client, DB handle, caches,
    circuit breaker, …).  Rather than using FastAPI's ``app.state`` — which
    would couple every router to the ``app`` object — the ``api._state``
    module exposes a simple ``init()`` function that main.py calls once at
    import time.  Routers then ``from api._state import db, llm_manager``
    like any normal Python import.

Author : Smart City IDS Team
Version: 2.0.0 (post-refactor)
"""

from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

# ── Path setup ───────────────────────────────────────────────────────────────
# Ensure the ``src/`` directory is on ``sys.path`` so that local packages
# (config, database, llm_manager, …) can be imported by name.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── Configuration & logging ──────────────────────────────────────────────────
# ``Config`` is a dataclass-style class defined in ``config.py``.  It reads
# all settings from environment variables with sensible defaults.
from config import Config

logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ── FastAPI application ──────────────────────────────────────────────────────
# Central ASGI application object.  Metadata here populates the auto-generated
# OpenAPI (Swagger) docs at ``/docs``.
app = FastAPI(
    title="Smart City IDS",
    description="LLM-Driven Intrusion Detection System",
    version="1.0.0",
)

# ── Static files ─────────────────────────────────────────────────────────────
# The dashboard UI is a single ``index.html`` + JS/CSS bundle.  We try
# several candidate directories because the working directory varies between
# local development and containerised deployment.
_static_candidates = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "static"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "static"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "static"),
]
STATIC_DIR = next((p for p in _static_candidates if os.path.exists(p)), None)
if STATIC_DIR:
    # Mount so that ``/ui/static/…`` serves CSS, JS, images.
    app.mount("/ui/static", StaticFiles(directory=STATIC_DIR), name="static")
    logger.info(f"Static files mounted: {STATIC_DIR}")

# ══════════════════════════════════════════════════════════════════════════════
# COMPONENT INITIALISATION
# ══════════════════════════════════════════════════════════════════════════════
# Import heavyweight singletons.  These are created once and live for the
# entire process lifetime.
from database import db  # noqa: E402  — synchronous DB singleton (psycopg2 / memory)
from k8s_automation import K8sAutomation  # noqa: E402  — Kubernetes client wrapper
from alert_deduplicator import AlertDeduplicator  # noqa: E402  — fingerprint-based dedup cache
from alert_rate_limiter import AlertRateLimiter  # noqa: E402  — per-rule / per-source rate limiter
from operator_interface import operator_interface  # noqa: E402  — incident-view builder
from infrastructure.middleware import AlertCache, RateLimiter, CircuitBreaker, RequestQueue  # noqa: E402

try:
    # Validate that at least one LLM API key is configured.
    Config.validate()

    # ── LLM provider initialisation ──────────────────────────────────────
    # The project has two LLM integration systems:
    #   1. New plugin-based ``llm_providers.manager.LLMManager`` (preferred)
    #   2. Legacy ``llm_manager.LLMEngineManager`` (fallback)
    #
    # ``_LegacyAdapter`` wraps the old system so the rest of the codebase
    # only ever interacts with a single, unified interface:
    #   - ``llm_manager.analyze(alert_dict)``   → run LLM analysis
    #   - ``llm_manager.get_status()``           → provider health info
    #   - ``llm_manager.get_available_providers()``
    try:
        from llm_providers.manager import LLMManager
        llm_manager = LLMManager()
    except Exception as provider_init_error:
        logger.warning(
            f"Provider manager init failed, falling back to legacy: {provider_init_error}"
        )
        from llm_manager import LLMEngineManager

        class _LegacyAdapter:
            """Adapter that wraps the legacy LLMEngineManager to expose the
            same interface as the new ``LLMManager`` plugin system.

            This allows all downstream code (routers, state helpers, etc.)
            to call ``llm_manager.analyze()``, ``llm_manager.get_status()``,
            etc. without caring which backend is actually running.
            """

            def __init__(self):
                # Delegate to the legacy engine manager instance.
                self._m = LLMEngineManager()

            @property
            def runtime_stats(self):
                """Per-engine runtime statistics (attempts, latencies, …)."""
                return self._m.runtime_stats

            async def analyze(self, alert_dict):
                """Run LLM analysis on an alert dictionary.

                Returns a dict with ``status``, ``analysis``, ``provider``,
                and optionally ``failed_engines``.
                """
                return await self._m.analyze(alert_dict)

            def get_available_providers(self):
                """Return list of engine names that have valid API keys."""
                return self._m.get_available_engines()

            def get_status(self):
                """Build a status dict compatible with the new LLMManager.

                Includes ``provider_count``, ``providers`` list, and per-
                provider ``details`` (model, attempts, successes, cooldown…).
                """
                providers = self._m.get_available_engines()
                details = {}
                for p in providers:
                    stats = self._m.runtime_stats.get(p, {})
                    cooldown_until = self._m.provider_cooldown_until.get(p, 0)
                    eng = self._m.engines.get(p)
                    details[p] = {
                        "configured": True,
                        "model": getattr(eng, "model", "unknown") if eng else "unknown",
                        "base_url": getattr(eng, "base_url", "") if eng else "",
                        "attempts": stats.get("attempts", 0),
                        "successes": stats.get("successes", 0),
                        "failures": stats.get("failures", 0),
                        "last_latency_ms": stats.get("last_latency_ms"),
                        "last_error": stats.get("last_error"),
                        "cooldown_until": int(cooldown_until),
                        "cooldown_remaining_seconds": max(0, int(cooldown_until - time.time())),
                    }
                return {
                    "provider_count": len(providers),
                    "providers": providers,
                    "details": details,
                }

        llm_manager = _LegacyAdapter()

    logger.info(f"✅ LLM: {llm_manager.get_status()['provider_count']} provider(s) ready")

    # ── Kubernetes automation client ─────────────────────────────────────
    # Wraps the K8s Python client for pod isolation, deployment scaling,
    # and pod eviction.  Requires a valid KUBECONFIG.
    k8s_automation = K8sAutomation()

    # ── Alert deduplication cache ────────────────────────────────────────
    # Fingerprints alerts by (rule + output_fields) and returns the
    # cached LLM analysis for duplicates, saving API calls and cost.
    deduplicator = AlertDeduplicator(
        ttl_seconds=int(os.getenv("DEDUPLICATOR_TTL_SECONDS", "60")),
        max_cache_size=int(os.getenv("DEDUPLICATOR_MAX_CACHE_SIZE", "10000")),
    )
    logger.info(
        f"Alert deduplicator initialized "
        f"(TTL={deduplicator.ttl}s, max_cache={deduplicator.max_cache_size})"
    )

    # ── Alert-level rate limiter ─────────────────────────────────────────
    # Prevents a flood of identical alerts from overwhelming the LLM.
    # Independent of the API-level ``RateLimiter`` (token bucket) below.
    alert_rate_limiter = AlertRateLimiter(
        window_seconds=int(os.getenv("ALERT_RATE_LIMIT_WINDOW", "60")),
        max_per_rule=int(os.getenv("ALERT_RATE_LIMIT_PER_RULE", "10")),
        max_per_source=int(os.getenv("ALERT_RATE_LIMIT_PER_SOURCE", "100")),
        max_global=int(os.getenv("ALERT_RATE_LIMIT_GLOBAL", "500")),
    )

    provider_count = llm_manager.get_status()["provider_count"]
    logger.info(f"✅ IDS API ready with {provider_count} LLM provider(s)")
    logger.info(f"Safety: mode={Config.AUTOMATION_MODE}, protected={Config.PROTECTED_SERVICES}")

except Exception as e:
    # Graceful degradation: the API still starts, but LLM / K8s features
    # will be unavailable.
    logger.error(f"Failed to initialize: {e}")
    llm_manager = None
    k8s_automation = None
    deduplicator = None
    alert_rate_limiter = None

# ── Production resilience middleware singletons ──────────────────────────────
# These four classes protect the API from overload, cascade failures, and
# duplicate work.  They are defined in ``infrastructure/middleware.py``.

# LRU cache (by alert fingerprint) to skip redundant LLM calls.
alert_cache = AlertCache(
    max_size=Config.ALERT_CACHE_MAX_SIZE,
    ttl_seconds=Config.ALERT_CACHE_TTL_SECONDS,
)

# Token-bucket rate limiter — caps requests/minute at the HTTP level.
rate_limiter = RateLimiter(
    requests_per_minute=int(os.getenv("RATE_LIMIT_PER_MINUTE", "120")),
    burst_size=int(os.getenv("RATE_LIMIT_BURST", "30")),
)

# Per-engine circuit breaker — stops calling a failing LLM provider and
# allows it to recover before retrying (closed → open → half-open → closed).
circuit_breaker = CircuitBreaker(
    failure_threshold=int(os.getenv("CIRCUIT_BREAKER_THRESHOLD", "5")),
    recovery_timeout=int(os.getenv("CIRCUIT_BREAKER_TIMEOUT", "30")),
    engines=(llm_manager.get_status().get("providers", []) if llm_manager else None),
)

# Simple counter-based queue that rejects new requests when the system is
# already processing too many concurrently.
request_queue = RequestQueue(
    max_queue_size=int(os.getenv("REQUEST_QUEUE_SIZE", "100")),
)

# ══════════════════════════════════════════════════════════════════════════════
# SHARED STATE INJECTION
# ══════════════════════════════════════════════════════════════════════════════
# ``api._state`` is a plain Python module whose module-level variables act as
# the "application context".  Calling ``init()`` once here populates those
# variables so that every router can simply ``from api._state import db``.
import api._state as _state  # noqa: E402

_state.init(
    _llm_manager=llm_manager,
    _k8s_automation=k8s_automation,
    _alert_cache=alert_cache,
    _rate_limiter=rate_limiter,
    _circuit_breaker=circuit_breaker,
    _request_queue=request_queue,
    _deduplicator=deduplicator,
    _alert_rate_limiter=alert_rate_limiter,
    _db=db,
    _operator_interface=operator_interface,
    _static_dir=STATIC_DIR,
)

# ══════════════════════════════════════════════════════════════════════════════
# ROUTER REGISTRATION
# ══════════════════════════════════════════════════════════════════════════════
# Each router is a self-contained module in ``api/``.  Importing them
# *after* ``_state.init()`` guarantees that the singletons are already set.
from api.auth import router as auth_router  # noqa: E402           — POST /api/auth/login, /logout
from api.alerts import router as alerts_router  # noqa: E402       — POST|GET /api/alerts, SSE /api/alerts/live
from api.governance import router as governance_router  # noqa: E402 — /api/governance/*  (HITL)
from api.operator import router as operator_router  # noqa: E402   — /api/operator/*    (incident view)
from api.llm import router as llm_router  # noqa: E402             — /api/llm/*, /api/circuit-breaker/*
from api.iot import router as iot_router  # noqa: E402             — /api/iot/*          (telemetry, sensors)
from api.metrics_routes import router as metrics_router  # noqa: E402 — /health, /metrics, /api/metrics
from api.health import router as health_router  # noqa: E402       — /, /ui

app.include_router(auth_router)
app.include_router(alerts_router)
app.include_router(governance_router)
app.include_router(operator_router)
app.include_router(llm_router)
app.include_router(iot_router)
app.include_router(metrics_router)
app.include_router(health_router)


# ══════════════════════════════════════════════════════════════════════════════
# PROMETHEUS METRIC RESTORATION
# ══════════════════════════════════════════════════════════════════════════════
# Prometheus counters are ephemeral — they reset to zero on process restart.
# The functions below reload historical counts from PostgreSQL so that Grafana
# dashboards show the *full* historical picture, not just "since last restart".

from infrastructure.metrics import (  # noqa: E402
    PROM_ALERTS_RECEIVED_TOTAL,
    PROM_ALERTS_PROCESSED_TOTAL,
    PROM_SEVERITY_DISTRIBUTION,
    PROM_THREAT_TYPES_TOTAL,
    PROM_ACTIONS_EXECUTED_TOTAL,
    PROM_CRITICAL_ALERTS_TOTAL,
    PROM_LLM_DECISION_OUTCOME,
    PROM_AUTOMATED_DECISIONS,
    PROM_IOT_DEVICES_ACTIVE,
    PROM_IOT_EVENTS_TOTAL,
    PROM_LLM_CACHE_SIZE,
    PROM_UPTIME_SECONDS,
)

from api._state import (  # noqa: E402
    metrics_dict,
    set_automation_mode_metric,
    update_circuit_breaker_metrics,
    refresh_iot_active_metric,
)
from governance import get_automation_mode  # noqa: E402


def _init_metrics_from_db():
    """Load aggregate alert counts from the database into the in-memory
    ``metrics_dict`` so that ``GET /api/metrics`` immediately returns
    correct numbers even before any new alerts arrive.
    """
    try:
        stats = db.get_stats()
        metrics_dict["total_alerts"] = stats.get("total_alerts", 0)
        metrics_dict["alerts_by_source"] = stats.get("alerts_by_source", {"falco": 0, "suricata": 0})
        logger.info(
            f"📊 Loaded metrics from DB: {stats['total_alerts']} alerts, "
            f"storage: {stats['storage_type']}"
        )
    except Exception as e:
        logger.warning(f"Could not load metrics from DB: {e}")


def _restore_prometheus_counters():
    """Restore Prometheus counters from PostgreSQL so Grafana shows the
    full historical timeline.

    Without this, every process restart would show a "gap" in metrics where
    all counters drop to zero.  This function reads aggregated data from the
    DB and pre-increments each counter by the historical value.

    Counters restored:
        - ``smartcity_ids_alerts_received_total``    (by source + priority)
        - ``smartcity_ids_alerts_processed_total``   (total successful)
        - ``smartcity_ids_severity_total``            (by severity 1-10)
        - ``smartcity_ids_threat_types_total``        (by threat type)
        - ``smartcity_ids_actions_executed_total``    (by action type)
        - ``smartcity_ids_critical_alerts_total``     (severity >= 8)
        - ``smartcity_ids_llm_decision_outcome_total`` (benign/suspicious/malicious)
        - ``smartcity_ids_automated_decisions_total``
        - ``smartcity_ids_iot_events_total``          (by device + event type)
    """
    logger.info("🔄 Starting Prometheus counter restoration from database...")
    try:
        restore_data = db.get_prometheus_restore_data()
        logger.info(f"🔄 Got restore data: {restore_data}")

        # ── Alerts received (by source:priority) ─────────────────────────
        for key, count in restore_data.get("alerts_by_source_priority", {}).items():
            parts = key.split(":")
            if len(parts) == 2:
                source, priority = parts[0], parts[1] or "Unknown"
                PROM_ALERTS_RECEIVED_TOTAL.labels(source=source, priority=priority).inc(count)

        # ── Total processed successfully ─────────────────────────────────
        total_processed = restore_data.get("total_processed", 0)
        if total_processed > 0:
            PROM_ALERTS_PROCESSED_TOTAL.labels(result="success").inc(total_processed)

        # ── Severity distribution (1-10) ─────────────────────────────────
        for severity, count in restore_data.get("alerts_by_severity", {}).items():
            PROM_SEVERITY_DISTRIBUTION.labels(severity=str(severity)).inc(count)

        # ── Threat types (Malware, DDoS, Privilege Escalation…) ──────────
        for threat_type, count in restore_data.get("alerts_by_threat_type", {}).items():
            if threat_type:
                PROM_THREAT_TYPES_TOTAL.labels(threat_type=threat_type).inc(count)

        # ── Automated actions (isolate_pod, scale_up…) ───────────────────
        for action, count in restore_data.get("actions_executed", {}).items():
            if action:
                PROM_ACTIONS_EXECUTED_TOTAL.labels(action=action).inc(count)

        # ── Critical alerts (severity >= 8) ──────────────────────────────
        critical_count = restore_data.get("critical_alerts", 0)
        if critical_count > 0:
            PROM_CRITICAL_ALERTS_TOTAL.inc(critical_count)

        # ── LLM decision outcome breakdown ───────────────────────────────
        # Map severity ranges → outcome labels for the pie chart:
        #   8-10 = malicious,  5-7 = suspicious,  1-4 = benign
        sev_map = restore_data.get("alerts_by_severity", {})
        malicious = sum(sev_map.get(str(s), 0) for s in (8, 9, 10))
        suspicious = sum(sev_map.get(str(s), 0) for s in (5, 6, 7))
        benign = max(0, total_processed - malicious - suspicious)
        if malicious > 0:
            PROM_LLM_DECISION_OUTCOME.labels(outcome="malicious").inc(malicious)
        if suspicious > 0:
            PROM_LLM_DECISION_OUTCOME.labels(outcome="suspicious").inc(suspicious)
        if benign > 0:
            PROM_LLM_DECISION_OUTCOME.labels(outcome="benign").inc(benign)

        # ── Automated decisions total ────────────────────────────────────
        auto_count = sum(restore_data.get("actions_executed", {}).values())
        if auto_count > 0:
            PROM_AUTOMATED_DECISIONS.labels(action_type="automated").inc(auto_count)

        # ── IoT events (by device_id:event_type) ────────────────────────
        for key, count in restore_data.get("iot_events_by_type", {}).items():
            parts = key.split(":")
            if len(parts) == 2:
                device_id, event_type = parts
                PROM_IOT_EVENTS_TOTAL.labels(device_id=device_id, event_type=event_type).inc(count)

        logger.info(
            f"🔄 Prometheus counters restored: "
            f"{total_processed} alerts, {critical_count} critical, "
            f"{len(restore_data.get('actions_executed', {}))} action types"
        )
    except Exception as e:
        logger.error(f"❌ Could not restore Prometheus counters: {e}", exc_info=True)


def _init_iot_from_db():
    """Pre-load existing IoT devices from the database into the in-memory
    ``iot_devices`` dict so the dashboard shows them immediately on restart.
    """
    try:
        devices = db.get_iot_devices()
        for device in devices:
            _state.iot_devices[device["device_id"]] = dict(device)
        logger.info(f"📡 Loaded {len(devices)} IoT devices from DB")
    except Exception as e:
        logger.warning(f"Could not load IoT devices from DB: {e}")


# Run synchronous init at import time so metric values are ready before
# the first request arrives.
_init_metrics_from_db()
_init_iot_from_db()
# Default automation mode is "assisted" (requires human approval for
# high-severity actions).
set_automation_mode_metric("assisted")


# ══════════════════════════════════════════════════════════════════════════════
# LIFECYCLE HOOKS
# ══════════════════════════════════════════════════════════════════════════════

@app.on_event("startup")
async def startup():
    """FastAPI startup hook — runs once when the ASGI server starts.

    Responsibilities:
        1. Log component readiness (LLM, K8s, DB).
        2. Apply data retention policy (purge old records).
        3. Restore Prometheus counters from database.
        4. Set initial gauge values (IoT devices, cache size, mode).
    """
    logger.info("🚀 Smart City IDS starting...")

    # -- Report LLM provider availability --
    if llm_manager:
        providers = llm_manager.get_available_providers()
        logger.info(f"LLM: ✅ {len(providers)} provider(s) — {', '.join(providers)}")
    else:
        logger.info("LLM: ❌ Not configured")

    # -- Report Kubernetes connectivity --
    logger.info(f"K8s: {'✅' if k8s_automation else '❌'}")

    # -- Report database storage type and counts --
    db_stats = db.get_stats()
    logger.info(
        f"💾 Storage: {db_stats['storage_type']} — "
        f"{db_stats['total_alerts']} alerts, {db_stats['iot_devices']} IoT devices"
    )

    # -- Data retention (delete alerts older than configured threshold) --
    retention = db.apply_retention()
    logger.info(f"🧹 Retention applied: {retention}")

    # -- Restore historical Prometheus counters from PostgreSQL --
    _restore_prometheus_counters()

    # -- Set initial gauge values --
    PROM_IOT_DEVICES_ACTIVE.set(db_stats.get("iot_devices", 0))
    refresh_iot_active_metric()    # live K8s pod count
    update_circuit_breaker_metrics()  # per-engine state gauges
    PROM_LLM_CACHE_SIZE.set(0)     # cache is empty at startup

    # -- Set automation mode gauge --
    set_automation_mode_metric(get_automation_mode())

    logger.info(f"🔧 Automation mode: {get_automation_mode()}")
    logger.info("📊 Prometheus metrics initialized")


@app.on_event("shutdown")
async def shutdown():
    """FastAPI shutdown hook — log final DB stats for debugging."""
    logger.info("Shutting down...")
    db_stats = db.get_stats()
    logger.info(f"Total alerts in DB: {db_stats['total_alerts']}")
    logger.info(f"Storage type: {db_stats['storage_type']}")


# ══════════════════════════════════════════════════════════════════════════════
# DEVELOPMENT ENTRY-POINT
# ══════════════════════════════════════════════════════════════════════════════
# Running ``python main.py`` starts uvicorn directly for local development.
# In production the container runs ``uvicorn main:app`` instead.
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
