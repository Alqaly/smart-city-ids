#!/bin/bash
# =============================================================================
# Smart City IDS - Comprehensive Test Suite
# Tests all components end-to-end with verbose output
# =============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/script-utils.sh"
set +e

# Color variables are already defined (readonly) in script-utils.sh.
# Only define missing ones locally to avoid readonly collisions.
: "${BLUE:=\033[0;34m}"
: "${CYAN:=\033[0;36m}"
: "${NC:=\033[0m}"

VERBOSE=0
if [[ "${1:-}" == "--verbose" || "${1:-}" == "-v" ]]; then
    VERBOSE=1
fi

log_section() {
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════════${NC}"
}

log_step() {
    echo -e "${CYAN}[TEST]${NC} $1"
}

log_pass() {
    echo -e "${GREEN}✓ PASS${NC} $1"
}

log_fail() {
    echo -e "${RED}✗ FAIL${NC} $1"
}

log_info() {
    echo -e "${YELLOW}ℹ INFO${NC} $1"
}

# Test counters
TESTS_PASSED=0
TESTS_FAILED=0

run_test() {
    local name="$1"
    local command="$2"
    log_step "$name"
    
    if eval "$command" >/dev/null 2>&1; then
        log_pass "$name"
        ((++TESTS_PASSED))
        return 0
    else
        log_fail "$name"
        ((++TESTS_FAILED))
        return 1
    fi
}

# =============================================================================
# MAIN TESTS
# =============================================================================

echo ""
echo -e "${CYAN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║${NC}           ${YELLOW}SMART CITY IDS - COMPREHENSIVE TEST SUITE${NC}           ${CYAN}║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

API_BASE="$(resolve_ids_api_url || true)"
if [[ -z "$API_BASE" ]]; then
    log_fail "Could not auto-detect IDS API URL"
    exit 1
fi
AUTH_TOKEN="$(ids_login_token "$API_BASE" admin admin)"

auth_curl_cmd() {
    local path="$1"
    if [[ -n "${AUTH_TOKEN:-}" ]]; then
        echo "curl -sf '${API_BASE}${path}' -H 'Authorization: Bearer ${AUTH_TOKEN}'"
    else
        echo "curl -sf '${API_BASE}${path}'"
    fi
}

log_info "Using IDS API: $API_BASE"
if [[ -n "$AUTH_TOKEN" ]]; then
    log_pass "Admin login works (admin/admin)"
    ((++TESTS_PASSED))
else
    log_fail "Admin login failed (admin/admin)"
    ((++TESTS_FAILED))
fi

# Test 1: Kubernetes Cluster
log_section "1. KUBERNETES CLUSTER"
run_test "Cluster API accessible" "kubectl cluster-info"
run_test "kubectl get nodes works" "kubectl get nodes"

if [[ $VERBOSE -eq 1 ]]; then
    log_info "Node details:"
    kubectl get nodes -o wide 2>/dev/null || true
fi

# Test 2: Namespaces
log_section "2. NAMESPACES"
for ns in smart-city monitoring falco-system; do
    run_test "Namespace $ns exists" "kubectl get namespace $ns"
done

# Test 3: Core Pods
log_section "3. CORE PODS"
CORE_PODS=(
    "smart-city:ids-api"
    "smart-city:postgres"
    "smart-city:traffic-camera"
    "smart-city:healthcare-api"
    "smart-city:parking-system"
    "smart-city:mqtt-broker"
    "monitoring:prometheus"
    "monitoring:grafana"
    "monitoring:suricata"
    "falco-system:falco"
)

for pod_spec in "${CORE_PODS[@]}"; do
    IFS=':' read -r ns name <<< "$pod_spec"
    run_test "Pod $ns/$name running" "kubectl get pods -n $ns | grep '^$name.*Running'"
done

if [[ $VERBOSE -eq 1 ]]; then
    log_info "All pods:"
    kubectl get pods -A 2>/dev/null | head -30 || true
fi

# Test 4: Services
log_section "4. SERVICES"
run_test "IDS API service exists" "kubectl get svc ids-api-service -n smart-city"
run_test "Grafana service exists" "kubectl get svc grafana -n monitoring"
run_test "Prometheus service exists" "kubectl get svc prometheus -n monitoring"

# Test 5: API Endpoints
log_section "5. API ENDPOINTS"
run_test "Health endpoint" "curl -sf ${API_BASE}/health"
run_test "Metrics endpoint" "curl -sf ${API_BASE}/api/metrics"
run_test "Alerts endpoint" "curl -sf '${API_BASE}/api/alerts?limit=1'"
run_test "IoT devices endpoint" "curl -sf ${API_BASE}/api/iot/devices"
run_test "Governance endpoint" "$(auth_curl_cmd '/api/governance/status')"
run_test "LLM diagnostics" "curl -sf ${API_BASE}/api/llm/diagnostics"
run_test "LLM usage metrics (today)" "curl -sf '${API_BASE}/api/metrics/llm-usage?window=today'"
run_test "Dashboard UI" "tmp=\$(curl -sf ${API_BASE}/ui) && grep -q 'Smart City IDS' <<<\"\$tmp\""

if [[ $VERBOSE -eq 1 ]]; then
    log_info "Health status:"
    curl -s "${API_BASE}/health" 2>/dev/null | python3 -m json.tool 2>/dev/null || true
fi

# Test 6: Data Validation
log_section "6. DATA VALIDATION"

# Check alert count
ALERT_COUNT=$(curl -s "${API_BASE}/api/metrics" 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('total_alerts',0))" || echo 0)
if [[ $ALERT_COUNT -gt 0 ]]; then
    log_pass "Alert count: $ALERT_COUNT"
    ((++TESTS_PASSED))
else
    log_fail "No alerts in system"
    ((++TESTS_FAILED))
fi

# Check IoT count using the hybrid inventory view
IOT_JSON="$(curl -s "${API_BASE}/api/iot/devices" 2>/dev/null || echo '{}')"
IOT_TOTAL=$(echo "$IOT_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('total',0))" 2>/dev/null || echo 0)
IOT_LOGICAL=$(echo "$IOT_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('logical_total',0))" 2>/dev/null || echo 0)
IOT_POD_BACKED=$(echo "$IOT_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('pod_backed_total',0))" 2>/dev/null || echo 0)
IOT_MODE=$(echo "$IOT_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('counting_mode','unknown'))" 2>/dev/null || echo unknown)
if [[ "$IOT_TOTAL" -gt 0 ]]; then
    log_pass "IoT device inventory: total=$IOT_TOTAL logical=$IOT_LOGICAL pod_backed=$IOT_POD_BACKED mode=$IOT_MODE"
    ((++TESTS_PASSED))
else
    log_fail "IoT inventory unreadable or empty: total=$IOT_TOTAL mode=$IOT_MODE"
    ((++TESTS_FAILED))
fi

# Check LLM providers
LLM_COUNT=$(curl -s "${API_BASE}/health" 2>/dev/null | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('components',{}).get('llm_providers',{})))" || echo 0)
if [[ $LLM_COUNT -ge 1 ]]; then
    log_pass "LLM providers configured: $LLM_COUNT"
    ((++TESTS_PASSED))
else
    log_fail "LLM providers configured: $LLM_COUNT"
    ((++TESTS_FAILED))
fi

# Test 7: HPA
log_section "7. HORIZONTAL POD AUTOSCALER"
run_test "ids-api HPA exists" "kubectl get hpa ids-api-hpa -n smart-city"
run_test "traffic-camera HPA exists" "kubectl get hpa traffic-camera-hpa -n smart-city"
run_test "healthcare-api HPA exists" "kubectl get hpa healthcare-api-hpa -n smart-city"
run_test "parking-system HPA exists" "kubectl get hpa parking-system-hpa -n smart-city"

if [[ $VERBOSE -eq 1 ]]; then
    log_info "HPA status:"
    kubectl get hpa -A 2>/dev/null || true
fi

# Test 8: ConfigMaps
log_section "8. CONFIGMAPS"
run_test "ids-app-code ConfigMap" "kubectl get configmap ids-app-code -n smart-city"
run_test "ids-app-static ConfigMap" "kubectl get configmap ids-app-static -n smart-city"

# Test 9: Secrets
log_section "9. SECRETS"
run_test "ids-secrets exists" "kubectl get secret ids-secrets -n smart-city"

# Test 10: Network Policies
log_section "10. NETWORK POLICIES"
run_test "Network policies exist" "kubectl get networkpolicy -n smart-city"

# =============================================================================
# SUMMARY
# =============================================================================

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  TEST SUMMARY${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════${NC}"
echo ""

echo -e "Tests Passed: ${GREEN}$TESTS_PASSED${NC}"
echo -e "Tests Failed: ${RED}$TESTS_FAILED${NC}"
echo ""

if [[ $TESTS_FAILED -eq 0 ]]; then
    echo -e "${GREEN}╔════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║${NC}              ALL TESTS PASSED - SYSTEM READY!                ${GREEN}║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "Dashboard: ${CYAN}${API_BASE}/ui${NC}"
    exit 0
else
    echo -e "${RED}╔════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║${NC}           SOME TESTS FAILED - REVIEW OUTPUT ABOVE            ${RED}║${NC}"
    echo -e "${RED}╚════════════════════════════════════════════════════════════════╝${NC}"
    exit 1
fi
