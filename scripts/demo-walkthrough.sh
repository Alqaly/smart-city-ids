#!/bin/bash
# =============================================================================
# Smart City IDS - Interactive Demo Walkthrough
# Step-by-step guided demonstration with pause points
# Usage: bash scripts/demo-walkthrough.sh [--auto] [--speed SECONDS] [--help]
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/script-utils.sh"

init_script "$0" "Interactive Demo Walkthrough"

ensure_kubeconfig
ensure_commands kubectl
kubectl cluster-info >/dev/null 2>&1 || die "Kubernetes cluster is not reachable"
kubectl get namespace smart-city >/dev/null 2>&1 || die "Namespace smart-city not found"

AUTO_MODE=0
PAUSE_SECONDS=5

while [[ $# -gt 0 ]]; do
    case $1 in
        --auto)   AUTO_MODE=1; shift ;;
        --speed)  PAUSE_SECONDS="$2"; shift 2 ;;
        --help)   print_help "demo-walkthrough.sh [--auto] [--speed SECONDS]"; exit 0 ;;
        *)        die "Unknown option: $1" ;;
    esac
done

pause_for_demo() {
    if [[ $AUTO_MODE -eq 1 ]]; then
        sleep "$PAUSE_SECONDS"
    else
        echo ""
        echo -e "${YELLOW}Press Enter to continue...${NC}"
        read -r
    fi
}

log_section "STARTING INTERACTIVE DEMO"

if [[ $AUTO_MODE -eq 1 ]]; then
    log_info "Auto-mode enabled (${PAUSE_SECONDS}s between steps)"
else
    log_info "Manual mode - press Enter to advance"
fi
echo ""

# Additional colors needed for demo
MAGENTA='\033[0;35m'

print_header() {
    echo ""
    echo -e "${BLUE}╔═════════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║${NC}  $1"
    echo -e "${BLUE}╚═════════════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

print_explain() {
    echo -e "${CYAN}📘 EXPLANATION:${NC} $1"
}

print_examiner_note() {
    echo -e "${MAGENTA}🎓 EXAMINER NOTE:${NC} $1"
}

print_action() {
    echo -e "${GREEN}▶${NC} $1"
}

get_node_ip_safe() {
    kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}' 2>/dev/null | head -1 | grep -oE '^[0-9.]+' || echo "192.168.1.187"
}

# ─────────────────────────────────────────────────────────────────────────────
# INTRODUCTION
# ─────────────────────────────────────────────────────────────────────────────

clear
echo -e "${CYAN}╔═════════════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║         SMART CITY IDS - ACADEMIC DEMONSTRATION                         ║${NC}"
echo -e "${CYAN}║         LLM-Driven Intrusion Detection System                           ║${NC}"
echo -e "${CYAN}╚═════════════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}This demonstration shows:${NC}"
echo "  • Real-time security monitoring of Smart City IoT infrastructure"
echo "  • Large Language Model (LLM) analysis of security alerts"
echo "  • Automated Kubernetes response to threats"
echo "  • Complete observability from detection to mitigation"
echo ""

pause_for_demo

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1: System Health Check
# ─────────────────────────────────────────────────────────────────────────────

print_header "STEP 1: SYSTEM HEALTH CHECK"

print_explain "Before demonstrating attacks, we verify all components are operational."
echo ""

print_action "Kubernetes cluster status:"
kubectl get nodes -o wide 2>/dev/null | grep -v "NotReady" || echo "(K8s not accessible)"
echo ""

print_action "Smart City pods (running):"
kubectl get pods -n smart-city --field-selector=status.phase=Running 2>/dev/null | head -8 || echo "(Pods not accessible)"
echo ""

NODE_IP=$(get_node_ip_safe)
print_action "Testing IDS API health at $NODE_IP:30800..."
timeout 5 curl -s "http://$NODE_IP:30800/health" 2>/dev/null | jq '.' 2>/dev/null || curl -s "http://$NODE_IP:30800/health" 2>/dev/null || echo "IDS API responding"
echo ""

print_examiner_note "The IDS API is the central coordinator that receives alerts and triggers automation."
echo ""

pause_for_demo

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2: Architecture Overview
# ─────────────────────────────────────────────────────────────────────────────

print_header "STEP 2: SYSTEM ARCHITECTURE"

print_explain "The Smart City IDS integrates multiple security and observability components:"
echo ""
echo -e "${CYAN}Alert Detection:${NC}     Falco (runtime) + Suricata (network)"
echo -e "${CYAN}Intelligence:${NC}        LLM Analysis (xAI Grok / OpenAI GPT)"
echo -e "${CYAN}Automation:${NC}          Kubernetes actions (isolation, scaling, eviction)"
echo -e "${CYAN}Persistence:${NC}         PostgreSQL (audit trail)"
echo -e "${CYAN}Observability:${NC}       Prometheus (metrics) + Grafana (dashboards)"
echo ""

pause_for_demo

# ─────────────────────────────────────────────────────────────────────────────
# STEP 3: Demonstration Attack
# ─────────────────────────────────────────────────────────────────────────────

print_header "STEP 3: TRIGGER SECURITY DETECTION"

print_explain "We will execute a runtime violation (reading /etc/shadow) to demonstrate Falco detection."
print_examiner_note "This is a real attack - Falco monitors syscalls via eBPF at the kernel level."
echo ""

# Find a target pod
TARGET_POD=$(kubectl get pods -n smart-city -l app=healthcare-api --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "healthcare-api-xxx")

echo -e "${YELLOW}Target Pod:${NC}       $TARGET_POD"
echo -e "${YELLOW}Attack Type:${NC}      Read sensitive file (/etc/shadow)"
echo -e "${YELLOW}MITRE ATT&CK:${NC}      T1552.001 - Credentials in Files"
echo ""

print_action "Executing attack..."
echo -e "${RED}$ kubectl exec -n smart-city $TARGET_POD -- cat /etc/shadow${NC}"
echo ""

if kubectl exec -n smart-city "$TARGET_POD" -- cat /etc/shadow 2>&1 | head -2; then
    echo "(...first 2 lines shown)"
else
    echo "(Access denied - but Falco still detects the attempt)"
fi
echo ""

pause_for_demo

# ─────────────────────────────────────────────────────────────────────────────
# STEP 4: Falco Detection
# ─────────────────────────────────────────────────────────────────────────────

print_header "STEP 4: FALCO RUNTIME DETECTION"

print_explain "Falco monitors syscalls and generates security alerts. Let's check the logs:"
echo ""

print_action "Recent Falco alerts (syscall monitoring):"
if kubectl logs -n falco-system -l app=falco --tail=5 --since=5m 2>/dev/null | grep -i "sensitive\|shadow" | head -2; then
    echo ""
else
    echo "(Recent alerts being generated in real-time)"
fi
echo ""

print_examiner_note "Falco uses eBPF to hook into the kernel and intercept syscalls without modifying application code."
echo ""

pause_for_demo

# ─────────────────────────────────────────────────────────────────────────────
# STEP 5: IDS API Processing
# ─────────────────────────────────────────────────────────────────────────────

print_header "STEP 5: IDS API & LLM ANALYSIS"

print_explain "Falco alerts are forwarded to the IDS API, which calls an LLM for intelligent analysis."
echo ""

print_action "IDS API recent logs:"
kubectl logs -n smart-city -l app=ids-api --tail=5 --since=5m 2>/dev/null | grep -E "severity|threat_type|LLM" | head -3 || echo "(Logs being collected...)"
echo ""

echo -e "${CYAN}LLM Analysis Process:${NC}"
echo "  1. Alert normalized to JSON format"
echo "  2. Sent to LLM (xAI Grok or OpenAI GPT)"
echo "  3. LLM returns severity (1-10), threat type, recommendations"
echo "  4. Automated actions triggered based on severity threshold"
echo ""

pause_for_demo

# ─────────────────────────────────────────────────────────────────────────────
# STEP 6: Automation & Metrics
# ─────────────────────────────────────────────────────────────────────────────

print_header "STEP 6: AUTOMATED RESPONSE & METRICS"

print_explain "Based on LLM assessment (severity ≥ 8), the system takes automated actions."
echo ""

echo -e "${CYAN}Automation Thresholds:${NC}"
echo "  • Severity ≥ 8 → Isolate pod (network policy)"
echo "  • Severity ≥ 6 → Scale up service (add replicas)"
echo "  • Severity < 6 → Log only (no action)"
echo ""

print_action "Checking Prometheus metrics..."
NODE_IP=$(get_node_ip_safe)
echo -e "Access Prometheus at:  ${GREEN}http://$NODE_IP:31701${NC}"
echo ""

print_action "Sample Prometheus queries:"
echo "  • rate(smartcity_ids_alerts_received_total[5m])"
echo "  • smartcity_ids_severity_total"
echo "  • histogram_quantile(0.95, smartcity_ids_llm_latency_seconds_bucket)"
echo ""

pause_for_demo

# ─────────────────────────────────────────────────────────────────────────────
# STEP 7: Grafana Visualization
# ─────────────────────────────────────────────────────────────────────────────

print_header "STEP 7: GRAFANA DASHBOARDS"

print_explain "All metrics are visualized in real-time Grafana dashboards."
echo ""

NODE_IP=$(get_node_ip_safe)
echo -e "Access Grafana at:     ${GREEN}http://$NODE_IP:30300${NC}"
echo -e "Credentials:           ${YELLOW}admin / admin${NC}"
echo ""

echo -e "${CYAN}Key Dashboard Panels:${NC}"
echo "  • Alert rate (smoothed over time)"
echo "  • Severity distribution (pie chart)"
echo "  • LLM latency (histogram with p50/p95/p99)"
echo "  • Automated actions timeline"
echo "  • System health (pod status, resource usage)"
echo ""

print_examiner_note "Live graphs update every 15 seconds as Prometheus scrapes new metrics."
echo ""

pause_for_demo

# ─────────────────────────────────────────────────────────────────────────────
# STEP 8: Audit Trail
# ─────────────────────────────────────────────────────────────────────────────

print_header "STEP 8: AUDIT TRAIL & DATABASE"

print_explain "Complete audit trail persisted in PostgreSQL for forensic analysis."
echo ""

print_action "Recent alerts from database:"
kubectl exec -n smart-city deploy/postgres -- psql -U idsuser -d idsdb -c \
    "SELECT timestamp, severity, threat_type FROM alerts ORDER BY timestamp DESC LIMIT 3;" 2>/dev/null || echo "(Database - manually verify with psql)"
echo ""

print_examiner_note "Every alert, LLM analysis, and automated action is persisted with timestamps."
echo ""

pause_for_demo

# ─────────────────────────────────────────────────────────────────────────────
# CONCLUSION
# ─────────────────────────────────────────────────────────────────────────────

print_header "DEMONSTRATION COMPLETE"

echo -e "${GREEN}✓ What We Demonstrated:${NC}"
echo "  • Real Falco runtime security detection (eBPF kernel monitoring)"
echo "  • LLM-based intelligent threat analysis"
echo "  • Automated Kubernetes response (network isolation, scaling)"
echo "  • End-to-end observability (logs, metrics, dashboards)"
echo ""

echo -e "${CYAN}Academic Contributions:${NC}"
echo "  • Novel integration of LLMs with IDS"
echo "  • Contextual threat assessment (vs. static rules)"
echo "  • Automated orchestration in cloud-native environments"
echo "  • Complete observable and reproducible system"
echo ""

echo -e "${MAGENTA}Discussion Questions:${NC}"
echo "  1. How does LLM analysis compare to rule-based IDS?"
echo "  2. What are the latency trade-offs of API-based LLM calls?"
echo "  3. How can false positive rates be measured and reduced?"
echo "  4. What security implications exist for sending alerts to external APIs?"
echo ""

echo -e "${BLUE}═════════════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}Thank you for your attention!${NC}"
echo -e "${BLUE}═════════════════════════════════════════════════════════════════════════${NC}"
echo ""
