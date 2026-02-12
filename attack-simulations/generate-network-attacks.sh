#!/bin/bash

set -euo pipefail

if [[ -n "${KUBECONFIG:-}" && ! -r "${KUBECONFIG}" && -r "$HOME/.kube/config" ]]; then
    export KUBECONFIG="$HOME/.kube/config"
fi

command -v kubectl >/dev/null 2>&1 || { echo "❌ kubectl not found"; exit 1; }
kubectl cluster-info >/dev/null 2>&1 || { echo "❌ Kubernetes cluster not reachable"; exit 1; }

echo "🌐 Generating Network IDS Events..."

# Get service IPs for testing
HEALTHCARE_IP=$(kubectl get svc -n smart-city healthcare-api-service -o jsonpath='{.spec.clusterIP}' 2>/dev/null || true)
IOT_IP=$(kubectl get svc -n smart-city iot-device-service -o jsonpath='{.spec.clusterIP}' 2>/dev/null || true)
if [[ -z "$HEALTHCARE_IP" ]]; then
    HEALTHCARE_IP=$(kubectl get svc -n smart-city ids-api-service -o jsonpath='{.spec.clusterIP}' 2>/dev/null || true)
fi
[[ -n "$HEALTHCARE_IP" ]] || { echo "❌ healthcare-api-service not found"; exit 1; }

echo "Target IPs - Healthcare: $HEALTHCARE_IP, IoT: $IOT_IP"
echo ""

# Use a pod to simulate network attacks
ATTACK_POD=""
for label in iot-device iot-device-enhanced iot-simulator traffic-camera healthcare-api; do
    ATTACK_POD=$(kubectl get pods -n smart-city -l app="$label" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
    if [[ -n "$ATTACK_POD" ]]; then
        break
    fi
done
[[ -n "$ATTACK_POD" ]] || { echo "❌ No suitable attack pod found"; exit 1; }

run_in_pod() {
    local cmd="$1"
    kubectl exec -n smart-city "$ATTACK_POD" -- sh -c "$cmd" >/dev/null 2>&1 || true
}

# 1. PORT SCAN DETECTION
echo "1. 🔍 Port Scan Detection"
run_in_pod 'for port in 22 80 443 8080 9000; do nc -z -w1 '"$HEALTHCARE_IP"' "$port" >/dev/null 2>&1 || true; done'
echo "Command attempted"
echo ""

# 2. HTTP ATTACK VECTORS
echo "2. 🕸️ HTTP Attack Vectors"
run_in_pod 'curl -s "http://'"$HEALTHCARE_IP"'/../../../etc/passwd" >/dev/null || true; curl -s "http://'"$HEALTHCARE_IP"'/<script>alert(1)</script>" >/dev/null || true; curl -s "http://'"$HEALTHCARE_IP"'/exec?cmd=whoami" >/dev/null || true'
echo "Command attempted"
echo ""

# 3. SQL INJECTION ATTEMPTS
echo "3. 🗃️ SQL Injection Attempts" 
run_in_pod 'curl -s "http://'"$HEALTHCARE_IP"'/users?id=1 OR 1=1" >/dev/null || true; curl -s "http://'"$HEALTHCARE_IP"'/login?user=admin&pass=anything OR 1=1" >/dev/null || true'
echo "Command attempted"
echo ""

# 4. DNS EXFILTRATION SIMULATION
echo "4. 📡 DNS Exfiltration Simulation"
run_in_pod 'nslookup google.com >/dev/null || true; nslookup malicious-domain.com >/dev/null 2>&1 || true'
echo "Command attempted"
echo ""

echo "✅ Network attack simulations completed!"
echo "Check Suricata logs: kubectl logs -n monitoring -l app=suricata --tail=10"
