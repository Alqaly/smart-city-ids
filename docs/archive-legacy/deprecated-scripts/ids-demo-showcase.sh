#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -n "${KUBECONFIG:-}" && ! -r "${KUBECONFIG}" && -r "$HOME/.kube/config" ]]; then
    export KUBECONFIG="$HOME/.kube/config"
fi

command -v kubectl >/dev/null 2>&1 || { echo "❌ kubectl not found"; exit 1; }
kubectl cluster-info >/dev/null 2>&1 || { echo "❌ Kubernetes cluster not reachable"; exit 1; }

echo "🎓 SMART CITY IDS - COMPLETE DEMO SHOWCASE"
echo "==========================================="

echo ""
echo "1. 🏗️ INFRASTRUCTURE OVERVIEW"
kubectl get pods -n smart-city
echo ""

echo "2. 🛡️ SECURITY STACK STATUS"
kubectl get pods -n falco-system --selector=app.kubernetes.io/name=falco || echo "⚠️ Falco namespace/pods unavailable"
kubectl get pods -n monitoring --selector=app=suricata || echo "⚠️ Suricata namespace/pods unavailable"

echo ""
echo "3. 🚨 GENERATING SECURITY EVENTS..."
echo "   This will create multiple attack types for demonstration"

# Generate various security events
"$SCRIPT_DIR/generate-security-events.sh"
sleep 2

echo ""
echo "4. 🌐 GENERATING NETWORK ATTACKS..."
"$SCRIPT_DIR/generate-network-attacks.sh"
sleep 2

echo ""
echo "5. 🎯 GENERATING ADVANCED ATTACK SCENARIOS..."
"$SCRIPT_DIR/generate-advanced-attacks.sh"
sleep 2

echo ""
echo "6. 📊 LIVE MONITORING DASHBOARD"
echo "   Starting real-time IDS monitoring..."
echo "   Press Ctrl+C to stop monitoring and continue"
echo ""
"$SCRIPT_DIR/monitor-ids-logs.sh"
