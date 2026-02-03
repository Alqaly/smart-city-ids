#!/bin/bash
# =============================================================================
# Smart City IDS - Phase 4 Full Attack Demo
#
# PURPOSE: Execute all attack types against Smart City services
#          Generates significant alert volume for Grafana demonstration
#
# ATTACKS:
#   1. DDoS on Traffic Camera (T1498)
#   2. SQL Injection on Healthcare API (T1190)
#   3. Privilege Escalation (T1611)
#   4. Data Exfiltration (T1041)
#
# Usage: ./scripts/phase4-run-smart-city-attacks.sh [duration_per_attack]
#        Default: 30 seconds per attack
# =============================================================================

set -e

# Configuration
DEMO_DURATION=${1:-30}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ATTACK_SCRIPT="${PROJECT_ROOT}/attack-simulator/phase4-smart-city-attacks.py"

# Get node IP
NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}' 2>/dev/null || echo "localhost")
GRAFANA_URL="http://${NODE_IP}:30300"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║   PHASE 4: Smart City IDS - Full Attack & Detection Demo       ║${NC}"
echo -e "${CYAN}║   Watch real-time attacks, detection, analysis, and response   ║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Helper functions
log_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[✅]${NC} $1"
}

log_attack() {
    echo -e "${RED}[🔴 ATTACK]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[⚠️]${NC} $1"
}

# Pre-flight checks
log_step "Pre-flight checks..."

if ! command -v kubectl &> /dev/null; then
    echo "❌ kubectl not found"
    exit 1
fi

if ! command -v python3 &> /dev/null; then
    echo "❌ python3 not found"
    exit 1
fi

if ! kubectl cluster-info &> /dev/null; then
    echo "❌ K3s cluster not responding"
    exit 1
fi

log_success "Pre-flight checks passed"
echo ""

# Phase 1: Verify all components
log_step "Verifying IDS components..."

COMPONENTS=("suricata" "prometheus" "grafana")
for component in "${COMPONENTS[@]}"; do
    if kubectl get pods -n monitoring -l app=$component | grep -q Running; then
        log_success "$component is running"
    else
        log_warning "$component may not be running"
    fi
done
echo ""

# Phase 2: Show dashboard info
log_step "Grafana Dashboard Information:"
echo "   📊 URL: $GRAFANA_URL"
echo "   👤 User: admin"
echo "   🔑 Password: admin"
echo ""
echo -e "   ${YELLOW}Open Grafana in browser NOW to watch live metrics!${NC}"
echo ""
echo "   Dashboards to watch:"
echo "   • SOC Overview - Alert rates and severity"
echo "   • LLM Performance - Analysis latency"
echo "   • IoT Load - Device metrics"
echo ""

read -p "Press ENTER when Grafana is open, or Ctrl+C to cancel..."
echo ""

# Phase 3: Attack sequence
log_step "Starting attack sequence (${DEMO_DURATION}s each)..."
echo ""

# Capture before metrics
BEFORE_ALERTS=$(kubectl exec -n smart-city deploy/ids-api -- curl -s localhost:8000/metrics 2>/dev/null \
    | grep "smartcity_ids_alerts_received_total{" | awk -F'} ' '{sum+=$2} END {print sum+0}')

# Record start time
START_TIME=$(date +%s)

# Attack 1: DDoS on Traffic Camera
log_attack "1️⃣ DDoS Attack on Traffic Camera Service"
echo "   Target: traffic-camera (vehicle detection API)"
echo "   Pattern: 100+ req/sec flood"
echo "   MITRE: T1498 - Network Denial of Service"
echo "   Detection: Suricata + rate anomaly"
echo ""

if [[ -f "$ATTACK_SCRIPT" ]]; then
    python3 "$ATTACK_SCRIPT" --service traffic-camera --attack ddos --duration $DEMO_DURATION 2>/dev/null || \
    log_warning "Attack script failed, using fallback"
else
    # Fallback: direct kubectl attacks
    for i in $(seq 1 10); do
        kubectl exec -n smart-city deploy/traffic-camera -- cat /etc/passwd > /dev/null 2>&1 || true
        sleep 1
    done
fi

sleep 3
echo ""

# Attack 2: SQL Injection on Healthcare API
log_attack "2️⃣ SQL Injection Attack on Healthcare API"
echo "   Target: healthcare-api (patient records)"
echo "   Pattern: SQL injection payloads"
echo "   MITRE: T1190 - Exploit Public-Facing Application"
echo "   Detection: Falco + Suricata SQL signatures"
echo ""

if [[ -f "$ATTACK_SCRIPT" ]]; then
    python3 "$ATTACK_SCRIPT" --service healthcare-api --attack sqli --duration $DEMO_DURATION 2>/dev/null || true
else
    for i in $(seq 1 10); do
        kubectl exec -n smart-city deploy/healthcare-api -- cat /etc/shadow > /dev/null 2>&1 || true
        sleep 1
    done
fi

sleep 3
echo ""

# Attack 3: Privilege Escalation
log_attack "3️⃣ Privilege Escalation on Healthcare API"
echo "   Target: healthcare-api (container escape attempt)"
echo "   Pattern: Sensitive file access, shell spawn"
echo "   MITRE: T1611 - Escape to Host"
echo "   Detection: Falco runtime monitoring"
echo ""

if [[ -f "$ATTACK_SCRIPT" ]]; then
    python3 "$ATTACK_SCRIPT" --service healthcare-api --attack privesc --duration $DEMO_DURATION 2>/dev/null || true
else
    for i in $(seq 1 10); do
        kubectl exec -n smart-city deploy/healthcare-api -- /bin/sh -c 'cat /etc/shadow' > /dev/null 2>&1 || true
        sleep 1
    done
fi

sleep 3
echo ""

# Attack 4: Data Exfiltration
log_attack "4️⃣ Data Exfiltration from Parking System"
echo "   Target: parking-system (payment records)"
echo "   Pattern: Large data reads, sensitive file access"
echo "   MITRE: T1041 - Exfiltration Over C2 Channel"
echo "   Detection: Falco file access monitoring"
echo ""

if [[ -f "$ATTACK_SCRIPT" ]]; then
    python3 "$ATTACK_SCRIPT" --service parking-system --attack exfil --duration $DEMO_DURATION 2>/dev/null || true
else
    for i in $(seq 1 10); do
        kubectl exec -n smart-city deploy/parking-system -- cat /etc/passwd > /dev/null 2>&1 || true
        kubectl exec -n smart-city deploy/parking-system -- ls -la /tmp > /dev/null 2>&1 || true
        sleep 1
    done
fi

sleep 3
echo ""

# Calculate total time
END_TIME=$(date +%s)
TOTAL_TIME=$((END_TIME - START_TIME))

# Capture after metrics
sleep 5  # Wait for pipeline
AFTER_ALERTS=$(kubectl exec -n smart-city deploy/ids-api -- curl -s localhost:8000/metrics 2>/dev/null \
    | grep "smartcity_ids_alerts_received_total{" | awk -F'} ' '{sum+=$2} END {print sum+0}')
DELTA_ALERTS=$((AFTER_ALERTS - BEFORE_ALERTS))

# Summary
echo -e "${CYAN}╔════════════════════════════════════════════════════════════════╗${NC}"
log_success "ALL ATTACKS COMPLETE"
echo -e "${CYAN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

echo "📊 Attack Summary:"
echo "   Total Duration:    ${TOTAL_TIME}s"
echo "   Attacks Executed:  4 types"
echo "   Alerts Generated:  +$DELTA_ALERTS (REAL detections)"
echo ""
echo "   Attack Types (MITRE ATT&CK):"
echo "   ├── T1498: DDoS (traffic-camera)"
echo "   ├── T1190: SQL Injection (healthcare-api)"
echo "   ├── T1611: Privilege Escalation (healthcare-api)"
echo "   └── T1041: Data Exfiltration (parking-system)"
echo ""

echo "🔍 Verify Results:"
echo "   • Grafana shows alert spike during attack window"
echo "   • Metrics return to baseline after attacks stop"
echo "   • This proves: data is REAL, not mocked"
echo ""

echo "📈 Check Now:"
echo "   Grafana:     $GRAFANA_URL"
echo "   Prometheus:  http://${NODE_IP}:31701"
echo ""

echo "📝 View Logs:"
echo "   kubectl logs -n smart-city deploy/ids-api --tail=50"
echo "   kubectl logs -n falco-system -l app.kubernetes.io/name=falco --tail=50"
echo ""
