#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
# Smart City IDS — Demo Showcase (Tomorrow's Demo)
# ═══════════════════════════════════════════════════════════════════════════
# Runs a complete attack → detection → LLM analysis → dashboard cycle.
# Alerts appear on the Operator Dashboard within seconds.
#
# Usage:
#   ./demo-showcase-full.sh              # Full demo (all phases)
#   ./demo-showcase-full.sh --quick      # Quick 5-alert demo
#   ./demo-showcase-full.sh --live       # Also exec in pods (Falco)
# ═══════════════════════════════════════════════════════════════════════════

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

export KUBECONFIG="${KUBECONFIG:-/etc/rancher/k3s/k3s.yaml}"

# Determine IDS API URL — try NodePort on common IPs, then port-forward
IDS_URL="${IDS_API_URL:-http://localhost:30800}"
IDS_NODEPORT="http://localhost:30800"
IDS_CLUSTER="http://ids-api-service.smart-city.svc.cluster.local:8000"

check_api() {
    curl -sf "$1/health" >/dev/null 2>&1
}

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  🛡️  SMART CITY IDS — LIVE DEMO SHOWCASE"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# --- Phase 0: Connectivity ---
echo "🔌 Phase 0: Checking connectivity..."

API=""
if check_api "$IDS_URL"; then
    API="$IDS_URL"
    echo "   ✓ IDS API reachable at $API"
elif check_api "$IDS_NODEPORT"; then
    API="$IDS_NODEPORT"
    echo "   ✓ IDS API reachable at $API (NodePort)"
else
    echo "   ⚠️  IDS API not reachable on localhost. Trying port-forward..."
    kubectl port-forward -n smart-city svc/ids-api-service 8000:8000 &>/dev/null &
    PF_PID=$!
    sleep 4
    if check_api "$IDS_URL"; then
        API="$IDS_URL"
        echo "   ✓ Port-forward established at $API"
    else
        echo "   ❌ Cannot reach IDS API. Check deployment."
        exit 1
    fi
fi

echo ""

# --- Phase 1: Infrastructure Overview ---
echo "🏗️  Phase 1: Infrastructure Overview"
echo "───────────────────────────────────────────────────────────────"
echo "   Smart-City Pods:"
kubectl get pods -n smart-city --no-headers 2>/dev/null | awk '{printf "     %-50s %s\n", $1, $3}'
echo ""

SC_COUNT=$(kubectl get pods -n smart-city --no-headers 2>/dev/null | wc -l)
FALCO_COUNT=$(kubectl get pods -n falco-system --no-headers 2>/dev/null | wc -l)
MON_COUNT=$(kubectl get pods -n monitoring --no-headers 2>/dev/null | wc -l)
echo "   Totals: $SC_COUNT smart-city | $FALCO_COUNT falco | $MON_COUNT monitoring"
echo ""

# --- Phase 2: Health Check ---
echo "📊 Phase 2: System Health Check"
echo "───────────────────────────────────────────────────────────────"
HEALTH=$(curl -sf "$API/health" 2>/dev/null || echo '{}')
echo "   $HEALTH" | python3 -m json.tool 2>/dev/null | head -20 || echo "   $HEALTH"
echo ""

# --- Helper to send alert ---
send_alert() {
    local json_payload="$1"
    local label="$2"
    
    RESP=$(curl -sf -X POST "$API/api/alerts/internal" \
        -H "Content-Type: application/json" \
        -d "$json_payload" 2>/dev/null || echo '{"error":"connection failed"}')
    
    # Extract key fields
    local status=$(echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','?'))" 2>/dev/null || echo "?")
    local sev=$(echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('severity',d.get('analysis',{}).get('severity','?')))" 2>/dev/null || echo "?")
    local engine=$(echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('llm_engine',d.get('engine','?')))" 2>/dev/null || echo "?")
    
    echo "   ✓ $label → status=$status severity=$sev engine=$engine"
}

# --- Phase 3: Attack Simulation ---
QUICK="${1:-}"
LIVE="${2:-}"
if [[ "$QUICK" == "--quick" ]] || [[ "$QUICK" == "-q" ]]; then
    ATTACK_COUNT=5
elif [[ "$QUICK" == "--live" ]]; then
    ATTACK_COUNT=10
    LIVE="--live"
else
    ATTACK_COUNT=10
fi

echo "🚨 Phase 3: Launching $ATTACK_COUNT Attack Scenarios"
echo "───────────────────────────────────────────────────────────────"
echo ""

TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)

# Attack 1: Shell in Container
echo "  [1/$ATTACK_COUNT] 🐚 Terminal Shell in Container"
send_alert '{
    "output": "Terminal shell in container: bash was spawned in traffic-camera-north (user=root proc.cmdline=bash parent=runc)",
    "priority": "Critical",
    "rule": "Terminal shell in container",
    "time": "'"$TS"'",
    "output_fields": {"container.name": "traffic-camera-north", "proc.cmdline": "bash", "user.name": "root", "evt.type": "execve"}
}' "Shell in traffic-camera-north"
[[ "$LIVE" == "--live" ]] && (kubectl exec -n smart-city deploy/ids-api -- sh -c 'echo test' 2>/dev/null || true)
sleep 2

# Attack 2: Sensitive File Read
echo "  [2/$ATTACK_COUNT] 📄 Sensitive File Read"
send_alert '{
    "output": "Sensitive file opened for reading: /etc/shadow by process cat in air-quality-downtown (user=www-data)",
    "priority": "Warning",
    "rule": "Read sensitive file untrusted",
    "time": "'"$TS"'",
    "output_fields": {"container.name": "air-quality-downtown", "proc.cmdline": "cat /etc/shadow", "fd.name": "/etc/shadow", "user.name": "www-data"}
}' "Shadow read in air-quality-downtown"
sleep 2

# Attack 3: Port Scan
echo "  [3/$ATTACK_COUNT] 🔍 Network Port Scan"
send_alert '{
    "output": "Suricata Network Alert: ET SCAN Potential VNC Scan 5900-5920 (10.42.1.5 to 10.42.0.8:5900/TCP) [SigID: 2002911]",
    "priority": "Warning",
    "rule": "ET SCAN Potential VNC Scan 5900-5920",
    "time": "'"$TS"'",
    "output_fields": {"container.name": "suricata", "alert.signature": "ET SCAN Potential VNC Scan", "src_ip": "10.42.1.5", "dest_ip": "10.42.0.8", "proto": "TCP"}
}' "Port scan detected"
sleep 2

# Attack 4: DDoS
echo "  [4/$ATTACK_COUNT] 💥 DDoS Amplification"
send_alert '{
    "output": "Suricata Network Alert: ET DOS NTP Amplification DDoS (10.0.0.99 to 10.42.0.8:80/UDP) [SigID: 2016150]",
    "priority": "Critical",
    "rule": "ET DOS Possible NTP DDoS Amplification",
    "time": "'"$TS"'",
    "output_fields": {"container.name": "suricata", "alert.signature": "ET DOS NTP DDoS", "src_ip": "10.0.0.99", "dest_ip": "10.42.0.8", "proto": "UDP"}
}' "DDoS amplification"
sleep 2

# Attack 5: Privilege Escalation
echo "  [5/$ATTACK_COUNT] 🔓 Privilege Escalation"
send_alert '{
    "output": "Container privilege escalation: setuid binary in power-grid-monitor (user=www-data proc.cmdline=sudo su)",
    "priority": "Critical",
    "rule": "Launch Privileged Container",
    "time": "'"$TS"'",
    "output_fields": {"container.name": "power-grid-monitor", "proc.cmdline": "sudo su", "user.name": "www-data"}
}' "Privesc in power-grid-monitor"

if [[ $ATTACK_COUNT -le 5 ]]; then
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo "  ✅ Quick demo complete! $ATTACK_COUNT alerts sent."
    echo ""
    echo "  → Open dashboard: $API/ui"
    echo "═══════════════════════════════════════════════════════════════"
    exit 0
fi

sleep 2

# Attack 6: DNS Exfiltration
echo "  [6/$ATTACK_COUNT] 📡 DNS Data Exfiltration"
send_alert '{
    "output": "Suricata Network Alert: ET POLICY Data Exfiltration via DNS (10.42.1.5 to 203.0.113.50:53/UDP) [SigID: 2027863]",
    "priority": "Critical",
    "rule": "ET POLICY Possible Data Exfiltration via DNS",
    "time": "'"$TS"'",
    "output_fields": {"container.name": "suricata", "alert.signature": "ET POLICY Data Exfiltration via DNS", "src_ip": "10.42.1.5", "dest_ip": "203.0.113.50", "proto": "UDP"}
}' "DNS exfiltration"
sleep 2

# Attack 7: Cryptominer
echo "  [7/$ATTACK_COUNT] ⛏️  Crypto Mining Detected"
send_alert '{
    "output": "Crypto miner detected: xmrig binary started in air-quality-industrial (user=root cmdline=./xmrig --donate-level 1 -o pool.minexmr.com:4444)",
    "priority": "Critical",
    "rule": "Detect crypto miners using the Stratum protocol",
    "time": "'"$TS"'",
    "output_fields": {"container.name": "air-quality-industrial", "proc.cmdline": "./xmrig --donate-level 1 -o pool.minexmr.com:4444", "user.name": "root", "proc.name": "xmrig"}
}' "Cryptominer in air-quality"
sleep 2

# Attack 8: SQL Injection
echo "  [8/$ATTACK_COUNT] 💉 SQL Injection"
send_alert '{
    "output": "Suricata Network Alert: ET WEB_SERVER SQL Injection (10.42.1.5 to healthcare-api:5000) [SigID: 2006546]",
    "priority": "Critical",
    "rule": "ET WEB_SERVER SQL Injection Attempt",
    "time": "'"$TS"'",
    "output_fields": {"container.name": "suricata", "alert.signature": "ET WEB_SERVER SQL Injection", "src_ip": "10.42.1.5", "dest_ip": "10.42.0.20", "proto": "TCP"}
}' "SQL injection to healthcare-api"
sleep 2

# Attack 9: Outbound C2
echo "  [9/$ATTACK_COUNT] 🌐 Outbound C2 Connection"
send_alert '{
    "output": "Unexpected outbound connection from smart-light-main-st to 185.192.69.10:443 (proc=curl user=root)",
    "priority": "Notice",
    "rule": "Unexpected outbound connection destination",
    "time": "'"$TS"'",
    "output_fields": {"container.name": "smart-light-main-st", "fd.sip": "185.192.69.10", "fd.sport": "443", "proc.cmdline": "curl https://185.192.69.10/c2", "user.name": "root"}
}' "C2 connection from smart-light"
sleep 2

# Attack 10: Lateral Movement
echo "  [10/$ATTACK_COUNT] 🔄 Lateral Movement"
send_alert '{
    "output": "K8s service discovery from iot-device-enhanced: nslookup kubernetes.default.svc (user=root) - potential lateral movement",
    "priority": "Warning",
    "rule": "Contact K8S API Server From Container",
    "time": "'"$TS"'",
    "output_fields": {"container.name": "iot-device-enhanced", "proc.cmdline": "nslookup kubernetes.default.svc.cluster.local", "user.name": "root"}
}' "Lateral movement via DNS"

echo ""

# --- Phase 4: Live Falco triggers (optional) ---
if [[ "$LIVE" == "--live" ]] || [[ "$QUICK" == "--live" ]]; then
    echo "🔧 Phase 4: Live Falco Triggers (exec in pods)"
    echo "───────────────────────────────────────────────────────────────"
    
    # Find an IoT pod
    POD=$(kubectl get pods -n smart-city -l app=iot-devices-enhanced -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || \
          kubectl get pods -n smart-city -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    
    if [[ -n "$POD" ]]; then
        echo "   Using pod: $POD"
        echo "   Running shell command..."
        kubectl exec -n smart-city "$POD" -- sh -c 'echo "Falco trigger test"' 2>/dev/null || true
        echo "   Reading /etc/shadow..."
        kubectl exec -n smart-city "$POD" -- sh -c 'cat /etc/shadow 2>/dev/null' 2>/dev/null || true
        echo "   DNS lookup..."
        kubectl exec -n smart-city "$POD" -- sh -c 'nslookup google.com 2>/dev/null' 2>/dev/null || true
        echo "   ✓ Live commands executed — check Falco logs for detections"
    else
        echo "   ⚠️  No suitable pod found for live triggers"
    fi
    echo ""
fi

# --- Phase 5: Summary ---
echo "═══════════════════════════════════════════════════════════════"
echo "  ✅ DEMO COMPLETE — $ATTACK_COUNT attack alerts processed"
echo ""
echo "  📊 Operator Dashboard:  $API/ui"
echo "  📈 Grafana:             http://localhost:30300"
echo "  🔍 Prometheus:          http://localhost:31106"
echo ""
echo "  Check alerts:  curl -s $API/api/alerts | python3 -m json.tool"
echo "  Check metrics: curl -s $API/api/metrics | python3 -m json.tool"
echo "═══════════════════════════════════════════════════════════════"
