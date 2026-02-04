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

# =============================================================================
# KUBECONFIG Setup (Permanent)
# =============================================================================
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

# Make KUBECONFIG permanent in user's profile
setup_kubeconfig_permanent() {
    for profile in ~/.bashrc ~/.zshrc ~/.profile; do
        if [ -f "$profile" ]; then
            if ! grep -q "export KUBECONFIG=/etc/rancher/k3s/k3s.yaml" "$profile"; then
                echo "export KUBECONFIG=/etc/rancher/k3s/k3s.yaml" >> "$profile"
            fi
        fi
    done
}

# Ensure we're running as root
if [[ $EUID -ne 0 ]]; then
    log_warn "This script requires root privileges. Re-invoking with sudo..."
    exec sudo "$0" "$@"
fi

cd "$PROJECT_ROOT"
setup_kubeconfig_permanent

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

# =============================================================================
# Setup Persistent Storage for Prometheus and Grafana (AUTOMATIC)
# =============================================================================
log_info "Setting up persistent storage directories..."
sudo mkdir -p /mnt/smart-city/prometheus
sudo mkdir -p /mnt/smart-city/grafana
sudo chmod -R 777 /mnt/smart-city/

# Verify K3s storage class exists
if ! kubectl get storageclass local-path &>/dev/null 2>&1; then
    log_info "Creating K3s local-path storage class..."
    kubectl apply -f - <<'STORAGEEOF'
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: local-path
provisioner: rancher.io/local-path
allowVolumeExpansion: true
STORAGEEOF
fi
log_info "Persistent storage configured (Prometheus: 50Gi, Grafana: 10Gi)"

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
    "$MANIFEST_DIR/suricata-fixed.yaml" \
    "$MANIFEST_DIR/suricata-forwarder-deployment.yaml"; do
    
    if [[ -f "$manifest" ]]; then
        log_info "Applying $(basename $manifest)..."
        kubectl apply -f "$manifest" 2>&1 | grep -E "(created|configured|unchanged)" | head -3 || true
    fi
done

log_info "Manifests applied successfully"

# Create IDS API ConfigMaps (code + operator UI)
log_info "Creating IDS API ConfigMaps..."
kubectl create configmap ids-app-code \
    --namespace=smart-city \
    --from-file=services/ids-api/src \
    --dry-run=client -o yaml | kubectl apply -f -
kubectl create configmap ids-app-static \
    --namespace=smart-city \
    --from-file=services/ids-api/static \
    --dry-run=client -o yaml | kubectl apply -f -

# =============================================================================
# Phase 5: Deploy Falco Runtime Security (with JSON output for forwarder)
# =============================================================================
log_section "PHASE 5: Falco Runtime Security Deployment"

# Check if Helm is installed
if ! command -v helm &> /dev/null; then
    log_info "Installing Helm..."
    curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
fi

# Add Falco Helm repo
helm repo add falcosecurity https://falcosecurity.github.io/charts 2>/dev/null || true
helm repo update 2>/dev/null || true

# Install/upgrade Falco with JSON output enabled (required for forwarder integration)
if helm status falco -n falco-system &>/dev/null; then
    log_info "Upgrading Falco with JSON output enabled..."
    helm upgrade falco falcosecurity/falco -n falco-system \
        -f "$PROJECT_ROOT/k8s-manifests/falco-values.yaml" \
        --wait --timeout 120s 2>&1 | tail -3 || true
else
    log_info "Installing Falco with JSON output enabled..."
    helm install falco falcosecurity/falco -n falco-system \
        -f "$PROJECT_ROOT/k8s-manifests/falco-values.yaml" \
        --wait --timeout 180s 2>&1 | tail -3 || true
fi

log_info "Falco deployed with JSON output for IDS integration"

# =============================================================================
# Phase 6: Deploy IoT Device Emulation (Controlled Scale)
# =============================================================================
log_section "PHASE 6: IoT Device Emulation Deployment"

# Use the existing enhanced IoT emulation manifest with controlled replicas
# This deploys 3 device classes: high-frequency (5), medium-frequency (10), burst (5)
# Total: 20 pods generating realistic MQTT traffic patterns
if [[ -f "$PROJECT_ROOT/iot-simulator/k8s-enhanced.yaml" ]]; then
    log_info "Deploying IoT device emulation from iot-simulator/k8s-enhanced.yaml..."
    kubectl apply -f "$PROJECT_ROOT/iot-simulator/k8s-enhanced.yaml" 2>&1 | grep -E "(created|configured|unchanged)" | head -5 || true
    log_info "IoT emulation deployed: 5 high-freq + 10 medium-freq + 5 burst = 20 devices"
else
    log_warn "iot-simulator/k8s-enhanced.yaml not found, skipping IoT emulation"
fi

# =============================================================================
# Phase 7: Wait for Services to be Ready
# =============================================================================
log_section "PHASE 7: Waiting for Services to Be Ready"

log_info "Waiting for IDS API to be ready..."
kubectl wait --for=condition=ready pod -l app=ids-api -n smart-city --timeout=120s 2>/dev/null || true

log_info "Waiting for Prometheus to be ready..."
kubectl wait --for=condition=ready pod -l app=prometheus -n monitoring --timeout=60s 2>/dev/null || true

log_info "Waiting for Grafana to be ready..."
kubectl wait --for=condition=ready pod -l app=grafana -n monitoring --timeout=60s 2>/dev/null || true

log_info "Waiting for Falco to be ready..."
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=falco -n falco-system --timeout=120s 2>/dev/null || true

log_info "Waiting for IoT device emulation pods to initialize..."
sleep 5

# Count ready pods
IOT_PODS=$(kubectl get pods -n smart-city -l app=iot-simulator --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l)
log_info "$IOT_PODS IoT emulation pods are running"

# =============================================================================
# Phase 8: Verify Kubernetes Organization
# =============================================================================
log_section "PHASE 8: System Health Check"

echo ""
log_info "Kubernetes Cluster Status:"
kubectl get nodes
echo ""

log_info "Smart City Namespace Pods:"
kubectl get pods -n smart-city --no-headers 2>/dev/null | wc -l | xargs echo "  Total pods:"
kubectl get pods -n smart-city -o wide 2>/dev/null | grep -E "(ids-api|postgres|mqtt|traffic-camera|iot-simulator)" | head -5 || true

echo ""
log_info "Monitoring Stack:"
kubectl get pods -n monitoring --no-headers 2>/dev/null | wc -l | xargs echo "  Total monitoring pods:"

echo ""
log_info "Security Tools:"
kubectl get pods -n falco-system --no-headers 2>/dev/null | wc -l | xargs echo "  Falco system pods:"

# =============================================================================
# Phase 9: Display Service URLs
# =============================================================================
log_section "PHASE 9: Service Endpoints"

# Get node IP
NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}' 2>/dev/null || echo "localhost")

echo ""
echo -e "${GREEN}✓ Deployment Complete!${NC}"
echo ""
echo "Access your Smart City IDS system at:"
echo ""
echo -e "  ${BLUE}🎯 Dashboard:${NC}              http://localhost:8000/ui"
echo -e "  ${BLUE}📊 API Documentation:${NC}      http://localhost:8000/docs"
echo -e "  ${BLUE}📈 Grafana Dashboards:${NC}     http://$NODE_IP:30300"
echo -e "  ${BLUE}📉 Prometheus Metrics:${NC}      http://$NODE_IP:31106"
echo ""
echo -e "${YELLOW}Login Credentials:${NC}"
echo "  Username: operator"
echo "  Password: operator"
echo ""
echo -e "${YELLOW}Quick Commands:${NC}"
echo "  View all pods:           kubectl get pods -A"
echo "  Watch IDS API logs:      kubectl logs -f -n smart-city -l app=ids-api"
echo "  Watch Falco alerts:      kubectl logs -f -n falco-system -l app.kubernetes.io/name=falco"
echo "  Scale IoT emulation:     kubectl scale deployment/iot-simulator-high -n smart-city --replicas=10"
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

log_info "✅ Smart City IDS is now running!"
echo "  KUBECONFIG: $KUBECONFIG (permanent in ~/.bashrc, ~/.zshrc)"
echo ""

# =============================================================================
# Auto Port-Forward Setup
# =============================================================================
log_section "PHASE 10: Setting Up Port-Forwarding"

# Kill any existing port-forwards
pkill -f "kubectl port-forward.*ids-api" 2>/dev/null || true
sleep 1

# Create background port-forward
nohup kubectl port-forward -n smart-city svc/ids-api-service 8000:8000 > /tmp/ids-api-portforward.log 2>&1 &
PID=$!
echo $PID > /tmp/ids-api-portforward.pid

# Wait for port-forward to connect
sleep 2

# Test connection
if curl -s http://localhost:8000/ > /dev/null 2>&1; then
    log_info "✅ Port-forward successful (localhost:8000 → IDS API)"
    echo ""
    echo -e "${GREEN}🎉 Dashboard ready at:${NC} http://localhost:8000/ui"
    echo ""
else
    log_warn "Port-forward started but connection test failed"
    echo "Try manually: kubectl port-forward -n smart-city svc/ids-api-service 8000:8000"
    echo "Or access on NodePort: http://localhost:30800/ui"
fi
echo ""
