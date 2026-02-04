# How Smart City IDS Works: Technical Deep Dive

This document explains the complete data flow and architecture of the Smart City IDS system, from threat detection to automated response.

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Component Architecture](#component-architecture)
3. [Data Flow: Complete Example](#data-flow-complete-example)
4. [Real vs. Emulated](#real-vs-emulated)

---

## System Overview

The Smart City IDS is a **real-time security orchestration system** that:

1. **Detects** security threats using runtime and network monitoring tools (Falco, Suricata)
2. **Analyzes** threats using Large Language Models (xAI Grok, OpenAI GPT)
3. **Responds** automatically with Kubernetes actions (pod isolation, scaling, eviction)
4. **Observes** the entire process through Prometheus metrics and Grafana dashboards
5. **Persists** all decisions in PostgreSQL for auditing and analysis

---

## Component Architecture

### Layer 1: IoT Device Emulation (30-100 pods)

**Purpose:** Generate realistic IoT traffic and events

**Components:**
- 30-100 MQTT-connected containers simulating:
  - Traffic cameras (high message rate: 1-2 msg/sec)
  - Environmental sensors (medium: 1 msg/10 sec)
  - Motion detectors (low/burst: 1 msg/30 sec)

**Real Behavior:**
```
IoT Pod #1 → Opens TCP connection to MQTT Broker
            → Publishes JSON message every 2 seconds
            → Message: {"vehicle_count": 47, "avg_speed": 35}
            → Broker stores message in memory
            
IoT Pod #2 → Same process, different device type
            → Message: {"temperature_c": 22.5, "humidity": 65}
```

**Why Real:**
- Uses real MQTT protocol (binary, not text)
- Real TCP/IP networking between pods
- Real message serialization/deserialization
- Can be detected by network monitoring tools

---

### Layer 2: Security Monitoring Tools

#### **Falco (Runtime IDS)**

**Purpose:** Detect suspicious process and system behavior inside containers

**How It Works:**
```
Container Process Executes System Call
    ↓
eBPF Kernel Hook Intercepts
    ↓
Compare Against 100+ Rules (YAML-defined)
    ↓
If Match → Generate Alert JSON
    ↓
Forward to IDS API
```

**Example Detection:**
```
Rule: "Terminal shell in container"
Triggered When:
  - Process name = "bash" OR "sh"
  - Container name matches known workload (traffic-camera, healthcare-api)
  - Process was NOT started by parent process

Real Event:
  Pod: traffic-camera-7ddc6b8db6-nj8w7
  Process: /bin/bash (PID 1234)
  User: root
  Parent: supervisord (suspicious!)
  
Alert Output:
{
  "rule": "Terminal shell in container",
  "priority": "Critical",
  "output": "A shell was spawned inside the container",
  "output_fields": {
    "container.name": "traffic-camera-7ddc6b8db6-nj8w7",
    "proc.pid": 1234,
    "proc.name": "bash",
    "proc.cmdline": "/bin/bash",
    "user.name": "root"
  }
}
```

**Why Real:**
- Detects actual kernel syscalls (`execve`, `open`, `connect`, etc.)
- Rules are from Falco community project (battle-tested)
- Zero false negatives for configured threats

---

#### **Suricata (Network IDS)**

**Purpose:** Detect suspicious network traffic patterns

**How It Works:**
```
Network Packet Traverses CNI Interface
    ↓
Suricata Decodes Packet (Layer 7: Application)
    ↓
Match Against ET (Emerging Threats) Rules
    ↓
If Match → Generate Alert
    ↓
Forward to IDS API
```

**Example Detection:**
```
Packet: IoT Pod sends HTTP GET to suspicious IP
  Source: 10.42.1.47 (IoT Pod)
  Destination: 203.0.113.45 (Malicious C2 Server)
  Protocol: HTTP
  URI: /api/cmd?id=12345

Rule Match: "ET TROJAN Known Botnet C2"
Alert:
{
  "event_type": "alert",
  "alert": {
    "action": "alert",
    "signature": "Known Botnet C2 Communication Detected",
    "category": "Trojan Traffic"
  },
  "src_ip": "10.42.1.47",
  "dest_ip": "203.0.113.45",
  "dest_port": 80
}
```

**Why Real:**
- Inspects actual packet payloads
- Uses curated threat intelligence rules
- Detects known attack patterns with high confidence

---

### Layer 3: Alert Forwarding

**Falco Forwarder & Suricata Forwarder**

Purpose: Normalize and forward raw security alerts to the IDS API

**Process:**
```
Raw Alert (from Falco/Suricata)
    ↓
Forwarder Pod Receives
    ↓
Parse & Normalize JSON
    ↓
POST to IDS API: /api/alerts
    ↓
HTTP 200 OK response
```

**Real Behavior:**
- Forwarders are stateless consumers
- Can scale horizontally (multiple replicas handle high alert volume)
- Network transport is HTTP/HTTPS (TLS optional)

---

### Layer 4: IDS API (Decision Engine)

**Purpose:** Receive alerts, analyze with LLM, execute automated actions

**Architecture:**
```
POST /api/alerts (Receives alert)
    ↓
┌─────────────────────────────────────┐
│ PHASE 1: Alert Parsing & Storage    │
│ - Extract rule, priority, container │
│ - Store raw alert in PostgreSQL     │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ PHASE 2: LLM Analysis               │
│ - Build system prompt with context  │
│ - Call xAI Grok or OpenAI GPT       │
│ - Parse JSON response               │
│ - Extract: severity, threat_type    │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ PHASE 3: Decision Logic             │
│ if severity >= 8:                   │
│    execute isolate_pod()            │
│ elif severity >= 6:                 │
│    execute scale_up()               │
│ else:                               │
│    log_only()                       │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ PHASE 4: Kubernetes Automation      │
│ - Call Kubernetes API               │
│ - Apply network policies, scale     │
│ - Record action in PostgreSQL       │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ PHASE 5: Metrics Emission           │
│ - Increment Prometheus counters     │
│ - Record LLM latency histogram      │
│ - Export metrics via /metrics       │
└─────────────────────────────────────┘
    ↓
HTTP 200 OK (Alert processed)
```

**Real Code Example:**
```python
@app.post("/api/alerts")
async def receive_alert(alert: Alert):
    # 1. Validate and store
    db_alert = db.save_alert(alert)
    
    # 2. Call LLM
    start_time = time.time()
    analysis = await xai_engine.analyze_alert(alert)
    llm_latency = time.time() - start_time
    
    # 3. Save analysis
    db.save_analysis(db_alert.id, analysis)
    
    # 4. Take action if needed
    if analysis["severity"] >= 8:
        k8s.isolate_pod(alert.output_fields["container.name"])
        db.save_action("isolate_pod", alert.id)
        metrics.actions_executed["isolate_pod"].inc()
    
    # 5. Emit metrics
    metrics.alerts_received.inc()
    metrics.severity[analysis["severity"]].inc()
    metrics.llm_latency.observe(llm_latency)
    
    return {"status": "processed", "alert_id": db_alert.id}
```

**Why Real:**
- Makes real HTTP calls to LLM APIs (costs real money)
- Uses real Kubernetes client (kubectl under the hood)
- Stores in real PostgreSQL database
- Emits real Prometheus metrics

---

### Layer 5: PostgreSQL (Persistent Storage)

**Purpose:** Store all alerts, analyses, and actions for auditing and forensics

**Tables:**
```sql
alerts:
  - id (UUID)
  - source (falco, suricata)
  - rule (string)
  - container_name (string)
  - severity (1-10)
  - timestamp (datetime)
  - raw_alert_json (jsonb)

analysis_results:
  - id (UUID)
  - alert_id (FK)
  - llm_engine (xai-grok, openai)
  - severity (1-10)
  - threat_type (string)
  - summary (text)
  - recommendations (array)
  - llm_latency_ms (integer)

automation_actions:
  - id (UUID)
  - alert_id (FK)
  - action_type (isolate_pod, scale_up, evict)
  - target_pod (string)
  - executed_at (datetime)
  - result (success, failed, pending_approval)
```

**Real Behavior:**
- All data persists to disk
- Supports ACID transactions
- Can query historical data
- Enables compliance/audit trail

---

### Layer 6: Prometheus (Metrics Collection)

**Purpose:** Collect time-series metrics from all components

**Scrape Process:**
```
Every 5 seconds:
  Prometheus → HTTP GET /metrics (from IDS API)
              → HTTP GET /metrics (from MQTT Broker)
              → HTTP GET /metrics (from each service)
  
  Collect response:
    ids_alerts_received_total{source="falco"} 1042
    ids_severity_total{severity="8"} 15
    ids_severity_total{severity="9"} 8
    ids_llm_latency_seconds_bucket{le="1.0"} 35
    ids_llm_latency_seconds_bucket{le="5.0"} 40
    ...
  
  Store in TSDB (Time-Series Database)
  at /prometheus/data/
```

**Real Behavior:**
- Stores 15 days of data by default
- Enables time-series queries and graphing
- Detects trends and anomalies
- Powers alerting rules

---

### Layer 7: Grafana (Visualization)

**Purpose:** Display system health and security posture in real-time

**Dashboards:**
```
Smart City IDS Dashboard
├─ Alert Rate (5-min moving average)
│  └─ Query: rate(ids_alerts_received_total[5m])
│     Shows: Spikes indicate attacks/anomalies
│
├─ Severity Distribution (pie chart)
│  └─ Query: sum by (severity) (ids_severity_total)
│     Shows: What % of alerts are critical vs. informational
│
├─ LLM Response Time (histogram)
│  └─ Query: histogram_quantile(0.95, ids_llm_latency_seconds)
│     Shows: p95 LLM latency (SLO = 5 seconds)
│
├─ Automated Actions (bar chart)
│  └─ Query: sum by (action) (increase(ids_actions_executed_total[1h]))
│     Shows: How many pods were isolated, scaled, etc.
│
└─ Pod Health (table)
   └─ Query: kube_pod_container_restarts_total
      Shows: Which pods are crashing
```

**Why Real:**
- Queries actual Prometheus API
- Displays live, interactive graphs
- Supports drill-down and time-range selection
- Enables real-time incident response

---

## Data Flow: Complete Example

**Scenario:** An attacker gains shell access to a traffic camera pod

```
[T=0ms] Attacker executes: kubectl exec -it traffic-camera-xyz -- /bin/bash

[T=10ms] Process /bin/bash is created in container
        Falco eBPF hook detects syscall: execve("/bin/bash")
        Compares against rules
        Rule "Terminal shell in container" MATCHES

[T=20ms] Falco generates alert JSON:
        {
          "rule": "Terminal shell in container",
          "priority": "Critical",
          "output": "A shell was spawned inside the container",
          "output_fields": {
            "container.name": "traffic-camera-xyz",
            "proc.name": "bash",
            "proc.pid": 5678
          }
        }

[T=25ms] Falco Forwarder receives alert
        POST /api/alerts with the JSON

[T=26ms] IDS API receives request
        Stores alert in PostgreSQL
        Calls xAI Grok LLM with context

[T=26 + LLM_LATENCY] xAI API returns:
        {
          "severity": 9,
          "threat_type": "Privilege Escalation",
          "summary": "Unauthorized shell access to containerized service"
        }

[T=27.5s] IDS API checks: severity 9 >= 8 (threshold)
         Executes isolate_pod("traffic-camera-xyz")
         
         Kubernetes Action:
         kubectl create networkpolicy --deny-all -l pod=traffic-camera-xyz

[T=28ms] Pod is now isolated
        - Cannot send outbound connections
        - Cannot receive inbound connections
        - But stays running (for forensics)

[T=28.5ms] IDS API saves action to PostgreSQL:
         INSERT INTO automation_actions
         (alert_id, action_type, target_pod, result)
         VALUES (1, 'isolate_pod', 'traffic-camera-xyz', 'success')

[T=29ms] IDS API emits Prometheus metrics:
        ids_severity_total{severity="9"} += 1
        ids_actions_executed_total{action="isolate_pod"} += 1
        ids_llm_latency_seconds.observe(1.5)

[T=35ms] Prometheus scrapes /metrics endpoint
        Stores the new metric values

[T=35s] Grafana dashboard updates
       Shows:
       - Alert count increased by 1
       - 1 pod was isolated in last 5 seconds
       - Severity histogram updated with a "9"

[T=5m] Security analyst is alerted by Grafana
      Logs into dashboard
      Sees the isolated pod
      Reviews the attack chain:
        - Original alert: shell spawn
        - LLM analysis: privilege escalation threat
        - Action taken: pod isolation
        - Time to mitigation: 1.5 seconds
      
      Analyst approves the action or rolls it back
```

---

## Real vs. Emulated

### What Is REAL

| Component | Real Behavior | Evidence |
|-----------|---------------|----------|
| **IoT Traffic** | Real MQTT messages, real TCP/IP | Packet capture shows actual protocol |
| **Falco Alerts** | Real kernel syscalls, real eBPF | Detects actual process creation |
| **Suricata Alerts** | Real packet inspection, real IDS rules | Matches known attack signatures |
| **IDS API Processing** | Real FastAPI application, real business logic | HTTP logs show processing pipeline |
| **LLM Calls** | Real API calls to xAI/OpenAI | API costs real money per call |
| **Kubernetes Actions** | Real kubectl commands, real NetworkPolicies | kubectl describe networkpolicies confirms |
| **PostgreSQL Storage** | Real SQL queries, real disk persistence | psql shows stored data after restart |
| **Prometheus Metrics** | Real time-series data, real scrapes | PromQL queries return numeric data |
| **Grafana Dashboards** | Real live data visualization | Browser shows interactive charts |

### What Is EMULATED (By Design)

| Aspect | Emulated As | Why |
|--------|------------|-----|
| **City Scale** | 30-100 IoT pods | Cannot deploy to actual city; scaled for testing |
| **Device Diversity** | Traffic/environment/motion types | Represents actual device classes |
| **Attack Scenarios** | ddos_simulator.py script | Can't attack real infrastructure |
| **Attack Timing** | Injected on demand | Can replay scenarios reproducibly |
| **Geographic Distribution** | All in single K3s cluster | Single test environment is sufficient |

### Key Principle

**The system detects and responds to REAL security events, even if the devices and attacks are EMULATED at scale.**

This is methodologically sound because:
1. **Real detection tools** (Falco, Suricata) trigger on real behavior
2. **Real processing** (IDS API, LLM) analyzes the real evidence
3. **Real response** (Kubernetes) executes the decided action
4. **Real persistence** (PostgreSQL) stores the outcome
5. **Real metrics** (Prometheus) measure the response

The emulation aspect (scale, device count, attack injection) is transparent and does not affect the validity of the security analysis.

---

## References

- [Falco Documentation](https://falco.org/docs/)
- [Suricata Documentation](https://suricata.readthedocs.io/)
- [Kubernetes Documentation](https://kubernetes.io/docs/)
- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/grafana/)
