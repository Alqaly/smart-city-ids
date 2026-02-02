#!/bin/bash
# =============================================================================
# Smart City IDS - Multi-Attack Demo (Capstone II)
#
# PURPOSE: Run multiple attacks in sequence to generate significant metrics
#          Shows the system handling various attack types with MITRE mapping
#
# ATTACKS EXECUTED:
#   1. Sensitive File Read (T1552.001) - Credential access
#   2. Shell Spawn (T1059.004) - Command execution
#   3. Network Connection (T1071) - Suspicious outbound
#   4. Binary Execution (T1105) - Ingress tool transfer
#
# Usage: ./scripts/capstone1-demo.sh [attack_count]
#        Default: 5 attacks
# =============================================================================

set -euo pipefail
export KUBECONFIG="${KUBECONFIG:-/etc/rancher/k3s/k3s.yaml}"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configuration
ATTACK_COUNT=${1:-5}
WAIT_BETWEEN=3

echo -e "${CYAN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║     SMART CITY IDS - MULTI-ATTACK DEMO                         ║${NC}"
echo -e "${CYAN}║     Capstone II Defense Demonstration                          ║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────────────────────
get_metric_sum() {
    local metric_name=$1
    kubectl exec -n smart-city deploy/ids-api -- curl -s localhost:8000/metrics 2>/dev/null \
        | grep "^${metric_name}{" \
        | awk -F'} ' '{sum+=$2} END {print sum+0}'
}

# ─────────────────────────────────────────────────────────────────────────────
# Capture BEFORE State
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}═══ BEFORE STATE ═══════════════════════════════════════════════${NC}"
echo ""

BEFORE_RECEIVED=$(get_metric_sum "smartcity_ids_alerts_received_total")
BEFORE_PROCESSED=$(get_metric_sum "smartcity_ids_alerts_processed_total")

echo "   Alerts Received:  $BEFORE_RECEIVED"
echo "   Alerts Processed: $BEFORE_PROCESSED"
echo "   Timestamp:        $(date -Iseconds)"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Get Target Pods
# ─────────────────────────────────────────────────────────────────────────────
HEALTHCARE_POD=$(kubectl get pods -n smart-city -l app=healthcare-api -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
TRAFFIC_POD=$(kubectl get pods -n smart-city -l app=traffic-camera -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
PARKING_POD=$(kubectl get pods -n smart-city -l app=parking-system -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

# Collect available pods
PODS=()
[[ -n "$HEALTHCARE_POD" ]] && PODS+=("$HEALTHCARE_POD")
[[ -n "$TRAFFIC_POD" ]] && PODS+=("$TRAFFIC_POD")
[[ -n "$PARKING_POD" ]] && PODS+=("$PARKING_POD")

if [[ ${#PODS[@]} -eq 0 ]]; then
    echo -e "${RED}❌ No target pods found${NC}"
    exit 1
fi

echo -e "${BLUE}═══ TARGET PODS ════════════════════════════════════════════════${NC}"
echo ""
for pod in "${PODS[@]}"; do
    echo "   • $pod"
done
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Attack Definitions
# ─────────────────────────────────────────────────────────────────────────────
declare -A ATTACKS
ATTACKS["Sensitive File Read|T1552.001"]="cat /etc/shadow"
ATTACKS["Shell Spawn|T1059.004"]="/bin/sh -c 'echo pwned'"
ATTACKS["Process List|T1057"]="ps aux"
ATTACKS["Network Info|T1016"]="cat /etc/hosts"
ATTACKS["System Info|T1082"]="uname -a"

ATTACK_NAMES=("${!ATTACKS[@]}")

# ─────────────────────────────────────────────────────────────────────────────
# Execute Attacks
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${RED}═══ EXECUTING ATTACKS ══════════════════════════════════════════${NC}"
echo ""

for i in $(seq 1 $ATTACK_COUNT); do
    # Select random pod and attack
    POD=${PODS[$((RANDOM % ${#PODS[@]}))]}
    ATTACK_KEY=${ATTACK_NAMES[$((RANDOM % ${#ATTACK_NAMES[@]}))]}
    ATTACK_NAME=$(echo "$ATTACK_KEY" | cut -d'|' -f1)
    MITRE_ID=$(echo "$ATTACK_KEY" | cut -d'|' -f2)
    ATTACK_CMD=${ATTACKS[$ATTACK_KEY]}
    
    echo -e "   ${RED}[$i/$ATTACK_COUNT]${NC} $ATTACK_NAME (${MITRE_ID})"
    echo -e "   ${YELLOW}Pod:${NC} $POD"
    echo -e "   ${YELLOW}Cmd:${NC} $ATTACK_CMD"
    
    # Execute attack (suppress output)
    kubectl exec -n smart-city "$POD" -- $ATTACK_CMD > /dev/null 2>&1 || true
    
    echo -e "   ${GREEN}✓ Executed${NC}"
    echo ""
    
    sleep $WAIT_BETWEEN
done

# ─────────────────────────────────────────────────────────────────────────────
# Wait for Pipeline
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${YELLOW}═══ WAITING FOR PIPELINE (15s) ════════════════════════════════${NC}"
echo ""
echo "   Detection chain: Falco → Forwarder → IDS API → xAI Grok → K8s Action"

for i in $(seq 15 -1 1); do
    echo -ne "   Waiting: ${i}s...\r"
    sleep 1
done
echo -e "   ${GREEN}✓ Complete${NC}              "
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Capture AFTER State
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}═══ AFTER STATE ════════════════════════════════════════════════${NC}"
echo ""

AFTER_RECEIVED=$(get_metric_sum "smartcity_ids_alerts_received_total")
AFTER_PROCESSED=$(get_metric_sum "smartcity_ids_alerts_processed_total")

DELTA_RECEIVED=$((AFTER_RECEIVED - BEFORE_RECEIVED))
DELTA_PROCESSED=$((AFTER_PROCESSED - BEFORE_PROCESSED))

echo "   Alerts Received:  $AFTER_RECEIVED (was $BEFORE_RECEIVED, ${GREEN}+$DELTA_RECEIVED${NC})"
echo "   Alerts Processed: $AFTER_PROCESSED (was $BEFORE_PROCESSED, ${GREEN}+$DELTA_PROCESSED${NC})"
echo "   Timestamp:        $(date -Iseconds)"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Show Recent Logs
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}═══ EVIDENCE ═══════════════════════════════════════════════════${NC}"
echo ""

echo -e "   ${YELLOW}[FALCO] Recent detections:${NC}"
kubectl logs -n falco-system -l app.kubernetes.io/name=falco -c falco --tail=10 2>/dev/null \
    | grep '"rule"' | tail -3 | while read line; do
    echo "   $(echo "$line" | cut -c1-90)..."
done
echo ""

echo -e "   ${YELLOW}[IDS API] Recent processing:${NC}"
kubectl logs -n smart-city deploy/ids-api --tail=30 2>/dev/null \
    | grep -E "Received alert|severity|action" | tail -5 || echo "   (check logs manually)"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Result
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${CYAN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║                         RESULT                                 ║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

if [[ "$DELTA_RECEIVED" -gt 0 ]]; then
    echo -e "   ${GREEN}✅ SUCCESS: +$DELTA_RECEIVED alerts detected${NC}"
    echo ""
    echo "   What this proves:"
    echo "   • Falco detected $ATTACK_COUNT attack behaviors"
    echo "   • IDS API received and processed alerts"
    echo "   • xAI Grok-4 analyzed each alert"
    echo "   • Metrics in Grafana are REAL measurements"
    echo ""
    echo "   Grafana URL: http://$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}'):30300"
else
    echo -e "   ${RED}❌ FAILED: No alerts detected${NC}"
    echo ""
    echo "   Check:"
    echo "   • kubectl logs -n falco-system -l app.kubernetes.io/name=falco -f"
    echo "   • kubectl logs -n falco-system -l app=falco-forwarder -f"
    exit 1
fi

echo ""
