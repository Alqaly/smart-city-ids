# Smart City IDS - Architecture

Technical architecture documentation for the LLM-driven Intrusion Detection System.

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            Smart City IDS Architecture                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                      │
│  │   Traffic   │    │  Healthcare │    │   Parking   │   Smart City         │
│  │   Camera    │    │     API     │    │   System    │   Services           │
│  │   :5000     │    │    :5001    │    │    :5002    │   (Vulnerable)       │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘                      │
│         │                  │                  │                              │
│         └──────────────────┼──────────────────┘                              │
│                            ▼                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                        Kubernetes Cluster (K3s)                         ││
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    ││
│  │  │   Falco     │  │  Suricata   │  │   MQTT      │  │    IoT      │    ││
│  │  │  (Runtime)  │  │  (Network)  │  │   Broker    │  │  Devices    │    ││
│  │  └──────┬──────┘  └──────┬──────┘  └─────────────┘  └─────────────┘    ││
│  │         │                │                                              ││
│  │         ▼                ▼                                              ││
│  │  ┌─────────────────────────────────────────────────────────────────┐   ││
│  │  │                    Falco Forwarder                               │   ││
│  │  │              (Normalizes alerts → IDS API)                       │   ││
│  │  └──────────────────────────┬──────────────────────────────────────┘   ││
│  │                             ▼                                          ││
│  │  ┌─────────────────────────────────────────────────────────────────┐   ││
│  │  │                        IDS API                                   │   ││
│  │  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │   ││
│  │  │  │   FastAPI   │  │ LLM Engine  │  │   K8s Automation        │  │   ││
│  │  │  │  Endpoints  │◄─┤ (xAI/OpenAI)│─►│ (isolate/scale/evict)   │  │   ││
│  │  │  └─────────────┘  └─────────────┘  └─────────────────────────┘  │   ││
│  │  │                                                                  │   ││
│  │  │  ┌─────────────────────────────────────────────────────────────┐│   ││
│  │  │  │                     PostgreSQL                              ││   ││
│  │  │  │ (alerts, analysis_results, automation_actions, audit_logs)  ││   ││
│  │  │  └─────────────────────────────────────────────────────────────┘│   ││
│  │  └─────────────────────────────────────────────────────────────────┘   ││
│  │                             │                                          ││
│  │                             ▼                                          ││
│  │  ┌─────────────────────────────────────────────────────────────────┐   ││
│  │  │                    Monitoring Stack                              │   ││
│  │  │  ┌─────────────┐                    ┌─────────────┐             │   ││
│  │  │  │  Prometheus │───────────────────►│   Grafana   │             │   ││
│  │  │  │   :9090     │    metrics         │    :3000    │             │   ││
│  │  │  └─────────────┘                    └─────────────┘             │   ││
│  │  └─────────────────────────────────────────────────────────────────┘   ││
│  └─────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Details

### 1. IDS API (Core)

**Location:** `services/ids-api/src/`

| File | Purpose |
|------|---------|
| `main.py` | FastAPI application, alert endpoints, automation orchestration |
| `config.py` | Environment configuration, validation |
| `database.py` | PostgreSQL connection, alerts, analysis results, actions, audit logs |
| `llm_engine_xai.py` | xAI Grok integration for threat analysis |
| `llm_engine_openai.py` | OpenAI GPT fallback |
| `k8s_automation.py` | Kubernetes actions (isolate, scale, evict) |
| `metrics.py` | Prometheus metrics export |

**API Endpoints:**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/alerts` | POST | Receive security alerts |
| `/api/alerts` | GET | List stored alerts |
| `/api/alerts/{id}` | GET | Get specific alert |
| `/health` | GET | Health check |
| `/metrics` | GET | Prometheus metrics |
| `/docs` | GET | OpenAPI documentation |

### 2. LLM Engine

**Architecture:**

```
Alert JSON ──► System Prompt ──► LLM API ──► JSON Response ──► Automated Actions
                   │                             │
                   ▼                             ▼
            "Analyze this              {"severity": 8,
             security alert..."          "threat_type": "...",
                                        "recommendations": [...]}
```

**LLM Response Contract:**

```json
{
  "status": "success",
  "analysis": {
    "summary": "Short 1-2 sentence explanation",
    "severity": 8,
    "threat_type": "Privilege Escalation",
    "recommendations": ["Isolate pod", "Collect logs"],
    "automated_actions": ["isolate_pod"]
  }
}
```

### 3. Smart City Services

**Purpose:** Intentionally vulnerable demo services for attack simulation.

| Service | Port | Vulnerabilities |
|---------|------|-----------------|
| Traffic Camera | 5000 | Command injection, exposed debug |
| Healthcare API | 5001 | SQL injection, data exposure |
| Parking System | 5002 | Authentication bypass |

**Location:** `smart-city-services/`

### 4. Security Monitoring

#### Falco (Runtime Security)

- Detects container runtime anomalies
- Monitors syscalls, process execution
- Alerts on policy violations

**Alert Flow:**
```
Container ──► Falco ──► Falco Forwarder ──► IDS API
                 │
            (syscall monitoring)
```

#### Suricata (Network IDS)

- Network traffic analysis
- Signature-based detection
- Protocol anomaly detection

### 5. Kubernetes Automation

**Automated Actions (based on severity):**

| Severity | Action | Description |
|----------|--------|-------------|
| ≥8 | `isolate_pod` | Apply network policy to isolate |
| ≥6 | `scale_up` | Increase replica count |
| ≥4 | `log_alert` | Record for review |

**Implementation:** `services/ids-api/src/k8s_automation.py`

```python
# Example isolation
def isolate_pod(pod_name, namespace):
    # Creates NetworkPolicy blocking all ingress/egress
    network_policy = {...}
    api.create_namespaced_network_policy(namespace, network_policy)
```

---

## Data Flow

### Alert Processing Pipeline

```
1. Security Event Generated
   └─► Falco detects syscall anomaly
   └─► Suricata detects network anomaly

2. Alert Forwarding
   └─► Forwarder normalizes alert format
   └─► POST to IDS API /api/alerts

3. LLM Analysis
   └─► Build context with alert + system prompt
   └─► Call xAI Grok (or OpenAI fallback)
   └─► Parse JSON response

4. Automated Response
   └─► Check severity thresholds
   └─► Execute Kubernetes actions
   └─► Update Prometheus metrics

5. Persistence
   └─► Store alert + analysis in PostgreSQL
   └─► Log to stdout for kubectl logs
```

### Metrics Pipeline

```
IDS API ──(metrics)──► Prometheus ──(queries)──► Grafana
    │
    └── /metrics endpoint exposes:
        - smartcity_ids_alerts_received_total (counter)
        - smartcity_ids_severity_total (counter)
        - smartcity_ids_llm_latency_seconds (histogram)
        - smartcity_ids_actions_executed_total (counter)
        - smartcity_ids_time_to_mitigation_seconds (histogram)
        - smartcity_ids_llm_decision_outcome_total (counter)
```

### Metrics Source of Truth

The IDS API is the authoritative source of IDS metrics. Prometheus scrapes
`/metrics` directly from the IDS API on port `8000` and Grafana uses those
`smartcity_ids_*` series as the monitoring ground truth.

---

## Kubernetes Resources

### Namespaces

| Namespace | Purpose |
|-----------|---------|
| `smart-city` | Main application workloads |
| `monitoring` | Prometheus, Grafana |
| `falco-system` | Falco runtime security |
| `suricata-system` | Suricata network IDS |

### Key Deployments

```yaml
# smart-city namespace
- ids-api          # Core IDS service
- traffic-camera   # Demo service
- healthcare-api   # Demo service
- parking-system   # Demo service
- postgres         # Alert database
- mqtt-broker      # IoT message broker
- iot-devices      # IoT simulator

# monitoring namespace
- prometheus       # Metrics collection
- grafana          # Visualization
```

### Service Ports

| Service | Type | Internal | External |
|---------|------|----------|----------|
| ids-api | NodePort | 8000 | 30800 |
| grafana | NodePort | 3000 | 30300 |
| prometheus | NodePort | 9090 | 31701 |
| postgres | ClusterIP | 5432 | - |

---

## Security Considerations

### Defense-in-Depth Layers

1. **Network Level:** Suricata monitors traffic patterns
2. **Runtime Level:** Falco monitors container behavior
3. **Application Level:** IDS API analyzes combined alerts
4. **Response Level:** Automated Kubernetes actions

### Secrets Management

- API keys stored in Kubernetes Secrets
- Never committed to repository
- Mounted as environment variables in pods

### RBAC

The IDS API service account has permissions to:
- List/get pods and deployments
- Create/update network policies
- Scale deployments
- Evict pods

---

## Performance Characteristics

| Metric | Target | Notes |
|--------|--------|-------|
| Alert processing latency | <5s | Includes LLM call |
| LLM response time | 1-3s | Depends on provider |
| Prometheus scrape interval | 15s | Configurable |
| Alert retention | 30 days | PostgreSQL storage |
| Automation/Audit retention | 180 days | Governance traceability |

---

## Extension Points

### Adding New Alert Sources

1. Create forwarder in `services/forwarders/`
2. Normalize to expected JSON format
3. POST to `/api/alerts`

### Adding New Automated Actions

1. Add method to `k8s_automation.py`
2. Register in `main.py` action dispatcher
3. Update LLM prompt in `llm_engine_*.py`

### Custom Dashboards

1. Export from Grafana as JSON
2. Place in `infrastructure/monitoring/`
3. Run `scripts/generate-grafana-provisioning.sh` and apply `k8s-manifests/grafana-provisioning-dashboards.yaml`

---

*For deployment instructions, see [SETUP.md](SETUP.md)*  
*For operational procedures, see [OPERATIONS.md](OPERATIONS.md)*
