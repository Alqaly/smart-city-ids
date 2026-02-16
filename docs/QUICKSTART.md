# Quick Start Guide

Get the Smart City IDS running in 5 minutes.

---

## Prerequisites

- **OS:** Linux (Kali, Ubuntu 22.04, Debian 12, or similar)
- **Hardware:** 4GB RAM, 2 CPU cores minimum (8GB/4 cores recommended)
- **Tools:** `kubectl`, `git`
- **LLM API Keys:** At least one of:
  - `XAI_API_KEY` (xAI Grok access)
  - `OPENAI_API_KEY` (OpenAI GPT access)
  - `ANTHROPIC_API_KEY` (Anthropic Claude access)
  - `GEMINI_API_KEY` (Google Gemini access)
  - `KIMI_API_KEY` (Moonshot Kimi access)

---

## Installation: 5 Minutes

### Step 1: Set LLM API Key

```bash
# Option A: Use xAI Grok (recommended)
export XAI_API_KEY="your-xai-key-here"

# Option B: Use OpenAI
export OPENAI_API_KEY="your-openai-key-here"

# Option C: Use Anthropic Claude
export ANTHROPIC_API_KEY="your-anthropic-key-here"

# Option D: Use Google Gemini (free tier: 1500 req/day)
export GEMINI_API_KEY="your-gemini-key-here"

# Option E: Use Moonshot Kimi
export KIMI_API_KEY="your-kimi-key-here"

# Persist to ~/.bashrc
echo 'export XAI_API_KEY="your-xai-key-here"' >> ~/.bashrc
source ~/.bashrc
```

### Step 2: Clone Repository

```bash
git clone https://github.com/YOUR-USERNAME/smart-city-ids.git
cd smart-city-ids
```

### Step 3: Start Everything

```bash
# This script handles K3s installation, Kubernetes deployment, and service startup
sudo bash scripts/start-everything.sh
```

**What happens:**
- Phase 1: Checks K3s installation
- Phase 2: Cleans up old deployments
- Phase 3: Starts K3s cluster
- Phase 4: Deploys manifests (namespace, services, operators)
- Phase 5: Launches IoT emulation (30-100 pods)
- Phase 6: Waits for services to be ready
- Phase 7: Performs health checks
- Phase 8: Displays service URLs

**Expected output (final 10 lines):**
```
[✓] Phase 8: Discovering service URLs
Smart City IDS is ready!

  Grafana (Live Dashboards): http://192.168.1.X:30300
  Prometheus (Metrics):      http://192.168.1.X:31106
  IDS API (Documentation):   http://192.168.1.X:30800/docs

Smart City Services:
  Traffic Camera:            http://192.168.1.X:30100
  Healthcare API:            http://192.168.1.X:30101
  Parking System:            http://192.168.1.X:30102
```

---

## Verify Installation

### Check All Pods Are Running

```bash
kubectl get pods -A
```

Expected output: ~45 pods total, all `Running` or `Completed`

```
NAMESPACE           NAME                                    READY   STATUS
smart-city          ids-api-...                             1/1     Running
smart-city          postgres-...                            1/1     Running
smart-city          mqtt-broker-...                         1/1     Running
smart-city          traffic-camera-...                      2/2     Running
smart-city          healthcare-api-...                      2/2     Running
smart-city          parking-system-...                      2/2     Running
smart-city          iot-device-burst-...                    5/5     Running
smart-city          iot-device-high-...                     5/5     Running
smart-city          iot-device-medium-...                  10/10    Running
monitoring          prometheus-...                          1/1     Running
monitoring          grafana-...                             1/1     Running
falco-system        falco-forwarder-...                     1/1     Running
suricata-system     suricata-forwarder-...                  1/1     Running
kube-system         coredns-...                             1/1     Running
kube-system         local-path-provisioner-...              1/1     Running
```

### Access Grafana Dashboard

1. Open browser: `http://YOUR-IP:30300`
2. Login: username `admin`, password `admin`
3. Look at "Smart City IDS" dashboard
4. You should see live graphs of:
   - Alert count
   - Severity distribution
   - LLM response latency
   - Automated actions executed

---

## Next Steps

### See It In Action: Run an Attack Simulation

```bash
# Simulate a DDoS attack on the IDS API
cd attack-simulator
python3 ddos_simulator.py http://YOUR-IP:30800 5 10
```

This will:
- Send 5 threads for 10 seconds
- Generate ~1000 alert events
- Show real-time detection in Grafana
- Demonstrate automated response (pod isolation, scaling)

### Review Detected Alerts

```bash
# Query stored alerts from PostgreSQL
curl -s "http://YOUR-IP:30800/api/alerts?limit=5" | python3 -m json.tool
```

You'll see:
- Alert source (Falco, Suricata)
- Security rule triggered
- LLM analysis and severity
- Automated actions taken

### Monitor Real-Time Events

```bash
# Watch IDS API logs
kubectl logs -n smart-city -l app=ids-api --tail=50 -f

# Watch Falco detections
kubectl logs -n falco-system -l app=falco-forwarder --tail=30 -f

# Watch K3s pod events
kubectl get events -n smart-city --sort-by='.lastTimestamp' | tail -20
```

---

## Troubleshooting

### Problem: Permission Denied (sudo errors)

**Solution:**
```bash
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
sudo chmod 644 /etc/rancher/k3s/k3s.yaml
sudo systemctl restart k3s
```

### Problem: Pods Not Starting

**Check logs:**
```bash
kubectl describe pod <pod-name> -n smart-city
kubectl logs <pod-name> -n smart-city
```

**Common causes:**
- LLM API key not set: `echo $XAI_API_KEY`
- Not enough disk space: `df -h`
- K3s not running: `sudo systemctl status k3s`

### Problem: Can't Access Grafana

**Check service is exposed:**
```bash
kubectl get svc -n monitoring
# Should show grafana on port 30300
```

**Get actual IP:**
```bash
kubectl get node -o wide
# Use the INTERNAL-IP or EXTERNAL-IP
```

### Problem: Attacks Not Being Detected

**Verify Falco is running:**
```bash
kubectl logs -n falco-system -l app=falco-forwarder | head -20
```

**Verify IoT pods are generating traffic:**
```bash
kubectl exec -n smart-city <iot-device-pod> -- curl http://mqtt-broker:1883 --max-time 1
# Should show MQTT broker responding
```

---

## Configuration

### Change Number of IoT Devices

Edit `scripts/start-everything.sh`:

```bash
# Find line: IoT_REPLICAS=30
# Change to: IoT_REPLICAS=100
```

Then restart:
```bash
sudo bash scripts/start-everything.sh
```

### Use Different LLM

Edit `services/ids-api/src/config.py`:

```python
# Change from:
LLM_ENGINE = "xai"  # Uses xAI Grok

# Change to:
LLM_ENGINE = "openai"  # Uses OpenAI GPT
```

### Adjust Automation Thresholds

Edit `services/ids-api/src/config.py`:

```python
# Severity >= 8 triggers pod isolation
ISOLATION_THRESHOLD = 8

# Severity >= 6 triggers pod scaling
SCALING_THRESHOLD = 6
```

---

## What's Running

| Service | Purpose | Port | Language |
|---------|---------|------|----------|
| **IDS API** | Alert processing, LLM analysis, Kubernetes automation | 30800 | Python (FastAPI) |
| **PostgreSQL** | Alert storage, audit logs | 5432 (internal) | SQL |
| **Prometheus** | Metrics collection | 31106 | Go |
| **Grafana** | Live dashboards | 30300 | JavaScript |
| **MQTT Broker** | IoT message bus | 1883 (internal) | C |
| **Falco Forwarder** | Runtime security alerts | (internal) | Python |
| **Suricata Forwarder** | Network security alerts | (internal) | Python |
| **Traffic Camera** | Demo vulnerable service #1 | 30100 | Python (Flask) |
| **Healthcare API** | Demo vulnerable service #2 | 30101 | Python (Flask) |
| **Parking System** | Demo vulnerable service #3 | 30102 | Python (Flask) |
| **IoT Devices** | 30-100 MQTT message generators | (internal) | Python |

---

## Next: Learn More

- [How It Works: Deep Technical Dive](HOW_IT_WORKS.md) - Component-level architecture
- [Architecture: System Design](ARCHITECTURE.md) - Data flow and dependencies
- [Operations: Managing the System](OPERATIONS.md) - Common tasks and commands
- [Troubleshooting: Common Issues](TROUBLESHOOTING.md) - Problem resolution
- [Academic Context: Why This Approach](ACADEMIC_CONTEXT.md) - Methodology justification

---

## Support

- **Issues:** Create a GitHub issue with error logs and configuration
- **Questions:** See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) or post a discussion
- **Contributions:** See [DEVELOPMENT.md](DEVELOPMENT.md) for contributor guidelines
