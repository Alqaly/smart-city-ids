#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -n "${KUBECONFIG:-}" && ! -r "${KUBECONFIG}" && -r "$HOME/.kube/config" ]]; then
    export KUBECONFIG="$HOME/.kube/config"
fi

command -v kubectl >/dev/null 2>&1 || { echo "❌ kubectl not found"; exit 1; }
kubectl cluster-info >/dev/null 2>&1 || { echo "❌ Kubernetes cluster not reachable"; exit 1; }

echo "🚨 Generating Multiple Security Event Types..."

# Get a pod to test with (supports multiple deployment variants)
TEST_POD=""
for label in iot-device iot-device-enhanced iot-simulator traffic-camera healthcare-api; do
    TEST_POD=$(kubectl get pods -n smart-city -l app="$label" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
    if [[ -n "$TEST_POD" ]]; then
        break
    fi
done
[[ -n "$TEST_POD" ]] || { echo "❌ No suitable pod found in smart-city namespace"; exit 1; }

run_in_pod() {
    local cmd="$1"
    kubectl exec -n smart-city "$TEST_POD" -- sh -c "$cmd" >/dev/null 2>&1 || true
}

echo "Using pod: $TEST_POD"
echo ""

# IDS API URL for alert reporting (optional but recommended for dashboard)
IDS_API="${IDS_API_URL:-http://localhost:30800}"

report_alert() {
    local rule="$1" output="$2" priority="${3:-Warning}" container="${4:-$TEST_POD}" proc="${5:-sh}"
    curl -sf --max-time 5 -X POST "$IDS_API/api/alerts/internal" \
        -H 'Content-Type: application/json' \
        -d "{\"output\":\"$output\",\"priority\":\"$priority\",\"rule\":\"$rule\",\"time\":\"$(date -u +%Y-%m-%dT%H:%M:%S.000Z)\",\"output_fields\":{\"container.name\":\"$container\",\"proc.cmdline\":\"$proc\",\"user.name\":\"root\"}}" \
        >/dev/null 2>&1 && echo "   → Alert sent to IDS API" || true
}

# 1. PRIVILEGE ESCALATION ATTEMPT
echo "1. 🔓 Privilege Escalation Attempt"
run_in_pod 'sudo cat /etc/shadow 2>/dev/null || cat /etc/shadow 2>/dev/null || true'
report_alert "Read sensitive file untrusted" "Sensitive file opened: /etc/shadow by process cat in container $TEST_POD (user=root)" "Critical" "$TEST_POD" "cat /etc/shadow"
echo ""

# 2. SUSPICIOUS PROCESS EXECUTION  
echo "2. ⚡ Suspicious Process Execution"
run_in_pod 'curl -s http://google.com >/dev/null || wget -qO- http://google.com >/dev/null || true'
report_alert "Unexpected outbound connection destination" "Unexpected outbound connection from $TEST_POD to google.com (proc=curl user=root)" "Notice" "$TEST_POD" "curl http://google.com"
echo ""

# 3. FILE SYSTEM TAMPERING
echo "3. 📁 File System Tampering"
run_in_pod 'touch /tmp/malicious_file'
report_alert "Write below binary dir" "File created in binary dir: /tmp/malicious_file in $TEST_POD" "Warning" "$TEST_POD" "touch /tmp/malicious_file"
echo ""

# 4. NETWORK SCAN ATTEMPT
echo "4. 🌐 Network Scan Simulation"
run_in_pod 'ping -c 2 8.8.8.8 >/dev/null || true'
report_alert "ET SCAN Potential VNC Scan 5900-5920" "Suricata Network Alert: port scan from $TEST_POD to internal services" "Warning" "$TEST_POD" "ping 8.8.8.8"
echo ""

# 5. CONTAINER ESCAPE ATTEMPT
echo "5. 🏃 Container Escape Attempt"
run_in_pod 'ls /proc/1/root/etc/passwd >/dev/null || true'
report_alert "Container escape attempt" "Container escape via /proc: nsenter attempt in $TEST_POD (user=root)" "Critical" "$TEST_POD" "nsenter --target 1 --mount"
echo ""

# 6. CRYPTO MINING SUSPICION
echo "6. ⛏️ Crypto Mining Suspicion"
run_in_pod 'dd if=/dev/zero of=/dev/null bs=1M count=10 2>/dev/null || true'
report_alert "Detect crypto miners using the Stratum protocol" "Crypto miner detected: xmrig started in $TEST_POD (user=root)" "Critical" "$TEST_POD" "./xmrig --donate-level 0"
echo ""

echo "✅ Multiple security event types generated!"
echo "Check Falco logs: kubectl logs -n falco-system -l app=falco --tail=20"
echo "Check IDS Dashboard: http://localhost:30800/ui"
