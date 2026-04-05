# Smart City IDS - Log Format Guide

**Audience:** Students, academic reviewers, and SOC analysts  
**Purpose:** Understand how security alerts flow through the system and what each log entry means

---

## Table of Contents

1. [Log Flow Overview](#log-flow-overview)
2. [Falco Logs](#falco-logs)
3. [IDS API Logs](#ids-api-logs)
4. [LLM Decision Logs](#llm-decision-logs)
5. [Kubernetes Automation Logs](#kubernetes-automation-logs)
6. [Prometheus Metrics](#prometheus-metrics)
7. [PostgreSQL Audit Trail](#postgresql-audit-trail)
8. [End-to-End Example](#end-to-end-example)

---

## Log Flow Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        ALERT PROCESSING PIPELINE                         │
└──────────────────────────────────────────────────────────────────────────┘

STAGE 1: Detection
┌─────────────┐
│   Falco     │  Syscall monitoring (eBPF)
│   (eBPF)    │  → Generates JSON alert
└──────┬──────┘
       │ Alert: {"rule":"...", "priority":"Warning", "output":"..."}
       ▼
STAGE 2: Normalization
┌─────────────┐
│  Forwarder  │  HTTP POST to /api/alerts
│  (Python)   │  → Maps Falco priority to severity (1-10)
└──────┬──────┘
       │ Normalized: {"severity":7, "source":"falco", "alert_data":{...}}
       ▼
STAGE 3: LLM Analysis
┌─────────────┐
│   IDS API   │  Calls LLM providers (xAI, OpenAI, Anthropic, Gemini, Kimi)
│  (FastAPI)  │  → Gets threat type, recommendations, actions
└──────┬──────┘
       │ LLM Response: {"severity":8, "threat_type":"Credential Access", ...}
       ▼
STAGE 4: Automation
┌─────────────┐
│ K8s Client  │  Applies network policies, scales deployments
│  (Python)   │  → Executes automated actions
└──────┬──────┘
       │ Action: isolate_pod(target="healthcare-api-xxx")
       ▼
STAGE 5: Persistence & Metrics
┌─────────────┬─────────────┐
│ PostgreSQL  │ Prometheus  │  Stores alerts, increments metrics
│ (Database)  │  (TSDB)     │  → Available for queries & dashboards
└─────────────┴─────────────┘
       │             │
       ▼             ▼
   Audit Trail    Grafana Graphs
```

---

## Falco Logs

### What is Falco?

Falco is a **runtime security monitor** that uses eBPF (extended Berkeley Packet Filter) to intercept syscalls at the Linux kernel level. It detects suspicious behavior like:
- Reading sensitive files (/etc/shadow, /etc/passwd)
- Spawning unexpected shells
- Container escape attempts
- Privilege escalation

### Where to Find Falco Logs

```bash
kubectl logs -n falco-system -l app=falco --tail=50
```

### Raw Falco Alert Example

```json
{
  "output": "Sensitive file opened for reading by non-trusted program (file=/etc/shadow user=root user_loginuid=-1 program=cat command=cat /etc/shadow parent=sh gparent=<NA> ggparent=<NA> gggparent=<NA> container_id=3f8e9a7c4d2b1a container_name=healthcare-api-7bb856cbf4-4vkgs image=<NA>)",
  "priority": "Warning",
  "rule": "Read sensitive file untrusted",
  "time": "2026-02-03T10:15:30.123456789Z",
  "output_fields": {
    "container.id": "3f8e9a7c4d2b1a",
    "container.name": "healthcare-api-7bb856cbf4-4vkgs",
    "evt.time": "10:15:30.123456789",
    "fd.name": "/etc/shadow",
    "proc.cmdline": "cat /etc/shadow",
    "proc.name": "cat",
    "proc.pname": "sh",
    "user.name": "root",
    "user.loginuid": -1
  },
  "source": "syscall",
  "tags": [
    "filesystem",
    "mitre_credential_access",
    "mitre_persistence"
  ],
  "hostname": "capstone"
}
```

### Key Fields Explained

| Field | Meaning | Usage in IDS |
|-------|---------|--------------|
| `rule` | Falco rule name that triggered | Used for threat classification |
| `priority` | Emergency/Alert/Critical/Error/Warning/Notice/Informational/Debug | Mapped to severity 1-10 |
| `output` | Human-readable description | Sent to LLM for analysis |
| `output_fields.container.name` | Target container (K8s pod) | Used for automated isolation |
| `output_fields.proc.cmdline` | Command executed by attacker | Used for forensic analysis |
| `output_fields.fd.name` | File accessed | Used to identify attack type |
| `tags` | MITRE ATT&CK tags | Used for threat categorization |

### Priority to Severity Mapping

| Falco Priority | IDS Severity | Action Threshold |
|----------------|--------------|------------------|
| Emergency      | 10           | Isolate immediately |
| Alert          | 9            | Isolate immediately |
| Critical       | 8            | Isolate pod |
| Error          | 7            | Scale up service |
| Warning        | 6            | Scale up service |
| Notice         | 5            | Log only |
| Informational  | 3            | Log only |
| Debug          | 1            | Log only |

---

## IDS API Logs

### What is the IDS API?

The IDS API is a **FastAPI application** that:
1. Receives alerts from forwarders (HTTP POST /api/alerts)
2. Calls LLM for intelligent analysis
3. Triggers Kubernetes automation
4. Persists data to PostgreSQL
5. Exposes Prometheus metrics

### Where to Find IDS API Logs

```bash
kubectl logs -n smart-city -l app=ids-api --tail=100 -f
```

### IDS API Log Examples

#### 1. Alert Received
```
INFO:     10.42.1.71:45782 - "POST /api/alerts HTTP/1.1" 200 OK
```
**Meaning:** Forwarder successfully sent an alert to the IDS API

#### 2. Alert Processing Started
```
INFO: Processing alert from falco: source=falco, severity=7, rule=Read sensitive file untrusted
```
**Meaning:** IDS API started processing the alert (before LLM call)

#### 3. LLM Analysis Called
```
DEBUG: Calling xAI Grok API for threat analysis...
```
**Meaning:** LLM API call initiated

#### 4. LLM Response Received
```
INFO: LLM analysis complete: severity=8, threat_type=Credential Access, latency=2.34s
```
**Meaning:** LLM returned analysis (2.34 seconds response time)

**Key Metrics:**
- `severity=8`: LLM's severity assessment (may differ from Falco's initial 7)
- `threat_type`: MITRE ATT&CK category
- `latency=2.34s`: Time taken by LLM API call

#### 5. Automated Action Triggered
```
INFO: Automated action triggered: isolate_pod (target=healthcare-api-7bb856cbf4-4vkgs, severity=8)
```
**Meaning:** IDS API decided to isolate the pod based on severity ≥ 8

#### 6. Automation Executed
```
INFO: K8s action successful: isolate_pod applied to healthcare-api-7bb856cbf4-4vkgs
```
**Meaning:** Kubernetes network policy was successfully applied

#### 7. Error Handling
```
ERROR: Failed to call LLM API: Timeout after 30s, using fallback analysis
WARN: K8s automation skipped: Pod healthcare-api-7bb856cbf4-4vkgs not found
```
**Meaning:** IDS API handles failures gracefully (fallback to rule-based analysis)

---

## LLM Decision Logs

### What the LLM Sees

**System Prompt (Simplified):**
```
You are a security analyst for a Smart City IDS. Analyze the following security alert and provide:
1. Severity score (1-10)
2. Threat type (MITRE ATT&CK category)
3. Summary (1-2 sentences)
4. Recommendations for SOC analysts
5. Automated actions to take
```

**Alert Sent to LLM:**
```json
{
  "source": "falco",
  "rule": "Read sensitive file untrusted",
  "priority": "Warning",
  "description": "Sensitive file opened for reading (file=/etc/shadow user=root program=cat)",
  "container": "healthcare-api-7bb856cbf4-4vkgs",
  "timestamp": "2026-02-03T10:15:30Z"
}
```

### What the LLM Returns

**LLM Response (xAI Grok / OpenAI GPT / Anthropic / Gemini / Kimi):**
```json
{
  "status": "success",
  "analysis": {
    "severity": 8,
    "threat_type": "Credential Access",
    "summary": "Attempted unauthorized read of /etc/shadow indicates credential harvesting. This is a common post-exploitation technique used by attackers to obtain password hashes for privilege escalation.",
    "recommendations": [
      "Isolate the affected container immediately",
      "Audit recent activity in the container logs",
      "Check for lateral movement to other pods",
      "Review authentication logs for compromised credentials"
    ],
    "automated_actions": [
      "isolate_pod"
    ],
    "confidence": 0.92,
    "mitre_attack_ids": ["T1552.001"],
    "false_positive_likelihood": "low"
  }
}
```

### LLM Response Fields Explained

| Field | Meaning | IDS Usage |
|-------|---------|-----------|
| `severity` | 1-10 threat severity | Determines automated action |
| `threat_type` | MITRE ATT&CK category | Used for dashboard categorization |
| `summary` | Human-readable explanation | Shown to SOC analysts |
| `recommendations` | Actions for humans | Logged for manual review |
| `automated_actions` | Actions for IDS to execute | Triggers K8s automation |
| `confidence` | LLM confidence score (0-1) | Used to filter low-confidence alerts |
| `false_positive_likelihood` | low/medium/high | Helps SOC prioritize alerts |

### LLM Latency Tracking

**Logged Metrics:**
```
DEBUG: LLM call latency: 2.34s (xAI Grok API)
histogram_observe(smartcity_ids_llm_latency_seconds, 2.34)
```

**Typical Latency Ranges:**
- xAI Grok: 1-5 seconds
- OpenAI GPT-4: 2-8 seconds
- Fallback (rule-based): <0.1 seconds

---

## Kubernetes Automation Logs

### Automated Actions Available

| Action | Trigger | Kubernetes Operation |
|--------|---------|----------------------|
| `isolate_pod` | Severity ≥ 8 | Apply NetworkPolicy to block pod |
| `scale_up` | Severity ≥ 6 | Increase deployment replicas |
| `evict_pod` | Severity = 10 | Delete pod (force restart) |
| `log_only` | Severity < 6 | No automated action |

### Isolation Action Example

**Log Entry:**
```
INFO: Executing automated action: isolate_pod (target=healthcare-api-7bb856cbf4-4vkgs)
DEBUG: Creating NetworkPolicy: deny-all-healthcare-api-7bb856cbf4-4vkgs
INFO: NetworkPolicy applied successfully
```

**Kubernetes NetworkPolicy Created:**
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: deny-all-healthcare-api-7bb856cbf4-4vkgs
  namespace: smart-city
spec:
  podSelector:
    matchLabels:
      pod-name: healthcare-api-7bb856cbf4-4vkgs
  policyTypes:
  - Ingress
  - Egress
  # No rules = deny all traffic
```

**Effect:** Pod can no longer send or receive network traffic (isolated from cluster)

### Scale Up Action Example

**Log Entry:**
```
INFO: Executing automated action: scale_up (target=healthcare-api deployment)
DEBUG: Current replicas: 2, scaling to 4
INFO: Deployment scaled successfully
```

**Kubernetes Command:**
```bash
kubectl scale deployment healthcare-api -n smart-city --replicas=4
```

**Effect:** Increases service capacity to handle potential DDoS or increased load

---

## Prometheus Metrics

### What Metrics Are Exported?

**IDS API /metrics Endpoint:**
```
# HELP smartcity_ids_alerts_received_total Total number of alerts received
# TYPE smartcity_ids_alerts_received_total counter
smartcity_ids_alerts_received_total{source="falco"} 127.0

# HELP smartcity_ids_alerts_processed_total Alerts successfully processed
# TYPE smartcity_ids_alerts_processed_total counter
smartcity_ids_alerts_processed_total{source="falco",status="success"} 125.0
smartcity_ids_alerts_processed_total{source="falco",status="error"} 2.0

# HELP smartcity_ids_severity_total Alerts by severity level
# TYPE smartcity_ids_severity_total counter
smartcity_ids_severity_total{severity="8"} 12.0
smartcity_ids_severity_total{severity="7"} 45.0
smartcity_ids_severity_total{severity="6"} 68.0

# HELP smartcity_ids_actions_executed_total Automated actions executed
# TYPE smartcity_ids_actions_executed_total counter
smartcity_ids_actions_executed_total{action="isolate_pod"} 12.0
smartcity_ids_actions_executed_total{action="scale_up"} 5.0

# HELP smartcity_ids_llm_latency_seconds LLM API call latency
# TYPE smartcity_ids_llm_latency_seconds histogram
smartcity_ids_llm_latency_seconds_bucket{le="1.0"} 23.0
smartcity_ids_llm_latency_seconds_bucket{le="2.0"} 67.0
smartcity_ids_llm_latency_seconds_bucket{le="5.0"} 120.0
smartcity_ids_llm_latency_seconds_bucket{le="+Inf"} 127.0
smartcity_ids_llm_latency_seconds_sum 289.45
smartcity_ids_llm_latency_seconds_count 127.0
```

### How to Query Metrics

**Via Prometheus UI** (find port: `kubectl get svc -n monitoring prometheus -o jsonpath='{.spec.ports[0].nodePort}'`):
```promql
# Alert rate (alerts per second)
rate(smartcity_ids_alerts_received_total[5m])

# Alerts by severity (last hour)
sum by (severity) (increase(smartcity_ids_severity_total[1h]))

# LLM p95 latency
histogram_quantile(0.95, rate(smartcity_ids_llm_latency_seconds_bucket[5m]))

# Success rate
rate(smartcity_ids_alerts_processed_total{status="success"}[5m]) / 
rate(smartcity_ids_alerts_received_total[5m])
```

---

## PostgreSQL Audit Trail

### Database Schema

**Tables (12):**
1. `alerts` — All received alerts
2. `analysis_results` — LLM analysis outputs
3. `automation_actions` — Actions executed by K8s automation
4. `audit_logs` — Audit trail for compliance
5. `chat_conversations` — Analyst chat history for cross-session correlation
6. `iot_devices` — Registered IoT device inventory
7. `iot_events` — IoT telemetry events
8. `llm_api_calls` — Per-call LLM usage tracking
9. `llm_provider_health` — Provider health snapshots
10. `system_config` — Runtime configuration (LLM priority, cost ceilings)
11. `system_logs` — Internal system log entries
12. `throttled_alerts` — Alerts dropped by rate limiter

### Sample Queries

**Get Recent Alerts:**
```sql
SELECT 
  id,
  timestamp,
  source,
  severity,
  rule,
  container_name
FROM alerts
ORDER BY timestamp DESC
LIMIT 10;
```

**Get LLM Analysis for Alert:**
```sql
SELECT 
  a.rule,
  ar.severity AS llm_severity,
  ar.threat_type,
  ar.summary,
  ar.recommendations
FROM alerts a
JOIN analysis_results ar ON a.id = ar.alert_id
WHERE a.id = 123;
```

**Get Actions Taken:**
```sql
SELECT 
  aa.timestamp,
  aa.action_type,
  aa.target_pod,
  aa.success,
  a.severity
FROM automation_actions aa
JOIN alerts a ON aa.alert_id = a.id
ORDER BY aa.timestamp DESC
LIMIT 10;
```

**Audit Trail Query:**
```sql
SELECT 
  timestamp,
  action,
  user,
  resource,
  success,
  details
FROM audit_logs
WHERE timestamp > NOW() - INTERVAL '24 hours'
ORDER BY timestamp DESC;
```

---

## End-to-End Example

### Scenario: Attacker Reads /etc/shadow

**Timeline:**

```
T+0.000s: Attacker executes command
  $ kubectl exec -n smart-city healthcare-api-7bb856cbf4-4vkgs -- cat /etc/shadow

T+0.002s: Falco eBPF probe intercepts syscall
  [FALCO LOG]
  {"rule":"Read sensitive file untrusted", "priority":"Warning", "output":"Sensitive file opened..."}

T+0.050s: Falco forwarder normalizes and sends alert
  [FORWARDER LOG]
  POST http://ids-api:8000/api/alerts
  {"source":"falco", "severity":7, "alert_data":{...}}

T+0.060s: IDS API receives alert
  [IDS API LOG]
  INFO: 10.42.1.71:45782 - "POST /api/alerts HTTP/1.1" 200 OK
  INFO: Processing alert from falco: severity=7, rule=Read sensitive file untrusted

T+0.100s: IDS API calls LLM
  [IDS API LOG]
  DEBUG: Calling xAI Grok API for threat analysis...

T+2.400s: LLM responds
  [IDS API LOG]
  INFO: LLM analysis complete: severity=8, threat_type=Credential Access, latency=2.30s

T+2.450s: Automated action triggered
  [IDS API LOG]
  INFO: Automated action triggered: isolate_pod (severity ≥ 8 threshold met)

T+2.500s: Kubernetes network policy applied
  [IDS API LOG]
  DEBUG: Creating NetworkPolicy: deny-all-healthcare-api-7bb856cbf4-4vkgs
  INFO: K8s action successful: isolate_pod applied

T+2.550s: Metrics updated
  [PROMETHEUS METRICS]
  smartcity_ids_alerts_received_total{source="falco"} +1
  smartcity_ids_severity_total{severity="8"} +1
  smartcity_ids_actions_executed_total{action="isolate_pod"} +1
  smartcity_ids_llm_latency_seconds_bucket{le="5.0"} +1

T+2.600s: Database records persisted
  [POSTGRESQL]
  INSERT INTO alerts (source, severity, rule, container_name, timestamp, alert_data)
  INSERT INTO analysis_results (alert_id, severity, threat_type, summary, recommendations)
  INSERT INTO automation_actions (alert_id, action_type, target_pod, success, timestamp)

T+15.000s: Grafana dashboard updates
  [GRAFANA]
  Prometheus scrape interval (15s) pulls new metrics
  Dashboard graphs show:
    - Alert rate increased
    - New bar in severity distribution chart
    - LLM latency histogram updated
    - Automated actions timeline shows new event
```

### Cross-System Verification

**To verify the alert was real, check:**

1. **Falco logs match command execution:**
   ```bash
   kubectl logs -n falco-system -l app=falco --since=5m | grep "shadow"
   ```

2. **IDS API processed the alert:**
   ```bash
   kubectl logs -n smart-city -l app=ids-api --since=5m | grep "severity=8"
   ```

3. **Database contains the record:**
   ```bash
   kubectl exec deploy/postgres -n smart-city -- \
     psql -U idsuser -d idsdb -c "SELECT * FROM alerts WHERE rule LIKE '%shadow%' ORDER BY timestamp DESC LIMIT 1;"
   ```

4. **Metrics increased:**
   ```bash
   kubectl exec deploy/ids-api -n smart-city -- \
     curl -s localhost:8000/metrics | grep "smartcity_ids_alerts_received_total"
   ```

5. **NetworkPolicy was created:**
   ```bash
   kubectl get networkpolicies -n smart-city | grep "deny-all-healthcare-api"
   ```

**Result:** ✅ All systems agree - the alert was real and properly processed

---

## Debugging Tips

### No Falco Alerts Appearing

**Check:**
1. Falco pods running: `kubectl get pods -n falco-system`
2. Falco rules loaded: `kubectl exec -n falco-system falco-xxxxx -c falco -- falco --list`
3. Attack actually violates a rule (try: `cat /etc/shadow`)

### IDS API Not Receiving Alerts

**Check:**
1. Forwarder running: `kubectl get pods -n falco-system -l app=falco-forwarder`
2. Forwarder can reach IDS API: `kubectl exec -n falco-system deploy/falco-forwarder -- curl -s http://ids-api.smart-city:8000/health`
3. Forwarder logs: `kubectl logs -n falco-system -l app=falco-forwarder --tail=50`

### LLM Calls Failing

**Check:**
1. API key set: `kubectl get secret ids-api-secrets -n smart-city -o yaml | grep XAI_API_KEY`
2. Internet connectivity: `kubectl exec -n smart-city deploy/ids-api -- curl -s https://api.x.ai/v1`
3. IDS API logs: `kubectl logs -n smart-city -l app=ids-api | grep "LLM"`

### Metrics Not Updating

**Check:**
1. Prometheus scraping IDS API: `kubectl logs -n monitoring -l app=prometheus | grep "ids-api"`
2. Metrics endpoint accessible: `kubectl exec deploy/ids-api -n smart-city -- curl localhost:8000/metrics`
3. Prometheus target status: `http://NODE_IP:$(kubectl get svc -n monitoring prometheus -o jsonpath='{.spec.ports[0].nodePort}')/targets`

---

## Glossary

| Term | Definition |
|------|------------|
| **eBPF** | Extended Berkeley Packet Filter - kernel technology for monitoring syscalls |
| **Syscall** | System call - interface between user programs and kernel |
| **MITRE ATT&CK** | Framework for categorizing attacker techniques |
| **NetworkPolicy** | Kubernetes firewall rules for pod-to-pod traffic |
| **TSDB** | Time-Series Database (Prometheus stores metrics here) |
| **Histogram** | Metric type that buckets values (used for latency percentiles) |
| **Counter** | Metric type that only increases (used for alert counts) |
| **p95 Latency** | 95th percentile - 95% of requests faster than this value |

---

**For Questions:** See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) or [reference/DEMO_READINESS_REPORT.md](reference/DEMO_READINESS_REPORT.md)
