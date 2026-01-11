#!/bin/bash

# 🚀 Smart City IDS - Complete Startup Script
# Container-Safe Version (No systemd required)

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "🚀 Starting Smart City IDS System"
echo "=================================="
echo "Project directory: $PROJECT_DIR"
echo ""

# Function to check if K3s is running
check_k3s_running() {
    if kubectl cluster-info &>/dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# 1. Check for K3s installation
echo "📦 Checking K3s installation..."
if command -v k3s &>/dev/null; then
    echo "✅ K3s is installed"
else
    echo "📥 Installing K3s..."
    curl -sfL https://get.k3s.io | sh -
    echo "✅ K3s installed"
fi

# 2. Kill any existing K3s processes
echo "🔄 Cleaning up existing K3s processes..."
pkill -f "k3s server" 2>/dev/null || true
sleep 2

# 3. Start K3s server
echo "🔧 Starting K3s server..."
k3s server \
    --write-kubeconfig-mode=644 \
    --write-kubeconfig=/etc/rancher/k3s/k3s.yaml \
    --disable=traefik \
    --disable=servicelb \
    > /tmp/k3s.log 2>&1 &

K3S_PID=$!
echo "K3s PID: $K3S_PID"

# 4. Wait for K3s to be ready
echo "⏳ Waiting for K3s to be ready..."
MAX_WAIT=60
ELAPSED=0
while ! check_k3s_running; do
    if [ $ELAPSED -ge $MAX_WAIT ]; then
        echo "❌ K3s failed to start within $MAX_WAIT seconds"
        echo "📋 K3s logs:"
        tail -20 /tmp/k3s.log
        kill $K3S_PID 2>/dev/null || true
        exit 1
    fi
    echo "   Waiting ($ELAPSED/$MAX_WAIT seconds)..."
    sleep 2
    ELAPSED=$((ELAPSED + 2))
done

echo "✅ K3s cluster is ready!"
echo ""

# 5. Create namespace
echo "📂 Setting up smart-city namespace..."
kubectl apply -f k8s-manifests/namespace.yaml
echo "✅ Namespace ready"
echo ""

# 6. Create ConfigMaps for application code
echo "📝 Creating ConfigMaps for services..."
kubectl create configmap traffic-camera-code \
    --from-file=smart-city-services/traffic-camera/app.py \
    -n smart-city \
    --dry-run=client -o yaml | kubectl apply -f -

kubectl create configmap healthcare-api-code \
    --from-file=smart-city-services/healthcare-api/app.py \
    -n smart-city \
    --dry-run=client -o yaml | kubectl apply -f -

kubectl create configmap parking-system-code \
    --from-file=smart-city-services/parking-system/app.py \
    -n smart-city \
    --dry-run=client -o yaml | kubectl apply -f -

echo "✅ ConfigMaps created"
echo ""

# 7. Deploy services
echo "🚀 Deploying smart city services..."
kubectl apply -f k8s-manifests/services-no-build.yaml
echo "✅ Services deployed"
echo ""

# 8. Wait for pods to be ready
echo "⏳ Waiting for pods to start..."
sleep 5

# 9. Display cluster status
echo ""
echo "====== CLUSTER STATUS ======"
echo ""
echo "📊 Nodes:"
kubectl get nodes
echo ""
echo "📦 Pods in smart-city namespace:"
kubectl get pods -n smart-city
echo ""
echo "🔌 Services:"
kubectl get svc -n smart-city
echo ""

# 10. Wait for pods to be ready
echo "⏳ Waiting for pods to become ready (this may take a minute)..."
kubectl wait --for=condition=ready pod \
    -l app=traffic-camera,app=healthcare-api,app=parking-system \
    -n smart-city \
    --timeout=120s 2>/dev/null || echo "⚠️  Note: Pods are still starting. Run 'kubectl get pods -n smart-city -w' to watch"

echo ""
echo "✅ Smart City IDS System is ready!"
echo ""
echo "====== QUICK START ======"
echo ""
echo "View real-time pod status:"
echo "  kubectl get pods -n smart-city -w"
echo ""
echo "Check pod logs:"
echo "  kubectl logs -f <pod-name> -n smart-city"
echo ""
echo "Port-forward a service:"
echo "  kubectl port-forward -n smart-city svc/traffic-camera-service 8001:80"
echo ""
echo "Access services (from another terminal):"
echo "  # After port-forward above:"
echo "  curl http://localhost:8001/health"
echo "  curl http://localhost:8001/api/cameras"
echo ""
echo "Run attack simulations:"
echo "  ./scripts/run-all-attacks.sh"
echo ""
echo "Stop the system:"
echo "  pkill -f 'k3s server'"
echo ""
