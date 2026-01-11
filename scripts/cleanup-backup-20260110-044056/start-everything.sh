#!/bin/bash

# Go to project root first
cd ~/smart-city-ids

echo "🚀 Starting Smart City IDS System"
echo "=================================="
echo "Project directory: $(pwd)"
echo ""

# Check K3s
echo "📦 Checking K3s installation..."
if command -v k3s &> /dev/null; then
    echo "✅ K3s is installed"
else
    echo "📥 Installing K3s..."
    curl -sfL https://get.k3s.io | sh -
fi

# Kill existing K3s
echo "🔄 Cleaning up existing K3s processes..."
pkill -f "k3s server" 2>/dev/null || true
sleep 2

# Start K3s
echo "🔧 Starting K3s server..."
k3s server --write-kubeconfig-mode=644 --write-kubeconfig=/etc/rancher/k3s/k3s.yaml --disable=traefik --disable=servicelb > /tmp/k3s.log 2>&1 &
K3S_PID=$!
echo "K3s PID: $K3S_PID"

# Wait for K3s ready
echo "⏳ Waiting for K3s to be ready..."
MAX_WAIT=60
ELAPSED=0
while ! kubectl cluster-info &>/dev/null 2>&1; do
    if [ $ELAPSED -ge $MAX_WAIT ]; then
        echo "❌ K3s failed to start"
        tail -20 /tmp/k3s.log
        exit 1
    fi
    echo "   Waiting ($ELAPSED/$MAX_WAIT seconds)..."
    sleep 2
    ELAPSED=$((ELAPSED + 2))
done

echo "✅ K3s cluster is ready!"
echo ""

# Create namespace
echo "📂 Setting up smart-city namespace..."
kubectl apply -f k8s-manifests/namespace.yaml
echo "✅ Namespace ready"
echo ""

# Create ConfigMaps
echo "📝 Creating ConfigMaps for services..."

# Check if files exist
if [ -f "smart-city-services/traffic-camera/app.py" ]; then
    kubectl create configmap traffic-camera-code \
        --from-file=smart-city-services/traffic-camera/app.py \
        -n smart-city \
        --dry-run=client -o yaml | kubectl apply -f -
    echo "✅ traffic-camera ConfigMap"
else
    echo "⚠️  traffic-camera/app.py not found"
fi

if [ -f "smart-city-services/healthcare-api/app.py" ]; then
    kubectl create configmap healthcare-api-code \
        --from-file=smart-city-services/healthcare-api/app.py \
        -n smart-city \
        --dry-run=client -o yaml | kubectl apply -f -
    echo "✅ healthcare-api ConfigMap"
else
    echo "⚠️  healthcare-api/app.py not found"
fi

if [ -f "smart-city-services/parking-system/app.py" ]; then
    kubectl create configmap parking-system-code \
        --from-file=smart-city-services/parking-system/app.py \
        -n smart-city \
        --dry-run=client -o yaml | kubectl apply -f -
    echo "✅ parking-system ConfigMap"
else
    echo "⚠️  parking-system/app.py not found"
fi

echo ""
echo "🚀 Deploying services..."
kubectl apply -f k8s-manifests/services-no-build.yaml
echo "✅ Services deployed"
echo ""

sleep 3

echo "📊 Cluster Status:"
kubectl get nodes
echo ""
echo "📦 Pods:"
kubectl get pods -n smart-city
echo ""
echo "🔌 Services:"
kubectl get svc -n smart-city
echo ""

echo "✅ Smart City IDS System is ready!"
echo ""
echo "Next steps:"
echo "  kubectl get pods -n smart-city -w          (watch pods)"
echo "  kubectl port-forward svc/traffic-camera-service 8001:80 -n smart-city"
echo "  curl http://localhost:8001/health"
echo ""

