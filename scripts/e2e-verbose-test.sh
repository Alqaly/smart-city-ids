#!/bin/bash
# =============================================================================
# Smart City IDS - End-to-End Verbose Test
# Tests the complete pipeline: Attack → Detection → Analysis → Action
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/script-utils.sh"

MAGENTA='\033[0;35m'

log_header() {
    echo ""
    echo -e "${MAGENTA}═══════════════════════════════════════════════════════════════════${NC}"
    echo -e "${MAGENTA}  $1${NC}"
    echo -e "${MAGENTA}═══════════════════════════════════════════════════════════════════${NC}"
}

log_phase() {
    echo ""
    echo -e "${BLUE}▶ $1${NC}"
    echo -e "${BLUE}───────────────────────────────────────────────────────────────────${NC}"
}

log_success() {
    echo -e "${GREEN}✓${NC} $1"
}

log_error() {
    echo -e "${RED}✗${NC} $1"
}

log_info() {
    echo -e "${CYAN}ℹ${NC} $1"
}

# =============================================================================
# E2E TEST
# =============================================================================

log_header "END-TO-END PIPELINE TEST"

API_BASE="$(resolve_ids_api_url || true)"
if [[ -z "$API_BASE" ]]; then
    log_error "Could not auto-detect IDS API URL (tried localhost:8000 / localhost:30800 / NodePort)"
    exit 1
fi
log_info "Using IDS API: $API_BASE"

AUTH_TOKEN="$(ids_login_token "$API_BASE" admin admin)"
if [[ -n "$AUTH_TOKEN" ]]; then
    log_success "Authenticated as admin"
else
    log_error "Could not login with admin/admin (protected endpoint checks may fail)"
fi

auth_curl() {
    local url="$1"
    if [[ -n "${AUTH_TOKEN:-}" ]]; then
        curl -s "$url" -H "Authorization: Bearer ${AUTH_TOKEN}" 2>/dev/null
    else
        curl -s "$url" 2>/dev/null
    fi
}

# Phase 1: Baseline
log_phase "PHASE 1: Establishing Baseline"

BASELINE_ALERTS=$(curl -s "${API_BASE}/api/metrics" 2>/dev/null | jq -r '.total_alerts // 0' 2>/dev/null || echo 0)
BASELINE_IOT=$(curl -s "${API_BASE}/api/metrics" 2>/dev/null | jq -r '.iot_devices_active // 0' 2>/dev/null || echo 0)
BASELINE_LLM=$(curl -s "${API_BASE}/api/llm/diagnostics" 2>/dev/null | jq -r '.summary.operational // 0' 2>/dev/null || echo 0)

log_info "Baseline alerts: $BASELINE_ALERTS"
log_info "Baseline IoT devices: $BASELINE_IOT"
log_info "Baseline operational LLM providers: $BASELINE_LLM"

# Phase 2: Health Check
log_phase "PHASE 2: System Health Verification"

HEALTH=$(curl -s "${API_BASE}/health" 2>/dev/null)
DB_STATUS=$(echo "$HEALTH" | jq -r '.components.database // "unknown"' 2>/dev/null || echo unknown)
K8S_STATUS=$(echo "$HEALTH" | jq -r '.components.kubernetes // "unknown"' 2>/dev/null || echo unknown)

if [[ "$DB_STATUS" == "connected" ]]; then
    log_success "Database connected"
else
    log_error "Database status: $DB_STATUS"
fi

if [[ "$K8S_STATUS" == "connected" ]]; then
    log_success "Kubernetes connected"
else
    log_error "Kubernetes status: $K8S_STATUS"
fi

# Phase 3: LLM Provider Status
log_phase "PHASE 3: LLM Provider Verification"

LLM_DIAG=$(curl -s "${API_BASE}/api/llm/diagnostics" 2>/dev/null)
PROVIDERS=$(echo "$LLM_DIAG" | jq -r '.providers | to_entries[]? | "\(.key):\(.value.status // "unknown")"' 2>/dev/null || echo "")

OPERATIONAL=0
while IFS=: read -r name status; do
    if [[ -n "$name" ]]; then
        if [[ "$status" == "operational" ]]; then
            log_success "$name: $status"
            ((OPERATIONAL++)) || true
        else
            log_error "$name: $status"
        fi
    fi
done <<< "$PROVIDERS"

TOTAL_PROVIDERS=$(echo "$LLM_DIAG" | jq -r '.providers | length // 0' 2>/dev/null || echo 0)
log_info "Operational providers: $OPERATIONAL/$TOTAL_PROVIDERS"

if [[ "$OPERATIONAL" -lt 1 ]]; then
    log_error "No operational LLM providers. Governance/action-path validation cannot run."
    echo "$LLM_DIAG" | jq '{summary, providers: (.providers | map_values({status, model, error_category, circuit_breaker_state}))}' 2>/dev/null || true
    exit 1
fi

# Phase 4: Governance Check
log_phase "PHASE 4: Governance Status"

GOV=$(auth_curl "${API_BASE}/api/governance/status")
GOV_MODE=$(echo "$GOV" | jq -r '.mode // "unknown"' 2>/dev/null || echo unknown)
AUTO_EXEC=$(echo "$GOV" | jq -r '.metrics.auto_executed // 0' 2>/dev/null || echo 0)

log_info "Governance mode: $GOV_MODE"
log_info "Auto-executed actions: $AUTO_EXEC"

# Phase 4B: Governance mode E2E validation (real alert path)
log_phase "PHASE 4B: Governance Mode E2E Validation"
if [[ ! -f "$SCRIPT_DIR/test-governance-modes.sh" ]]; then
    log_error "Missing governance mode test script: $SCRIPT_DIR/test-governance-modes.sh"
    exit 1
fi

GOV_MODE_TEST_ARGS=(--api-url "$API_BASE" --username admin --password admin --quiet)
if [[ "${E2E_ENABLE_FULL_AUTONOMY:-0}" == "1" ]]; then
    GOV_MODE_TEST_ARGS+=(--enable-full-autonomy)
fi

if bash "$SCRIPT_DIR/test-governance-modes.sh" "${GOV_MODE_TEST_ARGS[@]}"; then
    log_success "Governance modes validated (manual / assisted / autonomous)"
else
    log_error "Governance mode validation failed"
    exit 1
fi

# Phase 5: IoT Device Verification
log_phase "PHASE 5: IoT Device Count"

K8S_COUNT=$(kubectl get pods -n smart-city --field-selector=status.phase=Running 2>/dev/null | grep -E "traffic-camera|healthcare-api|parking-system|env-sensor|street-lighting|mqtt-broker" | wc -l || echo 0)
API_COUNT=$(curl -s "${API_BASE}/api/metrics" 2>/dev/null | jq -r '.iot_devices_active // 0' 2>/dev/null || echo 0)
IOT_DEVICES_JSON="$(curl -s "${API_BASE}/api/iot/devices" 2>/dev/null || echo '{}')"
IOT_TOTAL=$(echo "$IOT_DEVICES_JSON" | jq -r '.total // 0' 2>/dev/null || echo 0)
IOT_LOGICAL=$(echo "$IOT_DEVICES_JSON" | jq -r '.logical_total // 0' 2>/dev/null || echo 0)
IOT_POD_BACKED=$(echo "$IOT_DEVICES_JSON" | jq -r '.pod_backed_total // 0' 2>/dev/null || echo 0)
IOT_COUNTING_MODE=$(echo "$IOT_DEVICES_JSON" | jq -r '.counting_mode // "unknown"' 2>/dev/null || echo unknown)

log_info "Kubectl count: $K8S_COUNT pods"
log_info "API active metric: $API_COUNT"
log_info "API device view: total=$IOT_TOTAL logical=$IOT_LOGICAL pod_backed=$IOT_POD_BACKED mode=$IOT_COUNTING_MODE"

if [[ "$IOT_COUNTING_MODE" == "hybrid_registry_plus_pods" && "$IOT_TOTAL" -gt 0 && "$IOT_POD_BACKED" -ge "$K8S_COUNT" ]]; then
    log_success "IoT device inventory consistent with hybrid registry + pod counting"
elif [[ "$K8S_COUNT" -gt 0 && "$API_COUNT" -gt 0 ]]; then
    log_info "IoT activity metric and running emulator pods are both non-zero"
else
    log_error "IoT visibility check failed: active_metric=$API_COUNT total=$IOT_TOTAL k8s_pods=$K8S_COUNT mode=$IOT_COUNTING_MODE"
fi

# Phase 6: Live Attack Test (Optional - skip if --quick)
if [[ "${1:-}" != "--quick" ]]; then
    log_phase "PHASE 6: Live Attack Test (15 seconds)"
    log_info "Running live attacks..."
    
    # Run attacks in background
    timeout 20 bash scripts/run-live-attacks.sh --duration 15 --mode all 2>&1 | tail -20 &
    ATTACK_PID=$!
    
    # Wait for attacks to complete
    wait $ATTACK_PID 2>/dev/null || true
    
    # Check results
    sleep 3
    AFTER_ALERTS=$(curl -s "${API_BASE}/api/metrics" 2>/dev/null | jq -r '.total_alerts // 0' 2>/dev/null || echo 0)
    NEW_ALERTS=$((AFTER_ALERTS - BASELINE_ALERTS))
    
    log_info "Alerts before: $BASELINE_ALERTS"
    log_info "Alerts after: $AFTER_ALERTS"
    
    if [[ $NEW_ALERTS -gt 0 ]]; then
        log_success "New alerts generated: $NEW_ALERTS"
    else
        log_error "No new alerts detected"
    fi
    
    # Show recent alerts
    log_info "Recent alerts:"
    curl -s "${API_BASE}/api/alerts?limit=3" 2>/dev/null | python3 -c "
import sys,json
d=json.load(sys.stdin)
items = d if isinstance(d, list) else d.get('alerts', d.get('items', []))
for a in items[:3]:
    print(f'  [{a.get(\"severity\",\"?\")}] {a.get(\"rule\",\"Unknown\")[:50]}...')
" 2>/dev/null || log_error "Could not fetch recent alerts"
fi

# Phase 7: Dashboard Verification
log_phase "PHASE 7: Dashboard Verification"

UI_HTML=""
for _ in {1..5}; do
    UI_HTML="$(curl -s "${API_BASE}/ui" 2>/dev/null || true)"
    if [[ -n "$UI_HTML" ]] && grep -q "Smart City IDS" <<<"$UI_HTML"; then
        break
    fi
    sleep 1
done
if [[ -n "$UI_HTML" ]] && grep -q "Smart City IDS" <<<"$UI_HTML"; then
    log_success "Dashboard UI accessible"
else
    log_error "Dashboard UI not accessible"
fi

HELP_CODE="$(curl -s -o /dev/null -w '%{http_code}' "${API_BASE}/ui/static/help.html" 2>/dev/null || echo 000)"
if [[ "$HELP_CODE" == "200" ]]; then
    log_success "Dashboard help page accessible"
else
    log_error "Dashboard help page unavailable (HTTP $HELP_CODE)"
fi

# Phase 8: Pipeline Status
log_phase "PHASE 8: Pipeline Overview"

PIPELINE=$(curl -s "${API_BASE}/api/pipeline-overview" 2>/dev/null)
STAGES=$(echo "$PIPELINE" | jq -r '.stages[]? | "\(.label // "?"):\(.status // "?"):\(.rate_per_minute // 0)"' 2>/dev/null || echo "")

while IFS=: read -r label status rate; do
    if [[ -n "$label" ]]; then
        if [[ "$status" == "green" ]]; then
            log_success "$label: $status ($rate/min)"
        elif [[ "$status" == "idle" || "$status" == "yellow" || "$status" == "warning" ]]; then
            log_info "$label: $status ($rate/min)"
        else
            log_error "$label: $status ($rate/min)"
        fi
    fi
done <<< "$STAGES"

# =============================================================================
# SUMMARY
# =============================================================================

log_header "TEST SUMMARY"

echo ""
echo -e "${CYAN}System Status:${NC}"
echo "  Database: $DB_STATUS"
echo "  Kubernetes: $K8S_STATUS"
echo "  LLM Providers: $OPERATIONAL/$TOTAL_PROVIDERS operational"
echo "  Governance: $GOV_MODE mode"
echo "  IoT Devices: active_metric=$API_COUNT, total=$IOT_TOTAL, logical=$IOT_LOGICAL, pod_backed=$IOT_POD_BACKED"
echo "  Total Alerts: $BASELINE_ALERTS"
echo ""

echo -e "${CYAN}Dashboard:${NC} ${API_BASE}/ui"
echo ""

log_success "End-to-end test completed!"
