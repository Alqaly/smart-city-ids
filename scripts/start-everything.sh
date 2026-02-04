#!/bin/bash
# =============================================================================
# Smart City IDS - K3s Startup & Service Deployment
# Professional-grade deployment script for GitHub & Conference
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[✓]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[!]${NC} $1"; }
log_error() { echo -e "${RED}[✗]${NC} $1"; }
log_section() { echo ""; echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; echo -e "${BLUE}$1${NC}"; echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; }

# Ensure we're running as root
if [[ $EUID -ne 0 ]]; then
    log_warn "This script requires root privileges. Re-invoking with sudo..."
    exec sudo "$0" "$@"
fi

cd "$PROJECT_ROOT"

log_section "🚀 Smart City IDS - Complete System Deployment"

# =============================================================================
# Phase 1: Verify K3s Installation
# =============================================================================
log_section "PHASE 1: K3s Installation & Setup"

if ! command -v k3s &> /dev/null; then
    log_warn "K3s not found. Installing..."
    curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION="v1.33.5+k3s1" sh -s - \
        --write-kubeconfig-mode 644 \
        --disable traefik 2>&1 | grep -E "(Installing|Installed)" || true
    log_info "K3s installed successfully"
else
    log_info "K3s is installed"
fi

# =============================================================================
# Phase 2: Clean Shutdown of Existing K3s
# =============================================================================
log_section "PHASE 2: Cleanup (Stopping Previous K3s)"

# Try systemctl first
if systemctl list-unit-files 2>/dev/null | grep -q "k3s.service"; then
    log_info "Stopping K3s service via systemctl..."
    systemctl stop k3s 2>/dev/null || true
    sleep 2
fi

# Kill any remaining K3s processes
if pgrep -f "k3s server" > /dev/null; then
    log_info "Killing remaining K3s processes..."
    pkill -15 -f "k3s server" || true
    sleep 3
    pkill -9 -f "k3s server" 2>/dev/null || true
fi

log_info "Old K3s processes cleaned up"

# =============================================================================
# Phase 3: Start Fresh K3s Cluster
# =============================================================================
log_section "PHASE 3: Starting K3s Cluster"

export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

# Verify port 6443 is free
if lsof -Pi :6443 -sTCP:LISTEN -t >/dev/null 2>&1; then
    log_error "Port 6443 already in use!"
    exit 1
fi

# Start K3s in background
log_info "Starting K3s server..."
k3s server \
    --write-kubeconfig-mode=644 \
    --write-kubeconfig=/etc/rancher/k3s/k3s.yaml \
    --disable=traefik \
    --disable=servicelb \
    > /tmp/k3s.log 2>&1 &

K3S_PID=$!
log_info "K3s PID: $K3S_PID"

# Wait for K3s to be ready
log_info "Waiting for K3s cluster to become ready..."
RETRY=0
MAX_RETRIES=60

while [ $RETRY -lt $MAX_RETRIES ]; do
    if kubectl cluster-info &>/dev/null 2>&1; then
        log_info "K3s cluster is ready!"
        break
    fi
    RETRY=$((RETRY + 1))
    echo -ne "\r  ⏳ Attempt $RETRY/$MAX_RETRIES..."
    sleep 2
done

if [ $RETRY -ge $MAX_RETRIES ]; then
    log_error "K3s failed to start within ${MAX_RETRIES}s"
    log_error "K3s log output:"
    tail -30 /tmp/k3s.log
    exit 1
fi

echo ""
log_info "K3s cluster status:"
kubectl get nodes 2>/dev/null | tail -1

# =============================================================================
# Phase 4: Deploy Smart City Namespaces & Services
# =============================================================================
log_section "PHASE 4: Deploying Kubernetes Manifests"

# Create namespaces
log_info "Creating namespaces..."
kubectl create namespace smart-city --dry-run=client -o yaml | kubectl apply -f - 2>/dev/null || true
kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f - 2>/dev/null || true
kubectl create namespace falco-system --dry-run=client -o yaml | kubectl apply -f - 2>/dev/null || true

# Apply core manifests
MANIFEST_DIR="$PROJECT_ROOT/k8s-manifests"

log_info "Applying Kubernetes manifests..."

for manifest in \
    "$MANIFEST_DIR/namespace.yaml" \
    "$MANIFEST_DIR/rbac.yaml" \
    "$MANIFEST_DIR/postgres-deployment.yaml" \
    "$MANIFEST_DIR/mqtt-broker.yaml" \
    "$MANIFEST_DIR/ids-api-FINAL.yaml" \
    "$MANIFEST_DIR/services-no-build.yaml" \
    "$MANIFEST_DIR/prometheus-deployment.yaml" \
    "$MANIFEST_DIR/grafana-deployment.yaml" \
    "$MANIFEST_DIR/falco-forwarder.yaml" \
    "$MANIFEST_DIR/suricata-forwarder-deployment.yaml"; do
    
    if [[ -f "$manifest" ]]; then
        log_info "Applying $(basename $manifest)..."
        kubectl apply -f "$manifest" 2>&1 | grep -E "(created|configured|unchanged)" | head -3 || true
    fi
done

log_info "Manifests applied successfully"

# =============================================================================
# Phase 5: Deploy IoT Device Emulation (100 devices)
# =============================================================================
log_section "PHASE 5: IoT Device Emulation Deployment"

# Create IoT device emulation manifest dynamically
log_info "Creating unified IoT device emulation (100 pods)..."
cat > /tmp/iot-device-emulation.yaml <<'IOTEOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: iot-device-emulation
  namespace: smart-city
  labels:
    app.kubernetes.io/name: iot-device-emulation
spec:
  replicas: 100
  selector:
    matchLabels:
      app: iot-device-emulation
  template:
    metadata:
      labels:
        app: iot-device-emulation
        emulation-tier: production
    spec:
      containers:
      - name: mqtt-simulator
        image: ghcr.io/agazitt/smart-city-ids/iot-simulator:latest
        imagePullPolicy: IfNotPresent
        env:
        - name: MQTT_BROKER_HOST
          value: "mqtt-broker.smart-city.svc.cluster.local"
        - name: MQTT_BROKER_PORT
          value: "1883"
        resources:
          requests:
            cpu: "50m"
            memory: "64Mi"
          limits:
            cpu: "100m"
            memory: "128Mi"
IOTEOF

kubectl apply -f /tmp/iot-device-emulation.yaml

log_info "IoT emulation deployment created (100 replicas)"

# =============================================================================
# Phase 6: Wait for Services to be Ready
# =============================================================================
log_section "PHASE 6: Waiting for Services to Be Ready"

log_info "Waiting for IDS API to be ready..."
kubectl wait --for=condition=ready pod -l app=ids-api -n smart-city --timeout=120s 2>/dev/null || true

log_info "Waiting for Prometheus to be ready..."
kubectl wait --for=condition=ready pod -l app=prometheus -n monitoring --timeout=60s 2>/dev/null || true

log_info "Waiting for Grafana to be ready..."
kubectl wait --for=condition=ready pod -l app=grafana -n monitoring --timeout=60s 2>/dev/null || true

log_info "Waiting for IoT device emulation pods to initialize..."
sleep 10

# Count ready pods
READY_PODS=$(kubectl get pods -n smart-city -l app=iot-device-emulation --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l)
log_info "$READY_PODS / 100 IoT device emulation pods are running"

# =============================================================================
# Phase 7: Verify Kubernetes Organization
# =============================================================================
log_section "PHASE 7: System Health Check"

echo ""
log_info "Kubernetes Cluster Status:"
kubectl get nodes
echo ""

log_info "Smart City Namespace Pods:"
kubectl get pods -n smart-city --no-headers 2>/dev/null | wc -l | xargs echo "  Total pods:"
kubectl get pods -n smart-city -o wide 2>/dev/null | grep -E "(ids-api|postgres|mqtt|traffic-camera)" | head -5 || true

echo ""
log_info "Monitoring Stack:"
kubectl get pods -n monitoring --no-headers 2>/dev/null | wc -l | xargs echo "  Total monitoring pods:"

echo ""
log_info "Security Tools:"
kubectl get pods -n falco-system --no-headers 2>/dev/null | wc -l | xargs echo "  Falco system pods:"

# =============================================================================
# Phase 8: Display Service URLs
# =============================================================================
log_section "PHASE 8: Service Endpoints"

# Get node IP
NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}' 2>/dev/null || echo "localhost")

echo ""
echo -e "${GREEN}✓ Deployment Complete!${NC}"
echo ""
echo "Access your Smart City IDS system at:"
echo ""
echo -e "  ${BLUE}Grafana Dashboards:${NC}     http://$NODE_IP:30300"
echo -e "  ${BLUE}Prometheus Metrics:${NC}      http://$NODE_IP:31106"
echo -e "  ${BLUE}IDS API Documentation:${NC}   http://$NODE_IP:30800/docs"
echo ""
echo -e "${YELLOW}Quick Commands:${NC}"
echo "  View all pods:           kubectl get pods -A"
echo "  Watch IDS API logs:      kubectl logs -f -n smart-city -l app=ids-api"
echo "  Scale IoT devices:       kubectl scale deployment/iot-device-emulation --replicas=50 -n smart-city"
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

log_info "✅ Smart City IDS is now running!"
echo "  View logs:      kubectl logs -n smart-city -l app=ids-api -f"
echo "  Port forward:   kubectl port-forward svc/traffic-camera-service 8001:80 -n smart-city"
echo ""
