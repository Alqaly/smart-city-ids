#!/bin/bash

echo "🔧 Resetting Grafana password using correct method..."

# Get the Grafana pod name
GRAFANA_POD=$(kubectl get pods -n monitoring -l app=grafana -o jsonpath='{.items[0].metadata.name}')

echo "Grafana Pod: $GRAFANA_POD"

# Method 1: Use Grafana CLI to reset admin password
echo "Method 1: Using Grafana CLI..."
kubectl exec -n monitoring $GRAFANA_POD -- grafana-cli admin reset-admin-password admin123

# Wait for the command to complete
sleep 5

# Restart Grafana to ensure changes take effect
echo "Restarting Grafana..."
kubectl rollout restart deployment/grafana -n monitoring

echo "⌛ Waiting for restart (30 seconds)..."
sleep 30

# Check if pod is running
kubectl get pods -n monitoring -l app=grafana

echo ""
echo "✅ ✅ ✅ PASSWORD RESET COMPLETE ✅ ✅ ✅"
echo "🌐 URL: http://192.168.18.63:30030"
echo "👤 Username: admin"
echo "🔑 Password: admin123"

