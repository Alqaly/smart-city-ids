"""Smart City IDS - Main Application.

FastAPI-based intrusion detection system with LLM analysis.
Production-ready with rate limiting, circuit breaker, and comprehensive monitoring.
"""

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import Response, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, validator
from typing import List, Dict, Any, Optional, Union
import logging
from datetime import datetime
import time
import sys
import os
import hashlib
from collections import OrderedDict
import asyncio
from enum import Enum

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

# Add src directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from llm_engine_xai import XAIAnalyzer
from llm_engine_openai import OpenAIAnalyzer
from llm_engine_anthropic import AnthropicAnalyzer
from llm_engine_gemini import GeminiAnalyzer
from llm_engine_kimi import KimiAnalyzer
from k8s_automation import K8sAutomation
from database import db
from alert_deduplicator import AlertDeduplicator
from operator_interface import operator_interface
from alert_rate_limiter import AlertRateLimiter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(
    title="Smart City IDS",
    description="LLM-Driven Intrusion Detection System",
    version="1.0.0"
)

# Mount static files for UI (support dev + configmap-mounted layout)
_static_candidates = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "static"),  # repo layout
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "static"),        # packaged layout
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "static"),  # /app/static when /app points to src
]
STATIC_DIR = next((p for p in _static_candidates if os.path.exists(p)), None)
if STATIC_DIR:
    app.mount("/ui/static", StaticFiles(directory=STATIC_DIR), name="static")
    logger.info(f"Static files mounted: {STATIC_DIR}")

# Security
security = HTTPBearer()

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify API token is valid"""
    token = credentials.credentials
    if not token:
        raise HTTPException(status_code=401, detail="No token provided")
    username = verify_jwt_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return username

# Initialize components - Smart LLM Engine Management
# Supports single-engine mode (only one API key) OR multi-engine failover
try:
    Config.validate()
    
    # Initialize generic LLM provider system (preferred).
    # Fallback to legacy manager if llm_providers package isn't mounted.
    try:
        from llm_providers.manager import LLMManager
        llm_manager = LLMManager()
    except Exception as provider_init_error:
        logger.warning(f"Provider manager init failed, falling back to legacy manager: {provider_init_error}")
        from llm_manager import LLMEngineManager

        class LegacyLLMAdapter:
            def __init__(self):
                self._manager = LLMEngineManager()

            async def analyze(self, alert_dict):
                return await self._manager.analyze(alert_dict)

            def get_available_providers(self):
                return self._manager.get_available_engines()

            def get_status(self):
                providers = self._manager.get_available_engines()
                return {
                    "provider_count": len(providers),
                    "providers": providers,
                    "details": {p: {"configured": True} for p in providers},
                }

        llm_manager = LegacyLLMAdapter()
    
    # Clean logging
    logger.info(f"✅ LLM: {llm_manager.get_status()['provider_count']} provider(s) ready")
    
    k8s_automation = K8sAutomation()
    
    # Initialize alert deduplicator for LLM cost reduction
    deduplicator = AlertDeduplicator(
        ttl_seconds=int(os.getenv("DEDUPLICATOR_TTL_SECONDS", "60")),
        max_cache_size=int(os.getenv("DEDUPLICATOR_MAX_CACHE_SIZE", "10000"))
    )
    logger.info(f"Alert deduplicator initialized (TTL={deduplicator.ttl}s, max_cache={deduplicator.max_cache_size})")
    
    # Initialize alert rate limiter to prevent flooding
    alert_rate_limiter = AlertRateLimiter(
        window_seconds=int(os.getenv("ALERT_RATE_LIMIT_WINDOW", "60")),
        max_per_rule=int(os.getenv("ALERT_RATE_LIMIT_PER_RULE", "10")),
        max_per_source=int(os.getenv("ALERT_RATE_LIMIT_PER_SOURCE", "100")),
        max_global=int(os.getenv("ALERT_RATE_LIMIT_GLOBAL", "500"))
    )
    logger.info(f"Alert rate limiter initialized (window={alert_rate_limiter.window_seconds}s, per_rule={alert_rate_limiter.max_per_rule})")
    
    # Final status summary
    provider_count = llm_manager.get_status()["provider_count"]
    logger.info(f"✅ IDS API ready with {provider_count} LLM provider(s)")
    logger.info(f"Safety: mode={Config.AUTOMATION_MODE}, protected={Config.PROTECTED_SERVICES}")
except Exception as e:
    logger.error(f"Failed to initialize: {e}")
    llm_manager = None
    k8s_automation = None
    deduplicator = None
    alert_rate_limiter = None

# Alert Cache for deduplication (reduces LLM costs)
class AlertCache:
    """LRU cache for alert deduplication with TTL"""
    def __init__(self, max_size: int = 100, ttl_seconds: int = 60):
        self.cache: OrderedDict = OrderedDict()
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.hits = 0
        self.misses = 0
    
    def _get_hash(self, alert: dict) -> str:
        """Generate hash from alert rule + key output fields"""
        key = f"{alert.get('rule', '')}:{alert.get('output_fields', {}).get('proc.cmdline', '')}:{alert.get('output_fields', {}).get('container.name', '')}"
        return hashlib.md5(key.encode()).hexdigest()
    
    def get(self, alert: dict) -> Optional[dict]:
        """Get cached analysis if exists and not expired"""
        alert_hash = self._get_hash(alert)
        if alert_hash in self.cache:
            entry = self.cache[alert_hash]
            if time.time() - entry["timestamp"] < self.ttl_seconds:
                self.hits += 1
                self.cache.move_to_end(alert_hash)  # LRU update
                logger.info(f"Cache HIT for alert (hash={alert_hash[:8]})")
                return entry["analysis"]
            else:
                del self.cache[alert_hash]  # Expired
        self.misses += 1
        return None
    
    def set(self, alert: dict, analysis: dict):
        """Store analysis in cache"""
        alert_hash = self._get_hash(alert)
        if len(self.cache) >= self.max_size:
            self.cache.popitem(last=False)  # Remove oldest
        self.cache[alert_hash] = {"analysis": analysis, "timestamp": time.time()}
    
    def stats(self) -> dict:
        """Return cache statistics"""
        total = self.hits + self.misses
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(self.hits / total * 100, 1) if total > 0 else 0,
            "size": len(self.cache),
            "max_size": self.max_size
        }

# ============== RATE LIMITER ==============
class RateLimiter:
    """Token bucket rate limiter for API protection"""
    def __init__(self, requests_per_minute: int = 60, burst_size: int = 20):
        self.requests_per_minute = requests_per_minute
        self.burst_size = burst_size
        self.tokens = burst_size
        self.last_refill = time.time()
        self.total_requests = 0
        self.rejected_requests = 0
        self.lock = asyncio.Lock()
    
    async def acquire(self) -> tuple[bool, str]:
        """Try to acquire a token. Returns (allowed, reason)"""
        async with self.lock:
            now = time.time()
            # Refill tokens based on time passed
            time_passed = now - self.last_refill
            tokens_to_add = time_passed * (self.requests_per_minute / 60)
            self.tokens = min(self.burst_size, self.tokens + tokens_to_add)
            self.last_refill = now
            
            self.total_requests += 1
            
            if self.tokens >= 1:
                self.tokens -= 1
                return True, "OK"
            else:
                self.rejected_requests += 1
                return False, f"Rate limit exceeded. Max {self.requests_per_minute}/min, burst {self.burst_size}"
    
    def stats(self) -> dict:
        return {
            "requests_per_minute": self.requests_per_minute,
            "burst_size": self.burst_size,
            "current_tokens": round(self.tokens, 2),
            "total_requests": self.total_requests,
            "rejected_requests": self.rejected_requests,
            "rejection_rate": round(self.rejected_requests / self.total_requests * 100, 2) if self.total_requests > 0 else 0
        }

# ============== CIRCUIT BREAKER ==============
class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered

class CircuitBreaker:
    """Circuit breaker for LLM API resilience"""
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 30,
        half_open_max_calls: int = 3,
        engines: Optional[List[str]] = None,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0
        self.half_open_calls = 0
        
        # Track only configured providers to avoid misleading "closed/open" states.
        tracked_engines = engines or ["xai", "anthropic", "openai", "gemini", "kimi"]
        self.engine_stats = {
            engine: {"failures": 0, "successes": 0, "state": "closed"}
            for engine in tracked_engines
        }
    
    def can_execute(self, engine: str) -> tuple[bool, str]:
        """Check if we should try this engine"""
        stats = self.engine_stats.get(engine, {"failures": 0, "state": "closed"})
        
        if stats["state"] == "open":
            # Check if recovery timeout passed
            if time.time() - self.last_failure_time > self.recovery_timeout:
                stats["state"] = "half_open"
                self.half_open_calls = 0
                logger.info(f"Circuit breaker for {engine}: OPEN → HALF_OPEN")
            else:
                return False, f"Circuit OPEN for {engine} (cooling down)"
        
        if stats["state"] == "half_open":
            if self.half_open_calls >= self.half_open_max_calls:
                return False, f"Circuit HALF_OPEN max calls reached for {engine}"
            self.half_open_calls += 1
        
        return True, "OK"
    
    def record_success(self, engine: str):
        """Record successful call"""
        stats = self.engine_stats.get(engine, {"failures": 0, "successes": 0, "state": "closed"})
        stats["successes"] += 1
        stats["failures"] = 0  # Reset on success
        
        if stats["state"] == "half_open":
            stats["state"] = "closed"
            logger.info(f"Circuit breaker for {engine}: HALF_OPEN → CLOSED (recovered)")
        
        self.engine_stats[engine] = stats
    
    def record_failure(self, engine: str):
        """Record failed call"""
        stats = self.engine_stats.get(engine, {"failures": 0, "successes": 0, "state": "closed"})
        stats["failures"] += 1
        self.last_failure_time = time.time()
        
        if stats["failures"] >= self.failure_threshold:
            stats["state"] = "open"
            logger.warning(f"Circuit breaker for {engine}: → OPEN (failures={stats['failures']})")
        
        self.engine_stats[engine] = stats
    
    def get_stats(self) -> dict:
        return {
            "engines": self.engine_stats,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout_sec": self.recovery_timeout
        }

# ============== REQUEST QUEUE ==============
class RequestQueue:
    """Simple request queue for burst handling"""
    def __init__(self, max_queue_size: int = 100):
        self.max_queue_size = max_queue_size
        self.queue_size = 0
        self.total_queued = 0
        self.total_rejected = 0
        self.lock = asyncio.Lock()
    
    async def try_enqueue(self) -> tuple[bool, str]:
        """Try to add request to queue"""
        async with self.lock:
            if self.queue_size >= self.max_queue_size:
                self.total_rejected += 1
                return False, f"Queue full ({self.max_queue_size} max)"
            self.queue_size += 1
            self.total_queued += 1
            return True, "OK"
    
    async def dequeue(self):
        """Remove request from queue"""
        async with self.lock:
            if self.queue_size > 0:
                self.queue_size -= 1
    
    def stats(self) -> dict:
        return {
            "current_size": self.queue_size,
            "max_size": self.max_queue_size,
            "total_queued": self.total_queued,
            "total_rejected": self.total_rejected
        }

# Initialize production components
alert_cache = AlertCache(
    max_size=Config.ALERT_CACHE_MAX_SIZE,
    ttl_seconds=Config.ALERT_CACHE_TTL_SECONDS
)
rate_limiter = RateLimiter(
    requests_per_minute=int(os.getenv("RATE_LIMIT_PER_MINUTE", "120")),
    burst_size=int(os.getenv("RATE_LIMIT_BURST", "30"))
)
circuit_breaker = CircuitBreaker(
    failure_threshold=int(os.getenv("CIRCUIT_BREAKER_THRESHOLD", "5")),
    recovery_timeout=int(os.getenv("CIRCUIT_BREAKER_TIMEOUT", "30")),
    engines=(llm_manager.get_status().get("providers", []) if llm_manager else None),
)
request_queue = RequestQueue(
    max_queue_size=int(os.getenv("REQUEST_QUEUE_SIZE", "100"))
)

def is_protected_service(container_name: str) -> bool:
    """Check if a service is protected from automated actions"""
    if not container_name:
        return False
    for protected in Config.PROTECTED_SERVICES:
        if protected.lower() in container_name.lower():
            return True
    return False

def can_execute_action(action: str, container_name: str) -> tuple[bool, str]:
    """Check if an automated action can be executed based on safety controls"""
    # Check automation mode
    if Config.AUTOMATION_MODE == "dry-run":
        return False, f"DRY-RUN: Would execute {action} on {container_name}"
    
    if Config.AUTOMATION_MODE == "approval-required":
        return False, f"APPROVAL-REQUIRED: {action} on {container_name} needs manual approval"
    
    # Check protected services
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

def set_automation_mode_metric(mode: str):
    """Set automation mode gauge with normalized labels."""
    for label in ("autopilot", "assisted", "manual"):
        PROM_AUTOMATION_MODE.labels(mode=label).set(1 if label == mode else 0)

def update_circuit_breaker_metrics():
    """Update Prometheus metrics for circuit breaker states"""
    state_map = {"closed": 0, "half_open": 1, "open": 2, "unconfigured": 3}
    configured = set(circuit_breaker.engine_stats.keys())
    all_engines = ["xai", "anthropic", "openai", "gemini", "kimi"]

    for engine in all_engines:
        if engine in configured:
            stats = circuit_breaker.engine_stats.get(engine, {})
            state_val = state_map.get(stats.get("state", "closed"), 0)
        else:
            state_val = state_map["unconfigured"]
        PROM_CIRCUIT_BREAKER_STATE.labels(engine=engine).set(state_val)

def detect_alert_source(alert: "Alert") -> str:
    """Determine alert source using robust fields (not just rule text)."""
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

# Cache for refresh_iot_active_metric to avoid blocking event loop
# Pre-seed with 0 and expired cache so first call computes real count instantly
# (Safe now — K8s API calls removed, only fast local counting)
_iot_metric_cache = {"value": 0, "last_refresh": 0.0, "k8s_fail_until": 0.0}

# Known IoT deployments (from k8s-manifests) - used as baseline when K8s API is unreachable
_KNOWN_IOT_REPLICAS = 26  # 10 enhanced + 4 high + 5 medium + 1 burst + 2 cam + 2 health + 2 parking

def refresh_iot_active_metric() -> int:
    """Keep IoT active gauge accurate even when simulators don't hit /api/iot/sensor.
    Uses caching (120s TTL) to avoid blocking the async event loop with K8s API calls.
    Falls back to known deployment replica count when no devices have registered."""
    now = time.time()
    # Return cached value if refreshed within last 120 seconds
    if now - _iot_metric_cache["last_refresh"] < 120:
        return _iot_metric_cache["value"]

    db_count = db.get_iot_device_count()
    mem_count = len(iot_devices) if "iot_devices" in globals() else 0

    # Use known replica count as baseline when neither DB nor memory has devices
    # (K8s API is unreachable from pods so we can't count pods directly)
    active_count = max(db_count, mem_count, _KNOWN_IOT_REPLICAS)
    PROM_IOT_DEVICES_ACTIVE.set(active_count)
    _iot_metric_cache["value"] = active_count
    _iot_metric_cache["last_refresh"] = now
    return active_count

async def analyze_with_fallback(alert_dict: dict) -> tuple[dict, str, float]:
    """
    Analyze alert using unified LLM Manager.
    
    The provider-based LLMManager handles ALL cases uniformly:
    - 1 engine: Direct call
    - 2+ engines: Try in priority order with failover
    
    This is proper engineering - NO special cases for engine count.
    
    Uses cache for cost reduction.
    """
    
    # Check cache first (reduces LLM costs)
    cached = alert_cache.get(alert_dict)
    if cached:
        PROM_LLM_CACHE_OPERATIONS.labels(operation="hit").inc()
        PROM_LLM_CACHE_SIZE.set(len(alert_cache.cache))
        return cached, "cache", 0.0
    
    PROM_LLM_CACHE_OPERATIONS.labels(operation="miss").inc()
    
    # Use unified LLM Manager - handles any number of engines
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
        return analysis, engine_used, llm_duration
    
    # All engines failed
    error_msg = result.get("error", "Unknown error")
    for failed_engine in failed_engines:
        if failed_engine in circuit_breaker.engine_stats:
            circuit_breaker.record_failure(failed_engine)
    if engine_used in circuit_breaker.engine_stats:
        circuit_breaker.record_failure(engine_used)
    update_circuit_breaker_metrics()
    PROM_LLM_REQUESTS_TOTAL.labels(engine=engine_used, result="error").inc()
    raise Exception(f"LLM analysis failed: {error_msg}")

# Storage - Using database for persistence (alerts_db kept for backward compatibility)
alerts_db: List[Dict[str, Any]] = []  # In-memory cache, synced with database
metrics = {
    "total_alerts": 0,
    "critical_alerts": 0,
    "alerts_by_source": {"falco": 0, "suricata": 0},
    "automated_actions": 0,
    "started_at": datetime.now().isoformat(),
    "uptime_seconds": 0,
    "automation_rate": 0,
    "alert_reduction_percentage": 100,
    "avg_response_time_seconds": 3.5
}

# Initialize metrics from database on startup
def init_metrics_from_db():
    """Load existing counts from database."""
    global metrics
    try:
        stats = db.get_stats()
        metrics["total_alerts"] = stats.get("total_alerts", 0)
        metrics["alerts_by_source"] = stats.get("alerts_by_source", {"falco": 0, "suricata": 0})
        logger.info(f"📊 Loaded metrics from DB: {stats['total_alerts']} alerts, storage: {stats['storage_type']}")
    except Exception as e:
        logger.warning(f"Could not load metrics from DB: {e}")

# Load on startup
init_metrics_from_db()

# Prometheus counter restoration function (called after counters are defined)
def restore_prometheus_counters():
    """Restore Prometheus counters from PostgreSQL to show historical data.
    
    This ensures Grafana displays ALL historical alerts, not just since last restart.
    Critical for demonstrating weeks of work to supervisors.
    """
    logger.info("🔄 Starting Prometheus counter restoration from database...")
    try:
        restore_data = db.get_prometheus_restore_data()
        logger.info(f"🔄 Got restore data: {restore_data}")
        
        # Restore alerts received by source/priority
        for key, count in restore_data.get("alerts_by_source_priority", {}).items():
            parts = key.split(":")
            if len(parts) == 2:
                source, priority = parts[0], parts[1] or "Unknown"
                # Use inc() with the count value to restore the counter
                PROM_ALERTS_RECEIVED_TOTAL.labels(source=source, priority=priority).inc(count)
                logger.info(f"  ✓ Restored alerts_received: {source}/{priority} = {count}")
        
        # Restore processed alerts count
        total_processed = restore_data.get("total_processed", 0)
        if total_processed > 0:
            PROM_ALERTS_PROCESSED_TOTAL.labels(result="success").inc(total_processed)
            logger.info(f"  ✓ Restored alerts_processed: success = {total_processed}")
        
        # Restore severity distribution
        for severity, count in restore_data.get("alerts_by_severity", {}).items():
            PROM_SEVERITY_DISTRIBUTION.labels(severity=str(severity)).inc(count)
        
        # Restore threat types
        for threat_type, count in restore_data.get("alerts_by_threat_type", {}).items():
            if threat_type:
                PROM_THREAT_TYPES_TOTAL.labels(threat_type=threat_type).inc(count)
        
        # Restore actions executed
        for action, count in restore_data.get("actions_executed", {}).items():
            if action:
                PROM_ACTIONS_EXECUTED_TOTAL.labels(action=action).inc(count)
                logger.info(f"  ✓ Restored actions: {action} = {count}")
        
        # Set critical alerts gauge
        critical_count = restore_data.get("critical_alerts", 0)
        if critical_count > 0:
            PROM_CRITICAL_ALERTS_TOTAL.inc(critical_count)
        
        # Restore LLM decision outcomes based on severity
        # Malicious: severity >= 8, Suspicious: severity 5-7, Benign: severity < 5
        malicious = restore_data.get("alerts_by_severity", {}).get("8", 0) + \
                    restore_data.get("alerts_by_severity", {}).get("9", 0) + \
                    restore_data.get("alerts_by_severity", {}).get("10", 0)
        suspicious = restore_data.get("alerts_by_severity", {}).get("5", 0) + \
                     restore_data.get("alerts_by_severity", {}).get("6", 0) + \
                     restore_data.get("alerts_by_severity", {}).get("7", 0)
        benign = total_processed - malicious - suspicious
        if malicious > 0:
            PROM_LLM_DECISION_OUTCOME.labels(outcome="malicious").inc(malicious)
        if suspicious > 0:
            PROM_LLM_DECISION_OUTCOME.labels(outcome="suspicious").inc(suspicious)
        if benign > 0:
            PROM_LLM_DECISION_OUTCOME.labels(outcome="benign").inc(max(0, benign))
        logger.info(f"  ✓ Restored LLM decisions: malicious={malicious}, suspicious={suspicious}, benign={max(0, benign)}")
        
        # Restore automated decision counts (isolate_pod + scale_up = automated)
        auto_count = sum(restore_data.get("actions_executed", {}).values())
        if auto_count > 0:
            PROM_AUTOMATED_DECISIONS.labels(action_type="automated").inc(auto_count)
        
        # Restore IoT events
        for key, count in restore_data.get("iot_events_by_type", {}).items():
            parts = key.split(":")
            if len(parts) == 2:
                device_id, event_type = parts
                PROM_IOT_EVENTS_TOTAL.labels(device_id=device_id, event_type=event_type).inc(count)
        
        logger.info(f"🔄 Prometheus counters restored from DB: "
                   f"{total_processed} alerts, {critical_count} critical, "
                   f"{len(restore_data.get('actions_executed', {}))} action types")
    except Exception as e:
        logger.error(f"❌ Could not restore Prometheus counters: {e}", exc_info=True)

# Prometheus metrics
# ============== CORE ALERT METRICS ==============
PROM_ALERTS_RECEIVED_TOTAL = Counter(
    "smartcity_ids_alerts_received_total",
    "Total number of alerts received by the IDS API.",
    ["source", "priority"],
)
PROM_ALERTS_PROCESSED_TOTAL = Counter(
    "smartcity_ids_alerts_processed_total",
    "Total number of alerts processed by the IDS API, labeled by result.",
    ["result"],
)
PROM_ACTIONS_EXECUTED_TOTAL = Counter(
    "smartcity_ids_actions_executed_total",
    "Total number of automated actions triggered by the IDS API.",
    ["action"],
)
PROM_ACTIONS_BLOCKED_TOTAL = Counter(
    "smartcity_ids_actions_blocked_total",
    "Total number of automated actions blocked by safety controls.",
    ["action", "reason"],
)
PROM_ALERT_PROCESSING_SECONDS = Histogram(
    "smartcity_ids_alert_processing_seconds",
    "End-to-end IDS API /api/alerts processing duration (seconds).",
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 3, 5, 8, 13, 21),
)
PROM_UPTIME_SECONDS = Gauge(
    "smartcity_ids_uptime_seconds",
    "IDS API process uptime in seconds.",
)

# ============== LLM ANALYSIS METRICS ==============
PROM_LLM_REQUESTS_TOTAL = Counter(
    "smartcity_ids_llm_requests_total",
    "Total LLM API requests by engine and result.",
    ["engine", "result"],
)
PROM_LLM_LATENCY_SECONDS = Histogram(
    "smartcity_ids_llm_latency_seconds",
    "LLM API call latency in seconds.",
    ["engine"],
    buckets=(0.5, 1, 2, 3, 5, 8, 10, 15, 20, 30),
)
PROM_LLM_CACHE_OPERATIONS = Counter(
    "smartcity_ids_llm_cache_total",
    "LLM cache operations (hits/misses).",
    ["operation"],
)
PROM_LLM_CACHE_SIZE = Gauge(
    "smartcity_ids_llm_cache_size",
    "Current number of cached LLM responses.",
)

# ============== SECURITY ANALYSIS METRICS ==============
PROM_SEVERITY_DISTRIBUTION = Counter(
    "smartcity_ids_severity_total",
    "Distribution of alert severities (1-10).",
    ["severity"],
)
PROM_THREAT_TYPES_TOTAL = Counter(
    "smartcity_ids_threat_types_total",
    "Count of detected threat types.",
    ["threat_type"],
)
PROM_CRITICAL_ALERTS_TOTAL = Counter(
    "smartcity_ids_critical_alerts_total",
    "Total number of critical alerts observed (severity >= 8).",
)

# ============== LLM DECISION & GOVERNANCE METRICS ==============
PROM_LLM_DECISION_OUTCOME = Counter(
    "smartcity_ids_llm_decision_outcome_total",
    "LLM decision outcomes (benign, suspicious, malicious).",
    ["outcome"],
)
PROM_AUTOMATED_DECISIONS = Counter(
    "smartcity_ids_automated_decisions_total",
    "Decisions made automatically by the system.",
    ["action_type"],
)
PROM_HUMAN_OVERRIDE_REQUESTS = Counter(
    "smartcity_ids_human_override_requests_total",
    "Actions flagged for human review.",
    ["reason"],
)
PROM_ACTIONS_BLOCKED_POLICY = Counter(
    "smartcity_ids_actions_blocked_policy_total",
    "Automated actions blocked by policy rules.",
    ["policy", "action"],
)
PROM_TIME_TO_MITIGATION = Histogram(
    "smartcity_ids_time_to_mitigation_seconds",
    "Time from alert detection to automated mitigation action.",
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300),
)
PROM_LLM_FAILOVER_COUNT = Counter(
    "smartcity_ids_llm_failover_total",
    "Number of times LLM failed over to backup engine.",
    ["from_engine", "to_engine"],
)

# ============== IOT DEVICE METRICS ==============
PROM_IOT_EVENTS_TOTAL = Counter(
    "smartcity_ids_iot_events_total",
    "Total IoT sensor events received.",
    ["device_id", "event_type"],
)
PROM_IOT_DEVICES_ACTIVE = Gauge(
    "smartcity_ids_iot_devices_active",
    "Number of active IoT devices.",
)
PROM_IOT_LATENCY_SECONDS = Histogram(
    "smartcity_ids_iot_latency_seconds",
    "Latency from IoT event to IDS processing (seconds).",
    ["device_type"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
)
PROM_IOT_EVENTS_PER_DEVICE = Counter(
    "smartcity_ids_iot_events_per_device_total",
    "Event count per IoT device for bar chart visualization.",
    ["device_id", "device_type"],
)
PROM_IOT_SECURITY_EVENTS = Counter(
    "smartcity_ids_iot_security_events_total",
    "Security events from IoT devices.",
    ["device_id", "event_type"],
)
PROM_IOT_DEVICE_HEARTBEATS = Counter(
    "smartcity_ids_iot_heartbeats_total",
    "Heartbeat signals received from IoT devices.",
    ["device_id", "device_type"],
)

# ============== KUBERNETES AUTOMATION METRICS ==============
PROM_K8S_PODS_ISOLATED_TOTAL = Counter(
    "smartcity_ids_k8s_pods_isolated_total",
    "Total number of pod isolation actions executed.",
)
PROM_K8S_SCALE_OPERATIONS = Counter(
    "smartcity_ids_k8s_scale_operations_total",
    "Kubernetes scaling operations performed.",
    ["operation", "service"],
)
PROM_PROTECTED_SERVICE_HITS = Counter(
    "smartcity_ids_protected_service_hits_total",
    "Attempts to isolate protected services (blocked).",
    ["service"],
)

# ============== SYSTEM HEALTH METRICS ==============
PROM_API_REQUESTS_TOTAL = Counter(
    "smartcity_ids_api_requests_total",
    "Total API requests by endpoint and status.",
    ["endpoint", "method", "status"],
)
PROM_AUTOMATION_MODE = Gauge(
    "smartcity_ids_automation_mode",
    "Current automation mode indicator.",
    ["mode"],  # mode=active, mode=dry_run
)

# ============== PRODUCTION RESILIENCE METRICS ==============
PROM_RATE_LIMIT_REQUESTS = Counter(
    "smartcity_ids_rate_limit_requests_total",
    "Rate limiter requests by result.",
    ["result"],  # allowed, rejected
)
PROM_RATE_LIMIT_TOKENS = Gauge(
    "smartcity_ids_rate_limit_tokens_available",
    "Current available rate limit tokens.",
)
PROM_CIRCUIT_BREAKER_STATE = Gauge(
    "smartcity_ids_circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=half_open, 2=open).",
    ["engine"],
)
PROM_CIRCUIT_BREAKER_TRIPS = Counter(
    "smartcity_ids_circuit_breaker_trips_total",
    "Circuit breaker trip events.",
    ["engine"],
)
PROM_REQUEST_QUEUE_SIZE = Gauge(
    "smartcity_ids_request_queue_size",
    "Current request queue size.",
)
PROM_REQUEST_QUEUE_REJECTED = Counter(
    "smartcity_ids_request_queue_rejected_total",
    "Requests rejected due to full queue.",
)
PROM_PROTECTION_BYPASS_ATTEMPTS = Counter(
    "smartcity_ids_protection_bypass_attempts_total",
    "Attempts to bypass protection controls.",
    ["service", "action"],
)
PROM_AUTH_FAILURES = Counter(
    "smartcity_ids_auth_failures_total",
    "Authentication failures.",
    ["reason"],
)
PROM_LLM_CREDITS_REMAINING = Gauge(
    "smartcity_ids_llm_credits_remaining",
    "Estimated LLM API credits remaining (if available).",
    ["engine"],
)
PROM_APPROVAL_PENDING = Gauge(
    "smartcity_ids_approval_pending_count",
    "Number of actions pending approval.",
)

# ============== DATA QUALITY METRICS ==============
PROM_UNIQUE_ALERTS_FAILED = Gauge(
    "smartcity_ids_unique_alerts_failed_total",
    "Unique alerts that failed processing (not retry attempts).",
)
PROM_FALSE_POSITIVES_FILTERED = Counter(
    "smartcity_ids_false_positives_filtered_total",
    "Alerts filtered as false positives.",
    ["rule"],
)
PROM_DEDUP_HIT_RATE = Gauge(
    "smartcity_ids_dedup_hit_rate_percent",
    "Alert deduplication cache hit rate (percent).",
)
PROM_ALERTS_THROTTLED_TOTAL = Counter(
    "smartcity_ids_alerts_throttled_total",
    "Alerts throttled by rate limiter to prevent flooding.",
    ["reason"],
)

# Track unique failed alerts (not inflated by retries)
_unique_failed_alerts = set()


async def track_unique_failure(alert_hash: str) -> bool:
    """
    Track unique alert failures (not retry attempts).
    Returns True if this is a NEW unique failure, False if already tracked.
    """
    if alert_hash in _unique_failed_alerts:
        return False  # Already tracked
    
    _unique_failed_alerts.add(alert_hash)
    PROM_UNIQUE_ALERTS_FAILED.set(len(_unique_failed_alerts))
    return True

# ============== RESTORE HISTORICAL DATA ON STARTUP ==============
# This ensures Grafana shows ALL historical data, not just since last restart
# Note: Moved to FastAPI startup event for proper initialization order
print("📊 Prometheus metrics defined, restoration will happen on startup event...")

# Initialize automation mode gauge (normalized labels)
set_automation_mode_metric("assisted")

# Models
class Alert(BaseModel):
    output: str = Field(..., min_length=1, max_length=2048, description="Alert message")
    priority: str = Field(..., description="Alert priority level")
    rule: str = Field(..., min_length=1, max_length=512, description="Triggered rule")
    time: str = Field(..., description="ISO format timestamp")
    output_fields: Dict[str, Any] = Field(default_factory=dict, description="Extra fields")
    
    @validator('priority')
    def validate_priority(cls, v):
        allowed = {"Emergency", "Alert", "Critical", "Error", "Warning", "Notice", "Informational", "Debug"}
        if v not in allowed:
            raise ValueError(f'priority must be one of {allowed}')
        return v
    
    @validator('time')
    def validate_time(cls, v):
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
        except ValueError:
            raise ValueError('time must be ISO format')
        return v
    
    @validator('output_fields')
    def validate_fields_count(cls, v):
        if len(v) > 50:
            raise ValueError('output_fields cannot have more than 50 items')
        return v

class AlertResponse(BaseModel):
    status: str
    alert_id: Union[int, str]
    analysis: Optional[Dict[str, Any]] = None
    actions_taken: Optional[List[str]] = None
    error: Optional[str] = None

@app.get("/")
async def root():
    return {
        "service": "Smart City IDS",
        "version": "1.0.0",
        "status": "operational",
        "llm": "Multi-provider LLM manager (priority + failover)",
        "endpoints": ["/health", "/api/alerts (GET/POST)", "/api/metrics", "/metrics", "/api/auth/login", "/api/operator/*"],
        "ui": "http://localhost:8000/ui"
    }

@app.get("/ui")
async def serve_ui():
    """Serve the operator dashboard UI"""
    if STATIC_DIR:
        ui_file = os.path.join(STATIC_DIR, "index.html")
        if os.path.exists(ui_file):
            return FileResponse(ui_file, media_type="text/html")
    return {
        "message": "UI not found",
        "path": os.path.join(STATIC_DIR or "missing-static-dir", "index.html"),
        "api_endpoints": [
            "GET /api/operator/incidents",
            "GET /api/operator/incident/{id}",
            "GET /api/operator/evidence/{id}",
            "GET /api/operator/reasoning/{id}",
            "GET /api/operator/metrics"
        ]
    }

# ============================================================================
# AUTHENTICATION ENDPOINTS
# ============================================================================

class LoginRequest(BaseModel):
    """Login request model"""
    username: str
    password: str

class LoginResponse(BaseModel):
    """Login response with JWT token"""
    access_token: str
    token_type: str = "bearer"
    user: str

def create_jwt_token(username: str) -> str:
    """Create simple JWT token (demo purposes - use proper JWT in production)"""
    import jwt
    from datetime import datetime, timedelta
    
    payload = {
        "user": username,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=24)
    }
    try:
        token = jwt.encode(payload, Config.SECRET_KEY, algorithm="HS256")
        return token
    except:
        # Fallback if PyJWT not available
        import base64
        return base64.b64encode(f"{username}:{int(datetime.utcnow().timestamp())}".encode()).decode()

def verify_jwt_token(token: str) -> str:
    """Verify JWT token and return username"""
    try:
        import jwt
        payload = jwt.decode(token, Config.SECRET_KEY, algorithms=["HS256"])
        return payload.get("user", "unknown")
    except:
        # Fallback verification
        import base64
        try:
            decoded = base64.b64decode(token).decode()
            return decoded.split(":")[0]
        except:
            return None

@app.post("/api/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """
    Authenticate operator and return JWT token.
    
    Demo credentials:
    - username: operator
    - password: operator
    
    For production, integrate with your authentication system.
    """
    # Demo authentication (in production, check against AD/LDAP/database)
    DEMO_USERNAME = "operator"
    DEMO_PASSWORD = "operator"
    
    if request.username == DEMO_USERNAME and request.password == DEMO_PASSWORD:
        token = create_jwt_token(request.username)
        return LoginResponse(
            access_token=token,
            token_type="bearer",
            user=request.username
        )
    else:
        raise HTTPException(status_code=401, detail="Invalid credentials")

@app.post("/api/auth/logout")
async def logout(request: Request):
    """Logout operator (invalidate token on client side)"""
    # In production, you might want to blacklist the token
    return {"message": "Logged out successfully"}

def require_auth(token: str = None) -> str:
    """Dependency to verify authentication token"""
    if not token:
        raise HTTPException(status_code=401, detail="No token provided")
    
    username = verify_jwt_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    return username

@app.get("/health")
async def health():
    uptime = (datetime.now() - datetime.fromisoformat(metrics["started_at"])).total_seconds()
    PROM_UPTIME_SECONDS.set(uptime)
    
    # Build LLM provider status - generic, works with any provider
    llm_status = {}
    if llm_manager:
        status = llm_manager.get_status()
        for name, details in status.get("details", {}).items():
            cb_stats = circuit_breaker.engine_stats.get(name, {})
            cb_state = cb_stats.get("state", "unknown")
            failures = cb_stats.get("failures", 0)
            successes = cb_stats.get("successes", 0)
            llm_status[name] = f"configured (circuit: {cb_state}, ok={successes}, fail={failures})"
    
    # Check database connection
    db_status = "postgresql" if not db.use_memory else "memory-fallback"
    
    # Get Suricata forwarder status (check if target is up via config)
    suricata_status = "enabled" if Config.SURICATA_ENABLED else "disabled"
    
    return {
        "status": "healthy",
        "components": {
            "llm_providers": llm_status,
            "kubernetes": "connected" if k8s_automation else "disconnected",
            "database": db_status,
            "falco": "enabled" if Config.FALCO_ENABLED else "disabled",
            "suricata": suricata_status
        },
        "llm_provider_count": llm_manager.get_status()["provider_count"] if llm_manager else 0,
        "circuit_breaker_states": {k: v.get("state", "unknown") for k, v in circuit_breaker.engine_stats.items()},
        "uptime_seconds": uptime,
        "total_alerts_processed": metrics["total_alerts"],
        "storage_type": db_status
    }

@app.get("/api/safety")
async def get_safety_status():
    """Get safety controls status - for demo verification"""
    return {
        "automation_mode": Config.AUTOMATION_MODE,
        "protected_services": Config.PROTECTED_SERVICES,
        "cache_stats": alert_cache.stats(),
        "thresholds": {
            "critical_severity": Config.CRITICAL_SEVERITY_THRESHOLD,
            "high_severity": Config.HIGH_SEVERITY_THRESHOLD
        },
        "note": "Set AUTOMATION_MODE=dry-run for safe demos"
    }

@app.get("/api/production-status")
async def get_production_status():
    """Get production controls status - for monitoring and Grafana"""
    return {
        "rate_limiter": rate_limiter.stats(),
        "circuit_breaker": circuit_breaker.get_stats(),
        "request_queue": request_queue.stats(),
        "cache": alert_cache.stats(),
        "protected_services": Config.PROTECTED_SERVICES,
        "automation_mode": Config.AUTOMATION_MODE,
        "health": {
            "rate_limit_healthy": rate_limiter.rejected_requests < rate_limiter.total_requests * 0.1 if rate_limiter.total_requests > 0 else True,
            "circuit_breakers_healthy": all(s["state"] != "open" for s in circuit_breaker.engine_stats.values()),
            "queue_healthy": request_queue.queue_size < request_queue.max_queue_size * 0.8
        }
    }

@app.post("/api/circuit-breaker/reset")
async def reset_circuit_breakers(engine: str = None):
    """Reset circuit breakers to allow LLM engines to retry.
    
    Args:
        engine: Optional specific engine to reset (xai, anthropic, openai, gemini, kimi).
                If not specified, resets all circuit breakers.
    
    Use this after:
    - Fixing API key issues
    - Rate limit cooldown period has passed
    - Network issues resolved
    """
    engines_to_reset = [engine] if engine else list(circuit_breaker.engine_stats.keys())
    reset_results = {}
    
    for eng in engines_to_reset:
        if eng in circuit_breaker.engine_stats:
            old_state = circuit_breaker.engine_stats[eng]["state"]
            circuit_breaker.engine_stats[eng] = {
                "failures": 0,
                "successes": 0,
                "state": "closed"
            }
            reset_results[eng] = f"{old_state} → closed"
            logger.info(f"Circuit breaker reset: {eng} ({old_state} → closed)")
        else:
            reset_results[eng] = "not found"
    
    update_circuit_breaker_metrics()
    
    return {
        "status": "success",
        "message": f"Reset {len([r for r in reset_results.values() if 'closed' in r])} circuit breaker(s)",
        "results": reset_results,
        "current_states": {k: v.get("state", "unknown") for k, v in circuit_breaker.engine_stats.items()}
    }

@app.get("/api/circuit-breaker/status")
async def get_circuit_breaker_status():
    """Get detailed circuit breaker status for all LLM engines."""
    return {
        "engines": circuit_breaker.engine_stats,
        "failure_threshold": circuit_breaker.failure_threshold,
        "recovery_timeout_seconds": circuit_breaker.recovery_timeout,
        "summary": {
            "total_engines": len(circuit_breaker.engine_stats),
            "open": sum(1 for s in circuit_breaker.engine_stats.values() if s.get("state") == "open"),
            "closed": sum(1 for s in circuit_breaker.engine_stats.values() if s.get("state") == "closed"),
            "half_open": sum(1 for s in circuit_breaker.engine_stats.values() if s.get("state") == "half_open")
        }
    }


@app.get("/api/llm/status")
async def get_llm_status(user: str = Depends(verify_token)):
    """
    Get LLM provider status.
    
    Shows which providers are active based on valid API keys.
    Generic system - works with any provider.
    """
    if not llm_manager:
        return {
            "provider_count": 0,
            "providers": [],
            "priority_order": [p.strip() for p in Config.LLM_PRIORITY.split(",") if p.strip()],
            "details": {},
            "error": "No LLM provider configured"
        }
    return llm_manager.get_status()


@app.get("/api/rate-limiter/status")
async def get_rate_limiter_status():
    """Get alert rate limiter status and statistics."""
    if not alert_rate_limiter:
        return {"error": "Rate limiter not initialized"}
    
    stats = alert_rate_limiter.get_stats()
    return {
        "config": {
            "window_seconds": alert_rate_limiter.window_seconds,
            "max_per_rule": alert_rate_limiter.max_per_rule,
            "max_per_source": alert_rate_limiter.max_per_source,
            "max_global": alert_rate_limiter.max_global
        },
        "stats": {
            "total_received": stats.total_received,
            "total_throttled": stats.total_throttled,
            "total_processed": stats.total_processed,
            "throttle_rate_percent": round(stats.throttle_rate * 100, 2),
            "throttle_reasons": dict(stats.throttle_reasons)
        },
        "status": "healthy" if stats.throttle_rate < 0.5 else "high_throttle_rate"
    }


@app.post("/api/rate-limiter/reset")
async def reset_rate_limiter():
    """Reset rate limiter counters (admin use only)."""
    if not alert_rate_limiter:
        return {"error": "Rate limiter not initialized"}
    
    alert_rate_limiter.reset()
    logger.info("Alert rate limiter reset by admin request")
    return {"status": "success", "message": "Rate limiter counters reset"}


# ============== HUMAN-IN-THE-LOOP GOVERNANCE API ==============
# Capstone II TASK 4: Autopilot / Assisted / Manual modes

from governance import (
    governance, get_automation_mode, set_automation_mode,
    get_pending_actions, get_governance_status,
    approve_pending_action, reject_pending_action
)

@app.get("/api/governance/status")
async def governance_status(user: str = Depends(verify_token)):
    """Get Human-in-the-Loop governance status.
    
    Returns current mode (autopilot/assisted/manual), pending actions count,
    and metrics for IEEE-defensible audit trail.
    """
    return get_governance_status()

@app.get("/api/governance/mode")
async def get_mode(user: str = Depends(verify_token)):
    """Get current automation mode."""
    return {"mode": get_automation_mode()}

@app.post("/api/governance/mode")
async def change_mode(mode: str = "assisted", user: str = Depends(verify_token)):
    """Change automation mode.
    
    Args:
        mode: One of 'autopilot', 'assisted', 'manual'
        
    - AUTOPILOT: All actions execute automatically (fastest response)
    - ASSISTED: Severity >= 8 requires approval (balanced)
    - MANUAL: All actions require approval (safest)
    """
    result = set_automation_mode(mode)
    if result["status"] == "success":
        logger.info(f"Automation mode changed to: {mode}")
        set_automation_mode_metric(mode)
    return result

@app.get("/api/governance/pending")
async def list_pending_actions(user: str = Depends(verify_token)):
    """List actions pending human approval.
    
    In ASSISTED mode: only severity >= 8 actions appear here
    In MANUAL mode: all recommended actions appear here
    """
    actions = get_pending_actions()
    PROM_APPROVAL_PENDING.set(len(actions))
    return {"pending_count": len(actions), "actions": actions}

@app.post("/api/governance/approve/{action_id}")
async def approve_action(action_id: str, operator: str = "admin", comment: str = "", user: str = Depends(verify_token)):
    """Approve a pending action and execute it.
    
    Args:
        action_id: ID from /api/governance/pending
        operator: Who is approving (for audit trail)
    """
    # Find the action and get execution callback
    action = governance._pending_actions.get(action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    
    # Build execution callback based on action type
    def execute():
        if k8s_automation:
            if action.action_type == "isolate_pod":
                return k8s_automation.isolate_pod(action.target)
            elif action.action_type == "scale_up":
                return k8s_automation.scale_deployment(action.target, 3)
            elif action.action_type == "evict_pod":
                return k8s_automation.evict_pod(action.target)
        return {"success": False, "error": "K8s automation not available"}
    
    result = approve_pending_action(action_id, operator, execute, operator_comment=comment)
    
    if result.get("status") == "approved_and_executed":
        PROM_HUMAN_OVERRIDE_REQUESTS.labels(reason="approved").inc()
        PROM_AUTOMATED_DECISIONS.labels(action_type=action.action_type).inc()
        PROM_TIME_TO_MITIGATION.observe(max(0.0, time.time() - action.created_at))
        db.add_automation_action({
            "alert_id": action.alert_id,
            "action_type": action.action_type,
            "target_resource": action.target,
            "target_namespace": Config.K8S_NAMESPACE,
            "status": "approved_and_executed",
            "execution_time_ms": int(max(0.0, (time.time() - action.created_at)) * 1000),
            "mode": get_automation_mode(),
            "triggered_by": action.recommended_by,
            "operator_comment": comment,
            "created_at": datetime.fromtimestamp(action.created_at),
            "completed_at": datetime.now()
        })
    
    return result

@app.post("/api/governance/reject/{action_id}")
async def reject_action(action_id: str, operator: str = "admin", reason: str = "", user: str = Depends(verify_token)):
    """Reject a pending action.
    
    Args:
        action_id: ID from /api/governance/pending
        operator: Who is rejecting (for audit trail)
        reason: Why the action was rejected
    """
    result = reject_pending_action(action_id, operator, reason)
    
    if result.get("status") == "rejected":
        PROM_HUMAN_OVERRIDE_REQUESTS.labels(reason="rejected").inc()
        db.add_automation_action({
            "alert_id": result.get("action", {}).get("alert_id"),
            "action_type": result.get("action", {}).get("action_type"),
            "target_resource": result.get("action", {}).get("target"),
            "target_namespace": Config.K8S_NAMESPACE,
            "status": "rejected",
            "error_message": reason,
            "mode": get_automation_mode(),
            "triggered_by": result.get("action", {}).get("recommended_by"),
            "created_at": datetime.now()
        })
    
    return result

@app.get("/api/governance/history")
async def action_history(limit: int = 50, user: str = Depends(verify_token)):
    """Get recent action history for audit trail."""
    return {"history": governance.get_action_history(limit)}

# ============== OPERATOR INTERFACE API ==============
# PhD-Level Governance: Transparent, Evidence-Based, Human-Controlled

@app.get("/api/operator/incidents")
async def get_incidents_dashboard(limit: int = 50, user: str = Depends(verify_token)):
    """Operator dashboard: recent incidents with summaries and governance info.
    
    Returns:
        - Incident summaries (plain language, not technical)
        - Evidence (what Falco/Suricata actually detected)
        - Confidence scores (how certain is the analysis)
        - Reasoning (why the LLM reached this conclusion)
        - Actions (what's available, what needs approval, what's blocked)
    """
    dashboard = operator_interface.get_dashboard(limit=limit)
    return dashboard.dict()

@app.get("/api/operator/incident/{incident_id}")
async def get_incident_detail(incident_id: int, user: str = Depends(verify_token)):
    """Get detailed view of a single incident.
    
    Includes:
    - Complete incident summary
    - Full evidence from Falco/Suricata
    - LLM reasoning chain
    - Confidence score and mitigating factors
    - Available actions with governance constraints
    - Automation status (what runs automatically vs needs approval)
    """
    incident = operator_interface.get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    return incident.dict()

@app.get("/api/operator/evidence/{incident_id}")
async def get_incident_evidence(incident_id: int, user: str = Depends(verify_token)):
    """Get raw evidence for an incident.
    
    Returns original alert excerpts from Falco and Suricata,
    useful for deep-dive investigation and correlation.
    """
    incident = operator_interface.get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    return {
        "incident_id": incident_id,
        "timestamp": incident.timestamp.isoformat(),
        "evidence": [e.dict() for e in incident.evidence]
    }

@app.get("/api/operator/reasoning/{incident_id}")
async def get_incident_reasoning(incident_id: int, user: str = Depends(verify_token)):
    """Get LLM reasoning for an incident.
    
    Returns:
    - Threat classification
    - Key indicators (top signals that led to assessment)
    - Mitigating factors (why this might be false positive)
    - Confidence score and level
    - Plain English explanation
    
    This allows operators to understand AND verify the LLM's logic.
    """
    incident = operator_interface.get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    return {
        "incident_id": incident_id,
        "reasoning": incident.reasoning.dict(),
        "llm_model": incident.llm_model_used,
        "analysis_time_ms": incident.analysis_duration_ms
    }

@app.get("/api/operator/metrics")
async def get_operator_metrics(user: str = Depends(verify_token)):
    """Get operator dashboard metrics.
    
    Returns:
    - Average analysis time
    - Average confidence score
    - Operator approval/rejection rates
    - Incident volume trends
    
    Helps supervisor understand system performance and operator workload.
    """
    metrics = operator_interface.get_metrics()
    return metrics.dict()


@app.get("/api/operator/dashboard")
async def get_full_operator_dashboard(user: str = Depends(verify_token)):
    """Get comprehensive operator dashboard data.
    
    Returns:
    - Summary statistics (total, critical, pending approval)
    - Severity distribution
    - Threat type distribution
    - Recent timeline
    - Top incidents
    
    Used by the operator UI for the main dashboard view.
    """
    return operator_interface.get_full_dashboard_data()


@app.get("/api/operator/search")
async def search_incidents(
    query: str = None,
    severity_min: int = None,
    severity_max: int = None,
    threat_type: str = None,
    limit: int = 50,
    user: str = Depends(verify_token)
):
    """Search and filter incidents.
    
    Filters:
    - query: Text search in incident summary
    - severity_min/max: Filter by severity range (1-10)
    - threat_type: Filter by threat category
    - limit: Max results to return
    
    Returns matching incidents for investigation.
    """
    return operator_interface.search_incidents(
        query=query,
        severity_min=severity_min,
        severity_max=severity_max,
        threat_type=threat_type,
        limit=limit
    )


# ============== END OPERATOR INTERFACE ==============

@app.post("/api/alerts")
async def process_alert(alert: Alert, request: Request, token = Depends(verify_token)) -> AlertResponse:
    """Process security alert with LLM (xAI Grok-4 + OpenAI fallback)"""
    
    # ========== PRODUCTION CONTROLS ==========
    # 1. Rate limiting
    rate_allowed, rate_reason = await rate_limiter.acquire()
    PROM_RATE_LIMIT_TOKENS.set(rate_limiter.tokens)
    if not rate_allowed:
        PROM_RATE_LIMIT_REQUESTS.labels(result="rejected").inc()
        logger.warning(f"Rate limit exceeded from {request.client.host}")
        raise HTTPException(status_code=429, detail=rate_reason)
    PROM_RATE_LIMIT_REQUESTS.labels(result="allowed").inc()
    
    # 2. Request queue for burst protection
    queue_ok, queue_reason = await request_queue.try_enqueue()
    PROM_REQUEST_QUEUE_SIZE.set(request_queue.queue_size)
    if not queue_ok:
        PROM_REQUEST_QUEUE_REJECTED.inc()
        logger.warning(f"Request queue full from {request.client.host}")
        raise HTTPException(status_code=503, detail=f"Server overloaded: {queue_reason}")
    
    try:
        logger.info(f"Received alert: {alert.rule} (authenticated)")
        PROM_API_REQUESTS_TOTAL.labels(endpoint="/api/alerts", method="POST", status="received").inc()

        started = time.perf_counter()
    
        metrics["total_alerts"] += 1
    
        # Determine source
        source = detect_alert_source(alert)
        metrics["alerts_by_source"][source] += 1
        PROM_ALERTS_RECEIVED_TOTAL.labels(source=source, priority=alert.priority).inc()
        
        # ========== ALERT RATE LIMITING (FLOOD PREVENTION) ==========
        # Check if this alert should be throttled to prevent LLM overload
        if alert_rate_limiter:
            should_process, throttle_reason = alert_rate_limiter.should_process(
                {"rule": alert.rule, "source": source}
            )
            if not should_process:
                # Throttled - log to database but skip LLM analysis
                logger.warning(f"Alert throttled: {alert.rule} (reason: {throttle_reason.value})")
                PROM_ALERTS_PROCESSED_TOTAL.labels(result="throttled").inc()
                PROM_ALERTS_THROTTLED_TOTAL.labels(reason=throttle_reason.value).inc()
                
                # Store throttled alert in database for audit
                db.add_throttled_alert(
                    source=source,
                    rule=alert.rule,
                    throttle_reason=throttle_reason.value,
                    raw_alert=alert.dict()
                )
                
                await request_queue.dequeue()
                return AlertResponse(
                    status="throttled",
                    alert_id=f"throttled-{int(time.time()*1000)}",
                    severity=0,
                    summary=f"Alert throttled: {throttle_reason.value}",
                    threat_type="Throttled",
                    automated_actions=[],
                    processing_time_ms=int((time.perf_counter() - started) * 1000),
                    llm_engine="none"
                )
        
        # ========== ALERT DEDUPLICATION (LLM COST REDUCTION) ==========
        # Check if this alert was recently analyzed (cache hit)
        analysis = None
        llm_used = "none"
        analysis_cached = False
        llm_latency = 0.0
        
        if deduplicator:
            should_analyze, cached_analysis = deduplicator.should_analyze(alert.dict())
            if not should_analyze and cached_analysis:
                # Cache hit: use previous analysis
                analysis = cached_analysis
                llm_used = "cached"
                analysis_cached = True
                logger.info(f"✓ Alert dedup HIT (reusing recent analysis): severity={analysis.get('severity')}")
                
                # Log deduplication metrics
                stats = deduplicator.get_stats()
                logger.debug(f"Dedup stats: hit_rate={stats['hit_rate_percent']}%, cache_size={stats['cache_size']}/{stats['max_cache_size']}")
        
        # Analyze with LLM (xAI Grok-4 primary, OpenAI fallback)
        if analysis is None:
            logger.info("Analyzing alert with LLM...")
            analysis, llm_used, llm_latency = await analyze_with_fallback(alert.dict())
            
            # Cache the analysis for future deduplication
            if deduplicator:
                deduplicator.cache_analysis(alert.dict(), analysis)
                stats = deduplicator.get_stats()
                logger.info(f"✗ Alert dedup MISS (analyzed): severity={analysis.get('severity')}, cost_estimate=${analysis.get('llm_cost', 0):.4f}")
        
        severity = analysis.get("severity", 5)
        threat_type = analysis.get("threat_type", "Unknown")
        logger.info(f"Analysis complete ({llm_used}): severity={severity}, threat={threat_type}, cached={analysis_cached}")
        
        # Track severity and threat metrics
        PROM_SEVERITY_DISTRIBUTION.labels(severity=str(severity)).inc()
        PROM_THREAT_TYPES_TOTAL.labels(threat_type=threat_type).inc()
        PROM_LLM_DECISION_OUTCOME.labels(outcome=classify_decision_outcome(severity)).inc()
        
        # Track critical alerts
        if severity >= 8:
            metrics["critical_alerts"] += 1
            PROM_CRITICAL_ALERTS_TOTAL.inc()
        
        # Execute automated actions (with safety controls)
        actions_taken = []
        action_records = []
        
        if k8s_automation and severity >= 8:
            container_name = alert.output_fields.get("container.name", "")
            if container_name:
                can_execute, reason = can_execute_action("isolate_pod", container_name)
                if can_execute:
                    logger.info(f"Critical response for {container_name}")
                    actions_taken.append("isolate_pod")
                    metrics["automated_actions"] += 1
                    PROM_ACTIONS_EXECUTED_TOTAL.labels(action="isolate_pod").inc()
                    PROM_AUTOMATED_DECISIONS.labels(action_type="isolate_pod").inc()
                    PROM_K8S_PODS_ISOLATED_TOTAL.inc()
                    PROM_TIME_TO_MITIGATION.observe(time.perf_counter() - started)
                    action_records.append({
                        "action_type": "isolate_pod",
                        "target_resource": container_name,
                        "target_namespace": Config.K8S_NAMESPACE,
                        "status": "executed",
                        "execution_time_ms": int((time.perf_counter() - started) * 1000),
                        "mode": get_automation_mode(),
                        "triggered_by": llm_used
                    })
                else:
                    logger.warning(f"Action blocked: {reason}")
                    actions_taken.append(f"BLOCKED: {reason}")
                    if "protected service" in reason.lower():
                        PROM_PROTECTED_SERVICE_HITS.labels(service=container_name.split("-")[0]).inc()
                        PROM_ACTIONS_BLOCKED_TOTAL.labels(action="isolate_pod", reason="protected_service").inc()
                        action_records.append({
                            "action_type": "isolate_pod",
                            "target_resource": container_name,
                            "target_namespace": Config.K8S_NAMESPACE,
                            "status": "blocked",
                            "error_message": reason,
                            "mode": get_automation_mode(),
                            "triggered_by": llm_used
                        })
                    elif "DRY-RUN" in reason:
                        PROM_ACTIONS_BLOCKED_TOTAL.labels(action="isolate_pod", reason="dry_run").inc()
                        action_records.append({
                            "action_type": "isolate_pod",
                            "target_resource": container_name,
                            "target_namespace": Config.K8S_NAMESPACE,
                            "status": "blocked",
                            "error_message": reason,
                            "mode": get_automation_mode(),
                            "triggered_by": llm_used
                        })
                    else:
                        PROM_ACTIONS_BLOCKED_TOTAL.labels(action="isolate_pod", reason="other").inc()
                        action_records.append({
                            "action_type": "isolate_pod",
                            "target_resource": container_name,
                            "target_namespace": Config.K8S_NAMESPACE,
                            "status": "blocked",
                            "error_message": reason,
                            "mode": get_automation_mode(),
                            "triggered_by": llm_used
                        })
        
        elif k8s_automation and severity >= 6:
            service_name = alert.output_fields.get("container.name", "").split("-")[0]
            if service_name:
                can_execute, reason = can_execute_action("scale_up", service_name)
                if can_execute:
                    logger.info(f"Scaling up {service_name}")
                    actions_taken.append("scale_up")
                    metrics["automated_actions"] += 1
                    PROM_ACTIONS_EXECUTED_TOTAL.labels(action="scale_up").inc()
                    PROM_AUTOMATED_DECISIONS.labels(action_type="scale_up").inc()
                    PROM_K8S_SCALE_OPERATIONS.labels(operation="scale_up", service=service_name).inc()
                    PROM_TIME_TO_MITIGATION.observe(time.perf_counter() - started)
                    action_records.append({
                        "action_type": "scale_up",
                        "target_resource": service_name,
                        "target_namespace": Config.K8S_NAMESPACE,
                        "status": "executed",
                        "execution_time_ms": int((time.perf_counter() - started) * 1000),
                        "mode": get_automation_mode(),
                        "triggered_by": llm_used
                    })
                else:
                    logger.warning(f"Action blocked: {reason}")
                    actions_taken.append(f"BLOCKED: {reason}")
                    PROM_ACTIONS_BLOCKED_TOTAL.labels(action="scale_up", reason="blocked").inc()
                    action_records.append({
                        "action_type": "scale_up",
                        "target_resource": service_name,
                        "target_namespace": Config.K8S_NAMESPACE,
                        "status": "blocked",
                        "error_message": reason,
                        "mode": get_automation_mode(),
                        "triggered_by": llm_used
                    })
        
        # Store alert in database
        alert_record = {
            "timestamp": alert.time,
            "source": source,
            "rule": alert.rule,
            "priority": alert.priority,
            "severity": severity,
            "summary": analysis.get("summary", ""),
            "threat_type": analysis.get("threat_type", ""),
            "recommendations": analysis.get("recommendations", []),
            "automated_actions": actions_taken,
            "raw_alert": alert.dict(),
            "analysis": analysis
        }
        alert_id = db.add_alert(alert_record)
        alert_record["id"] = alert_id

        # Persist LLM analysis results for auditability
        db.add_analysis_result(
            alert_id,
            {
                "model": llm_used,
                "analysis": analysis,
                "analysis_time_ms": int(llm_latency * 1000),
                "confidence_score": analysis.get("confidence") if isinstance(analysis, dict) else None,
                "analyzed_at": datetime.now()
            }
        )

        # Persist automation action records
        for action in action_records:
            action["alert_id"] = alert_id
            db.add_automation_action(action)
        
        # Build operator interface incident (PhD-level governance view)
        try:
            operator_incident = operator_interface.build_incident_for_operator(
                alert_id=alert_id,
                alert_data=alert.dict(),
                analysis=analysis,
                llm_model_used=llm_used,
                analysis_duration_ms=int(llm_latency * 1000),
                automation_mode=Config.AUTOMATION_MODE,
                protected_services=Config.PROTECTED_SERVICES
            )
            logger.info(f"✓ Built operator incident view: confidence={operator_incident.reasoning.confidence_score:.0%}")
        except Exception as e:
            logger.warning(f"Could not build operator incident: {e}")
        
        # Also keep in memory for quick access
        alerts_db.append(alert_record)
        
        if metrics["total_alerts"] > 0:
            metrics["automation_rate"] = (metrics["automated_actions"] / metrics["total_alerts"]) * 100

        PROM_ALERTS_PROCESSED_TOTAL.labels(result="success").inc()
        PROM_API_REQUESTS_TOTAL.labels(endpoint="/api/alerts", method="POST", status="success").inc()
        PROM_ALERT_PROCESSING_SECONDS.observe(time.perf_counter() - started)
        
        logger.info(f"✅ Alert processed: ID={alert_id}, Severity={severity}, Storage={db.get_stats()['storage_type']}")
        
        return AlertResponse(
            status="processed",
            alert_id=alert_id,
            analysis=analysis,
            actions_taken=actions_taken
        )
        
    except Exception as e:
        logger.error(f"Error: {e}")

        PROM_ALERTS_PROCESSED_TOTAL.labels(result="error").inc()
        PROM_API_REQUESTS_TOTAL.labels(endpoint="/api/alerts", method="POST", status="error").inc()
        PROM_ALERT_PROCESSING_SECONDS.observe(time.perf_counter() - started)
        
        # Store error alert in database
        alert_record = {
            "timestamp": alert.time,
            "source": source,
            "rule": alert.rule,
            "priority": alert.priority,
            "severity": 0,
            "summary": f"Error processing alert: {str(e)}",
            "threat_type": "unknown",
            "recommendations": [],
            "automated_actions": [],
            "raw_alert": alert.dict(),
            "analysis": {"error": str(e)}
        }
        alert_id = db.add_alert(alert_record)
        alert_record["id"] = alert_id
        alerts_db.append(alert_record)
        
        return AlertResponse(
            status="error",
            alert_id=alert_id,
            error=str(e)
        )
    finally:
        # Always dequeue when done
        await request_queue.dequeue()
        PROM_REQUEST_QUEUE_SIZE.set(request_queue.queue_size)

@app.post("/api/alerts/internal")
async def process_alert_internal(alert: Alert) -> AlertResponse:
    """Process security alert (no auth - cluster-internal only)"""
    logger.info(f"Received internal alert: {alert.rule}")
    PROM_API_REQUESTS_TOTAL.labels(endpoint="/api/alerts/internal", method="POST", status="received").inc()

    # Apply same protection controls as public endpoint to prevent internal flood cost spikes.
    rate_allowed, rate_reason = await rate_limiter.acquire()
    PROM_RATE_LIMIT_TOKENS.set(rate_limiter.tokens)
    if not rate_allowed:
        PROM_RATE_LIMIT_REQUESTS.labels(result="rejected").inc()
        raise HTTPException(status_code=429, detail=rate_reason)
    PROM_RATE_LIMIT_REQUESTS.labels(result="allowed").inc()

    queue_ok, queue_reason = await request_queue.try_enqueue()
    PROM_REQUEST_QUEUE_SIZE.set(request_queue.queue_size)
    if not queue_ok:
        PROM_REQUEST_QUEUE_REJECTED.inc()
        raise HTTPException(status_code=503, detail=f"Server overloaded: {queue_reason}")

    started = time.perf_counter()
    
    metrics["total_alerts"] += 1
    
    # Determine source
    source = detect_alert_source(alert)
    metrics["alerts_by_source"][source] += 1
    PROM_ALERTS_RECEIVED_TOTAL.labels(source=source, priority=alert.priority).inc()
    
    try:
        if alert_rate_limiter:
            should_process, throttle_reason = alert_rate_limiter.should_process(
                {"rule": alert.rule, "source": source}
            )
            if not should_process:
                logger.warning(f"Internal alert throttled: {alert.rule} (reason: {throttle_reason.value})")
                PROM_ALERTS_PROCESSED_TOTAL.labels(result="throttled").inc()
                PROM_ALERTS_THROTTLED_TOTAL.labels(reason=throttle_reason.value).inc()
                db.add_throttled_alert(
                    source=source,
                    rule=alert.rule,
                    throttle_reason=throttle_reason.value,
                    raw_alert=alert.dict()
                )
                return AlertResponse(
                    status="throttled",
                    alert_id=f"throttled-{int(time.time()*1000)}",
                    severity=0,
                    summary=f"Alert throttled: {throttle_reason.value}",
                    threat_type="Throttled",
                    automated_actions=[],
                    processing_time_ms=int((time.perf_counter() - started) * 1000),
                    llm_engine="none"
                )

        analysis = None
        llm_used = "none"
        llm_latency = 0.0
        if deduplicator:
            should_analyze, cached_analysis = deduplicator.should_analyze(alert.dict())
            if not should_analyze and cached_analysis:
                analysis = cached_analysis
                llm_used = "cached"
                logger.info(f"✓ Internal alert dedup HIT: severity={analysis.get('severity')}")

        if analysis is None:
            logger.info("Analyzing internal alert with LLM...")
            analysis, llm_used, llm_latency = await analyze_with_fallback(alert.dict())
            if deduplicator:
                deduplicator.cache_analysis(alert.dict(), analysis)

        severity = analysis.get("severity", 5)
        threat_type = analysis.get("threat_type", "Unknown")
        logger.info(f"Analysis complete ({llm_used}): severity={severity}, threat={threat_type}")
        
        # Track severity and threat metrics
        PROM_SEVERITY_DISTRIBUTION.labels(severity=str(severity)).inc()
        PROM_THREAT_TYPES_TOTAL.labels(threat_type=threat_type).inc()
        PROM_LLM_DECISION_OUTCOME.labels(outcome=classify_decision_outcome(severity)).inc()
        
        # Track critical alerts
        if severity >= 8:
            metrics["critical_alerts"] += 1
            PROM_CRITICAL_ALERTS_TOTAL.inc()
        
        # Execute automated actions (with safety controls)
        actions_taken = []
        action_records = []
        
        if k8s_automation and severity >= 8:
            container_name = alert.output_fields.get("container.name", "")
            if container_name:
                can_execute, reason = can_execute_action("isolate_pod", container_name)
                if can_execute:
                    logger.info(f"Critical response for {container_name}")
                    actions_taken.append("isolate_pod")
                    metrics["automated_actions"] += 1
                    PROM_ACTIONS_EXECUTED_TOTAL.labels(action="isolate_pod").inc()
                    PROM_AUTOMATED_DECISIONS.labels(action_type="isolate_pod").inc()
                    PROM_K8S_PODS_ISOLATED_TOTAL.inc()
                    PROM_TIME_TO_MITIGATION.observe(time.perf_counter() - started)
                    action_records.append({
                        "action_type": "isolate_pod",
                        "target_resource": container_name,
                        "target_namespace": Config.K8S_NAMESPACE,
                        "status": "executed",
                        "execution_time_ms": int((time.perf_counter() - started) * 1000),
                        "mode": get_automation_mode(),
                        "triggered_by": llm_used
                    })
                else:
                    logger.warning(f"Action blocked: {reason}")
                    actions_taken.append(f"BLOCKED: {reason}")
                    if "protected service" in reason.lower():
                        PROM_PROTECTED_SERVICE_HITS.labels(service=container_name.split("-")[0]).inc()
                        PROM_ACTIONS_BLOCKED_TOTAL.labels(action="isolate_pod", reason="protected_service").inc()
                        action_records.append({
                            "action_type": "isolate_pod",
                            "target_resource": container_name,
                            "target_namespace": Config.K8S_NAMESPACE,
                            "status": "blocked",
                            "error_message": reason,
                            "mode": get_automation_mode(),
                            "triggered_by": llm_used
                        })
                    elif "DRY-RUN" in reason:
                        PROM_ACTIONS_BLOCKED_TOTAL.labels(action="isolate_pod", reason="dry_run").inc()
                        action_records.append({
                            "action_type": "isolate_pod",
                            "target_resource": container_name,
                            "target_namespace": Config.K8S_NAMESPACE,
                            "status": "blocked",
                            "error_message": reason,
                            "mode": get_automation_mode(),
                            "triggered_by": llm_used
                        })
                    else:
                        PROM_ACTIONS_BLOCKED_TOTAL.labels(action="isolate_pod", reason="other").inc()
                        action_records.append({
                            "action_type": "isolate_pod",
                            "target_resource": container_name,
                            "target_namespace": Config.K8S_NAMESPACE,
                            "status": "blocked",
                            "error_message": reason,
                            "mode": get_automation_mode(),
                            "triggered_by": llm_used
                        })
        
        elif k8s_automation and severity >= 6:
            service_name = alert.output_fields.get("container.name", "").split("-")[0]
            if service_name:
                can_execute, reason = can_execute_action("scale_up", service_name)
                if can_execute:
                    logger.info(f"Scaling up {service_name}")
                    actions_taken.append("scale_up")
                    metrics["automated_actions"] += 1
                    PROM_ACTIONS_EXECUTED_TOTAL.labels(action="scale_up").inc()
                    PROM_AUTOMATED_DECISIONS.labels(action_type="scale_up").inc()
                    PROM_K8S_SCALE_OPERATIONS.labels(operation="scale_up", service=service_name).inc()
                    PROM_TIME_TO_MITIGATION.observe(time.perf_counter() - started)
                    action_records.append({
                        "action_type": "scale_up",
                        "target_resource": service_name,
                        "target_namespace": Config.K8S_NAMESPACE,
                        "status": "executed",
                        "execution_time_ms": int((time.perf_counter() - started) * 1000),
                        "mode": get_automation_mode(),
                        "triggered_by": llm_used
                    })
                else:
                    logger.warning(f"Action blocked: {reason}")
                    actions_taken.append(f"BLOCKED: {reason}")
                    PROM_ACTIONS_BLOCKED_TOTAL.labels(action="scale_up", reason="blocked").inc()
                    action_records.append({
                        "action_type": "scale_up",
                        "target_resource": service_name,
                        "target_namespace": Config.K8S_NAMESPACE,
                        "status": "blocked",
                        "error_message": reason,
                        "mode": get_automation_mode(),
                        "triggered_by": llm_used
                    })
        
        # Store alert in database
        alert_record = {
            "timestamp": alert.time,
            "source": source,
            "rule": alert.rule,
            "priority": alert.priority,
            "severity": severity,
            "summary": analysis.get("summary", ""),
            "threat_type": analysis.get("threat_type", ""),
            "recommendations": analysis.get("recommendations", []),
            "automated_actions": actions_taken,
            "raw_alert": alert.dict(),
            "analysis": analysis
        }
        alert_id = db.add_alert(alert_record)
        alert_record["id"] = alert_id

        db.add_analysis_result(
            alert_id,
            {
                "model": llm_used,
                "analysis": analysis,
                "analysis_time_ms": int(llm_latency * 1000),
                "confidence_score": analysis.get("confidence") if isinstance(analysis, dict) else None,
                "analyzed_at": datetime.now()
            }
        )

        for action in action_records:
            action["alert_id"] = alert_id
            db.add_automation_action(action)
        alerts_db.append(alert_record)
        
        if metrics["total_alerts"] > 0:
            metrics["automation_rate"] = (metrics["automated_actions"] / metrics["total_alerts"]) * 100

        PROM_ALERTS_PROCESSED_TOTAL.labels(result="success").inc()
        PROM_API_REQUESTS_TOTAL.labels(endpoint="/api/alerts/internal", method="POST", status="success").inc()
        PROM_ALERT_PROCESSING_SECONDS.observe(time.perf_counter() - started)
        
        logger.info(f"✅ Alert processed: ID={alert_id}, Severity={severity}")
        
        return AlertResponse(
            status="processed",
            alert_id=alert_id,
            analysis=analysis,
            actions_taken=actions_taken
        )
        
    except Exception as e:
        logger.error(f"Error: {e}")

        PROM_ALERTS_PROCESSED_TOTAL.labels(result="error").inc()
        PROM_API_REQUESTS_TOTAL.labels(endpoint="/api/alerts/internal", method="POST", status="error").inc()
        PROM_ALERT_PROCESSING_SECONDS.observe(time.perf_counter() - started)
        
        alert_record = {
            "timestamp": alert.time,
            "source": source,
            "rule": alert.rule,
            "priority": alert.priority,
            "severity": 0,
            "summary": f"Error: {str(e)}",
            "threat_type": "unknown",
            "recommendations": [],
            "automated_actions": [],
            "raw_alert": alert.dict(),
            "analysis": {"error": str(e)}
        }
        alert_id = db.add_alert(alert_record)
        alert_record["id"] = alert_id
        alerts_db.append(alert_record)
        
        return AlertResponse(
            status="error",
            alert_id=alert_id,
            error=str(e)
        )
    finally:
        await request_queue.dequeue()
        PROM_REQUEST_QUEUE_SIZE.set(request_queue.queue_size)

# ============== IOT SENSOR ENDPOINTS ==============

# IoT device registry (in-memory cache, backed by database)
iot_devices: Dict[str, Dict[str, Any]] = {}
iot_events: List[Dict[str, Any]] = []

# Initialize IoT data from database
def init_iot_from_db():
    """Load existing IoT devices from database."""
    global iot_devices
    try:
        devices = db.get_iot_devices()
        for device in devices:
            iot_devices[device["device_id"]] = dict(device)
        logger.info(f"📡 Loaded {len(devices)} IoT devices from DB")
    except Exception as e:
        logger.warning(f"Could not load IoT devices from DB: {e}")

init_iot_from_db()

class IoTSensorData(BaseModel):
    device_id: str = Field(..., min_length=1, max_length=64, description="Unique device identifier")
    device_type: str = Field(..., description="Type of device (motion_sensor, temperature, etc.)")
    event_type: str = Field(..., description="Event type (motion_detected, heartbeat, anomaly)")
    value: Optional[Any] = Field(None, description="Sensor value")
    timestamp: Optional[str] = Field(None, description="ISO timestamp")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)

@app.post("/api/iot/sensor")
async def receive_iot_sensor_data(data: IoTSensorData):
    """Receive sensor data from Raspberry Pi / IoT devices.
    
    This endpoint:
    1. Registers/updates device in registry
    2. Logs sensor events
    3. If event_type is 'anomaly' or suspicious, creates a security alert
    """
    logger.info(f"📡 IoT data from {data.device_id}: {data.event_type}")
    
    # Update device registry (both in database and memory)
    now = datetime.now().isoformat()
    is_new_device = db.register_iot_device(data.device_id, data.device_type, data.metadata)
    
    if data.device_id not in iot_devices or is_new_device:
        iot_devices[data.device_id] = {
            "device_id": data.device_id,
            "device_type": data.device_type,
            "first_seen": now,
            "last_seen": now,
            "event_count": 0
        }
        PROM_IOT_DEVICES_ACTIVE.set(db.get_iot_device_count())
    
    iot_devices[data.device_id]["last_seen"] = now
    iot_devices[data.device_id]["event_count"] += 1
    
    # Log event to database
    event_record = {
        "device_id": data.device_id,
        "device_type": data.device_type,
        "event_type": data.event_type,
        "value": data.value,
        "timestamp": data.timestamp or now,
        "metadata": data.metadata
    }
    event_id = db.add_iot_event(event_record)
    event_record["id"] = event_id
    iot_events.append(event_record)
    PROM_IOT_EVENTS_TOTAL.labels(device_id=data.device_id, event_type=data.event_type).inc()
    
    # Check if this is a security-relevant event
    security_events = ["anomaly", "intrusion", "tampering", "unauthorized", "rapid_motion"]
    
    # Track heartbeat events separately
    if data.event_type == "heartbeat":
        PROM_IOT_DEVICE_HEARTBEATS.labels(device_id=data.device_id, device_type=data.device_type).inc()
    
    if data.event_type in security_events:
        # Track IoT security events
        PROM_IOT_SECURITY_EVENTS.labels(device_id=data.device_id, event_type=data.event_type).inc()
        # Generate internal security alert
        logger.warning(f"🚨 Security event from IoT device: {data.event_type}")
        
        alert = Alert(
            output=f"IoT Security Event: {data.event_type} detected by {data.device_id} ({data.device_type})",
            priority="Warning" if data.event_type != "intrusion" else "Critical",
            rule=f"IoT_{data.event_type}",
            time=data.timestamp or now,
            output_fields={
                "container.name": f"iot-{data.device_id}",
                "device.id": data.device_id,
                "device.type": data.device_type,
                "event.value": str(data.value) if data.value else "",
                "source": "raspberry_pi"
            }
        )
        
        # Process as internal alert (no auth required for IoT devices)
        alert_response = await process_alert_internal(alert)
        
        return {
            "status": "security_event_processed",
            "event_id": event_record["id"],
            "alert_id": alert_response.alert_id,
            "analysis": alert_response.analysis
        }
    
    return {
        "status": "received",
        "event_id": event_record["id"],
        "device_registered": data.device_id in iot_devices
    }

@app.get("/api/iot/devices")
async def get_iot_devices():
    """List all registered IoT devices"""
    return {
        "total": len(iot_devices),
        "devices": list(iot_devices.values())
    }

@app.get("/api/iot/events")
async def get_iot_events(limit: int = 50, device_id: Optional[str] = None):
    """Get recent IoT events"""
    filtered = iot_events
    if device_id:
        filtered = [e for e in iot_events if e["device_id"] == device_id]
    return {
        "total": len(filtered),
        "showing": min(limit, len(filtered)),
        "events": filtered[-limit:]
    }

# ============== ALERT ENDPOINTS ==============

@app.get("/api/alerts")
async def get_alerts(limit: int = 10, source: Optional[str] = None):
    """Get alerts from database."""
    alerts = db.get_alerts(limit=limit, source=source)
    total = db.get_alert_count(source=source)
    return {
        "total": total,
        "showing": len(alerts),
        "storage": db.get_stats()["storage_type"],
        "alerts": alerts
    }

@app.get("/api/metrics")
async def get_metrics():
    uptime = (datetime.now() - datetime.fromisoformat(metrics["started_at"])).total_seconds()
    metrics["uptime_seconds"] = uptime
    
    # Update metrics from database
    db_stats = db.get_stats()
    metrics["total_alerts"] = db_stats["total_alerts"]
    metrics["alerts_by_source"] = db_stats["alerts_by_source"]
    metrics["storage_type"] = db_stats["storage_type"]
    
    PROM_UPTIME_SECONDS.set(uptime)
    metrics["iot_devices_active"] = refresh_iot_active_metric()
    return metrics

@app.get("/api/db/stats")
async def get_db_stats():
    """Get database statistics."""
    return db.get_stats()


@app.get("/api/deduplicator-stats")
async def get_dedup_stats(token = Depends(verify_token)):
    """Get alert deduplication cache statistics."""
    if not deduplicator:
        return {"error": "Deduplicator not initialized"}
    
    stats = deduplicator.get_stats()
    
    # Calculate estimated cost savings
    if stats["total_alerts"] > 0:
        # Estimate: $0.001 per LLM call (xAI Grok-4 pricing)
        cost_without_dedup = stats["total_alerts"] * 0.001
        cost_with_dedup = stats["misses"] * 0.001
        cost_saved = cost_without_dedup - cost_with_dedup
    else:
        cost_saved = 0
    
    return {
        **stats,
        "cost_saved_usd": round(cost_saved, 4),
        "estimated_cost_without_dedup": round(cost_without_dedup if stats["total_alerts"] > 0 else 0, 4),
        "estimated_cost_with_dedup": round(cost_with_dedup if stats["total_alerts"] > 0 else 0, 4),
    }


@app.post("/api/deduplicator/clear")
async def clear_dedup_cache(token = Depends(verify_token)):
    """Clear alert deduplication cache (administrative)."""
    if not deduplicator:
        return {"error": "Deduplicator not initialized"}
    
    stats_before = deduplicator.get_stats()
    deduplicator.clear_cache()
    
    return {
        "status": "success",
        "cleared_fingerprints": stats_before["cache_size"],
        "previous_hit_rate": f"{stats_before['hit_rate_percent']}%"
    }


@app.get("/metrics")
async def prometheus_metrics():
    """Prometheus exposition endpoint."""
    uptime = (datetime.now() - datetime.fromisoformat(metrics["started_at"])).total_seconds()
    PROM_UPTIME_SECONDS.set(uptime)
    update_circuit_breaker_metrics()
    refresh_iot_active_metric()
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.on_event("startup")
async def startup():
    logger.info("🚀 Smart City IDS starting...")
    
    # Generic LLM status
    if llm_manager:
        providers = llm_manager.get_available_providers()
        logger.info(f"LLM: ✅ {len(providers)} provider(s) - {', '.join(providers)}")
    else:
        logger.info("LLM: ❌ Not configured")
    
    logger.info(f"K8s: {'✅' if k8s_automation else '❌'}")
    
    # Database status
    db_stats = db.get_stats()
    logger.info(f"💾 Storage: {db_stats['storage_type']} - {db_stats['total_alerts']} alerts, {db_stats['iot_devices']} IoT devices")

    # Apply retention policy (alerts/iot: 30d, automation/audit: 180d)
    retention = db.apply_retention()
    logger.info(f"🧹 Retention applied: {retention}")
    
    # ============== RESTORE PROMETHEUS COUNTERS FROM DATABASE ==============
    # This ensures Grafana shows ALL historical data, not just since last restart
    # Critical for demonstrating weeks of work to supervisors
    restore_prometheus_counters()
    
    # Initialize Prometheus gauges from database
    PROM_IOT_DEVICES_ACTIVE.set(db_stats.get("iot_devices", 0))
    refresh_iot_active_metric()
    update_circuit_breaker_metrics()
    # Note: PROM_CRITICAL_ALERTS_TOTAL is restored in restore_prometheus_counters()
    PROM_LLM_CACHE_SIZE.set(0)
    
    # Set automation mode gauge from governance controller
    set_automation_mode_metric(get_automation_mode())
    
    logger.info(f"🔧 Automation mode: {get_automation_mode()}")
    logger.info(f"📊 Prometheus metrics initialized")

@app.on_event("shutdown")
async def shutdown():
    logger.info("Shutting down...")
    db_stats = db.get_stats()
    logger.info(f"Total alerts in DB: {db_stats['total_alerts']}")
    logger.info(f"Storage type: {db_stats['storage_type']}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
