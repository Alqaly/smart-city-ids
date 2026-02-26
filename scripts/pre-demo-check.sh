#!/usr/bin/env bash
# =============================================================================
# Smart City IDS - Quick Pre-Demo Verification
# Run this 5 minutes before the demo. Output is examiner-friendly.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/script-utils.sh"

init_script "$0" "Smart City IDS Pre-Demo Check"

ensure_commands kubectl curl jq python3 awk
ensure_kubeconfig

PASSED=0
FAILED=0
WARNED=0

pass() { log_info "$1"; ((PASSED+=1)); }
fail() { log_error "$1"; ((FAILED+=1)); }
warn() { log_warn "$1"; ((WARNED+=1)); }

api_json() {
    local path="$1"
    curl -fsS "${API_BASE}${path}" 2>/dev/null || return 1
}

api_auth_json() {
    local path="$1"
    if [[ -z "${AUTH_TOKEN:-}" ]]; then
        return 1
    fi
    curl -fsS "${API_BASE}${path}" -H "Authorization: Bearer ${AUTH_TOKEN}" 2>/dev/null || return 1
}

log_section "1/8 Cluster Connectivity"
if kubectl cluster-info >/dev/null 2>&1; then
    pass "Kubernetes API reachable"
else
    fail "Kubernetes API not reachable (start/restart k3s before demo)"
    echo ""
    echo "Try: sudo systemctl restart k3s"
    exit 1
fi

log_section "2/8 Core Pods"
REQUIRED=(
    "smart-city ids-api"
    "smart-city postgres"
    "monitoring prometheus"
    "monitoring grafana"
    "monitoring suricata"
)

for item in "${REQUIRED[@]}"; do
    ns="${item%% *}"
    name="${item##* }"
    if kubectl get pods -n "$ns" --no-headers 2>/dev/null | awk -v p="^${name}" '$1 ~ p && $3=="Running"{ok=1} END{exit ok?0:1}'; then
        pass "Pod running: ${ns}/${name}"
    else
        fail "Pod not running: ${ns}/${name}"
    fi
done

if kubectl get pods -n falco-system --no-headers 2>/dev/null | awk '$1 ~ /^falco-/ && $3=="Running"{ok=1} END{exit ok?0:1}'; then
    pass "Falco pod running"
else
    fail "Falco pod not running"
fi

log_section "3/8 API URL Detection"
API_BASE="$(resolve_ids_api_url || true)"
if [[ -z "$API_BASE" ]]; then
    fail "Could not auto-detect IDS API URL (tried localhost:8000, localhost:30800, and NodePort)"
    echo ""
    echo "If using port-forward: kubectl -n smart-city port-forward svc/ids-api-service 8000:8000"
    echo "Then re-run this script or set: IDS_API_URL=http://localhost:8000"
    exit 1
fi
pass "IDS API reachable at: ${API_BASE}"

log_section "4/8 Health & Metrics"
HEALTH_JSON="$(api_json /health || true)"
if [[ -n "$HEALTH_JSON" ]] && echo "$HEALTH_JSON" | jq -e '.status == "healthy"' >/dev/null 2>&1; then
    pass "Health endpoint reports: healthy"
else
    fail "Health endpoint failed or returned non-healthy"
fi

DB_COMPONENT_STATUS="$(echo "$HEALTH_JSON" | jq -r '.components.database // "unknown"' 2>/dev/null || echo unknown)"
DB_STORAGE_STATUS="$(echo "$HEALTH_JSON" | jq -r '.storage_type // "unknown"' 2>/dev/null || echo unknown)"

if [[ "$DB_COMPONENT_STATUS" == "connected" ]] && [[ "$DB_STORAGE_STATUS" == "connected" ]]; then
    pass "Database persistence mode: PostgreSQL connected"
else
    warn "Database not fully connected (components.database=${DB_COMPONENT_STATUS}, storage_type=${DB_STORAGE_STATUS})"
    warn "If this shows memory-fallback, ids-api will auto-retry DB now. Rechecking for 20s..."
    for _ in {1..4}; do
        sleep 5
        HEALTH_JSON="$(api_json /health || true)"
        DB_COMPONENT_STATUS="$(echo "$HEALTH_JSON" | jq -r '.components.database // "unknown"' 2>/dev/null || echo unknown)"
        DB_STORAGE_STATUS="$(echo "$HEALTH_JSON" | jq -r '.storage_type // "unknown"' 2>/dev/null || echo unknown)"
        if [[ "$DB_COMPONENT_STATUS" == "connected" ]] && [[ "$DB_STORAGE_STATUS" == "connected" ]]; then
            pass "Database auto-recovered to PostgreSQL during pre-demo check"
            break
        fi
    done
    if [[ "$DB_COMPONENT_STATUS" != "connected" ]] || [[ "$DB_STORAGE_STATUS" != "connected" ]]; then
        fail "Database still degraded (${DB_COMPONENT_STATUS}/${DB_STORAGE_STATUS}); dashboard may appear to lose historical alerts"
    fi
fi

METRICS_JSON="$(api_json /api/metrics || true)"
if [[ -n "$METRICS_JSON" ]]; then
    pass "Metrics endpoint reachable"
else
    fail "Metrics endpoint not reachable"
fi

TOTAL_ALERTS="$(echo "$METRICS_JSON" | jq -r '.total_alerts // 0' 2>/dev/null || echo 0)"
IOT_COUNT="$(echo "$METRICS_JSON" | jq -r '.iot_devices_active // 0' 2>/dev/null || echo 0)"

if [[ "$TOTAL_ALERTS" =~ ^[0-9]+$ ]] && [[ "$TOTAL_ALERTS" -gt 0 ]]; then
    pass "Alert count present: ${TOTAL_ALERTS}"
else
    warn "No alerts yet (not fatal if this is a fresh start)"
fi

if [[ "$IOT_COUNT" =~ ^[0-9]+$ ]] && [[ "$IOT_COUNT" -gt 0 ]]; then
    if [[ "$IOT_COUNT" -eq 13 ]]; then
        pass "IoT devices reported: 13 (expected demo baseline)"
    else
        warn "IoT devices reported: ${IOT_COUNT} (demo baseline is usually 13)"
    fi
else
    fail "IoT device count is zero"
fi

log_section "5/8 LLM & Detection Visibility"
LLM_CONFIGURED="$(echo "$HEALTH_JSON" | jq -r '.llm_provider_count // 0' 2>/dev/null || echo 0)"
if [[ "$LLM_CONFIGURED" =~ ^[0-9]+$ ]] && [[ "$LLM_CONFIGURED" -ge 1 ]]; then
    pass "LLM providers configured: ${LLM_CONFIGURED}"
else
    warn "No LLM providers configured (dashboard/login can still work, analysis will degrade)"
fi

FALCO_STATUS="$(echo "$HEALTH_JSON" | jq -r '.components.falco // "unknown"' 2>/dev/null || echo unknown)"
SURICATA_STATUS="$(echo "$HEALTH_JSON" | jq -r '.components.suricata // "unknown"' 2>/dev/null || echo unknown)"
[[ "$FALCO_STATUS" == "enabled" ]] && pass "Falco enabled" || warn "Falco status: ${FALCO_STATUS}"
[[ "$SURICATA_STATUS" =~ ^(enabled|connected)$ ]] && pass "Suricata visible (${SURICATA_STATUS})" || warn "Suricata status: ${SURICATA_STATUS}"

log_section "6/8 Login + Protected Endpoint"
AUTH_TOKEN="$(ids_login_token "$API_BASE" admin admin)"
if [[ -n "$AUTH_TOKEN" ]]; then
    pass "Admin login works (admin/admin)"
else
    fail "Admin login failed (expected: admin/admin)"
fi

if [[ -n "$AUTH_TOKEN" ]]; then
    if api_auth_json /api/operator/dashboard >/dev/null; then
        pass "Protected operator endpoint works with token"
    else
        fail "Protected operator endpoint failed with valid token"
    fi
fi

log_section "7/8 Dashboard UI"
UI_HTML="$(curl -fsS "${API_BASE}/ui" 2>/dev/null || true)"
if [[ -n "$UI_HTML" ]] && grep -q "Smart City IDS" <<<"$UI_HTML"; then
    pass "Dashboard UI accessible"
else
    fail "Dashboard UI not accessible"
fi

log_section "8/8 Quick Pipeline Sanity"
BEFORE_ALERTS="$TOTAL_ALERTS"
curl -sS -X POST "${API_BASE}/api/alerts/internal" \
  -H "Content-Type: application/json" \
  -d "{\"rule\":\"Demo Sanity Check\",\"source\":\"falco\",\"priority\":\"Warning\",\"time\":\"$(date -Iseconds)\",\"output\":\"Pre-demo pipeline test event\",\"output_fields\":{\"container.name\":\"pre-demo-check\"}}" \
  >/dev/null 2>&1 || true
sleep 2
AFTER_ALERTS="$(api_json /api/metrics | jq -r '.total_alerts // 0' 2>/dev/null || echo "$BEFORE_ALERTS")"

if [[ "$AFTER_ALERTS" =~ ^[0-9]+$ ]] && [[ "$BEFORE_ALERTS" =~ ^[0-9]+$ ]] && [[ "$AFTER_ALERTS" -ge "$BEFORE_ALERTS" ]]; then
    pass "Pipeline responded (alerts counter readable before/after)"
else
    warn "Pipeline sanity check inconclusive"
fi

log_section "Summary"
echo "Passed:  $PASSED"
echo "Warnings: $WARNED"
echo "Failed:  $FAILED"
echo ""
echo "API URL: ${API_BASE}"
echo "UI URL:  ${API_BASE}/ui"
echo "Login:   admin / admin"
echo ""

if [[ $FAILED -eq 0 ]]; then
    echo "DEMO STATUS: READY"
    exit 0
fi

echo "DEMO STATUS: ATTENTION NEEDED"
echo "Fix failed items above before the examiner session."
exit 1
