"""Smart City IDS — Main Application.

FastAPI-based intrusion detection system with LLM analysis.
Production-ready with rate limiting, circuit breaker, and comprehensive monitoring.

This file is the application entry-point.  Business logic, models, and route
handlers live in the ``api/``, ``models/``, ``services/``, and
``infrastructure/`` packages.
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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── Configuration & logging ──────────────────────────────────────────────────
from config import Config

logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ── FastAPI application ──────────────────────────────────────────────────────
app = FastAPI(
    title="Smart City IDS",
    description="LLM-Driven Intrusion Detection System",
    version="1.0.0",
)

# ── Static files ─────────────────────────────────────────────────────────────
_static_candidates = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "static"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "static"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "static"),
]
STATIC_DIR = next((p for p in _static_candidates if os.path.exists(p)), None)
if STATIC_DIR:
    app.mount("/ui/static", StaticFiles(directory=STATIC_DIR), name="static")
    logger.info(f"Static files mounted: {STATIC_DIR}")

# ── Component initialisation ────────────────────────────────────────────────
from database import db  # noqa: E402
from k8s_automation import K8sAutomation  # noqa: E402
from alert_deduplicator import AlertDeduplicator  # noqa: E402
from alert_rate_limiter import AlertRateLimiter  # noqa: E402
from operator_interface import operator_interface  # noqa: E402
from infrastructure.middleware import AlertCache, RateLimiter, CircuitBreaker, RequestQueue  # noqa: E402

try:
    Config.validate()

    # ── LLM provider (prefer new plugin system, fall back to legacy) ──
    try:
        from llm_providers.manager import LLMManager
        llm_manager = LLMManager()
    except Exception as provider_init_error:
        logger.warning(
            f"Provider manager init failed, falling back to legacy: {provider_init_error}"
        )
        from llm_manager import LLMEngineManager

        class _LegacyAdapter:
            """Thin adapter so the rest of the app sees the same interface."""

            def __init__(self):
                self._m = LLMEngineManager()

            @property
            def runtime_stats(self):
                return self._m.runtime_stats

            async def analyze(self, alert_dict):
                return await self._m.analyze(alert_dict)

            def get_available_providers(self):
                return self._m.get_available_engines()

            def get_status(self):
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

    k8s_automation = K8sAutomation()

    deduplicator = AlertDeduplicator(
        ttl_seconds=int(os.getenv("DEDUPLICATOR_TTL_SECONDS", "60")),
        max_cache_size=int(os.getenv("DEDUPLICATOR_MAX_CACHE_SIZE", "10000")),
    )
    logger.info(
        f"Alert deduplicator initialized "
        f"(TTL={deduplicator.ttl}s, max_cache={deduplicator.max_cache_size})"
    )

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
    logger.error(f"Failed to initialize: {e}")
    llm_manager = None
    k8s_automation = None
    deduplicator = None
    alert_rate_limiter = None

# ── Production middleware singletons ─────────────────────────────────────────
alert_cache = AlertCache(
    max_size=Config.ALERT_CACHE_MAX_SIZE,
    ttl_seconds=Config.ALERT_CACHE_TTL_SECONDS,
)
rate_limiter = RateLimiter(
    requests_per_minute=int(os.getenv("RATE_LIMIT_PER_MINUTE", "120")),
    burst_size=int(os.getenv("RATE_LIMIT_BURST", "30")),
)
circuit_breaker = CircuitBreaker(
    failure_threshold=int(os.getenv("CIRCUIT_BREAKER_THRESHOLD", "5")),
    recovery_timeout=int(os.getenv("CIRCUIT_BREAKER_TIMEOUT", "30")),
    engines=(llm_manager.get_status().get("providers", []) if llm_manager else None),
)
request_queue = RequestQueue(
    max_queue_size=int(os.getenv("REQUEST_QUEUE_SIZE", "100")),
)

# ── Populate shared state so routers can access singletons ───────────────────
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

# ── Register API routers ─────────────────────────────────────────────────────
from api.auth import router as auth_router  # noqa: E402
from api.alerts import router as alerts_router  # noqa: E402
from api.governance import router as governance_router  # noqa: E402
from api.operator import router as operator_router  # noqa: E402
from api.llm import router as llm_router  # noqa: E402
from api.iot import router as iot_router  # noqa: E402
from api.metrics_routes import router as metrics_router  # noqa: E402
from api.health import router as health_router  # noqa: E402

app.include_router(auth_router)
app.include_router(alerts_router)
app.include_router(governance_router)
app.include_router(operator_router)
app.include_router(llm_router)
app.include_router(iot_router)
app.include_router(metrics_router)
app.include_router(health_router)


# ── Metrics initialisation ───────────────────────────────────────────────────
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
    """Load existing counts from database."""
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
    """Restore Prometheus counters from PostgreSQL to show historical data.

    Ensures Grafana displays ALL historical alerts, not just since last restart.
    """
    logger.info("🔄 Starting Prometheus counter restoration from database...")
    try:
        restore_data = db.get_prometheus_restore_data()
        logger.info(f"🔄 Got restore data: {restore_data}")

        for key, count in restore_data.get("alerts_by_source_priority", {}).items():
            parts = key.split(":")
            if len(parts) == 2:
                source, priority = parts[0], parts[1] or "Unknown"
                PROM_ALERTS_RECEIVED_TOTAL.labels(source=source, priority=priority).inc(count)

        total_processed = restore_data.get("total_processed", 0)
        if total_processed > 0:
            PROM_ALERTS_PROCESSED_TOTAL.labels(result="success").inc(total_processed)

        for severity, count in restore_data.get("alerts_by_severity", {}).items():
            PROM_SEVERITY_DISTRIBUTION.labels(severity=str(severity)).inc(count)

        for threat_type, count in restore_data.get("alerts_by_threat_type", {}).items():
            if threat_type:
                PROM_THREAT_TYPES_TOTAL.labels(threat_type=threat_type).inc(count)

        for action, count in restore_data.get("actions_executed", {}).items():
            if action:
                PROM_ACTIONS_EXECUTED_TOTAL.labels(action=action).inc(count)

        critical_count = restore_data.get("critical_alerts", 0)
        if critical_count > 0:
            PROM_CRITICAL_ALERTS_TOTAL.inc(critical_count)

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

        auto_count = sum(restore_data.get("actions_executed", {}).values())
        if auto_count > 0:
            PROM_AUTOMATED_DECISIONS.labels(action_type="automated").inc(auto_count)

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
    """Load existing IoT devices from database."""
    try:
        devices = db.get_iot_devices()
        for device in devices:
            _state.iot_devices[device["device_id"]] = dict(device)
        logger.info(f"📡 Loaded {len(devices)} IoT devices from DB")
    except Exception as e:
        logger.warning(f"Could not load IoT devices from DB: {e}")


# Run synchronous init at import time (same as before)
_init_metrics_from_db()
_init_iot_from_db()
set_automation_mode_metric("assisted")


# ── Startup / shutdown events ────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    logger.info("🚀 Smart City IDS starting...")

    if llm_manager:
        providers = llm_manager.get_available_providers()
        logger.info(f"LLM: ✅ {len(providers)} provider(s) — {', '.join(providers)}")
    else:
        logger.info("LLM: ❌ Not configured")

    logger.info(f"K8s: {'✅' if k8s_automation else '❌'}")

    db_stats = db.get_stats()
    logger.info(
        f"💾 Storage: {db_stats['storage_type']} — "
        f"{db_stats['total_alerts']} alerts, {db_stats['iot_devices']} IoT devices"
    )

    retention = db.apply_retention()
    logger.info(f"🧹 Retention applied: {retention}")

    _restore_prometheus_counters()

    PROM_IOT_DEVICES_ACTIVE.set(db_stats.get("iot_devices", 0))
    refresh_iot_active_metric()
    update_circuit_breaker_metrics()
    PROM_LLM_CACHE_SIZE.set(0)

    set_automation_mode_metric(get_automation_mode())

    logger.info(f"🔧 Automation mode: {get_automation_mode()}")
    logger.info("📊 Prometheus metrics initialized")


@app.on_event("shutdown")
async def shutdown():
    logger.info("Shutting down...")
    db_stats = db.get_stats()
    logger.info(f"Total alerts in DB: {db_stats['total_alerts']}")
    logger.info(f"Storage type: {db_stats['storage_type']}")


# ── Entrypoint ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
