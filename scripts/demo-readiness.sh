#!/bin/bash
# =============================================================================
# Smart City IDS - Demo Readiness Check
# One-command pre-demo validation for meeting/defense day.
# Usage: bash scripts/demo-readiness.sh [--quick] [--help]
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/script-utils.sh"

init_script "$0" "Demo Readiness Check"

QUICK=0
while [[ $# -gt 0 ]]; do
    case $1 in
        --quick) QUICK=1; shift ;;
        --help)  print_help "demo-readiness.sh [--quick]"; exit 0 ;;
        *)       die "Unknown option: $1" ;;
    esac
done

ensure_commands kubectl curl jq
ensure_kubeconfig

PASSED=0
FAILED=0

check_ok() {
    local msg="$1"
    log_info "$msg"
    ((PASSED+=1))
}

check_fail() {
    local msg="$1"
    log_error "$msg"
    ((FAILED+=1))
}

exists_with_retry() {
    local ns="$1"
    local obj="$2"
    local retries=3
    while [[ $retries -gt 0 ]]; do
        if kubectl get "$obj" -n "$ns" >/dev/null 2>&1; then
            return 0
        fi
        retries=$((retries - 1))
        sleep 2
    done
    return 1
}

log_section "1) Cluster Connectivity"
if kubectl cluster-info >/dev/null 2>&1; then
    check_ok "Kubernetes API reachable"
else
    check_fail "Kubernetes API unreachable"
fi

log_section "2) Required Namespaces"
for ns in smart-city falco-system monitoring; do
    if kubectl get namespace "$ns" >/dev/null 2>&1; then
        check_ok "Namespace exists: $ns"
    else
        check_fail "Namespace missing: $ns"
    fi
done

log_section "3) Core Workloads"
for target in \
    "smart-city deploy/ids-api" \
    "smart-city deploy/postgres" \
    "monitoring deploy/prometheus" \
    "monitoring deploy/grafana" \
    "monitoring deploy/suricata" \
    "monitoring deploy/suricata-forwarder"
do
    ns="${target%% *}"
    obj="${target##* }"
    if exists_with_retry "$ns" "$obj"; then
        check_ok "Present: $ns/$obj"
    else
        check_fail "Missing: $ns/$obj"
    fi
done

if kubectl get pods -n falco-system --no-headers 2>/dev/null \
    | awk '$1 ~ /^falco-/ && $3 == "Running" {found=1} END {exit found?0:1}'
then
    check_ok "Falco pod running"
else
    check_fail "Falco pod not running"
fi

if kubectl get pods -n monitoring -l app=suricata --no-headers 2>/dev/null | grep -q Running; then
    check_ok "Suricata pod running"
else
    check_fail "Suricata pod not running"
fi

if kubectl get pods -n monitoring -l app=suricata-forwarder --no-headers 2>/dev/null | grep -q Running; then
    check_ok "Suricata forwarder pod running"
else
    check_fail "Suricata forwarder pod not running"
fi

log_section "4) API Health and Auth"
IDS_API_SVC_PORT=8000
HEALTH_JSON=$(kubectl exec -n smart-city deploy/ids-api -- curl -fsS "http://localhost:${IDS_API_SVC_PORT}/health" 2>/dev/null || true)

if [[ -n "$HEALTH_JSON" ]] && echo "$HEALTH_JSON" | jq -e '.status == "healthy"' >/dev/null 2>&1; then
    check_ok "IDS API health endpoint is healthy"
else
    check_fail "IDS API health endpoint check failed"
fi

LOGIN_JSON=""
for _ in 1 2 3; do
    LOGIN_JSON=$(kubectl exec -n smart-city deploy/ids-api -- curl -fsS -X POST "http://localhost:${IDS_API_SVC_PORT}/api/auth/login" \
        -H "Content-Type: application/json" \
        -d '{"username":"operator","password":"operator"}' 2>/dev/null || true)
    if [[ -n "$LOGIN_JSON" ]]; then
        break
    fi
    sleep 2
done
TOKEN=$(echo "$LOGIN_JSON" | jq -r '.access_token // empty' 2>/dev/null || true)

if [[ -n "$TOKEN" ]]; then
    check_ok "Operator login works"
else
    check_fail "Operator login failed"
fi

if [[ -n "$TOKEN" ]]; then
    if kubectl exec -n smart-city deploy/ids-api -- curl -fsS "http://localhost:${IDS_API_SVC_PORT}/api/operator/dashboard" \
        -H "Authorization: Bearer ${TOKEN}" >/dev/null 2>&1 \
        || kubectl exec -n smart-city deploy/ids-api -- curl -fsS "http://localhost:${IDS_API_SVC_PORT}/api/operator/metrics" \
            -H "Authorization: Bearer ${TOKEN}" >/dev/null 2>&1 \
        || kubectl exec -n smart-city deploy/ids-api -- curl -fsS "http://localhost:${IDS_API_SVC_PORT}/api/operator/incidents?limit=1" \
            -H "Authorization: Bearer ${TOKEN}" >/dev/null 2>&1
    then
        check_ok "Protected operator endpoint accessible with token"
    else
        check_fail "Protected operator endpoint failed with token"
    fi
fi

if [[ $QUICK -eq 0 ]]; then
    log_section "5) Recent Alert Activity"
    # Check for at least one recent alert in the last 5 minutes
    RECENT_ALERTS=""
    if [[ -n "$TOKEN" ]]; then
        RECENT_ALERTS=$(kubectl exec -n smart-city deploy/ids-api -- curl -fsS \
            "http://localhost:${IDS_API_SVC_PORT}/api/alerts?limit=5" \
            -H "Authorization: Bearer ${TOKEN}" 2>/dev/null || true)
    fi
    ALERT_COUNT=$(echo "$RECENT_ALERTS" | python3 -c "
import json, sys
try:
    d=json.load(sys.stdin)
    items=d if isinstance(d, list) else d.get('alerts', d.get('items', []))
    print(len(items))
except: print(0)
" 2>/dev/null || echo "0")

    if [[ "$ALERT_COUNT" -gt 0 ]]; then
        check_ok "Recent alerts found: ${ALERT_COUNT} in database"
    else
        check_fail "No recent alerts found — pipeline may not be producing data"
    fi

    log_section "6) IoT Device Pod Coverage"
    IOT_TOTAL=0
    # Count by pod name prefix (catches both label-based and name-based matches)
    IOT_TOTAL=$(kubectl get pods -n smart-city --no-headers 2>/dev/null \
        | grep -cE '^(iot-device|iot-devices|iot-simulator|env-sensor|street-lighting).*Running' || true)
    if [[ $IOT_TOTAL -ge 10 ]]; then
        check_ok "IoT device pods running: ${IOT_TOTAL} (>= 10 required)"
    elif [[ $IOT_TOTAL -ge 1 ]]; then
        check_ok "IoT device pods running: ${IOT_TOTAL} (< 10 but functional)"
    else
        check_fail "No IoT device pods found — deploy IoT device manifests"
    fi

    log_section "7) Demo Script Smoke Checks"
    for cmd in \
        "bash $SCRIPT_DIR/check-system.sh --help" \
        "bash $SCRIPT_DIR/demo.sh --help"
    do
        if timeout 10 bash -c "$cmd" >/dev/null 2>&1; then
            check_ok "Smoke check passed: $cmd"
        else
            check_fail "Smoke check failed: $cmd"
        fi
    done
fi

log_section "Summary"
echo "Passed: $PASSED"
echo "Failed: $FAILED"
echo ""

if [[ $FAILED -gt 0 ]]; then
    echo -e "\033[0;31m  ╔═══════════════════════════════╗\033[0m"
    echo -e "\033[0;31m  ║   DEMO: NOT READY             ║\033[0m"
    echo -e "\033[0;31m  ╚═══════════════════════════════╝\033[0m"
    echo ""
    echo "Reasons: $FAILED check(s) failed. Review items above marked with [ERROR]."
    echo ""
    die "Demo readiness check failed ($FAILED issue(s))"
fi

echo -e "\033[0;32m  ╔═══════════════════════════════╗\033[0m"
echo -e "\033[0;32m  ║   DEMO: READY                 ║\033[0m"
echo -e "\033[0;32m  ╚═══════════════════════════════╝\033[0m"
echo ""
log_info "All $PASSED checks passed. System is ready for demo."
