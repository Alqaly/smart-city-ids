# Deployment Guide

Complete instructions for deploying the Smart City IDS system to various environments.

---

## Quick Deploy (Recommended)

```bash
# 1. Set API key
export XAI_API_KEY="your-key-here"
# OR
export OPENAI_API_KEY="your-key-here"

# 2. Run deployment script (handles everything)
cd /path/to/smart-city-ids
sudo bash scripts/start-everything.sh

# 3. Wait for services to be ready (5-10 minutes)
# Script will display service URLs when complete
```

---

## What Gets Deployed

### Kubernetes Namespaces & Services

| Namespace | Service | Replicas | Purpose |
|-----------|---------|----------|---------|
| **smart-city** | ids-api | 1 | Alert processing and LLM analysis |
| **smart-city** | postgres | 1 | Alert storage and audit logs |
| **smart-city** | mqtt-broker | 1 | IoT device message bus |
| **smart-city** | traffic-camera | 2 | Vulnerable demo service |
| **smart-city** | healthcare-api | 2 | Vulnerable demo service |
| **smart-city** | parking-system | 2 | Vulnerable demo service |
| **smart-city** | iot-device-* | 30+ | MQTT message generators |
| **monitoring** | prometheus | 1 | Metrics collection |
| **monitoring** | grafana | 1 | Live dashboards |
| **falco-system** | falco-forwarder | 1 | Runtime security alerts |
| **suricata-system** | suricata-forwarder | 1 | Network security alerts |

### Storage

- **PostgreSQL PVC:** 10GB persistent volume for alert data
- **Prometheus PVC:** 50GB persistent volume for metrics

### Network

- **ClusterIP Services:** For internal communication
- **NodePort Services:** Exposed to host network for external access
- **NetworkPolicies:** Control pod-to-pod communication

---

## Deployment Script Phases

The `scripts/start-everything.sh` script executes 8 phases:

### Phase 1: K3s Verification
- Checks if K3s is installed
- Verifies kubectl connectivity
- Validates KUBECONFIG

**What can go wrong:**
- K3s not installed → Script will offer to install
- Permission denied → Ensure running with sudo
- kubectl not found → Install kubectl

### Phase 2: Cleanup
- Removes old K3s installation
- Deletes previous namespaces
- Clears stale configurations

**What can go wrong:**
- Cleanup hangs → May take 60+ seconds, be patient
- Ports still in use → System will warn and continue

### Phase 3: K3s Cluster Startup
- Starts K3s service
- Waits for cluster readiness
- Verifies node is Ready

**What can go wrong:**
- K3s fails to start → Check logs with `sudo systemctl status k3s`
- Timeout waiting for node → System may need reboot

### Phase 4: Kubernetes Manifests Deployment
- Creates namespaces (smart-city, monitoring, falco-system, suricata-system)
- Deploys RBAC and network policies
- Deploys all services and applications

**What can go wrong:**
- ImagePullBackOff → Image not available, check Docker
- CrashLoopBackOff → Application error, check pod logs
- Pending → Insufficient resources, check `kubectl top nodes`

### Phase 5: IoT Services / Emulation Bring-up
- Deploys core IoT emulator services (traffic camera, healthcare API, parking system, etc.)
- Starts supporting IoT components (e.g., MQTT broker and any configured simulators)
- Waits for service readiness so Falco/Suricata detections can be generated against real workloads

**What can go wrong:**
- Pods not starting → Insufficient resources
- MQTT connection refused → Broker not ready
- High CPU usage → Expected during startup, normalizes after 2-3 minutes

### Phase 6: Service Readiness Monitoring
- Waits for all deployments to be ready
- Monitors pod startup progress
- Verifies no CrashLoopBackOff pods

**What can go wrong:**
- Timeout → Services taking longer than expected
- Pods crashing → Check specific pod logs

### Phase 7: System Health Checks
- Verifies IDS API responding
- Checks PostgreSQL connectivity
- Validates Prometheus metrics collection
- Confirms Grafana availability

**What can go wrong:**
- API returns 500 error → Check application logs
- PostgreSQL connection refused → Wait for startup

### Phase 8: URL Discovery and Display
- Discovers node IP address
- Calculates service URLs
- Displays access information

**Output example:**
```
[✓] Phase 8: Discovering service URLs
Smart City IDS is ready!

  Grafana (Live Dashboards): http://192.168.1.187:30300
  Prometheus (Metrics):      http://192.168.1.187:31106
  IDS API (Documentation):   http://192.168.1.187:30800/docs

Smart City Services:
  Traffic Camera:            http://192.168.1.187:30100
  Healthcare API:            http://192.168.1.187:30101
  Parking System:            http://192.168.1.187:30102
```

---

## Manual Deployment (Advanced)

If you prefer manual control:

### 1. Prepare Environment

```bash
# Install K3s
curl -sfL https://get.k3s.io | sudo bash -
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

# Verify installation
sudo kubectl get nodes
```

### 2. Create Namespaces

```bash
kubectl create namespace smart-city
kubectl create namespace monitoring
kubectl create namespace falco-system
kubectl create namespace suricata-system
```

### 3. Deploy Services

```bash
# Deploy manifests in order
kubectl apply -f k8s-manifests/namespace.yaml
kubectl apply -f k8s-manifests/rbac.yaml
kubectl apply -f k8s-manifests/network-policies.yaml
kubectl apply -f k8s-manifests/postgres-deployment.yaml
kubectl apply -f k8s-manifests/mqtt-broker.yaml
kubectl apply -f k8s-manifests/ids-api-FINAL.yaml
kubectl apply -f k8s-manifests/services-no-build.yaml
kubectl apply -f k8s-manifests/prometheus-deployment.yaml
kubectl apply -f k8s-manifests/grafana-deployment.yaml
kubectl apply -f k8s-manifests/falco-forwarder.yaml
kubectl apply -f k8s-manifests/suricata-forwarder-deployment.yaml
```

### 4. Wait for Readiness

```bash
# Watch pod startup
kubectl get pods -A -w

# Check specific service
kubectl rollout status deployment/ids-api -n smart-city
```

### 5. Validate IoT Emulation

```bash
# Check emulator deployments/services
kubectl get deploy,svc -n smart-city | grep -E 'traffic-camera|healthcare-api|parking-system|env-sensor|street-lighting|mqtt-broker'

# Verify IDS API sees IoT telemetry/device inventory
curl -s http://localhost:30800/api/iot/devices | jq .
curl -s http://localhost:30800/api/iot/telemetry | jq .
```

---

## Verify Deployment

### Check Cluster Status

```bash
# All nodes ready
kubectl get nodes
# Output: capstone   Ready    control-plane   X

# All pods running
kubectl get pods -A
# Output: pod count varies by profile/replicas; focus on expected core services Running

# All services accessible
kubectl get svc -A
# Output: NodePort services on 30100-31999
```

### Health Checks

```bash
# IDS API health
curl http://YOUR-IP:30800/health

# PostgreSQL ready
kubectl exec -n smart-city postgres-xxx -- pg_isready

# Prometheus scraping
curl http://YOUR-IP:31106/api/v1/query?query=up

# Grafana running
curl http://YOUR-IP:30300/api/health
```

### Test Alert Pipeline

```bash
# 1. Trigger live detections
bash scripts/run-live-attacks.sh --duration 10 --show-alerts 2

# 2. Check IDS API logs
kubectl logs -n smart-city -l app=ids-api --tail=20

# 3. Query stored alerts
curl http://YOUR-IP:30800/api/alerts?limit=5

# 4. View Grafana dashboard
# Open http://YOUR-IP:30300 in browser
```

---

## Configuration Options

### Environment Variables

Edit `scripts/start-everything.sh` before running:

```bash
# IoT scaling is profile/manifests-driven; use `kubectl scale` / HPA / emulator env vars after deploy
# (e.g., DEVICE_COUNT, ENV_SENSOR_STATION_COUNT, PARKING_SLOT_MULTIPLIER)

# K3s Cluster Name
CLUSTER_NAME="capstone"

# PostgreSQL Credentials (defaults are fine)
DB_NAME="smart_city_ids"
DB_USER="ids_admin"
DB_PASSWORD="secure_default_password"

# MQTT Broker Configuration
MQTT_PORT=1883
```

### Kubernetes Resource Limits

Edit individual manifests in `k8s-manifests/`:

```yaml
resources:
  limits:
    cpu: "1000m"        # Max CPU
    memory: "512Mi"     # Max memory
  requests:
    cpu: "500m"         # Requested CPU
    memory: "256Mi"     # Requested memory
```

### LLM Configuration

Edit `services/ids-api/src/config.py`:

```python
# Use xAI Grok
LLM_ENGINE = "xai"
XAI_MODEL = "grok-4"
XAI_API_BASE = "https://api.x.ai/v1"

# OR use OpenAI
LLM_ENGINE = "openai"
OPENAI_MODEL = "gpt-4-turbo"
OPENAI_ORG_ID = "your-org-id"

# Automation Thresholds
ISOLATION_THRESHOLD = 8   # Isolate if severity >= 8
SCALING_THRESHOLD = 6     # Scale up if severity >= 6
```

---

## Troubleshooting Deployment

### K3s Installation Fails

```bash
# Check K3s service status
sudo systemctl status k3s

# View K3s logs
sudo journalctl -u k3s -n 50

# Restart K3s
sudo systemctl restart k3s

# Force reinstall
sudo /usr/local/bin/k3s-uninstall.sh
curl -sfL https://get.k3s.io | sudo bash -
```

### Pods Stuck in Pending

```bash
# Check available resources
kubectl describe nodes

# Check pod events
kubectl describe pod <pod-name> -n smart-city

# Common causes:
# - Insufficient CPU: reduce replicas or add more resources
# - No available storage: create PV, check disk space
# - ImagePullBackOff: ensure Docker images are available
```

### IDS API Won't Start

```bash
# Check logs
kubectl logs -n smart-city -l app=ids-api

# Common causes:
# - LLM API key not set: export XAI_API_KEY or OPENAI_API_KEY
# - PostgreSQL not ready: wait 30 seconds, then redeploy
# - Port conflict: change port in manifest

# Fix:
export XAI_API_KEY="your-key"
kubectl delete pod <ids-api-pod> -n smart-city
# New pod will start with env var
```

### PostgreSQL Data Loss

```bash
# Check PVC status
kubectl get pvc -n smart-city

# Verify persistence
kubectl get pv

# If PVC lost:
# Option 1: Delete and recreate
kubectl delete pvc postgres-pvc -n smart-city
kubectl apply -f k8s-manifests/postgres-deployment.yaml

# Option 2: Backup before restart
kubectl exec -n smart-city postgres-xxx -- \
  pg_dump -U ids_admin smart_city_ids > backup.sql
```

### High Memory Usage

```bash
# Check memory per pod
kubectl top pods -n smart-city

# Common causes:
# - Prometheus retention too large: edit prometheus-deployment.yaml
# - Too many IoT replicas: reduce IoT_REPLICAS

# Fix:
# Reduce retention
--storage.tsdb.retention.time=7d  # Down from 15d

# Reduce IoT replicas
kubectl delete deployment iot-device-* -n smart-city
```

---

## Post-Deployment

### Enable Persistent Storage

```bash
# Create local storage path
sudo mkdir -p /mnt/smart-city/postgres
sudo mkdir -p /mnt/smart-city/prometheus
sudo chown -R 1000:1000 /mnt/smart-city

# Redeploy with updated paths in manifests
```

### Configure Backups

```bash
# Backup PostgreSQL daily
0 2 * * * kubectl exec -n smart-city postgres-xxx -- pg_dump -U ids_admin smart_city_ids > /backups/ids-$(date +\%Y\%m\%d).sql
```

### Set Up Monitoring Alerts

```bash
# Add alert rules to prometheus-deployment.yaml
groups:
  - name: smart-city-alerts
    rules:
      - alert: HighAlertRate
        expr: rate(ids_alerts_received_total[5m]) > 10
        for: 5m
```

---

## Cleanup

```bash
# Remove entire deployment
sudo bash scripts/cleanup.sh

# Or manually:
kubectl delete namespace smart-city monitoring falco-system suricata-system
sudo k3s-uninstall.sh

# Check removal
kubectl get ns
kubectl get pods -A
```

---

## Performance Tuning

### For High Alert Volume

```yaml
# Increase IDS API replicas
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ids-api
spec:
  replicas: 3  # Up from 1
  
# Increase database connections
POSTGRES_MAX_CONNECTIONS: 100
```

### For Limited Resources

```bash
# Reduce IoT devices
IoT_REPLICAS=5

# Reduce Prometheus retention
--storage.tsdb.retention.time=7d

# Reduce Grafana memory
memory: "128Mi"
```

---

## References

- [K3s Documentation](https://docs.k3s.io/)
- [Kubernetes Deployment Documentation](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
- [Persistent Volumes](https://kubernetes.io/docs/concepts/storage/persistent-volumes/)
