"""
Smart City IDS - Comprehensive Prometheus Metrics
Capstone II Integration Plan - TASK 2

Implements ~40 metrics covering:
- Alert ingestion (by source, severity, type)
- LLM analysis (latency, success, cache)
- Automated actions (by type, outcome)
- System health (queue depth, circuit breaker)
- IoT device status (active, rates)
"""

from prometheus_client import (
    Counter, Histogram, Gauge, Summary, Info,
    generate_latest, CONTENT_TYPE_LATEST, CollectorRegistry
)
from functools import wraps
import time
import threading

# =============================================================================
# METRIC DEFINITIONS (40+ metrics per integration plan)
# =============================================================================

# -----------------------------------------------------------------------------
# ALERT INGESTION METRICS
# -----------------------------------------------------------------------------

# Counter: Total alerts received
ids_alerts_received_total = Counter(
    'ids_alerts_received_total',
    'Total number of alerts received',
    ['source', 'severity', 'rule']
)

# Counter: Alerts processed (sent to LLM)
ids_alerts_processed_total = Counter(
    'ids_alerts_processed_total',
    'Total alerts sent to LLM for analysis',
    ['source']
)

# Counter: Alerts deduplicated (cache hits)
ids_alerts_deduplicated_total = Counter(
    'ids_alerts_deduplicated_total',
    'Alerts skipped due to cache deduplication',
    ['rule']
)

# Counter: Alerts dropped (rate limited / queue full)
ids_alerts_dropped_total = Counter(
    'ids_alerts_dropped_total',
    'Alerts dropped due to rate limiting or queue overflow',
    ['reason']
)

# Gauge: Alerts in processing queue
ids_alerts_queued = Gauge(
    'ids_alerts_queued',
    'Current number of alerts waiting in queue'
)

# Histogram: Alert severity distribution
ids_alert_severity_bucket = Histogram(
    'ids_alert_severity_bucket',
    'Distribution of alert severity scores (1-10)',
    buckets=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
)

# Counter: Alerts by threat type
ids_alerts_by_threat_type_total = Counter(
    'ids_alerts_by_threat_type_total',
    'Alerts categorized by threat type',
    ['threat_type']
)

# -----------------------------------------------------------------------------
# LLM ANALYSIS METRICS
# -----------------------------------------------------------------------------

# Counter: LLM API calls
ids_llm_requests_total = Counter(
    'ids_llm_requests_total',
    'Total LLM API requests',
    ['engine', 'status']  # engine: xai-grok-4, openai; status: success, failure
)

# Histogram: LLM latency
ids_llm_latency_seconds = Histogram(
    'ids_llm_latency_seconds',
    'LLM API response time in seconds',
    ['engine'],
    buckets=[0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 15.0, 30.0]
)

# Summary: LLM latency percentiles
ids_llm_latency_summary = Summary(
    'ids_llm_latency_summary_seconds',
    'LLM latency percentiles',
    ['engine']
)

# Counter: LLM token usage (estimated)
ids_llm_tokens_total = Counter(
    'ids_llm_tokens_total',
    'Estimated LLM tokens used',
    ['engine', 'type']  # type: input, output
)

# Gauge: LLM cache hit rate
ids_llm_cache_hit_rate = Gauge(
    'ids_llm_cache_hit_rate',
    'Percentage of LLM requests served from cache'
)

# Counter: LLM cache operations
ids_llm_cache_operations_total = Counter(
    'ids_llm_cache_operations_total',
    'LLM cache operations',
    ['operation']  # hit, miss, eviction
)

# Gauge: LLM cache size
ids_llm_cache_size = Gauge(
    'ids_llm_cache_size',
    'Current number of entries in LLM cache'
)

# Counter: LLM fallback events
ids_llm_fallback_total = Counter(
    'ids_llm_fallback_total',
    'Times fallback engine was used',
    ['primary_engine', 'fallback_engine']
)

# Gauge: Primary LLM availability
ids_llm_primary_available = Gauge(
    'ids_llm_primary_available',
    'Whether primary LLM engine is available (1=yes, 0=no)',
    ['engine']
)

# -----------------------------------------------------------------------------
# AUTOMATED ACTIONS METRICS
# -----------------------------------------------------------------------------

# Counter: Actions executed
ids_actions_executed_total = Counter(
    'ids_actions_executed_total',
    'Total automated actions executed',
    ['action_type', 'outcome']  # action_type: isolate, scale, evict; outcome: success, failure
)

# Counter: Actions by automation mode
ids_actions_by_mode_total = Counter(
    'ids_actions_by_mode_total',
    'Actions executed by automation mode',
    ['mode', 'action_type']  # mode: autopilot, assisted, manual, live, dry-run
)

# Counter: Actions blocked
ids_actions_blocked_total = Counter(
    'ids_actions_blocked_total',
    'Actions blocked by safety controls',
    ['reason']  # protected_service, dry_run, approval_required
)

# Gauge: Pending actions awaiting approval
ids_actions_pending_approval = Gauge(
    'ids_actions_pending_approval',
    'Actions waiting for operator approval'
)

# Histogram: Action execution time
ids_action_execution_seconds = Histogram(
    'ids_action_execution_seconds',
    'Time to execute automated action',
    ['action_type'],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

# Histogram: End-to-end response time (alert → action)
ids_response_time_seconds = Histogram(
    'ids_response_time_seconds',
    'Total time from alert receipt to action completion',
    buckets=[1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
)

# Gauge: Pods currently isolated
ids_pods_isolated = Gauge(
    'ids_pods_isolated',
    'Number of pods currently in isolation',
    ['namespace']
)

# -----------------------------------------------------------------------------
# SYSTEM HEALTH METRICS
# -----------------------------------------------------------------------------

# Gauge: Rate limiter tokens available
ids_rate_limiter_tokens = Gauge(
    'ids_rate_limiter_tokens',
    'Current rate limiter token count'
)

# Counter: Rate limiter rejections
ids_rate_limiter_rejections_total = Counter(
    'ids_rate_limiter_rejections_total',
    'Requests rejected by rate limiter'
)

# Gauge: Circuit breaker state
ids_circuit_breaker_state = Gauge(
    'ids_circuit_breaker_state',
    'Circuit breaker state (0=closed, 1=open, 2=half-open)',
    ['engine']
)

# Counter: Circuit breaker state changes
ids_circuit_breaker_state_changes_total = Counter(
    'ids_circuit_breaker_state_changes_total',
    'Circuit breaker state transitions',
    ['engine', 'from_state', 'to_state']
)

# Gauge: Request queue depth
ids_request_queue_depth = Gauge(
    'ids_request_queue_depth',
    'Current request queue depth'
)

# Gauge: API uptime
ids_uptime_seconds = Gauge(
    'ids_uptime_seconds',
    'Seconds since IDS API started'
)

# Info: Version and configuration
ids_info = Info(
    'ids',
    'IDS API information'
)

# -----------------------------------------------------------------------------
# DATABASE METRICS
# -----------------------------------------------------------------------------

# Counter: Database operations
ids_db_operations_total = Counter(
    'ids_db_operations_total',
    'Database operations',
    ['operation', 'status']  # operation: insert, select, update; status: success, failure
)

# Histogram: Database query latency
ids_db_latency_seconds = Histogram(
    'ids_db_latency_seconds',
    'Database query latency',
    ['operation'],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0]
)

# Gauge: Active database connections
ids_db_connections_active = Gauge(
    'ids_db_connections_active',
    'Active database connections'
)

# Gauge: Total alerts in database
ids_db_alerts_total = Gauge(
    'ids_db_alerts_total',
    'Total alerts stored in database'
)

# -----------------------------------------------------------------------------
# IOT DEVICE METRICS (aggregated from simulators)
# -----------------------------------------------------------------------------

# Gauge: Active IoT devices
ids_iot_devices_active = Gauge(
    'ids_iot_devices_active',
    'Number of active IoT devices',
    ['class', 'namespace']
)

# Gauge: IoT message rate (aggregate)
ids_iot_message_rate = Gauge(
    'ids_iot_message_rate',
    'Current aggregate IoT message rate (msg/min)',
    ['class']
)

# Gauge: Rush hour status
ids_iot_rush_hour_active = Gauge(
    'ids_iot_rush_hour_active',
    'Whether rush hour burst is active (1=yes, 0=no)'
)


# =============================================================================
# METRICS HELPER CLASS
# =============================================================================

class MetricsManager:
    """Centralized metrics management with thread-safe updates."""
    
    _instance = None
    _lock = threading.Lock()
    _start_time = time.time()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._cache_hits = 0
        self._cache_total = 0
        
        # Set initial info
        ids_info.info({
            'version': '2.1.0',
            'capstone': 'II',
            'llm_primary': 'xai-grok-4',
            'llm_fallback': 'openai-gpt4'
        })
    
    # -------------------------------------------------------------------------
    # Alert Metrics
    # -------------------------------------------------------------------------
    
    def record_alert_received(self, source: str, severity: str, rule: str = "unknown"):
        """Record incoming alert."""
        ids_alerts_received_total.labels(source=source, severity=severity, rule=rule).inc()
    
    def record_alert_processed(self, source: str):
        """Record alert sent to LLM."""
        ids_alerts_processed_total.labels(source=source).inc()
    
    def record_alert_deduplicated(self, rule: str):
        """Record cache deduplication."""
        ids_alerts_deduplicated_total.labels(rule=rule).inc()
    
    def record_alert_dropped(self, reason: str):
        """Record dropped alert."""
        ids_alerts_dropped_total.labels(reason=reason).inc()
    
    def record_alert_severity(self, severity: int):
        """Record severity for distribution."""
        ids_alert_severity_bucket.observe(severity)
    
    def record_threat_type(self, threat_type: str):
        """Record alert threat type."""
        ids_alerts_by_threat_type_total.labels(threat_type=threat_type).inc()
    
    def set_queue_depth(self, depth: int):
        """Update queue depth gauge."""
        ids_alerts_queued.set(depth)
        ids_request_queue_depth.set(depth)
    
    # -------------------------------------------------------------------------
    # LLM Metrics
    # -------------------------------------------------------------------------
    
    def record_llm_request(self, engine: str, success: bool, latency: float, 
                          input_tokens: int = 0, output_tokens: int = 0):
        """Record LLM API request."""
        status = "success" if success else "failure"
        ids_llm_requests_total.labels(engine=engine, status=status).inc()
        ids_llm_latency_seconds.labels(engine=engine).observe(latency)
        ids_llm_latency_summary.labels(engine=engine).observe(latency)
        
        if input_tokens > 0:
            ids_llm_tokens_total.labels(engine=engine, type="input").inc(input_tokens)
        if output_tokens > 0:
            ids_llm_tokens_total.labels(engine=engine, type="output").inc(output_tokens)
    
    def record_cache_operation(self, hit: bool):
        """Record cache hit/miss."""
        self._cache_total += 1
        if hit:
            self._cache_hits += 1
            ids_llm_cache_operations_total.labels(operation="hit").inc()
        else:
            ids_llm_cache_operations_total.labels(operation="miss").inc()
        
        # Update hit rate
        if self._cache_total > 0:
            ids_llm_cache_hit_rate.set(self._cache_hits / self._cache_total * 100)
    
    def record_cache_eviction(self):
        """Record cache eviction."""
        ids_llm_cache_operations_total.labels(operation="eviction").inc()
    
    def set_cache_size(self, size: int):
        """Update cache size gauge."""
        ids_llm_cache_size.set(size)
    
    def record_llm_fallback(self, primary: str, fallback: str):
        """Record fallback to secondary LLM."""
        ids_llm_fallback_total.labels(primary_engine=primary, fallback_engine=fallback).inc()
    
    def set_llm_availability(self, engine: str, available: bool):
        """Update LLM availability gauge."""
        ids_llm_primary_available.labels(engine=engine).set(1 if available else 0)
    
    # -------------------------------------------------------------------------
    # Action Metrics
    # -------------------------------------------------------------------------
    
    def record_action(self, action_type: str, success: bool, execution_time: float,
                     mode: str = "live"):
        """Record automated action."""
        outcome = "success" if success else "failure"
        ids_actions_executed_total.labels(action_type=action_type, outcome=outcome).inc()
        ids_actions_by_mode_total.labels(mode=mode, action_type=action_type).inc()
        ids_action_execution_seconds.labels(action_type=action_type).observe(execution_time)
    
    def record_action_blocked(self, reason: str):
        """Record blocked action."""
        ids_actions_blocked_total.labels(reason=reason).inc()
    
    def set_pending_approvals(self, count: int):
        """Update pending approvals gauge."""
        ids_actions_pending_approval.set(count)
    
    def record_response_time(self, duration: float):
        """Record end-to-end response time."""
        ids_response_time_seconds.observe(duration)
    
    def set_isolated_pods(self, namespace: str, count: int):
        """Update isolated pods gauge."""
        ids_pods_isolated.labels(namespace=namespace).set(count)
    
    # -------------------------------------------------------------------------
    # System Health Metrics
    # -------------------------------------------------------------------------
    
    def set_rate_limiter_tokens(self, tokens: float):
        """Update rate limiter tokens."""
        ids_rate_limiter_tokens.set(tokens)
    
    def record_rate_limit_rejection(self):
        """Record rate limiter rejection."""
        ids_rate_limiter_rejections_total.inc()
    
    def set_circuit_breaker_state(self, engine: str, state: str):
        """Update circuit breaker state (closed=0, open=1, half_open=2)."""
        state_map = {"closed": 0, "open": 1, "half_open": 2, "half-open": 2}
        ids_circuit_breaker_state.labels(engine=engine).set(state_map.get(state, 0))
    
    def record_circuit_breaker_transition(self, engine: str, from_state: str, to_state: str):
        """Record circuit breaker state change."""
        ids_circuit_breaker_state_changes_total.labels(
            engine=engine, from_state=from_state, to_state=to_state
        ).inc()
    
    def update_uptime(self):
        """Update uptime gauge."""
        ids_uptime_seconds.set(time.time() - self._start_time)
    
    # -------------------------------------------------------------------------
    # Database Metrics
    # -------------------------------------------------------------------------
    
    def record_db_operation(self, operation: str, success: bool, latency: float):
        """Record database operation."""
        status = "success" if success else "failure"
        ids_db_operations_total.labels(operation=operation, status=status).inc()
        ids_db_latency_seconds.labels(operation=operation).observe(latency)
    
    def set_db_connections(self, count: int):
        """Update active DB connections gauge."""
        ids_db_connections_active.set(count)
    
    def set_db_alerts_total(self, count: int):
        """Update total alerts in DB."""
        ids_db_alerts_total.set(count)
    
    # -------------------------------------------------------------------------
    # IoT Metrics
    # -------------------------------------------------------------------------
    
    def set_iot_devices_active(self, device_class: str, namespace: str, count: int):
        """Update active IoT devices gauge."""
        ids_iot_devices_active.labels(class=device_class, namespace=namespace).set(count)
    
    def set_iot_message_rate(self, device_class: str, rate: float):
        """Update IoT message rate gauge."""
        ids_iot_message_rate.labels(class=device_class).set(rate)
    
    def set_rush_hour_active(self, active: bool):
        """Update rush hour status."""
        ids_iot_rush_hour_active.set(1 if active else 0)
    
    # -------------------------------------------------------------------------
    # Export
    # -------------------------------------------------------------------------
    
    def get_metrics(self) -> bytes:
        """Generate Prometheus metrics output."""
        self.update_uptime()
        return generate_latest()
    
    def get_content_type(self) -> str:
        """Get Prometheus content type."""
        return CONTENT_TYPE_LATEST


# Singleton instance
metrics = MetricsManager()


# =============================================================================
# DECORATORS FOR AUTOMATIC INSTRUMENTATION
# =============================================================================

def track_llm_latency(engine: str):
    """Decorator to track LLM call latency."""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                latency = time.time() - start
                metrics.record_llm_request(engine, True, latency)
                return result
            except Exception as e:
                latency = time.time() - start
                metrics.record_llm_request(engine, False, latency)
                raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = func(*args, **kwargs)
                latency = time.time() - start
                metrics.record_llm_request(engine, True, latency)
                return result
            except Exception as e:
                latency = time.time() - start
                metrics.record_llm_request(engine, False, latency)
                raise
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator


def track_action_execution(action_type: str):
    """Decorator to track action execution time."""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                execution_time = time.time() - start
                metrics.record_action(action_type, True, execution_time)
                return result
            except Exception as e:
                execution_time = time.time() - start
                metrics.record_action(action_type, False, execution_time)
                raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = func(*args, **kwargs)
                execution_time = time.time() - start
                metrics.record_action(action_type, True, execution_time)
                return result
            except Exception as e:
                execution_time = time.time() - start
                metrics.record_action(action_type, False, execution_time)
                raise
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator


def track_db_operation(operation: str):
    """Decorator to track database operation latency."""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                latency = time.time() - start
                metrics.record_db_operation(operation, True, latency)
                return result
            except Exception as e:
                latency = time.time() - start
                metrics.record_db_operation(operation, False, latency)
                raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = func(*args, **kwargs)
                latency = time.time() - start
                metrics.record_db_operation(operation, True, latency)
                return result
            except Exception as e:
                latency = time.time() - start
                metrics.record_db_operation(operation, False, latency)
                raise
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator
