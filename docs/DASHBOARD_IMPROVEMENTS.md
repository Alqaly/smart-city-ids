# Grafana Dashboard Improvements - IEEE Capstone II

## Summary of Changes

The improved dashboard (`Smart City IDS - IEEE Capstone II (Improved)`) addresses all the identified gaps while preserving the strong existing metrics.

### Access the New Dashboard
- **URL**: `http://192.168.153.129:30300/d/smartcity-ids-ieee-v2`
- **Credentials**: `admin` / `admin`

---

## What Was Added

### 1. System Overview Row (TOP) - Enhanced

| Panel | Metric | Why It Matters |
|-------|--------|----------------|
| **Processing Success Rate** | `alerts_processed / alerts_received * 100` | Shows end-to-end reliability (should be 100%) |
| **Automation Mode** | `smartcity_ids_automation_mode` | Clear ACTIVE/DRY-RUN indicator |

### 2. Alert Pipeline & Threat Intelligence - Made Investigative

| Panel | What Changed | Why |
|-------|--------------|-----|
| **Alerts Over Time (Stacked)** | NEW - Time series with severity colors | Examiners can see attack patterns and spikes |
| **Top 5 Threat Types** | Uses `topk(5, ...)` | Focuses on active threats, not all history |
| Severity colors | Red=Critical, Orange=Warning, Blue=Notice | Visual urgency hierarchy |

### 3. LLM Analysis & Decision Quality - IEEE-Strong

| Panel | Metric | Purpose |
|-------|--------|---------|
| **LLM Decision Outcomes** | `smartcity_ids_llm_decision_outcome_total{outcome}` | Shows AI reasoning: malicious/suspicious/benign |
| **LLM Failovers** | `smartcity_ids_llm_failover_total` | Tracks engine reliability |
| **Cache Hit Rate** | Fixed division-by-zero with `+ 0.001` | Shows cost optimization |
| **LLM Requests by Engine** | Time series with success/error/circuit_open | Shows failover behavior |

**Current LLM Decision Distribution:**
- Malicious: 144 (91.7%)
- Suspicious: 13 (8.3%)
- Benign: 0

### 4. Automation & Governance (Human-in-the-Loop) - Critical for Capstone II

| Panel | Metric | Why |
|-------|--------|-----|
| **Auto vs Human Decisions** | `smartcity_ids_automated_decisions_total` | Proves governance model |
| **Pending Approvals** | `smartcity_ids_approval_pending_count` | Shows human-in-the-loop queue |
| **Policy Blocks (Protected)** | `smartcity_ids_protected_service_hits_total` | Demonstrates safety controls |
| **Actions Over Time** | Time series of `actions_executed_total` | Shows automation responding to threats |

**What "0" Values Mean:**
- Pending Approvals = 0 → No actions waiting for human review (ACTIVE mode)
- Policy Blocks = 0 → No attempts to modify protected services (healthcare-api, postgres)

### 5. IoT Device Monitoring - Made Real

| Panel | What Changed | Why |
|-------|--------------|-----|
| **Active IoT Devices (Gauge)** | NEW - Visual gauge with thresholds | Shows scaling potential |
| **Events per IoT Device (Bar)** | NEW - Horizontal bar chart | Which devices are most active |
| **IoT Events Over Time** | Kept, improved labels | Time-based activity patterns |

**Current IoT Stats:**
- 3 active devices
- 51 total events (heartbeats + motion detection + rapid motion)

---

## Panel Reordering (Narrative Flow)

The dashboard now tells an investigation story:

1. **System & Health** → Is the system working?
2. **Alert Pipeline** → What threats are we seeing?
3. **LLM Analysis** → How is AI classifying them?
4. **Automation & Governance** → What actions were taken? Who approved?
5. **IoT Monitoring** → Are edge devices contributing?

---

## New Prometheus Metrics Added

```python
# LLM Decision & Governance Metrics
PROM_LLM_DECISION_OUTCOME          # benign, suspicious, malicious
PROM_LLM_CONFIDENCE_BUCKET         # low, medium, high
PROM_AUTOMATED_DECISIONS           # automated vs human_review
PROM_HUMAN_OVERRIDE_REQUESTS       # flagged for human review
PROM_ACTIONS_BLOCKED_POLICY        # blocked by policy
PROM_LLM_FAILOVER_COUNT            # engine failovers

# IoT Latency Metrics
PROM_IOT_LATENCY_SECONDS           # p50/p95 IoT-to-IDS latency
PROM_IOT_EVENTS_PER_DEVICE         # per-device event counts
```

---

## "No Data" Panels - Fixed

Every panel that previously showed "No data" now either:

1. **Shows actual data** (if the feature has been used)
2. **Shows "0 (normal)"** with descriptive tooltip (if zero is expected)
3. **Has a clear description** explaining what the metric means

Examples:
- "Policy Blocks (Protected)" → Shows "0 (normal)" with description: "Zero means policies are not being triggered - this is expected"
- "LLM Failovers" → Shows "0" with description: "Number of times LLM failed over to backup engine"

---

## Numbers You Can State Out Loud (From This Dashboard)

| Metric | Current Value | How to Say It |
|--------|---------------|---------------|
| Alerts processed | 157 | "We've processed 157 security alerts end-to-end" |
| Processing success rate | 100% | "100% of alerts were successfully analyzed" |
| Critical alerts | 144 | "144 alerts were classified as critical (severity ≥ 8)" |
| Automated actions | 157 | "The system executed 157 automated mitigations" |
| Pod isolations | 144 | "144 pods were isolated in response to threats" |
| Scale-up actions | 13 | "13 services were scaled up to handle load" |
| LLM decision: malicious | 91.7% | "91.7% of threats were classified as malicious by the LLM" |
| Active IoT devices | 3 | "3 IoT edge devices are actively reporting" |
| Automation mode | ACTIVE | "System is in ACTIVE mode - fully automated response" |

---

## File Locations

- **Improved Dashboard JSON**: `infrastructure/monitoring/grafana-dashboard-ieee-improved.json`
- **Updated Metrics Code**: `services/ids-api/src/main.py` (lines 556-605)
- **Original Dashboard** (unchanged): `infrastructure/monitoring/grafana-dashboard-ieee.json`

---

## Verification Commands

```bash
# Check new metrics are available
curl -s http://192.168.153.129:30800/metrics | grep smartcity_ids_llm_decision
curl -s http://192.168.153.129:30800/metrics | grep smartcity_ids_automated_decisions

# Query Prometheus for decision outcomes
curl -s "http://192.168.153.129:31701/api/v1/query?query=smartcity_ids_llm_decision_outcome_total"

# View dashboard
open http://192.168.153.129:30300/d/smartcity-ids-ieee-v2
```
