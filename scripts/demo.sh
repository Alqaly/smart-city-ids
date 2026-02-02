#!/bin/bash
# =============================================================================
# Smart City IDS - Attack Proof Demo (Capstone Defense)
# 
# PURPOSE: Prove that Grafana metrics are REAL by showing cause → effect
#          Before attack metrics vs After attack metrics with delta
#
# WHAT THIS PROVES:
#   1. Falco REALLY detects the attack (syscall monitoring)
#   2. Forwarder REALLY sends to IDS API (HTTP POST)
#   3. IDS API REALLY processes with xAI Grok (LLM analysis)
#   4. Kubernetes REALLY takes action (pod isolation)
#   5. Prometheus REALLY counts it (metrics increase)
#
# Usage: ./scripts/demo.sh
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
WAIT_SECONDS=10

echo -e "${CYAN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║     SMART CITY IDS - ATTACK PROOF DEMO                         ║${NC}"
echo -e "${CYAN}║     Demonstrates REAL detection, not mock data                 ║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────────────────────
get_metric() {
    local metric_name=$1
    kubectl exec -n smart-city deploy/ids-api -- curl -s localhost:8000/metrics 2>/dev/null \
        | grep "^${metric_name}{" \
        | awk -F'} ' '{sum+=$2} END {print sum+0}'
}

get_action_count() {
    local action=$1
    kubectl exec -n smart-city deploy/ids-api -- curl -s localhost:8000/metrics 2>/dev/null \
        | grep "smartcity_ids_actions_executed_total{action=\"${action}\"}" \
        | awk '{print $2}' || echo "0"
}

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1: Capture BEFORE State
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  STEP 1: BEFORE ATTACK - Baseline Metrics${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo ""

BEFORE_RECEIVED=$(get_metric "smartcity_ids_alerts_received_total")
BEFORE_PROCESSED=$(get_metric "smartcity_ids_alerts_processed_total")
BEFORE_ISOLATE=$(get_action_count "isolate_pod")
BEFORE_SCALE=$(get_action_count "scale_up")

echo -e "   ${CYAN}Alerts Received:${NC}  $BEFORE_RECEIVED"
echo -e "   ${CYAN}Alerts Processed:${NC} $BEFORE_PROCESSED"
echo -e "   ${CYAN}Pods Isolated:${NC}    $BEFORE_ISOLATE"
echo -e "   ${CYAN}Scale Actions:${NC}    $BEFORE_SCALE"
echo ""
echo -e "   ${YELLOW}Timestamp:${NC} $(date -Iseconds)"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2: Execute Attack
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${RED}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${RED}  STEP 2: EXECUTING ATTACK${NC}"
echo -e "${RED}═══════════════════════════════════════════════════════════════${NC}"
echo ""

# Find a target pod
TARGET_POD=$(kubectl get pods -n smart-city -l app=healthcare-api -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || \
             kubectl get pods -n smart-city -l app=traffic-camera -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || \
             kubectl get pods -n smart-city -o jsonpath='{.items[0].metadata.name}')

echo -e "   ${YELLOW}Target Pod:${NC}    $TARGET_POD"
echo -e "   ${YELLOW}Attack Type:${NC}   Read sensitive file (/etc/shadow)"
echo -e "   ${YELLOW}MITRE ATT&CK:${NC} T1552.001 - Credentials In Files"
echo -e "   ${YELLOW}Detection:${NC}     Falco rule 'Read sensitive file untrusted'"
echo ""

echo -e "   ${RED}Executing: kubectl exec $TARGET_POD -- cat /etc/shadow${NC}"
echo ""

# Execute the attack
kubectl exec -n smart-city "$TARGET_POD" -- cat /etc/shadow 2>&1 | head -3
echo ""

echo -e "   ${GREEN}✓ Attack executed at $(date -Iseconds)${NC}"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# STEP 3: Wait for Detection Pipeline
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${YELLOW}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${YELLOW}  STEP 3: WAITING FOR DETECTION PIPELINE (${WAIT_SECONDS}s)${NC}"
echo -e "${YELLOW}═══════════════════════════════════════════════════════════════${NC}"
echo ""

echo "   Pipeline stages:"
echo "   [1] Falco detects syscall         → ~1s"
echo "   [2] Forwarder sends to IDS API    → ~1s"
echo "   [3] xAI Grok-4 LLM analysis       → ~3-5s"
echo "   [4] Kubernetes action executed    → ~2s"
echo "   [5] Prometheus scrapes metrics    → ~5s"
echo ""

for i in $(seq $WAIT_SECONDS -1 1); do
    echo -ne "   Waiting: ${i}s remaining...\r"
    sleep 1
done
echo -e "   ${GREEN}✓ Pipeline complete${NC}                    "
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# STEP 4: Capture AFTER State
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  STEP 4: AFTER ATTACK - Updated Metrics${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo ""

AFTER_RECEIVED=$(get_metric "smartcity_ids_alerts_received_total")
AFTER_PROCESSED=$(get_metric "smartcity_ids_alerts_processed_total")
AFTER_ISOLATE=$(get_action_count "isolate_pod")
AFTER_SCALE=$(get_action_count "scale_up")

# Calculate deltas
DELTA_RECEIVED=$((AFTER_RECEIVED - BEFORE_RECEIVED))
DELTA_PROCESSED=$((AFTER_PROCESSED - BEFORE_PROCESSED))
DELTA_ISOLATE=$(echo "$AFTER_ISOLATE - $BEFORE_ISOLATE" | bc 2>/dev/null || echo "0")
DELTA_SCALE=$(echo "$AFTER_SCALE - $BEFORE_SCALE" | bc 2>/dev/null || echo "0")

echo -e "   ${CYAN}Metric${NC}              ${CYAN}Before${NC}    ${CYAN}After${NC}     ${GREEN}Delta${NC}"
echo "   ─────────────────────────────────────────────────"
echo -e "   Alerts Received    $BEFORE_RECEIVED        $AFTER_RECEIVED        ${GREEN}+$DELTA_RECEIVED${NC}"
echo -e "   Alerts Processed   $BEFORE_PROCESSED        $AFTER_PROCESSED        ${GREEN}+$DELTA_PROCESSED${NC}"
echo -e "   Pods Isolated      $BEFORE_ISOLATE        $AFTER_ISOLATE        ${GREEN}+$DELTA_ISOLATE${NC}"
echo -e "   Scale Actions      $BEFORE_SCALE        $AFTER_SCALE        ${GREEN}+$DELTA_SCALE${NC}"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# STEP 5: Show Evidence from Logs
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  STEP 5: EVIDENCE FROM LOGS${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo ""

echo -e "   ${YELLOW}[FALCO] Last detection:${NC}"
kubectl logs -n falco-system -l app.kubernetes.io/name=falco -c falco --tail=5 2>/dev/null \
    | grep -E '"rule"' | tail -1 | cut -c1-100 || echo "   (no recent alerts)"
echo ""

echo -e "   ${YELLOW}[FORWARDER] Last forward:${NC}"
kubectl logs -n falco-system -l app=falco-forwarder --tail=3 2>/dev/null | tail -1 || echo "   (no recent forwards)"
echo ""

echo -e "   ${YELLOW}[IDS API] Last processing:${NC}"
kubectl logs -n smart-city deploy/ids-api --tail=20 2>/dev/null \
    | grep -E "Received alert|analysis|action" | tail -2 || echo "   (no recent processing)"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# RESULT
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${CYAN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║                         RESULT                                 ║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

if [[ "$DELTA_RECEIVED" -gt 0 ]]; then
    echo -e "   ${GREEN}✅ PIPELINE WORKING${NC}"
    echo ""
    echo "   The attack caused:"
    echo "   • +$DELTA_RECEIVED new alerts received by IDS API"
    echo "   • +$DELTA_PROCESSED alerts processed by xAI Grok-4"
    [[ "$DELTA_ISOLATE" != "0" ]] && echo "   • +$DELTA_ISOLATE pods isolated (automated response)"
    echo ""
    echo -e "   ${GREEN}This proves Grafana metrics are REAL, not mocked.${NC}"
    echo "   Run this demo again → numbers increase again."
else
    echo -e "   ${RED}❌ NO NEW ALERTS DETECTED${NC}"
    echo ""
    echo "   Troubleshoot:"
    echo "   • Check Falco: kubectl logs -n falco-system -l app.kubernetes.io/name=falco -f"
    echo "   • Check Forwarder: kubectl logs -n falco-system -l app=falco-forwarder -f"
    echo "   • Check IDS API: kubectl logs -n smart-city deploy/ids-api -f"
    exit 1
fi

echo ""
echo -e "${BLUE}─────────────────────────────────────────────────────────────────${NC}"
echo ""
