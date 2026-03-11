#!/bin/bash
# =============================================================================
# Smart City IDS - Evaluation Runbook Orchestrator
# One real script for readiness, access URLs, key checks, and controlled attacks.
# Usage: bash scripts/demo-day.sh [--profile minimal|standard|full] [--runs N]
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
source "$SCRIPT_DIR/lib/script-utils.sh"
source "$SCRIPT_DIR/lib/llm-control.sh"

init_script "$0" "Smart City IDS Evaluation Run"

PROFILE="minimal"
RUNS=1
NO_BOOTSTRAP=0

while [[ $# -gt 0 ]]; do
    case $1 in
        --profile) PROFILE="$2"; shift 2 ;;
        --runs) RUNS="$2"; shift 2 ;;
        --no-bootstrap) NO_BOOTSTRAP=1; shift ;;
        --help)
            print_help "demo-day.sh [--profile minimal|standard|full] [--runs N] [--no-bootstrap]"
            exit 0
            ;;
        *) die "Unknown option: $1" ;;
    esac
done

[[ "$PROFILE" =~ ^(minimal|standard|full)$ ]] || die "Invalid --profile: $PROFILE"
[[ "$RUNS" =~ ^[0-9]+$ ]] || die "--runs must be an integer"
[[ "$RUNS" -ge 1 ]] || die "--runs must be >= 1"

ensure_commands kubectl curl jq awk
ensure_kubeconfig

API_BASE="${IDS_API_URL:-}"
if [[ -z "$API_BASE" ]]; then
    API_BASE="$(resolve_ids_api_url || true)"
fi
API_BASE="${API_BASE:-http://localhost:8000}"

print_access_urls() {
    local node_ip ids_port grafana_port prom_port local_base
    node_ip="$(get_node_ip)"
    ids_port="$(get_service_nodeport ids-api-service smart-city 30800)"
    grafana_port="$(get_service_nodeport grafana monitoring 30300)"
    prom_port="$(get_service_nodeport prometheus monitoring 31106)"
    local_base="$API_BASE"

    echo ""
    echo "Access URLs:"
    echo "  IDS API:     http://${node_ip}:${ids_port}"
    echo "  IDS UI:      http://${node_ip}:${ids_port}/ui"
    echo "  Grafana:     http://${node_ip}:${grafana_port}"
    echo "  Prometheus:  http://${node_ip}:${prom_port}"
    echo "  Local IDS:   ${local_base}"
    echo "  Local UI:    ${local_base}/ui"
    echo ""
}

check_keys_three_places() {
    log_section "API Key Checks (3 places)"

    local env_xai env_openai env_kimi
    env_xai="$(grep -E '^XAI_API_KEY=' "$PROJECT_ROOT/.env" 2>/dev/null | head -n1 | cut -d= -f2- || true)"
    env_openai="$(grep -E '^OPENAI_API_KEY=' "$PROJECT_ROOT/.env" 2>/dev/null | head -n1 | cut -d= -f2- || true)"
    env_kimi="$(grep -E '^KIMI_API_KEY=' "$PROJECT_ROOT/.env" 2>/dev/null | head -n1 | cut -d= -f2- || true)"

    echo ".env lengths:"
    echo "  XAI_API_KEY: ${#env_xai}"
    echo "  OPENAI_API_KEY: ${#env_openai}"
    echo "  KIMI_API_KEY: ${#env_kimi}"

    echo "ids-secrets lengths:"
    kubectl -n smart-city get secret ids-secrets -o json 2>/dev/null \
        | jq -r '.data|to_entries[]|select(.key=="xai-api-key" or .key=="openai-api-key" or .key=="kimi-api-key")|"  \(.key): \((.value|@base64d|length))"' \
        || true

    local pod
    pod="$(kubectl get pods -n smart-city -l app=ids-api -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
    [[ -n "$pod" ]] || die "No ids-api pod found"

    echo "ids-api pod env lengths:"
    kubectl exec -n smart-city "$pod" -- sh -lc '
      for k in XAI_API_KEY OPENAI_API_KEY KIMI_API_KEY; do
        v=$(printenv "$k" || true); echo "  ${k}: ${#v}";
      done'
}

check_llm_runtime_status() {
    log_section "LLM Runtime Status"
    local token
    token="$(curl -s -X POST "${API_BASE}/api/auth/login" -H 'Content-Type: application/json' \
        -d '{"username":"admin","password":"admin"}' | jq -r '.access_token // empty')"
    [[ -n "$token" ]] || die "Could not login to ids-api at ${API_BASE} with admin/admin"

    curl -s "${API_BASE}/api/llm/status" -H "Authorization: Bearer $token" | jq .
    
    # Also check credits
    echo ""
    log_info "Checking LLM credits..."
    llm_check_credits 2.0 true || true
}

start_local_port_forwards() {
    log_section "Starting Local Access"
    local state_dir="/tmp/smart-city-ids"
    mkdir -p "$state_dir"

    stop_port_forward_checked "$state_dir/pf-ids-api.pid" "kubectl .*port-forward .*svc/ids-api-service .*8000:8000"
    stop_port_forward_checked "$state_dir/pf-grafana.pid" "kubectl .*port-forward .*svc/grafana .*3000:3000"
    stop_port_forward_checked "$state_dir/pf-prometheus.pid" "kubectl .*port-forward .*svc/prometheus .*9090:9090"

    start_port_forward_checked "smart-city" "ids-api-service" "8000:8000" \
        "http://localhost:8000/health" "/tmp/ids-api-portforward.log" "$state_dir/pf-ids-api.pid" 25 1 \
        || die "ids-api port-forward failed"

    start_port_forward_checked "monitoring" "grafana" "3000:3000" \
        "http://localhost:3000/api/health" "/tmp/grafana-portforward.log" "$state_dir/pf-grafana.pid" 20 0 \
        || true

    start_port_forward_checked "monitoring" "prometheus" "9090:9090" \
        "http://localhost:9090/-/healthy" "/tmp/prometheus-portforward.log" "$state_dir/pf-prometheus.pid" 20 0 \
        || true
}

run_controlled_attacks() {
    log_section "Controlled Attack Run"
    echo "Profile: $PROFILE"
    echo "Runs: $RUNS"
    echo ""

    local duration="30"
    case "$PROFILE" in
        minimal)  duration="20" ;;
        standard) duration="30" ;;
        full)     duration="60" ;;
    esac

    local i
    for i in $(seq 1 "$RUNS"); do
        echo "Run $i/$RUNS"
        bash "$SCRIPT_DIR/run-live-attacks.sh" --duration "$duration" || true
        echo ""
    done
}

show_workloads() {
    log_section "Workload Summary"
    kubectl get pods -n smart-city -o wide
    echo ""
    kubectl get pods -n monitoring -o wide
}

log_section "Phase 1 - Bootstrap"
if [[ "$NO_BOOTSTRAP" -eq 0 ]]; then
    bash "$SCRIPT_DIR/one-command-ready.sh"
fi

start_local_port_forwards
print_access_urls
show_workloads
check_keys_three_places
check_llm_runtime_status
run_controlled_attacks

log_section "Phase 2 - Final Checks"
bash "$SCRIPT_DIR/demo-readiness.sh" --quick || true

log_info "Evaluation runbook script completed"
