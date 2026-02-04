# Smart City IDS - Quick Start Guide

## What You Have

**A complete LLM-driven Intrusion Detection System with:**
- ✅ Operator Dashboard (web UI) at `http://localhost:8000/ui`
- ✅ REST API for threat analysis
- ✅ Real-time Falco/Suricata integration
- ✅ Kubernetes automation (K3s)
- ✅ LLM-powered threat analysis (xAI Grok-4 / OpenAI)
- ✅ Persistent storage (PostgreSQL)
- ✅ Monitoring (Prometheus/Grafana)

---

## Prerequisites

```bash
# You need these installed:
- Docker (or K3s pre-installed)
- kubectl
- Python 3.9+
- Git
```

Check your setup:
```bash
docker --version
kubectl version --client
python --version
```

---

## Deploy in 3 Steps

### Step 1: Start Everything

```bash
cd /home/kali/smart-city-ids
chmod +x scripts/start-everything.sh
./scripts/start-everything.sh
```

This will:
- ✅ Start K3s (Kubernetes)
- ✅ Deploy PostgreSQL
- ✅ Deploy Prometheus & Grafana
- ✅ Deploy Falco (runtime security)
- ✅ Deploy IDS API
- ✅ Deploy demo IoT services
- ⏱️ Takes 2-5 minutes

### Step 2: Wait for Services to Be Ready

```bash
# Watch pods come up
kubectl get pods -n smart-city -w

# Wait until all pods show "Running" (1/1 ready)
# Press Ctrl+C when done
```

### Step 3: Access the Dashboard

**Operator Dashboard (Web UI):**
```
http://localhost:8000/ui
```

**Login Credentials:**
- Username: `operator`
- Password: `operator`

---

## What You Can Do

### 1. View Security Incidents

**Web UI (Easiest):**
1. Go to `http://localhost:8000/ui`
2. Login with: operator / operator
3. See incidents, evidence, confidence scores

**Or via curl:**
```bash
# Get incidents
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"operator","password":"operator"}' | jq -r '.access_token')

curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/operator/incidents
```

### 2. Review Threat Analysis

```bash
# See a specific incident's analysis
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/operator/incident/{incident_id}
```

### 3. Check System Metrics

**In Web UI:** Click "Metrics" tab

**Via API:**
```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/operator/metrics
```

### 4. Change Automation Mode

**In Web UI:** Click "Settings" tab, select:
- **MANUAL** - Approve every action (safest)
- **ASSISTED** - Auto for low severity, approve high
- **AUTOPILOT** - Full automation (for mature teams)

---

## Send Test Alerts (Optional)

Simulate attacks to see the system in action:

```bash
# DDoS simulation
cd /home/kali/smart-city-ids
python attack-simulator/ddos_simulator.py http://localhost:8080 10 10

# Privilege escalation
python attack-simulator/privilege_escalation.py http://localhost:8080

# Data exfiltration
python attack-simulator/data_exfiltration.py http://localhost:8080
```

Watch the dashboard - new incidents will appear in real-time!

---

## API Endpoints

### Authentication
```
POST /api/auth/login
  Body: {"username":"operator","password":"operator"}
  Returns: {"access_token":"...", "token_type":"bearer", "user":"operator"}
```

### Incidents (Protected - Requires Token)
```
GET /api/operator/incidents?limit=50
  Returns: List of recent incidents with summaries, severity, confidence

GET /api/operator/incident/{incident_id}
  Returns: Full incident detail, evidence, reasoning, actions

GET /api/operator/evidence/{incident_id}
  Returns: Raw Falco/Suricata evidence with humanized descriptions

GET /api/operator/reasoning/{incident_id}
  Returns: LLM reasoning chain, confidence scores, key indicators

GET /api/operator/metrics
  Returns: System health metrics
```

### System Status (No Auth Required)
```
GET /
  Returns: Service status and available endpoints

GET /health
  Returns: Component health (xAI, OpenAI, K3s, Falco)
```

---

## Troubleshooting

### Issue: "K3s permission denied"
**Solution:**
```bash
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
sudo chmod 644 /etc/rancher/k3s/k3s.yaml
```

### Issue: "IDS API not running"
**Solution:**
```bash
# Check IDS API logs
kubectl logs -n smart-city deployment/ids-api -f

# Check if pod is running
kubectl get pods -n smart-city | grep ids-api
```

### Issue: "Dashboard shows 'Connection error'"
**Solution:**
```bash
# Check API is accessible
curl http://localhost:8000/health

# Check IDS API service
kubectl get svc -n smart-city | grep ids-api

# Port forward if needed
kubectl port-forward -n smart-city svc/ids-api 8000:8000 &
```

### Issue: "Login credentials not working"
**Solution:**
```bash
# Check auth is enabled in API
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"operator","password":"operator"}' | jq .
```

### Issue: "No incidents showing"
**Solution:**
```bash
# Check if Falco is running
kubectl get pods -n falco-system

# Generate test alerts
python attack-simulator/ddos_simulator.py http://localhost:8080 5 5

# Check IDS API is processing
curl http://localhost:8000/health | jq .
```

---

## Monitoring

### Grafana Dashboards
```
http://localhost:3000
Default: admin / admin
```

Dashboards available:
- Smart City IDS Overview
- Incident Timeline
- System Health

### Prometheus Metrics
```
http://localhost:9090
```

Query examples:
```
# LLM analysis count
ids_llm_analyses_total

# Average analysis time
ids_analysis_time_seconds

# False positive rate
ids_false_positive_rate
```

---

## Configuration

### LLM Provider

**xAI Grok-4 (Recommended):**
```bash
export XAI_API_KEY="your-xai-key"
```

**OpenAI GPT-4 (Fallback):**
```bash
export OPENAI_API_KEY="your-openai-key"
```

### Automation Mode

```bash
# Safe for demos
export AUTOMATION_MODE=dry-run

# Standard (manual approval for high severity)
export AUTOMATION_MODE=assisted

# Full automation
export AUTOMATION_MODE=autopilot
```

### Other Settings

```bash
# Alert deduplication (reduces LLM cost)
export DEDUPLICATOR_TTL_SECONDS=60
export DEDUPLICATOR_MAX_CACHE_SIZE=10000

# Severity thresholds
export CRITICAL_SEVERITY_THRESHOLD=8
export HIGH_SEVERITY_THRESHOLD=6
```

---

## Next Steps

### For Operators
1. ✅ Login to dashboard at `http://localhost:8000/ui`
2. ✅ Review incidents and evidence
3. ✅ Approve or adjust automated actions
4. ✅ Check metrics to understand system behavior

### For DevOps
1. ✅ Review Kubernetes deployments: `kubectl get all -n smart-city`
2. ✅ Check logs: `kubectl logs -n smart-city -f deployment/ids-api`
3. ✅ Monitor resources: `kubectl top pods -n smart-city`
4. ✅ Access Grafana: `http://localhost:3000`

### For Developers
1. ✅ Review API code: `services/ids-api/src/main.py`
2. ✅ Review operator interface: `services/ids-api/src/operator_interface.py`
3. ✅ Review data models: `services/ids-api/src/operator_models.py`
4. ✅ Check deployment: `k8s-manifests/services-no-build.yaml`

### For Security Analysis
1. ✅ Check threat intelligence: `docs/OPERATOR_INTERFACE.md`
2. ✅ Review LLM decisions: `/api/operator/reasoning/{id}`
3. ✅ See confidence scores: `/api/operator/incident/{id}`
4. ✅ Analyze patterns: Prometheus metrics

---

## Stopping the System

```bash
# Stop all Smart City services
kubectl delete namespace smart-city

# Stop K3s
sudo systemctl stop k3s

# Or full cleanup
./scripts/cleanup.sh
```

---

## Getting Help

### Documentation
- **Complete Guide:** `docs/SUPERVISOR_GUIDE.md`
- **Operator Manual:** `docs/OPERATOR_INTERFACE.md`
- **Architecture:** `docs/ARCHITECTURE.md`
- **Troubleshooting:** `docs/TROUBLESHOOTING.md`

### API Documentation
```bash
# FastAPI Swagger UI
http://localhost:8000/docs

# ReDoc
http://localhost:8000/redoc
```

### Logs
```bash
# All Smart City services
kubectl logs -n smart-city -f

# Specific service
kubectl logs -n smart-city -f deployment/ids-api

# Previous logs (if crashed)
kubectl logs -n smart-city --previous deployment/ids-api
```

---

## Common Workflows

### Respond to a Critical Alert
1. Dashboard shows alert with severity 8+
2. Review evidence (Falco/Suricata raw data)
3. Read LLM reasoning (confidence, key indicators)
4. Click "Approve Action" to isolate container
5. Monitor in Kubernetes: `kubectl get pods -n smart-city`

### Investigate False Positive
1. Click incident to see full detail
2. Check "Mitigating Factors" in reasoning
3. Review raw evidence for context
4. Dismiss alert if false positive

### Tune Automation
1. Go to Settings → Governance Mode
2. Start with MANUAL (all approval)
3. Monitor approval patterns
4. Upgrade to ASSISTED when comfortable
5. Graduate to AUTOPILOT only for mature team

### Performance Monitoring
1. Check metrics at `/api/operator/metrics`
2. Monitor Grafana dashboards
3. Analyze response times
4. Review operator approval rates
5. Adjust thresholds as needed

---

## Quick Reference

| Task | Command | URL |
|------|---------|-----|
| View Dashboard | Browser | `http://localhost:8000/ui` |
| API Docs | Browser | `http://localhost:8000/docs` |
| Grafana | Browser | `http://localhost:3000` |
| Prometheus | Browser | `http://localhost:9090` |
| Get Incidents | Curl | `curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/operator/incidents` |
| Check Health | Curl | `curl http://localhost:8000/health` |
| View K8s Pods | kubectl | `kubectl get pods -n smart-city` |
| View K8s Logs | kubectl | `kubectl logs -n smart-city -f deployment/ids-api` |
| Stop All | kubectl | `kubectl delete namespace smart-city` |

---

## Ready to Go!

Your Smart City IDS is now:
- ✅ **Deployed** on Kubernetes
- ✅ **Accessible** via web dashboard
- ✅ **Monitored** with Prometheus/Grafana
- ✅ **Ready** to detect and respond to threats

**Start here:** `http://localhost:8000/ui`
**Default Login:** operator / operator

Questions? Check `docs/TROUBLESHOOTING.md`
