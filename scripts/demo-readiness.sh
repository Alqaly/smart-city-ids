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
IDS_API_SVC_PORT=$(kubectl get svc ids-api-service -n smart-city -o jsonpath='{.spec.ports[0].port}' 2>/dev/null || echo "8000")
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
    log_section "5) Demo Script Smoke Checks"
    for cmd in \
        "bash $SCRIPT_DIR/check-system.sh --help" \
        "bash $SCRIPT_DIR/demo.sh --help" \
        "bash $SCRIPT_DIR/demos/phase4-run-smart-city-attacks.sh 1 >/dev/null"
    do
        if eval "$cmd" >/dev/null 2>&1; then
            check_ok "Smoke check passed: $cmd"
        else
            check_fail "Smoke check failed: $cmd"
        fi
    done
fi

log_section "Summary"
echo "Passed: $PASSED"
echo "Failed: $FAILED"

if [[ $FAILED -gt 0 ]]; then
    die "Demo readiness check failed ($FAILED issue(s))"
fi

log_info "Demo readiness check passed. System is ready for tomorrow."
