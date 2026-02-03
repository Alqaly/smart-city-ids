#!/bin/bash
# =============================================================================
# Smart City IDS - K3s Startup & Service Deployment
# Safely restarts K3s and deploys all services
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

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

cd "$PROJECT_ROOT"

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}🚀 Smart City IDS - K3s Startup${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# =============================================================================
# Step 1: Check/Install K3s
# =============================================================================
log_info "Step 1/4: Checking K3s installation..."

if ! command -v k3s &> /dev/null; then
    log_warn "K3s not installed. Installing..."
    curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION="v1.33.5+k3s1" sh -s - \
        --write-kubeconfig-mode 644 \
        --disable traefik
    log_info "✓ K3s installed"
else
    log_info "✓ K3s already installed"
fi

# =============================================================================
# Step 2: Safely Stop Existing K3s
# =============================================================================
log_info "Step 2/4: Stopping existing K3s processes..."

if systemctl is-active --quiet k3s 2>/dev/null || [[ -f /var/run/k3s.pid ]]; then
    # If installed via systemd, use systemctl
    if systemctl list-unit-files | grep -q "k3s.service"; then
        log_info "Stopping K3s via systemctl..."
        sudo systemctl stop k3s || true
        sleep 2
    else
        # Otherwise use killall with graceful timeout
        log_info "Stopping K3s via killall..."
        if command -v k3s-killall.sh &> /dev/null; then
            /usr/local/bin/k3s-killall.sh || true
        else
            pkill -15 -f "k3s server" || true
            sleep 3
            pkill -9 -f "k3s server" || true
        fi
    fi
    sleep 2
    log_info "✓ Old K3s stopped"
else
    log_info "✓ No existing K3s processes found"
fi

# =============================================================================
# Step 3: Start K3s
# =============================================================================
log_info "Step 3/4: Starting K3s server..."

export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

# Check if port 6443 is free
if lsof -Pi :6443 -sTCP:LISTEN -t >/dev/null 2>&1; then
    log_error "Port 6443 already in use. Kill processes: lsof -i :6443"
    exit 1
fi

# Start K3s
k3s server \
    --write-kubeconfig-mode=644 \
    --write-kubeconfig=/etc/rancher/k3s/k3s.yaml \
    --disable=traefik \
    --disable=servicelb \
    > /tmp/k3s.log 2>&1 &

K3S_PID=$!
log_info "K3s started with PID: $K3S_PID"

# Wait for K3s cluster to be ready
log_info "Waiting for K3s cluster to be ready (max 60s)..."
ELAPSED=0
MAX_WAIT=60

while ! kubectl cluster-info &>/dev/null 2>&1; do
    if [[ $ELAPSED -ge $MAX_WAIT ]]; then
        log_error "K3s failed to start within ${MAX_WAIT}s"
        log_error "Last 20 lines of /tmp/k3s.log:"
        tail -20 /tmp/k3s.log
        exit 1
    fi
    
    ELAPSED=$((ELAPSED + 2))
    echo -ne "\r  ⏳ Waiting... ${ELAPSED}/${MAX_WAIT}s"
    sleep 2
done

echo ""
log_info "✓ K3s cluster is ready!"

# Verify nodes
log_info "Cluster status:"
kubectl get nodes

echo ""

# =============================================================================
# Step 4: Deploy Services
# =============================================================================
log_info "Step 4/4: Deploying services..."

# Create namespace
kubectl apply -f k8s-manifests/namespace.yaml

# Create ConfigMaps for smart city services
log_info "Creating ConfigMaps..."

for service in traffic-camera healthcare-api parking-system; do
    if [[ -f "smart-city-services/${service}/app.py" ]]; then
        kubectl create configmap "${service}-code" \
            --from-file="smart-city-services/${service}/app.py" \
            -n smart-city \
            --dry-run=client -o yaml | kubectl apply -f - 2>/dev/null || true
        log_info "  ✓ ${service} ConfigMap"
    else
        log_warn "  ⚠️  ${service}/app.py not found"
    fi
done

# Deploy services
log_info "Deploying services..."
kubectl apply -f k8s-manifests/services-no-build.yaml

sleep 3

# Show status
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
log_info "Cluster Status:"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
kubectl get pods -n smart-city
echo ""
log_info "Services:"
kubectl get svc -n smart-city
echo ""

echo -e "${GREEN}✅ Smart City IDS System is ready!${NC}"
echo ""
echo "Quick commands:"
echo "  Watch pods:     kubectl get pods -n smart-city -w"
echo "  View logs:      kubectl logs -n smart-city -l app=ids-api -f"
echo "  Port forward:   kubectl port-forward svc/traffic-camera-service 8001:80 -n smart-city"
echo ""
