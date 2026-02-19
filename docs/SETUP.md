# Smart City IDS - Setup Guide

Complete guide for deploying the Smart City IDS on a fresh machine.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Start (One-Click)](#quick-start-one-click)
3. [Manual Setup](#manual-setup)
4. [Configuration](#configuration)
5. [Verification](#verification)
6. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Hardware Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 2 cores | 4 cores |
| RAM | 4 GB | 8 GB |
| Disk | 20 GB | 50 GB |
| Network | Internet access | Internet + static IP |

### Software Requirements

- **OS:** Ubuntu 20.04+ (or similar Linux distribution)
- **Git:** For cloning the repository
- **curl:** For API calls and k3s installation
- **sudo access:** For k3s installation

### API Keys Required

You need **at least one** of the following LLM API keys:

| Provider | Get Key At | Notes |
|----------|------------|-------|
| xAI Grok | https://console.x.ai/ | Primary (recommended) |
| OpenAI | https://platform.openai.com/ | Fallback option |

---

## Quick Start (One-Click)

```bash
# 1. Clone the repository
git clone https://github.com/your-org/smart-city-ids.git
cd smart-city-ids

# 2. Create environment configuration
cp .env.example .env
nano .env  # Add your API keys

# 3. Deploy everything
./deploy.sh
```

That's it! The script handles:
- K3s installation
- Docker image building
- Kubernetes manifest deployment
- Prometheus & Grafana setup
- Health verification

---

## Manual Setup

If you prefer step-by-step control:

### Step 1: Clone Repository

```bash
git clone https://github.com/your-org/smart-city-ids.git
cd smart-city-ids
```

### Step 2: Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your values:

```bash
XAI_API_KEY=xai-your-actual-key
OPENAI_API_KEY=sk-your-actual-key  # optional
```

### Step 3: Install K3s

```bash
curl -sfL https://get.k3s.io | sh -s - --write-kubeconfig-mode 644 --disable traefik
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
echo 'export KUBECONFIG=/etc/rancher/k3s/k3s.yaml' >> ~/.bashrc
```

Wait for k3s to be ready:
```bash
kubectl get nodes
# Should show: Ready status
```

### Step 4: Build Images (Optional)

If you have Docker installed:
```bash
./scripts/build-images.sh
```

### Step 5: Deploy Manifests

```bash
# Create namespaces
kubectl apply -f k8s-manifests/namespace.yaml

# Create secrets
kubectl create secret generic ids-api-secrets \
    --namespace=smart-city \
    --from-literal=XAI_API_KEY="$XAI_API_KEY" \
    --from-literal=OPENAI_API_KEY="$OPENAI_API_KEY"

# Deploy RBAC
kubectl apply -f k8s-manifests/rbac.yaml

# Create ConfigMaps for services
kubectl create configmap traffic-camera-code \
    --namespace=smart-city \
    --from-file=app.py=smart-city-services/traffic-camera/app.py

kubectl create configmap healthcare-api-code \
    --namespace=smart-city \
    --from-file=app.py=smart-city-services/healthcare-api/app.py

kubectl create configmap parking-system-code \
    --namespace=smart-city \
    --from-file=app.py=smart-city-services/parking-system/app.py

# Deploy services
kubectl apply -f k8s-manifests/services-no-build.yaml
kubectl apply -f k8s-manifests/ids-api-FINAL.yaml
kubectl apply -f k8s-manifests/mqtt-broker.yaml
kubectl apply -f k8s-manifests/iot-simulator.yaml
```

### Step 6: Deploy Monitoring

```bash
kubectl apply -f k8s-manifests/prometheus-deployment.yaml
kubectl apply -f k8s-manifests/grafana-deployment.yaml
```

---

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `XAI_API_KEY` | Yes* | - | xAI Grok API key |
| `OPENAI_API_KEY` | Yes* | - | OpenAI API key |
| `KUBECONFIG` | No | /etc/rancher/k3s/k3s.yaml | Kubernetes config |
| `K8S_NAMESPACE` | No | smart-city | Target namespace |
| `POSTGRES_USER` | No | idsuser | Database user |
| `POSTGRES_PASSWORD` | No | idspassword | Database password |
| `IDS_USER_ADMIN` | No | admin | Dashboard admin username |
| `IDS_PASS_ADMIN` | No | admin | Dashboard admin password |
| `IDS_USER_ANALYST` | No | analyst | Dashboard analyst username |
| `IDS_PASS_ANALYST` | No | analyst | Dashboard analyst password |
| `IDS_USER_OPERATOR` | No | operator | Dashboard operator username |
| `IDS_PASS_OPERATOR` | No | operator | Dashboard operator password |
| `IDS_EXTRA_USERS` | No | - | Extra users as `user:pass,user2:pass2` |
| `SECRET_KEY` | No | auto-generated | JWT signing key |

*At least one LLM API key is required.

### Changing Dashboard Passwords

Edit your `.env` file (or set environment variables):

```bash
# Change the admin password
IDS_PASS_ADMIN=my-secure-password

# Change all passwords
IDS_PASS_ADMIN=admin-secret-123
IDS_PASS_ANALYST=analyst-secret-456
IDS_PASS_OPERATOR=operator-secret-789

# Add extra users
IDS_EXTRA_USERS=alice:hunter2,bob:s3cure
```

Then restart the IDS API to pick up the changes:

```bash
kubectl rollout restart deployment/ids-api -n smart-city
```

### Customizing Thresholds

Edit `services/ids-api/src/config.py`:

```python
# Severity thresholds for automated actions
SEVERITY_THRESHOLD_ISOLATE = 8  # Isolate pod at this severity
SEVERITY_THRESHOLD_SCALE = 6    # Scale up at this severity
```

---

## Verification

### Check Pod Status

```bash
kubectl get pods -n smart-city
kubectl get pods -n monitoring
```

All pods should show `Running` status.

### Test IDS API

```bash
# Get node IP
NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')

# Health check
curl http://${NODE_IP}:30800/health

# API documentation
curl http://${NODE_IP}:30800/docs
```

### Access Dashboards

| Service | URL | Credentials |
|---------|-----|-------------|
| IDS Dashboard | http://NODE_IP:30800/ui | admin / admin (configurable via `IDS_PASS_ADMIN`) |
| Grafana | http://NODE_IP:30300 | admin / admin |
| Prometheus | http://NODE_IP:31106 | - |
| IDS API Docs | http://NODE_IP:30800/docs | - |

**Tip:** Run `./scripts/check-setup.sh` to see all URLs with current IP.

---

## Raspberry Pi Motion Sensor Setup

### Hardware Required

- Raspberry Pi 5 (or 4)
- AM312 PIR Motion Sensor (3.3V)
- 3 jumper wires

### Wiring (AM312 - 3.3V)

```
AM312 PIR Sensor       Raspberry Pi
═════════════════      ═════════════════
VCC (Left)     ─────►  Pin 1  (3.3V)  ⚠️ NOT Pin 2 (5V)!
OUT (Middle)   ─────►  Pin 11 (GPIO 17)
GND (Right)    ─────►  Pin 6  (Ground)
```

### Software Setup (on Pi)

```bash
# Install dependencies
sudo apt update && sudo apt install python3-pip python3-gpiozero -y
pip3 install requests --break-system-packages

# Copy motion sensor script from laptop
scp /home/kali/smart-city-ids/raspberry-pi/motion_sensor.py pi@<PI_IP>:/home/pi/

# Run sensor (replace IP with your Kali IP)
python3 motion_sensor.py --ids-url http://<KALI_IP>:30800
```

### Get Current IPs

```bash
# On Kali - get all URLs including Pi command
./scripts/check-setup.sh

# Find Pi on network
nmap -sn 192.168.1.0/24 | grep -i raspberry
```

---

## Troubleshooting

### WiFi Changed / IP Issues

```bash
# Run this after WiFi change or reboot
./scripts/check-setup.sh
```

### K3s Won't Start

```bash
# Restart k3s
sudo systemctl restart k3s

# Check status
sudo systemctl status k3s

# Fix permissions
sudo chmod 644 /etc/rancher/k3s/k3s.yaml
```

### Pods Stuck in Pending

```bash
# Check events
kubectl describe pod <pod-name> -n smart-city

# Check node resources
kubectl describe node
```

### API Key Errors

```bash
# Verify secret exists
kubectl get secret ids-api-secrets -n smart-city -o yaml

# Update secret
kubectl delete secret ids-api-secrets -n smart-city
kubectl create secret generic ids-api-secrets \
    --namespace=smart-city \
    --from-literal=XAI_API_KEY="$XAI_API_KEY"
```

### View Logs

```bash
# IDS API logs
kubectl logs -n smart-city -l app=ids-api -f

# Specific pod logs
kubectl logs -n smart-city <pod-name> -f
```

---

## Next Steps

After successful deployment:

1. **Check System:** Run `./scripts/check-setup.sh` to verify everything
2. **Import Grafana Dashboard:** Go to Grafana → Import → Upload `infrastructure/monitoring/grafana-dashboard-ieee-improved.json`
3. **Connect Raspberry Pi:** Set up motion sensor following guide above
4. **Run Attack Simulation:** `python attack-simulator/ddos_simulator.py http://NODE_IP:30800 5 10`
5. **Run Demo:** `./scripts/demo-walkthrough.sh`
6. **Read Operations Guide:** See [OPERATIONS.md](OPERATIONS.md)

---

*For architecture details, see [ARCHITECTURE.md](ARCHITECTURE.md)*
