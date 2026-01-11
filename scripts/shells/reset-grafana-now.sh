#!/bin/bash

echo "🔄 Resetting Grafana password..."

# Method 1: Check if there's a secret to update
SECRET_NAME=$(kubectl get secrets -n monitoring -o name | grep -E "(grafana|admin)" | head -1)

if [ -n "$SECRET_NAME" ]; then
    echo "Updating existing secret: $SECRET_NAME"
    kubectl patch $SECRET_NAME -n monitoring -p '{"data":{"admin-password":"YWRtaW4="}}'  # "admin" in base64
else
    echo "Creating new admin secret..."
    kubectl create secret generic grafana-admin-credentials \
        --namespace monitoring \
        --from-literal=admin-user=admin \
        --from-literal=admin-password=admin
fi

# Restart Grafana to apply changes
kubectl rollout restart deployment/grafana -n monitoring

echo "⌛ Waiting for restart..."
sleep 20

NODE_IP=$(kubectl get nodes -o wide | awk 'NR==2 {print $6}')
echo "✅ ✅ ✅ PASSWORD RESET COMPLETE ✅ ✅ ✅"
echo "🌐 URL: http://$NODE_IP:30030"
echo "👤 Username: admin"
echo "🔑 Password: admin"

