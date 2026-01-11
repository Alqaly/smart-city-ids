#!/bin/bash
set -e

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║   PHASE 4: Smart City IDS - Full Attack & Detection Demo       ║"
echo "║   Watch real-time attacks, detection, analysis, and response   ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Configuration
DEMO_DURATION=${1:-30}  # Default 30 seconds per attack
IDS_API_URL="http://localhost:8000"
GRAFANA_URL="http://localhost:30300"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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
echo "   Open in browser while attacks run to see:"
echo "   • Real-time alert rates"
echo "   • Alert severity distribution"
echo "   • Automated K8s actions"
echo "   • Detection latency metrics"
echo ""

# Phase 3: Attack sequence
log_step "Starting attack sequence (${DEMO_DURATION}s each)..."
echo ""

# Record start time
START_TIME=$(date +%s)

# Attack 1: DDoS on Traffic Camera
log_attack "1️⃣ DDoS Attack on Traffic Camera Service"
echo "   Target: traffic-camera:5000 (vehicle detection API)"
echo "   Pattern: 100+ req/sec flood"
echo "   Expected Detection: Suricata detects unusual traffic volume"
echo ""

python3 /home/aka/smart-city-ids/attack-simulator/phase4-smart-city-attacks.py \
    --service traffic-camera \
    --attack ddos \
    --duration $DEMO_DURATION

sleep 3
echo ""

# Attack 2: SQL Injection on Healthcare API
log_attack "2️⃣ SQL Injection Attack on Healthcare API"
echo "   Target: healthcare-api:5000 (patient records)"
echo "   Pattern: SQL injection payloads in query parameters"
echo "   Expected Detection: Suricata detects SQL injection signatures"
echo ""

python3 /home/aka/smart-city-ids/attack-simulator/phase4-smart-city-attacks.py \
    --service healthcare-api \
    --attack sqli \
    --duration $DEMO_DURATION

sleep 3
echo ""

# Attack 3: Privilege Escalation
log_attack "3️⃣ Privilege Escalation on Healthcare API"
echo "   Target: healthcare-api:5000 (unauthorized admin access)"
echo "   Pattern: Forged admin tokens, sudo bypass attempts"
echo "   Expected Detection: Falco detects unauthorized process execution"
echo ""

python3 /home/aka/smart-city-ids/attack-simulator/phase4-smart-city-attacks.py \
    --service healthcare-api \
    --attack privesc \
    --duration $DEMO_DURATION

sleep 3
echo ""

# Attack 4: Data Exfiltration
log_attack "4️⃣ Data Exfiltration from Parking System"
echo "   Target: parking-system:5000 (payment records)"
echo "   Pattern: Large data downloads, export requests"
echo "   Expected Detection: Falco detects file read operations on sensitive data"
echo ""

python3 /home/aka/smart-city-ids/attack-simulator/phase4-smart-city-attacks.py \
    --service parking-system \
    --attack exfil \
    --duration $DEMO_DURATION

sleep 3
echo ""

# Calculate total time
END_TIME=$(date +%s)
TOTAL_TIME=$((END_TIME - START_TIME))

# Summary
echo "╔════════════════════════════════════════════════════════════════╗"
log_success "ALL ATTACKS COMPLETE"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

echo "📊 Attack Summary:"
echo "   Total Duration: ${TOTAL_TIME}s"
echo "   Attacks Executed: 4"
echo "   - DDoS (traffic-camera)"
echo "   - SQL Injection (healthcare-api)"
echo "   - Privilege Escalation (healthcare-api)"
echo "   - Data Exfiltration (parking-system)"
echo ""

echo "🔍 Expected Results:"
echo "   ✅ 100+ Alerts generated"
echo "   ✅ Critical/Error alerts triggered"
echo "   ✅ Groq LLM analysis on each alert"
echo "   ✅ K8s automation actions (pod isolation, scaling)"
echo "   ✅ Grafana dashboard showing live metrics"
echo ""

echo "📈 Check Metrics:"
echo "   IDS API:  $IDS_API_URL/api/metrics"
echo "   Grafana:  $GRAFANA_URL"
echo ""

echo "📝 View Logs:"
echo "   IDS API logs:     kubectl logs -n smart-city -l app=ids-api -f"
echo "   Falco logs:       kubectl logs -n falco-system -l app=falco -f"
echo "   Suricata logs:    kubectl logs -n monitoring -l app=suricata -f"
echo ""

echo "🎯 Next Steps:"
echo "   1. Open Grafana: $GRAFANA_URL"
echo "   2. Login: admin/admin"
echo "   3. View dashboard: Smart City IDS - Real-Time Detection & Response"
echo "   4. Watch metrics update in real-time"
echo "   5. Note alert reduction ratio (100+ alerts → actionable summaries)"
echo ""
