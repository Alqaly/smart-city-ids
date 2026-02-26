# Metrics Contract (Frozen)

**Status:** Frozen (do not rename metrics without a versioned contract update)  
**Owner:** IDS API + IoT Device  
**Last Updated:** 2026-02-04  

This document defines the **authoritative metrics contract** for the Smart City IDS.  
Metrics are treated as an API. Names, types, and labels are stable.

## Categories

- **Detection**: evidence that a security event occurred.
- **Reasoning**: LLM analysis latency and decisions.
- **Decision**: human or automated approval logic.
- **Action**: response execution or blocking.
- **Impact/Scale**: system load, queue pressure, and IoT volume.

## IDS API Metrics (`smartcity_ids_*`)

### Detection

| Metric | Type | Labels | Question Answered |
|---|---|---|---|
| `smartcity_ids_alerts_received_total` | Counter | `priority`, `source` | Are alerts arriving and from where? |
| `smartcity_ids_alerts_processed_total` | Counter | `result` | Are alerts successfully processed? |
| `smartcity_ids_critical_alerts_total` | Counter | none | How many critical alerts occurred? |
| `smartcity_ids_severity_total` | Counter | `severity` | How does severity distribution evolve? |
| `smartcity_ids_threat_types_total` | Counter | `threat_type` | Which threat classes dominate? |
| `smartcity_ids_alert_processing_seconds` | Histogram | none | How long does detection → analysis take? |

### Reasoning

| Metric | Type | Labels | Question Answered |
|---|---|---|---|
| `smartcity_ids_llm_requests_total` | Counter | `engine`, `result` | Is the LLM being called and succeeding? |
| `smartcity_ids_llm_latency_seconds` | Histogram | `engine` | Is LLM latency acceptable? |
| `smartcity_ids_llm_decision_outcome_total` | Counter | `outcome` | Are decisions benign/suspicious/malicious? |
| `smartcity_ids_llm_failover_total` | Counter | `from_engine`, `to_engine` | How often do we fail over? |
| `smartcity_ids_llm_cache_total` | Counter | `operation` | Is caching effective? |
| `smartcity_ids_llm_cache_size` | Gauge | none | What is the current cache size? |
| `smartcity_ids_llm_credits_remaining` | Gauge | `engine` | Are API credits near exhaustion? |

### Decision

| Metric | Type | Labels | Question Answered |
|---|---|---|---|
| `smartcity_ids_automation_mode` | Gauge | `mode` | Is the system in autonomous/assisted/manual (or emergency) mode? |
| `smartcity_ids_approval_pending_count` | Gauge | none | Are approvals backing up? |
| `smartcity_ids_human_override_requests_total` | Counter | `reason` | How often is human override required? |
| `smartcity_ids_automated_decisions_total` | Counter | `action_type` | How many decisions were automated? |

### Action

| Metric | Type | Labels | Question Answered |
|---|---|---|---|
| `smartcity_ids_actions_executed_total` | Counter | `action` | What actions are being taken? |
| `smartcity_ids_actions_blocked_total` | Counter | `action`, `reason` | What actions were blocked by safety? |
| `smartcity_ids_actions_blocked_policy_total` | Counter | `policy`, `action` | Which policies block actions? |
| `smartcity_ids_k8s_pods_isolated_total` | Counter | none | How many isolation actions occurred? |
| `smartcity_ids_k8s_scale_operations_total` | Counter | `operation`, `service` | How often are services scaled? |
| `smartcity_ids_time_to_mitigation_seconds` | Histogram | none | How long until mitigation executes? |

### Impact / Scale / Stability

| Metric | Type | Labels | Question Answered |
|---|---|---|---|
| `smartcity_ids_request_queue_size` | Gauge | none | Is request backlog forming? |
| `smartcity_ids_request_queue_rejected_total` | Counter | none | Are requests dropped due to overload? |
| `smartcity_ids_rate_limit_requests_total` | Counter | `result` | Is rate limiting engaged? |
| `smartcity_ids_rate_limit_tokens_available` | Gauge | none | Remaining capacity in the limiter? |
| `smartcity_ids_circuit_breaker_state` | Gauge | `engine` | Is the LLM circuit breaker open? |
| `smartcity_ids_circuit_breaker_trips_total` | Counter | `engine` | How often does the breaker trip? |
| `smartcity_ids_uptime_seconds` | Gauge | none | Is the IDS API stable? |
| `smartcity_ids_api_requests_total` | Counter | `endpoint`, `method`, `status` | Is the API under abnormal load? |
| `smartcity_ids_auth_failures_total` | Counter | `type` | Are auth failures occurring? |
| `smartcity_ids_protected_service_hits_total` | Counter | `service` | Attempts to isolate protected services? |
| `smartcity_ids_protection_bypass_attempts_total` | Counter | `action` | Safety bypass attempts? |

## IoT Device Metrics (`iot_*`)

**Owner:** `iot-device` services (MQTT emulation)

| Metric | Type | Labels | Question Answered |
|---|---|---|---|
| `iot_messages_sent_total` | Counter | `device`, `namespace`, `class` | Are devices generating traffic? |
| `iot_messages_failed_total` | Counter | `device`, `namespace`, `class` | Is device traffic failing? |
| `iot_device_active` | Gauge | `device`, `namespace`, `class` | How many devices are active? |
| `iot_current_message_rate` | Gauge | `device`, `class` | Instantaneous device message rate? |
| `iot_burst_factor` | Gauge | `device` | Is burst behavior active? |
| `iot_message_latency_seconds` | Histogram | `device` | Latency of IoT message handling? |
| `iot_device_disconnects_total` | Counter | `device` | Are devices dropping off? |
| `iot_latency_spikes_total` | Counter | `device` | Are latencies spiking? |

## Contract Rules (Non‑Negotiable)

- **No metric renames** without updating this document and versioning the dashboards.
- **Dashboards must use only these metrics**.
- **Every metric must answer a research question** tied to detection, reasoning, decision, action, or scale.
- **Counters are graphed with `rate()` or `increase()`**; no raw counter panels.
