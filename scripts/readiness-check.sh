#!/bin/bash
# =============================================================================
# Smart City IDS - Readiness Check
# One-command validation for operational readiness.
# Usage: bash scripts/readiness-check.sh [--quick] [--help]
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/script-utils.sh"

init_script "$0" "Readiness Check"

QUICK=0
while [[ $# -gt 0 ]]; do
    case $1 in
        --quick) QUICK=1; shift ;;
        --help)
            cat <<'HELP'
Usage: readiness-check.sh [options]

Options:
  --quick   Skip slow checks (LLM probe, scalability)
  --help    Show this help message
HELP
            exit 0 ;;
        *)       die "Unknown option: $1" ;;
    esac
done

ensure_commands kubectl curl jq
ensure_kubeconfig

API_BASE="${IDS_API_URL:-}"
if [[ -z "$API_BASE" ]]; then
    API_BASE="$(resolve_ids_api_url || true)"
fi

PASSED=0
FAILED=0
WARNED=0

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

check_warn() {
    local msg="$1"
    log_warn "$msg"
    ((WARNED+=1))
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
    "monitoring deploy/suricata-forwarder" \
    "falco-system deploy/falco-forwarder"
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

if kubectl get pods -n falco-system -l app=falco-forwarder --no-headers 2>/dev/null | grep -q Running; then
    check_ok "Falco forwarder pod running"
else
    check_fail "Falco forwarder pod not running"
fi

log_section "4) Prometheus & Grafana"
NODE_IP="$(get_node_ip)"
PROM_PORT="$(get_service_nodeport prometheus monitoring 31106)"
GRAFANA_PORT="$(get_service_nodeport grafana monitoring 30300)"
PROM_BASE=""
GRAFANA_BASE=""

prom_up_is_1() {
    local job="$1"
    local tries="${2:-6}"
    local i
    [[ -n "${PROM_BASE:-}" ]] || return 1
    for i in $(seq 1 "$tries"); do
        if curl -fsS --connect-timeout 2 --max-time 4 \
            "${PROM_BASE}/api/v1/query?query=up%7Bjob%3D%22${job}%22%7D" 2>/dev/null \
            | jq -e '.data.result[0].value[1] == "1"' >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
    done
    return 1
}

if curl -fsS --connect-timeout 2 --max-time 4 "http://${NODE_IP}:${PROM_PORT}/-/healthy" >/dev/null 2>&1; then
    PROM_BASE="http://${NODE_IP}:${PROM_PORT}"
    check_ok "Prometheus healthy (NodePort)"
elif curl -fsS --connect-timeout 2 --max-time 4 "http://localhost:9090/-/healthy" >/dev/null 2>&1; then
    PROM_BASE="http://localhost:9090"
    check_ok "Prometheus healthy (local port-forward)"
else
    if [[ $QUICK -eq 1 ]]; then
        check_warn "Prometheus not reachable (NodePort/local)"
    else
        check_fail "Prometheus not reachable (NodePort/local)"
    fi
fi

if curl -fsS --connect-timeout 2 --max-time 4 "http://${NODE_IP}:${GRAFANA_PORT}/api/health" >/dev/null 2>&1; then
    GRAFANA_BASE="http://${NODE_IP}:${GRAFANA_PORT}"
    check_ok "Grafana healthy (NodePort)"
elif curl -fsS --connect-timeout 2 --max-time 4 "http://localhost:3000/api/health" >/dev/null 2>&1; then
    GRAFANA_BASE="http://localhost:3000"
    check_ok "Grafana healthy (local port-forward)"
else
    if [[ $QUICK -eq 1 ]]; then
        check_warn "Grafana not reachable (NodePort/local)"
    else
        check_fail "Grafana not reachable (NodePort/local)"
    fi
fi

if prom_up_is_1 "smart-city-ids"; then
    check_ok "Prometheus scraping IDS API (up=1)"
else
    if [[ $QUICK -eq 1 ]]; then
        check_warn "Prometheus scrape missing for IDS API (up!=1)"
    else
        check_fail "Prometheus scrape missing for IDS API (up!=1)"
    fi
fi

if prom_up_is_1 "suricata-forwarder"; then
    check_ok "Prometheus scraping Suricata forwarder (up=1)"
else
    if [[ $QUICK -eq 1 ]]; then
        check_warn "Prometheus scrape missing for Suricata forwarder (up!=1)"
    else
        check_fail "Prometheus scrape missing for Suricata forwarder (up!=1)"
    fi
fi

if prom_up_is_1 "falco-forwarder"; then
    check_ok "Prometheus scraping Falco forwarder (up=1)"
else
    if [[ $QUICK -eq 1 ]]; then
        check_warn "Prometheus scrape missing for Falco forwarder (up!=1)"
    else
        check_fail "Prometheus scrape missing for Falco forwarder (up!=1)"
    fi
fi

log_section "5) API Health and Auth"
IDS_API_SVC_PORT=8000
HEALTH_JSON=$(kubectl exec -n smart-city deploy/ids-api -- curl -fsS "http://localhost:${IDS_API_SVC_PORT}/health" 2>/dev/null || true)

if [[ -n "$HEALTH_JSON" ]] && echo "$HEALTH_JSON" | jq -e '.status == "healthy"' >/dev/null 2>&1; then
    check_ok "IDS API health endpoint is healthy"
else
    check_fail "IDS API health endpoint check failed"
fi

# Database connectivity check (via health endpoint component field)
DB_STATUS=""
if [[ -n "$HEALTH_JSON" ]]; then
    DB_STATUS=$(echo "$HEALTH_JSON" | jq -r '.components.database // empty' 2>/dev/null || true)
fi
if [[ "$DB_STATUS" == "postgresql" ]]; then
    check_ok "PostgreSQL database connected (components.database=postgresql)"
else
    # Fallback: direct psql ping
    if kubectl exec -n smart-city deploy/postgres -- psql -U postgres -d smartcity_ids -c "SELECT 1" >/dev/null 2>&1; then
        check_ok "PostgreSQL database connected (psql ping)"
    else
        check_fail "PostgreSQL database unreachable (status=${DB_STATUS:-unknown})"
    fi
fi

# LLM provider check (at least 1 configured and not auth_failed)
LLM_CONFIGURED_COUNT=""
if [[ -n "$HEALTH_JSON" ]]; then
    LLM_CONFIGURED_COUNT=$(echo "$HEALTH_JSON" | jq '.llm_provider_count // 0' 2>/dev/null || echo "0")
fi
if [[ "${LLM_CONFIGURED_COUNT:-0}" -ge 1 ]]; then
    check_ok "LLM providers configured: ${LLM_CONFIGURED_COUNT} provider(s) available"
else
    check_fail "No LLM providers configured — alerts will be queued/degraded until keys are restored"
fi

LOGIN_JSON=""
for _ in 1 2 3; do
    LOGIN_JSON=$(kubectl exec -n smart-city deploy/ids-api -- curl -fsS -X POST "http://localhost:${IDS_API_SVC_PORT}/api/auth/login" \
        -H "Content-Type: application/json" \
        -d '{"username":"admin","password":"admin"}' 2>/dev/null || true)
    if [[ -n "$LOGIN_JSON" ]]; then
        break
    fi
    sleep 2
done
TOKEN=$(echo "$LOGIN_JSON" | jq -r '.access_token // empty' 2>/dev/null || true)

if [[ -n "$TOKEN" ]]; then
    check_ok "Admin login works (admin/admin)"
else
    check_fail "Admin login failed (expected admin/admin)"
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
    log_section "6) Recent Alert Activity"
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

    log_section "7) BYO IoT Device Ingest (REST)"
    local_ingest_base="${API_BASE:-}"
    if [[ -z "$local_ingest_base" ]]; then
        IDS_PORT="$(get_service_nodeport ids-api-service smart-city 30800)"
        local_ingest_base="http://${NODE_IP}:${IDS_PORT}"
    fi
    BYO_JSON=$(curl -fsS -X POST "${local_ingest_base}/api/iot/sensor" \
        -H "Content-Type: application/json" \
        -d '{"device_id":"readiness-check-device","device_type":"external","event_type":"heartbeat","value":{"status":"alive"}}' \
        2>/dev/null || true)

    if [[ -n "$BYO_JSON" ]] && echo "$BYO_JSON" | jq -e '.status == "received"' >/dev/null 2>&1; then
        check_ok "IoT REST ingest works (/api/iot/sensor)"
    else
        check_fail "IoT REST ingest failed (/api/iot/sensor)"
    fi
fi

log_section "Summary"
echo "Passed: $PASSED"
echo "Warnings: $WARNED"
echo "Failed: $FAILED"
echo ""

if [[ $FAILED -gt 0 ]]; then
    echo -e "\033[0;31m  ╔═══════════════════════════════╗\033[0m"
    echo -e "\033[0;31m  ║   SYSTEM: NOT READY           ║\033[0m"
    echo -e "\033[0;31m  ╚═══════════════════════════════╝\033[0m"
    echo ""
    echo "Reasons: $FAILED check(s) failed. Review items above marked with [ERROR]."
    echo ""
    die "Readiness check failed ($FAILED issue(s))"
fi

echo -e "\033[0;32m  ╔═══════════════════════════════╗\033[0m"
echo -e "\033[0;32m  ║   SYSTEM: READY               ║\033[0m"
echo -e "\033[0;32m  ╚═══════════════════════════════╝\033[0m"
echo ""
log_info "All $PASSED checks passed. System is ready for operation/evaluation."
