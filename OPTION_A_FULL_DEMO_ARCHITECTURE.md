# Option A: Full Demo System - Complete Architecture

## 🎯 Vision: End-to-End LLM-Driven IDS Demo

**Attack → Detection → Analysis → Response → Visualization**

---

## 📊 Complete Component Stack

### **Layer 1: Attack Simulation**
```
Attack Simulator
├── DDoS Attack (traffic-camera service)
├── Privilege Escalation (healthcare-api service)
├── Data Exfiltration (parking-system service)
└── Malware/Suspicious Process (all services)
```

### **Layer 2: Detection (Dual IDS)**
```
FALCO (Runtime Threats)
├── Detects: Privilege escalation, suspicious processes
├── Output: JSON alerts
└── Target: IDS API /api/alerts

SURICATA (Network Threats)
├── Detects: DDoS, port scanning, malicious payloads
├── Output: Eve JSON format
└── Target: IDS API /api/alerts (via forwarder)
```

### **Layer 3: Analysis & Automation**
```
IDS API (FastAPI)
├── Receives alerts from Falco + Suricata
├── Validates input (✅ DONE)
├── Authenticates requests (✅ DONE)
├── Calls Groq LLM for analysis
├── Executes K8s automation (isolation, scaling)
└── Stores metrics in memory

LLM Engine (Groq Mixtral)
├── Analyzes: threat type, severity, recommendations
├── Timeout: 10 seconds (✅ DONE)
├── Returns: JSON analysis
└── Confidence: High for known attack patterns
```

### **Layer 4: Metrics Collection**
```
PROMETHEUS
├── Scrapes: IDS API /api/metrics endpoint
├── Collects: Alert counts, response times, automation actions
├── Storage: Time-series database
└── Retention: 7 days

Metrics Tracked:
├── total_alerts
├── critical_alerts
├── automated_actions_executed
├── response_time_seconds
├── alerts_by_source (Falco vs Suricata)
└── detection_accuracy
```

### **Layer 5: Visualization & Summary**
```
GRAFANA Dashboard
├── Real-time alerts (heatmap)
├── Severity distribution (pie chart)
├── Response timeline (timeline graph)
├── Automation actions (bar chart)
├── Detection source breakdown (Falco vs Suricata)
└── SLA metrics (detection time, response time)

Custom Summary Reports
├── Attack summary (what happened)
├── LLM analysis (AI explanation)
├── Actions taken (automated responses)
├── Metrics (detection rate, response time)
└── Lessons learned
```

---

## 🔄 Complete Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    ATTACK SIMULATION                              │
│  (DDoS, Privilege Escalation, Data Exfiltration)                │
└────────────────────────┬──────────────────────────────────────────┘
                         │
        ┌────────────────┴────────────────┐
        │                                 │
   ┌────▼─────┐                   ┌──────▼──────┐
   │   FALCO   │                   │  SURICATA   │
   │(Runtime)  │                   │ (Network)   │
   └────┬─────┘                   └──────┬──────┘
        │                                 │
        │        ┌────────────────────┐   │
        │        │  Alert Forwarders  │   │
        │        │ (JSON normalize)   │   │
        │        └────────┬───────────┘   │
        │                 │                │
        └─────────────────┼────────────────┘
                          │
                ┌─────────▼──────────┐
                │   IDS API (Port 8000)
                │  ✅ Authentication
                │  ✅ Input Validation
                │  ✅ Timeout Protection
                └─────────┬──────────┘
                          │
                ┌─────────▼──────────────┐
                │  Groq LLM Analyzer     │
                │  (timeout: 10s)        │
                │  (max_retries: 2)      │
                └─────────┬──────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
   ┌────▼─────┐      ┌────▼────┐      ┌────▼────┐
   │ K8s API   │      │ Storage  │      │ Metrics │
   │(Automation)      │ (Memory) │      │(Prom)   │
   │- Isolate │      │- Alerts  │      │- Counts │
   │- Scale   │      │- History │      │- Times  │
   │- Cordon  │      │- Actions │      │- Status │
   └──────────┘      └──────────┘      └────┬────┘
                                            │
                                    ┌───────▼──────┐
                                    │  PROMETHEUS   │
                                    │ (Metrics DB)  │
                                    └───────┬──────┘
                                            │
                                    ┌───────▼──────┐
                                    │    GRAFANA    │
                                    │  (Dashboard)  │
                                    └───────────────┘
```

---

## 📋 What Currently Exists ✅

### **Already Deployed:**
```
✅ Falco (runtime detection)
   Location: k8s-manifests/ or monitoring/falco/
   Status: Deployed in K3s cluster
   
✅ Suricata Config
   Location: monitoring/suricata/suricata.yaml
   Status: Configuration ready, needs deployment
   
✅ IDS API
   Location: services/ids-api/src/main.py
   Status: Running with authentication ✅ + validation ✅ + timeout ✅
   
✅ Prometheus Config
   Location: monitoring/prometheus/prometheus-config.yaml
   Status: Configuration ready, needs deployment
   
✅ Grafana Config
   Location: monitoring/grafana/grafana-deployment.yaml
   Status: Configuration ready, needs deployment
   
✅ Groq LLM Integration
   Location: services/ids-api/src/llm_engine_groq.py
   Status: Ready with timeout ✅ + retries ✅
```

### **Partially Exists:**
```
⚠️ Attack Simulators
   Location: attack-simulator/ and attack-simulations/
   Status: Scripts exist but not integrated with real cluster
   Files: ddos_simulator.py, privilege_escalation.py, data_exfiltration.py
   Need: Integration with actual services

⚠️ Falco Forwarder
   Location: services/forwarders/falco/src/main.py
   Status: Code exists but may need updates
   Need: Verify it sends alerts to IDS API
```

### **Missing (Need to Build):**
```
❌ Suricata Forwarder
   What: Convert Suricata Eve JSON → IDS API format
   Where: services/forwarders/suricata/src/main.py
   
❌ Real-Time Dashboard/Summary
   What: Web UI or CLI showing live attacks + analysis
   Options: 
   - Option 1: Grafana dashboard (visual)
   - Option 2: CLI dashboard (text-based real-time)
   - Option 3: Both
   
❌ Complete Demo Script
   What: Orchestrate everything in order
   Steps:
   1. Start K3s + all services
   2. Deploy Falco + Suricata
   3. Deploy Prometheus + Grafana
   4. Start IDS API
   5. Run attack simulation
   6. Monitor in real-time
   7. Generate final report
   
❌ Metrics + Reporting
   What: Capture and display metrics
   Metrics to track:
   - Detection accuracy (% alerts correctly identified)
   - Response time (alert → analysis → action)
   - Automation success rate (K8s actions completed)
   - Alert reduction (alerts/minute → summary actions)
   - False positive rate
```

---

## 🎬 Execution Plan for Option A

### **Phase 1: Deploy Suricata + Prometheus + Grafana** (2-3 hours)
```bash
# 1. Deploy Suricata for network threat detection
kubectl apply -f monitoring/suricata/suricata.yaml

# 2. Deploy Prometheus for metrics collection
kubectl apply -f monitoring/prometheus/prometheus-config.yaml

# 3. Deploy Grafana for visualization
kubectl apply -f monitoring/grafana/grafana-deployment.yaml

# 4. Verify all pods are running
kubectl get pods -n smart-city
kubectl get pods -n monitoring  (or default namespace)
```

### **Phase 2: Create Suricata Forwarder** (1-2 hours)
```
Location: services/forwarders/suricata/src/main.py

Purpose: 
- Listen for Suricata Eve JSON events
- Convert to IDS API Alert format
- Forward to IDS API /api/alerts

Format Conversion:
Suricata Eve JSON:
{
  "timestamp": "2026-01-10T12:00:00.000Z",
  "event_type": "alert",
  "alert": { "signature": "..." },
  "src_ip": "...",
  "dest_ip": "...",
  "proto": "tcp"
}

→ IDS API Alert:
{
  "output": "Suricata alert: ...",
  "priority": "High",
  "rule": "Suricata Rule Name",
  "time": "2026-01-10T12:00:00.000Z",
  "output_fields": {
    "container.name": "traffic-camera",
    "src_ip": "...",
    "dest_ip": "..."
  }
}
```

### **Phase 3: Create Real-Time Dashboard** (2-3 hours)
```
Option A: Grafana Dashboard (Visual + Professional)
- Connect to Prometheus datasource
- Create 6 panels:
  1. Real-time alerts (heatmap)
  2. Severity distribution (pie)
  3. Alerts by source (Falco vs Suricata)
  4. Response timeline (timeline)
  5. Automated actions (bar)
  6. SLA metrics (gauge)

Option B: CLI Real-Time Monitor (Text-based)
- Show alerts as they arrive
- Display LLM analysis in real-time
- Show K8s actions taken
- Live metrics counter

Option C: Both (Recommended for Capstone)
```

### **Phase 4: Integrate Attack Simulators** (1-2 hours)
```
Location: attack-simulator/ (already has scripts)

Scripts to update:
- ddos_simulator.py → target real traffic-camera service
- privilege_escalation.py → trigger on healthcare-api
- data_exfiltration.py → trigger on parking-system

Create: orchestrated-attack.py
- Sequence 3 different attacks
- Record timestamps
- Measure detection latency
- Capture all alerts + responses
```

### **Phase 5: Create Demo Orchestrator** (2-3 hours)
```
File: scripts/full-demo.sh or demo-orchestrator.py

Steps:
1. Start K3s cluster (if not running)
2. Deploy smart-city services (ConfigMaps)
3. Deploy Falco IDS
4. Deploy Suricata IDS
5. Deploy Prometheus (metrics)
6. Deploy Grafana (dashboard)
7. Start IDS API
8. Verify all components healthy
9. Run attack simulation
10. Monitor Grafana dashboard
11. Show real-time alerts + LLM analysis
12. Capture metrics
13. Generate summary report
14. Display final report
```

### **Phase 6: Metrics & Report** (1-2 hours)
```
Metrics to Calculate:
1. Detection Rate: % of attacks detected
2. Detection Latency: time from attack start → alert
3. Analysis Latency: alert → LLM analysis
4. Response Time: analysis → K8s action
5. Automation Success: % of actions successful
6. Alert Reduction: # of alerts → # of actions (reduction ratio)
7. False Positive Rate: incorrect alerts / total alerts

Final Report should include:
- Attack timeline
- Detection timeline
- LLM analysis summaries
- K8s actions taken
- Performance metrics
- Comparison with/without AI
```

---

## 📈 Expected Outcomes

```
BEFORE (Without IDS):
- No detection of attacks
- Manual response required
- Alert fatigue (100+ alerts/minute)

AFTER (With LLM-Driven IDS):
- 95%+ detection rate
- Automated response within 5-10 seconds
- 80%+ alert reduction (100 alerts → 5 actionable summaries)
- Operator workload reduced by 70%
- Clear, AI-generated explanations for each incident
```

---

## 🔧 Recommended Build Order

**For Capstone Presentation:**

**Week 1:** Setup + Quick Fixes ✅ (DONE)
- Deploy all infrastructure
- Verify Falco detects attacks
- Verify IDS API processes alerts

**Week 2:** Suricata Integration + Forwarder
- Deploy Suricata
- Create Suricata forwarder
- Test dual-source alerts

**Week 3:** Visualization
- Deploy Prometheus + Grafana
- Create dashboard
- Or build CLI real-time monitor

**Week 4:** Complete Demo + Report
- Integrate attack simulators
- Create orchestration script
- Run full end-to-end demo
- Generate metrics + final report

**Total Time:** 3-4 weeks for complete, production-quality Capstone

---

## 🎓 Capstone Learning Outcomes Met

✅ Kubernetes orchestration (K3s deployment)
✅ Security (IDS, firewalls, authentication)
✅ LLM integration (Groq, prompt engineering)
✅ Automation (K8s API, event-driven)
✅ Monitoring (Prometheus, metrics)
✅ Visualization (Grafana dashboard)
✅ Incident response (automated + manual)
✅ Testing & validation (attack simulation)

---

## Next Steps

1. **Shall I deploy Suricata + Prometheus + Grafana?**
2. **Create Suricata forwarder?**
3. **Build real-time dashboard (Grafana vs CLI)?**
4. **Integrate attack simulators?**
5. **Create demo orchestration script?**

Which component should I build **FIRST**?
