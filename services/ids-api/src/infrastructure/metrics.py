"""Prometheus metric definitions for Smart City IDS.

All PROM_* counters, gauges, and histograms in one place.
Imported by routers and services that need to record metrics.
"""

from prometheus_client import Counter, Gauge, Histogram

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
PROM_ALERTS_RAW_TOTAL = Counter(
    "smartcity_ids_alerts_raw_total",
    "Raw alerts entering IDS before dedup/throttling.",
    ["source"],
)
PROM_ALERTS_AFTER_DEDUP_TOTAL = Counter(
    "smartcity_ids_alerts_after_dedup_total",
    "Alerts that required a fresh analysis after dedup checks.",
)
PROM_LLM_TRIAGED_ALERTS_TOTAL = Counter(
    "smartcity_ids_llm_triaged_alerts_total",
    "Alerts triaged by LLM/local analysis (non-cached).",
)
PROM_HUMAN_REVIEW_REQUIRED_TOTAL = Counter(
    "smartcity_ids_human_review_required_total",
    "Alerts requiring analyst review based on governance mode/threshold.",
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
    buckets=(0.01, 0.05, 0.1, 0.5, 1, 2, 3, 5, 8, 10, 15, 20, 30),
)
PROM_LLM_COST_USD = Counter(
    "smartcity_ids_llm_cost_usd_total",
    "Estimated LLM API cost in USD by engine.",
    ["engine"],
)
PROM_LLM_TOKENS_TOTAL = Counter(
    "smartcity_ids_llm_tokens_total",
    "Estimated LLM token usage by engine and token kind.",
    ["engine", "kind"],
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
    ["mode"],
)

# ============== PRODUCTION RESILIENCE METRICS ==============
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
