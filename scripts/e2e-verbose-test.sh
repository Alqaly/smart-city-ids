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

BASELINE_ALERTS=$(curl -s "${API_BASE}/api/metrics" 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('total_alerts',0))" || echo 0)
BASELINE_IOT=$(curl -s "${API_BASE}/api/metrics" 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('iot_devices_active',0))" || echo 0)
BASELINE_LLM=$(curl -s "${API_BASE}/api/llm/diagnostics" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('summary',{}).get('operational',0))" || echo 0)

log_info "Baseline alerts: $BASELINE_ALERTS"
log_info "Baseline IoT devices: $BASELINE_IOT"
log_info "Baseline operational LLM providers: $BASELINE_LLM"

# Phase 2: Health Check
log_phase "PHASE 2: System Health Verification"

HEALTH=$(curl -s "${API_BASE}/health" 2>/dev/null)
DB_STATUS=$(echo "$HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin).get('components',{}).get('database','unknown'))")
K8S_STATUS=$(echo "$HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin).get('components',{}).get('kubernetes','unknown'))")

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
PROVIDERS=$(echo "$LLM_DIAG" | python3 -c "import sys,json; d=json.load(sys.stdin).get('providers',{}); [print(f'{k}:{v.get(\"status\",\"unknown\")}') for k,v in d.items()]" 2>/dev/null || echo "")

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

TOTAL_PROVIDERS=$(echo "$LLM_DIAG" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('providers',{})))" 2>/dev/null || echo 0)
log_info "Operational providers: $OPERATIONAL/$TOTAL_PROVIDERS"

# Phase 4: Governance Check
log_phase "PHASE 4: Governance Status"

GOV=$(auth_curl "${API_BASE}/api/governance/status")
GOV_MODE=$(echo "$GOV" | python3 -c "import sys,json; print(json.load(sys.stdin).get('mode','unknown'))")
AUTO_EXEC=$(echo "$GOV" | python3 -c "import sys,json; print(json.load(sys.stdin).get('metrics',{}).get('auto_executed',0))")

log_info "Governance mode: $GOV_MODE"
log_info "Auto-executed actions: $AUTO_EXEC"

# Phase 5: IoT Device Verification
log_phase "PHASE 5: IoT Device Count"

K8S_COUNT=$(kubectl get pods -n smart-city --field-selector=status.phase=Running 2>/dev/null | grep -E "traffic-camera|healthcare-api|parking-system|env-sensor|street-lighting|mqtt-broker" | wc -l || echo 0)
API_COUNT=$(curl -s "${API_BASE}/api/metrics" 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('iot_devices_active',0))" || echo 0)

log_info "Kubectl count: $K8S_COUNT pods"
log_info "API reports: $API_COUNT devices"

if [[ "$API_COUNT" -eq 13 ]]; then
    log_success "IoT device count correct (13)"
else
    log_error "IoT device count differs from demo baseline: $API_COUNT (expected 13)"
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
    AFTER_ALERTS=$(curl -s "${API_BASE}/api/metrics" 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('total_alerts',0))" || echo 0)
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

UI_HTML="$(curl -s "${API_BASE}/ui" 2>/dev/null || true)"
if [[ -n "$UI_HTML" ]] && grep -q "Smart City IDS" <<<"$UI_HTML"; then
    log_success "Dashboard UI accessible"
else
    log_error "Dashboard UI not accessible"
fi

# Phase 8: Pipeline Status
log_phase "PHASE 8: Pipeline Overview"

PIPELINE=$(curl -s "${API_BASE}/api/pipeline-overview" 2>/dev/null)
STAGES=$(echo "$PIPELINE" | python3 -c "import sys,json; d=json.load(sys.stdin); [print(f'{s.get(\"label\",\"?\")}:{s.get(\"status\",\"?\")}:{s.get(\"rate_per_minute\",0)}') for s in d.get('stages',[])]" 2>/dev/null || echo "")

while IFS=: read -r label status rate; do
    if [[ -n "$label" ]]; then
        if [[ "$status" == "green" ]]; then
            log_success "$label: $status ($rate/min)"
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
echo "  IoT Devices: $API_COUNT (verified: $K8S_COUNT pods)"
echo "  Total Alerts: $BASELINE_ALERTS"
echo ""

echo -e "${CYAN}Dashboard:${NC} ${API_BASE}/ui"
echo ""

log_success "End-to-end test completed!"
