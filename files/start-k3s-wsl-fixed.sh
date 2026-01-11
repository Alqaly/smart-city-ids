#!/bin/bash

# 🚀 Smart City IDS - K3s Startup Script for WSL2
# Handles systemd limitations in WSL environments

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "🚀 Starting Smart City IDS System (WSL2 Mode)"
echo "=============================================="
echo "Project directory: $PROJECT_DIR"
echo "System: $(uname -s) $(uname -r)"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print success
success() {
    echo -e "${GREEN}✅ $1${NC}"
}

# Function to print warning
warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

# Function to print error
error() {
    echo -e "${RED}❌ $1${NC}"
}

# Function to check if K3s is running
check_k3s_running() {
    if kubectl cluster-info &>/dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

echo "Step 1: Checking system prerequisites..."
echo ""

# 1. Check if running as root
if [ "$EUID" -ne 0 ]; then
    error "This script must be run as root (use: sudo ./scripts/start-everything.sh)"
    exit 1
fi
success "Running as root"

# 2. Check for required tools
echo ""
echo "Step 2: Checking required tools..."

if ! command -v kubectl &>/dev/null; then
    warning "kubectl not found, will be installed with K3s"
else
    success "kubectl is installed: $(kubectl version --client --short 2>/dev/null | head -1)"
fi

# 3. Check systemd status
echo ""
echo "Step 3: Checking systemd status..."

if systemctl list-unit-files &>/dev/null 2>&1; then
    success "systemd is available"
    SYSTEMD_AVAILABLE=true
else
    warning "systemd not available (typical in some WSL2 configurations)"
    warning "Will run K3s in foreground mode instead"
    SYSTEMD_AVAILABLE=false
fi

# 4. Install K3s if needed
echo ""
echo "Step 4: Checking K3s installation..."

if command -v k3s &>/dev/null; then
    success "K3s is already installed: $(k3s --version)"
else
    echo "📥 Installing K3s..."
    curl -sfL https://get.k3s.io | sh -
    if [ $? -eq 0 ]; then
        success "K3s installed successfully"
    else
        error "Failed to install K3s"
        exit 1
    fi
fi

# 5. Clean up any existing K3s processes
echo ""
echo "Step 5: Cleaning up existing K3s processes..."
pkill -f "k3s server" 2>/dev/null || true
sleep 2
success "Cleanup complete"

# 6. Start K3s
echo ""
echo "Step 6: Starting K3s server..."

if [ "$SYSTEMD_AVAILABLE" = true ]; then
    # Try systemd first
    echo "Attempting to start K3s via systemd..."
    if systemctl start k3s.service 2>/dev/null; then
        success "K3s started via systemd"
        systemctl status k3s.service --no-pager | head -10
    else
        warning "systemd startup failed, falling back to direct mode"
        # Fallback: start directly
        k3s server \
            --write-kubeconfig-mode=644 \
            --write-kubeconfig=/etc/rancher/k3s/k3s.yaml \
            --disable=traefik \
            --disable=servicelb \
            > /tmp/k3s.log 2>&1 &
        K3S_PID=$!
        echo "K3s PID: $K3S_PID"
    fi
else
    # Start K3s directly (no systemd)
    echo "Starting K3s in foreground mode (no systemd)..."
    k3s server \
        --write-kubeconfig-mode=644 \
        --write-kubeconfig=/etc/rancher/k3s/k3s.yaml \
        --disable=traefik \
        --disable=servicelb \
        > /tmp/k3s.log 2>&1 &
    K3S_PID=$!
    echo "K3s PID: $K3S_PID"
fi

# 7. Wait for K3s to be ready
echo ""
echo "Step 7: Waiting for K3s cluster to be ready..."

MAX_WAIT=90
ELAPSED=0
while ! check_k3s_running; do
    if [ $ELAPSED -ge $MAX_WAIT ]; then
        error "K3s failed to start within $MAX_WAIT seconds"
        echo ""
        echo "📋 K3s logs:"
        tail -30 /tmp/k3s.log 2>/dev/null || echo "No logs available"
        echo ""
        echo "Troubleshooting:"
        echo "1. Check if K3s service is running: systemctl status k3s"
        echo "2. View detailed logs: journalctl -xeu k3s.service"
        echo "3. Check for port conflicts: sudo netstat -tlnp | grep 6443"
        exit 1
    fi
    printf "   ⏳ Waiting ($ELAPSED/$MAX_WAIT seconds)...\r"
    sleep 3
    ELAPSED=$((ELAPSED + 3))
done
echo ""
success "K3s cluster is ready!"

# 8. Create namespace
echo ""
echo "Step 8: Setting up smart-city namespace..."

if kubectl apply -f k8s-manifests/namespace.yaml &>/dev/null; then
    success "Namespace created/updated"
else
    error "Failed to create namespace"
    exit 1
fi

# 9. Create ConfigMaps
echo ""
echo "Step 9: Creating ConfigMaps for services..."

services=("traffic-camera" "healthcare-api" "parking-system")
for service in "${services[@]}"; do
    if kubectl create configmap "${service}-code" \
        --from-file="smart-city-services/${service}/app.py" \
        -n smart-city \
        --dry-run=client -o yaml | kubectl apply -f - &>/dev/null; then
        success "${service} ConfigMap created"
    else
        error "Failed to create ${service} ConfigMap"
    fi
done

# 10. Deploy services
echo ""
echo "Step 10: Deploying smart city services..."

if kubectl apply -f k8s-manifests/services-no-build.yaml &>/dev/null; then
    success "Services deployed"
else
    error "Failed to deploy services"
    kubectl apply -f k8s-manifests/services-no-build.yaml
    exit 1
fi

# 11. Wait for pods
echo ""
echo "Step 11: Waiting for pods to be ready..."
sleep 5

# 12. Display final status
echo ""
echo "====== CLUSTER STATUS ======"
echo ""
success "Cluster Information:"
kubectl cluster-info 2>/dev/null | grep -v "^$" || echo "  (Cluster is running)"

echo ""
echo "📦 Nodes:"
kubectl get nodes 2>/dev/null || echo "  Unable to get nodes"

echo ""
echo "📦 Pods in smart-city namespace:"
kubectl get pods -n smart-city 2>/dev/null || echo "  No pods found"

echo ""
echo "🔌 Services:"
kubectl get svc -n smart-city 2>/dev/null || echo "  No services found"

echo ""
echo "====== QUICK START GUIDE ======"
echo ""
echo "✅ System is ready! Use these commands:"
echo ""
echo "📊 Watch pods in real-time:"
echo "  kubectl get pods -n smart-city -w"
echo ""
echo "📋 View pod logs:"
echo "  kubectl logs -f <pod-name> -n smart-city"
echo "  # Example: kubectl logs -f traffic-camera-7d4f9c8b2 -n smart-city"
echo ""
echo "🔌 Port-forward a service (from another terminal):"
echo "  kubectl port-forward -n smart-city svc/traffic-camera-service 8001:80"
echo ""
echo "🌐 Test the services:"
echo "  curl http://localhost:8001/health"
echo "  curl http://localhost:8001/api/cameras"
echo ""
echo "🎯 Run attacks:"
echo "  python attack-simulator/ddos_simulator.py http://localhost:8001/api/cameras 10 30"
echo "  python attack-simulator/data_exfiltration.py http://localhost:8001"
echo ""
echo "🛑 Stop the system:"
echo "  sudo systemctl stop k3s.service"
echo "  # OR (if using direct mode):"
echo "  sudo pkill -f 'k3s server'"
echo ""
echo "====== TROUBLESHOOTING ======"
echo ""
echo "❓ If pods don't start, check logs:"
echo "  kubectl describe pod <pod-name> -n smart-city"
echo "  kubectl logs <pod-name> -n smart-city"
echo ""
echo "❓ If K3s won't start, check:"
echo "  sudo systemctl status k3s.service"
echo "  sudo journalctl -xeu k3s.service"
echo "  tail -50 /tmp/k3s.log"
echo ""
