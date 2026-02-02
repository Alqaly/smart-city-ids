#!/bin/bash

echo "🚀 Starting Grafana Demo..."

# Stop any existing port-forwards
pkill -f "port-forward" 2>/dev/null

# Start Grafana
GRAFANA_POD=$(kubectl get pods -n monitoring -l app=grafana -o jsonpath='{.items[0].metadata.name}')
echo "📊 Grafana: http://localhost:3000 (admin/admin)"
kubectl port-forward -n monitoring $GRAFANA_POD 3000:3000

