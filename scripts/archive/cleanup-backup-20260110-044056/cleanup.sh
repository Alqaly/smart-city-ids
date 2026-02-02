#!/bin/bash

# 🧹 Smart City IDS - Cleanup & Shutdown Script
# Stops all services and cleans up resources

echo "🧹 Smart City IDS - Cleanup"
echo "==========================="
echo ""

# Kill port forwards
echo "Stopping port forwards..."
pkill -f "kubectl port-forward" 2>/dev/null || true
echo "✅ Port forwards stopped"

# Delete Kubernetes resources
echo ""
echo "Deleting Kubernetes resources..."
kubectl delete namespace smart-city 2>/dev/null || true
echo "✅ Namespace deleted"

# Stop K3s
echo ""
echo "Stopping K3s server..."
pkill -f "k3s server" 2>/dev/null || true
sleep 2
echo "✅ K3s stopped"

# Optional: Clean K3s data
echo ""
read -p "Remove K3s data directory? (y/n) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    rm -rf /var/lib/rancher/k3s 2>/dev/null || true
    echo "✅ K3s data removed"
fi

echo ""
echo "✅ Cleanup complete!"
echo ""
echo "To start again: ./scripts/start-everything.sh"
