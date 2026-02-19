"""Prometheus metric definitions for the Smart City IDS.

This module is the **single source of truth** for all ~40 Prometheus
metrics used across the IDS API.  Every counter, gauge, and histogram
is defined here and imported by the router and service modules that
record observations.

Naming convention:
    All metrics use the ``smartcity_ids_`` prefix to avoid collisions
    with Kubernetes / Falco / node-exporter metrics in Grafana.

Category groups (8 categories, ~40 metrics):
    1. **Core Alert Metrics** — ingest, processing, dedup, fatigue
    2. **LLM Analysis Metrics** — requests, latency, cost, tokens, cache
    3. **Security Analysis Metrics** — severity distribution, threat types
    4. **LLM Decision & Governance** — outcomes, overrides, failover
    5. **IoT Device Metrics** — events, heartbeats, latency
    6. **Kubernetes Automation** — pod isolation, scaling, protection
    7. **System Health** — API requests, automation mode
    8. **Production Resilience** — rate-limiter, circuit-breaker, queue
    9. **Data Quality** — false positives, dedup hit-rate, throttling

Usage:
    from infrastructure.metrics import PROM_ALERTS_RECEIVED_TOTAL
    PROM_ALERTS_RECEIVED_TOTAL.labels(source="falco", priority="Critical").inc()
"""

from prometheus_client import Counter, Gauge, Histogram

# ══════════════════════════════════════════════════════════════════════════════
# 1. CORE ALERT METRICS
# ══════════════════════════════════════════════════════════════════════════════
PROM_ALERTS_RECEIVED_TOTAL = Counter(
    "smartcity_ids_alerts_received_total",
    "Total number of alerts received by the IDS API.",
    ["source", "priority"],
)
# Alerts that completed the full processing pipeline (success/error/cached).
PROM_ALERTS_PROCESSED_TOTAL = Counter(
    "smartcity_ids_alerts_processed_total",
    "Total number of alerts processed by the IDS API, labeled by result.",
    ["result"],
)
# Raw alert count before any dedup or throttling (for fatigue-reduction ratio).
PROM_ALERTS_RAW_TOTAL = Counter(
    "smartcity_ids_alerts_raw_total",
    "Raw alerts entering IDS before dedup/throttling.",
    ["source"],
)
# Alerts that survived deduplication and needed fresh LLM analysis.
PROM_ALERTS_AFTER_DEDUP_TOTAL = Counter(
    "smartcity_ids_alerts_after_dedup_total",
    "Alerts that required a fresh analysis after dedup checks.",
)
# Alerts triaged by LLM or rule-based engine (excludes cached results).
PROM_LLM_TRIAGED_ALERTS_TOTAL = Counter(
    "smartcity_ids_llm_triaged_alerts_total",
    "Alerts triaged by LLM/rule-based analysis (non-cached).",
)
# Alerts that require human analyst review (governance mode dependent).
PROM_HUMAN_REVIEW_REQUIRED_TOTAL = Counter(
    "smartcity_ids_human_review_required_total",
    "Alerts requiring analyst review based on governance mode/threshold.",
)
# Kubernetes actions actually executed (isolate_pod, scale_up, etc.).
PROM_ACTIONS_EXECUTED_TOTAL = Counter(
    "smartcity_ids_actions_executed_total",
    "Total number of automated actions triggered by the IDS API.",
    ["action"],
)
# Actions blocked by safety controls (dry-run, protected service, etc.).
PROM_ACTIONS_BLOCKED_TOTAL = Counter(
    "smartcity_ids_actions_blocked_total",
    "Total number of automated actions blocked by safety controls.",
    ["action", "reason"],
)
# End-to-end processing time histogram — Fibonacci-like buckets for LLM tail.
PROM_ALERT_PROCESSING_SECONDS = Histogram(
    "smartcity_ids_alert_processing_seconds",
    "End-to-end IDS API /api/alerts processing duration (seconds).",
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 3, 5, 8, 13, 21),
)
# Application uptime — refreshed on /health and /metrics scrapes.
PROM_UPTIME_SECONDS = Gauge(
    "smartcity_ids_uptime_seconds",
    "IDS API process uptime in seconds.",
)

# ══════════════════════════════════════════════════════════════════════════════
# 2. LLM ANALYSIS METRICS
#    Per-engine request counts, latency histograms, cost and token tracking.
# ══════════════════════════════════════════════════════════════════════════════
# LLM API calls labelled by engine (xai/openai/anthropic/…) and result.
PROM_LLM_REQUESTS_TOTAL = Counter(
    "smartcity_ids_llm_requests_total",
    "Total LLM API requests by engine and result.",
    ["engine", "result"],
)
# LLM call latency histogram — wide buckets to capture slow API calls.
PROM_LLM_LATENCY_SECONDS = Histogram(
    "smartcity_ids_llm_latency_seconds",
    "LLM API call latency in seconds.",
    ["engine"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1, 2, 3, 5, 8, 10, 15, 20, 30),
)
# Cumulative estimated cost in USD per engine.
PROM_LLM_COST_USD = Counter(
    "smartcity_ids_llm_cost_usd_total",
    "Estimated LLM API cost in USD by engine.",
    ["engine"],
)
# Token usage per engine (prompt / completion).
PROM_LLM_TOKENS_TOTAL = Counter(
    "smartcity_ids_llm_tokens_total",
    "Estimated LLM token usage by engine and token kind.",
    ["engine", "kind"],
)
# LLM response cache hit / miss counter.
PROM_LLM_CACHE_OPERATIONS = Counter(
    "smartcity_ids_llm_cache_total",
    "LLM cache operations (hits/misses).",
    ["operation"],
)
# Current number of entries in the LLM response cache.
PROM_LLM_CACHE_SIZE = Gauge(
    "smartcity_ids_llm_cache_size",
    "Current number of cached LLM responses.",
)

# ══════════════════════════════════════════════════════════════════════════════
# 3. SECURITY ANALYSIS METRICS
#    Severity histograms and threat-type counters for Grafana dashboards.
# ══════════════════════════════════════════════════════════════════════════════
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

# ══════════════════════════════════════════════════════════════════════════════
# 4. LLM DECISION & GOVERNANCE METRICS
#    Track automated vs human decisions, policy blocks, and failover events.
# ══════════════════════════════════════════════════════════════════════════════
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

# ══════════════════════════════════════════════════════════════════════════════
# 5. IOT DEVICE METRICS
#    Telemetry from Raspberry Pi and edge devices reporting to the IDS.
# ══════════════════════════════════════════════════════════════════════════════
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

# ══════════════════════════════════════════════════════════════════════════════
# 6. KUBERNETES AUTOMATION METRICS
#    Pod isolation, scaling, and protection-bypass counters.
# ══════════════════════════════════════════════════════════════════════════════
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

# ══════════════════════════════════════════════════════════════════════════════
# 7. SYSTEM HEALTH METRICS
#    HTTP-level request counting and automation-mode indicator.
# ══════════════════════════════════════════════════════════════════════════════
PROM_API_REQUESTS_TOTAL = Counter(
    "smartcity_ids_api_requests_total",
    "Total API requests by endpoint and status.",
    ["endpoint", "method", "status"],
)
PROM_AUTOMATION_MODE = Gauge(
    "smartcity_ids_automation_mode",
    "Current automation mode indicator.",
    ["mode"],
)

# ══════════════════════════════════════════════════════════════════════════════
# 8. PRODUCTION RESILIENCE METRICS
#    Rate-limiter, circuit-breaker, request-queue, and auth gauges.
# ══════════════════════════════════════════════════════════════════════════════
PROM_RATE_LIMIT_REQUESTS = Counter(
    "smartcity_ids_rate_limit_requests_total",
    "Rate limiter requests by result.",
    ["result"],
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

# ══════════════════════════════════════════════════════════════════════════════
# 9. DATA QUALITY METRICS
#    False-positive filtering, dedup hit-rate, and throttling counters.
# ══════════════════════════════════════════════════════════════════════════════
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
