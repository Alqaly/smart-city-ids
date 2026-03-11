#!/bin/bash
# =============================================================================
# Smart City IDS - One Command Ready Script
# Bootstraps and validates the full stack, then prints monitoring endpoints.
#
# IMPORTANT:
# - IoT emulation pods are OPTIONAL and are NOT deployed by default.
# - Synthetic seed events (posting to /api/iot/sensor) are OPTIONAL and are NOT
#   sent by default.
#
# Usage:
#   bash scripts/one-command-ready.sh [--monitor] [--with-iot-emulation] [--allow-synthetic-seed]
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
source "$SCRIPT_DIR/lib/script-utils.sh"

init_script "$0" "Smart City IDS One-Command Ready"

MONITOR=0
SKIP_SEED=0
NO_PORT_FORWARD=0
WITH_IOT_EMULATION=0
ALLOW_SYNTHETIC_SEED=0
while [[ $# -gt 0 ]]; do
    case $1 in
        --monitor) MONITOR=1; shift ;;
        --skip-seed) SKIP_SEED=1; shift ;;
        --with-iot-emulation) WITH_IOT_EMULATION=1; shift ;;
        --allow-synthetic-seed) ALLOW_SYNTHETIC_SEED=1; shift ;;
        --no-port-forward) NO_PORT_FORWARD=1; shift ;;
        --help)
            print_help "one-command-ready.sh [--monitor] [--with-iot-emulation] [--allow-synthetic-seed] [--skip-seed] [--no-port-forward]"
            exit 0
            ;;
        *) die "Unknown option: $1" ;;
    esac
done

ensure_commands kubectl curl jq

USER_HOME="${HOME}"
USER_KUBECONFIG="${USER_HOME}/.kube/config"

persist_kubeconfig_profile() {
    local profile
    for profile in "$USER_HOME/.bashrc" "$USER_HOME/.zshrc" "$USER_HOME/.profile"; do
        [[ -f "$profile" ]] || continue
        sed -i '/export KUBECONFIG=\/etc\/rancher\/k3s\/k3s.yaml/d' "$profile" || true
        if ! grep -q "export KUBECONFIG=${USER_KUBECONFIG}" "$profile"; then
            echo "export KUBECONFIG=${USER_KUBECONFIG}" >> "$profile"
        fi
    done
}

fix_kubeconfig() {
    mkdir -p "$(dirname "$USER_KUBECONFIG")"

    if [[ -r "$USER_KUBECONFIG" ]]; then
        export KUBECONFIG="$USER_KUBECONFIG"
    elif [[ -r "/etc/rancher/k3s/k3s.yaml" ]]; then
        cp /etc/rancher/k3s/k3s.yaml "$USER_KUBECONFIG"
        chmod 600 "$USER_KUBECONFIG" || true
        export KUBECONFIG="$USER_KUBECONFIG"
    elif command -v sudo >/dev/null 2>&1; then
        sudo mkdir -p "$(dirname "$USER_KUBECONFIG")"
        sudo cp /etc/rancher/k3s/k3s.yaml "$USER_KUBECONFIG"
        sudo chown "$(id -u):$(id -g)" "$USER_KUBECONFIG"
        sudo chmod 600 "$USER_KUBECONFIG"
        export KUBECONFIG="$USER_KUBECONFIG"
    else
        die "Could not read kubeconfig. Create ${USER_KUBECONFIG} first."
    fi

    persist_kubeconfig_profile
    log_info "Using kubeconfig: $KUBECONFIG"
}

kubectl_retry() {
    local retries="${1:-8}"
    shift
    local n=1
    while [[ $n -le $retries ]]; do
        if "$@"; then
            return 0
        fi
        sleep 2
        n=$((n + 1))
    done
    return 1
}

apply_manifest_retry() {
    local manifest="$1"
    kubectl_retry 8 kubectl apply --validate=false -f "$manifest" >/dev/null
}

upsert_ids_secret_from_env() {
    local secret_args=()
    [[ -n "${XAI_API_KEY:-}" ]] && secret_args+=(--from-literal=xai-api-key="${XAI_API_KEY}")
    [[ -n "${OPENAI_API_KEY:-}" ]] && secret_args+=(--from-literal=openai-api-key="${OPENAI_API_KEY}")
    [[ -n "${ANTHROPIC_API_KEY:-}" ]] && secret_args+=(--from-literal=anthropic-api-key="${ANTHROPIC_API_KEY}")
    [[ -n "${GEMINI_API_KEY:-}" ]] && secret_args+=(--from-literal=gemini-api-key="${GEMINI_API_KEY}")
    [[ -n "${KIMI_API_KEY:-}" ]] && secret_args+=(--from-literal=kimi-api-key="${KIMI_API_KEY}")

    if [[ ${#secret_args[@]} -eq 0 ]]; then
        die "No LLM API keys found in environment or .env. Set XAI_API_KEY (or another provider key) before running."
    fi

    kubectl create secret generic ids-secrets -n smart-city "${secret_args[@]}" \
        --dry-run=client -o yaml | kubectl apply --validate=false -f - >/dev/null
    log_info "Updated ids-secrets with available LLM keys"
}

load_local_env_keys() {
    if [[ -f "$PROJECT_ROOT/.env" ]]; then
        set -a
        # shellcheck disable=SC1090
        source "$PROJECT_ROOT/.env"
        set +a
        log_info "Loaded API key env vars from .env"
    fi
}

verify_api_key_consistency() {
    local env_xai="${XAI_API_KEY:-}"
    local secret_xai=""
    local pod_xai_len=""
    local ids_pod=""

    if kubectl get secret ids-secrets -n smart-city >/dev/null 2>&1; then
        secret_xai="$(kubectl get secret ids-secrets -n smart-city -o jsonpath='{.data.xai-api-key}' 2>/dev/null | base64 -d || true)"
    fi

    ids_pod="$(kubectl get pods -n smart-city -l app=ids-api --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
    if [[ -n "$ids_pod" ]]; then
        pod_xai_len="$(kubectl exec -n smart-city "$ids_pod" -- sh -lc 'printf %s "${XAI_API_KEY:-}" | wc -c' 2>/dev/null | tr -d '[:space:]' || true)"
    fi

    echo ""
    echo "LLM key check (xAI):"
    echo "  .env/env length:   ${#env_xai}"
    echo "  ids-secrets length:${#secret_xai}"
    echo "  pod env length:    ${pod_xai_len:-0}"

    if [[ -n "$env_xai" && -n "$secret_xai" && "$env_xai" != "$secret_xai" ]]; then
        log_warn "xAI key mismatch between .env and ids-secrets"
    fi
    if [[ -n "$secret_xai" && -n "$pod_xai_len" && "$pod_xai_len" -eq 0 ]]; then
        log_warn "xAI key exists in secret but not visible in running pod env"
    fi
}

sync_ids_code_configmaps() {
    kubectl create configmap ids-app-code -n smart-city \
        --from-file="$PROJECT_ROOT/services/ids-api/src" \
        --from-file="$PROJECT_ROOT/services/ids-api/src/llm_providers" \
        --dry-run=client -o yaml | kubectl apply --validate=false --server-side --force-conflicts -f - >/dev/null
    kubectl create configmap ids-app-static -n smart-city \
        --from-file="$PROJECT_ROOT/services/ids-api/static" \
        --dry-run=client -o yaml | kubectl apply --validate=false --server-side --force-conflicts -f - >/dev/null
    log_info "Synced ids-app-code/ids-app-static"
}

normalize_ids_api_env() {
    local desired_env_json patch_payload
    desired_env_json="$(python - <<'PY'
import json
import yaml

with open("k8s-manifests/ids-api-FINAL.yaml", "r", encoding="utf-8") as fh:
    for doc in yaml.safe_load_all(fh):
        if doc and doc.get("kind") == "Deployment" and doc.get("metadata", {}).get("name") == "ids-api":
            print(json.dumps(doc["spec"]["template"]["spec"]["containers"][0]["env"]))
            break
PY
)"
    [[ -n "$desired_env_json" ]] || return 0
    patch_payload="$(jq -cn --argjson env "$desired_env_json" '[{"op":"replace","path":"/spec/template/spec/containers/0/env","value":$env}]')"
    kubectl patch deployment ids-api -n smart-city --type=json -p "$patch_payload" >/dev/null 2>&1 || true
}

apply_iot_manifest() {
    local manifest="$PROJECT_ROOT/iot-simulator/k8s-enhanced.yaml"
    local fallback="$PROJECT_ROOT/iot-simulator/k8s-fixed.yaml"
    if kubectl get crd servicemonitors.monitoring.coreos.com >/dev/null 2>&1; then
        kubectl apply -f "$manifest" >/dev/null
        return 0
    fi

    if [[ -f "$fallback" ]]; then
        kubectl apply -f "$fallback" >/dev/null
    else
        log_warn "ServiceMonitor CRD missing and no fallback IoT manifest found; skipping IoT device apply"
    fi
}

remove_iot_emulation_if_present() {
    # Best-effort cleanup of emulator workloads so "no emulation" runs are truly no-emulation.
    # Safe to call repeatedly.
    local ns="smart-city"

    # Common labels
    kubectl -n "$ns" delete deploy,svc -l app=iot-device --ignore-not-found >/dev/null 2>&1 || true
    kubectl -n "$ns" delete deploy,svc -l app=iot-mqtt --ignore-not-found >/dev/null 2>&1 || true

    # Known deployment/service names across older/newer manifests
    local names=(
        iot-device-high iot-device-medium iot-device-burst
        iot-devices-enhanced
        iot-mqtt
        iot-simulator-high iot-simulator-medium iot-simulator-burst
        iot-device iot-device-metrics
    )

    local n
    for n in "${names[@]}"; do
        kubectl -n "$ns" delete deploy "$n" --ignore-not-found >/dev/null 2>&1 || true
        kubectl -n "$ns" delete svc "$n" --ignore-not-found >/dev/null 2>&1 || true
    done
}

seed_demo_data_if_needed() {
    [[ $SKIP_SEED -eq 1 ]] && return 0
    [[ $ALLOW_SYNTHETIC_SEED -eq 1 ]] || return 0
    local exec_target
    exec_target="$(kubectl get pods -n smart-city -l app=ids-api --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
    [[ -n "$exec_target" ]] || return 0

    local iot_count
    iot_count="$(kubectl exec -n smart-city "$exec_target" -- sh -lc "curl -s localhost:8000/metrics | awk '/^smartcity_ids_iot_devices_active /{print \$2; exit}'" 2>/dev/null || echo "0")"
    if [[ "${iot_count%.*}" -eq 0 ]]; then
        log_warn "IoT active metric is 0; seeding heartbeat events"
        for d in cam-1 cam-2 env-1; do
            kubectl exec -n smart-city "$exec_target" -- sh -lc "curl -s -X POST localhost:8000/api/iot/sensor -H 'Content-Type: application/json' -d '{\"device_id\":\"$d\",\"device_type\":\"emulator\",\"event_type\":\"heartbeat\",\"value\":1}' >/dev/null" || true
        done
    fi

    local suricata_seen
    suricata_seen="$(kubectl exec -n smart-city "$exec_target" -- sh -lc "curl -s localhost:8000/metrics | awk '/^smartcity_ids_alerts_received_total\\{/ && /source=\"suricata\"/ {sum+=\$NF} END{print sum+0}'" 2>/dev/null || echo "0")"
    if [[ "${suricata_seen%.*}" -eq 0 ]]; then
        log_warn "Suricata alert metric is 0; injecting one Suricata-format internal alert for pipeline validation"
        echo "Skipping synthetic alert injection (live-only evaluation flow)." || true
    fi
}

print_endpoints() {
    local node_ip ids_port grafana_port prom_port
    node_ip="$(get_node_ip)"
    ids_port="$(get_service_nodeport ids-api-service smart-city 30800)"
    grafana_port="$(get_service_nodeport grafana monitoring 30300)"
    prom_port="$(get_service_nodeport prometheus monitoring 31106)"

    echo ""
    echo "Ready endpoints:"
    echo "  IDS API:     http://${node_ip}:${ids_port}"
    echo "  IDS UI:      http://${node_ip}:${ids_port}/ui"
    echo "  Grafana:     http://${node_ip}:${grafana_port}"
    echo "  Prometheus:  http://${node_ip}:${prom_port}"
    echo ""
}

start_local_access() {
    local state_dir="/tmp/smart-city-ids"
    mkdir -p "$state_dir"

    stop_port_forward_checked "$state_dir/pf-ids-api.pid" "kubectl .*port-forward .*svc/ids-api-service .*8000:8000"
    stop_port_forward_checked "$state_dir/pf-grafana.pid" "kubectl .*port-forward .*svc/grafana .*3000:3000"
    stop_port_forward_checked "$state_dir/pf-prometheus.pid" "kubectl .*port-forward .*svc/prometheus .*9090:9090"

    local ids_ok=0
    local graf_ok=0
    local prom_ok=0

    if start_port_forward_checked "smart-city" "ids-api-service" "8000:8000" \
        "http://localhost:8000/health" "/tmp/ids-api-portforward.log" "$state_dir/pf-ids-api.pid" 25 1; then
        ids_ok=1
    fi

    if start_port_forward_checked "monitoring" "grafana" "3000:3000" \
        "http://localhost:3000/api/health" "/tmp/grafana-portforward.log" "$state_dir/pf-grafana.pid" 20 0; then
        curl -fsS http://localhost:3000/api/health >/dev/null 2>&1 && graf_ok=1 || true
    fi

    if start_port_forward_checked "monitoring" "prometheus" "9090:9090" \
        "http://localhost:9090/-/healthy" "/tmp/prometheus-portforward.log" "$state_dir/pf-prometheus.pid" 20 0; then
        curl -fsS http://localhost:9090/-/healthy >/dev/null 2>&1 && prom_ok=1 || true
    fi

    echo ""
    echo "Local access (port-forward):"
    echo "  IDS API:     http://localhost:8000        [$([[ $ids_ok -eq 1 ]] && echo OK || echo FAIL)]"
    echo "  IDS UI:      http://localhost:8000/ui     [$([[ $ids_ok -eq 1 ]] && echo OK || echo FAIL)]"
    echo "  Grafana:     http://localhost:3000        [$([[ $graf_ok -eq 1 ]] && echo OK || echo FAIL)]"
    echo "  Prometheus:  http://localhost:9090        [$([[ $prom_ok -eq 1 ]] && echo OK || echo FAIL)]"
    echo ""
}

print_workload_summary() {
    local smart_running monitoring_running iot_running
    smart_running="$(kubectl get pods -n smart-city --no-headers 2>/dev/null | awk '$3=="Running"{c++} END{print c+0}')"
    monitoring_running="$(kubectl get pods -n monitoring --no-headers 2>/dev/null | awk '$3=="Running"{c++} END{print c+0}')"
    iot_running="$(kubectl get pods -n smart-city --no-headers 2>/dev/null | awk '$1 ~ /(traffic-camera|healthcare-api|parking-system|env-sensor|street-lighting|mqtt-broker)/ {if($3=="Running") c++} END{print c+0}')"
    echo ""
    echo "Workloads:"
    echo "  smart-city running pods: ${smart_running}"
    echo "  monitoring running pods: ${monitoring_running}"
    echo "  iot-related running pods: ${iot_running}"
    echo ""
}

log_section "Phase 1 - Kubeconfig and Cluster"
fix_kubeconfig
load_local_env_keys

# Quick cluster check — avoid unnecessary K3s restart
CLUSTER_OK=false
if kubectl cluster-info >/dev/null 2>&1; then
    CLUSTER_OK=true
elif kubectl_retry 4 kubectl get nodes >/dev/null 2>&1; then
    CLUSTER_OK=true
fi

if ! $CLUSTER_OK; then
    log_warn "Cluster not reachable; attempting lightweight k3s recovery"
    if command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
        sudo systemctl restart k3s >/dev/null 2>&1 || true
        sleep 6
    fi
    export KUBECONFIG="$USER_KUBECONFIG"
    if ! kubectl_retry 8 kubectl cluster-info >/dev/null 2>&1; then
        die "Cluster is still unreachable. Run: bash scripts/start-everything.sh"
    fi
fi

log_section "Phase 2 - Core Sync"
normalize_ids_api_env
apply_manifest_retry "$PROJECT_ROOT/k8s-manifests/ids-api-FINAL.yaml"
apply_manifest_retry "$PROJECT_ROOT/k8s-manifests/services-no-build.yaml"
apply_manifest_retry "$PROJECT_ROOT/k8s-manifests/prometheus-deployment.yaml"
apply_manifest_retry "$PROJECT_ROOT/k8s-manifests/grafana-deployment.yaml"
apply_manifest_retry "$PROJECT_ROOT/k8s-manifests/suricata-fixed.yaml"
apply_manifest_retry "$PROJECT_ROOT/k8s-manifests/falco-forwarder.yaml"

if [[ $WITH_IOT_EMULATION -eq 1 ]]; then
    log_info "IoT emulation enabled: applying iot-simulator manifests"
    apply_iot_manifest
else
    log_warn "IoT emulation disabled (default): no iot-simulator pods will be deployed"
    remove_iot_emulation_if_present
fi

sync_ids_code_configmaps
upsert_ids_secret_from_env
kubectl rollout restart deployment/ids-api -n smart-city >/dev/null || true

log_section "Phase 3 - Wait and Validate"
kubectl rollout status deployment/ids-api -n smart-city --timeout=180s >/dev/null || true
kubectl wait --for=condition=ready pod -n monitoring -l app=suricata --timeout=180s >/dev/null || true
kubectl wait --for=condition=ready pod -n monitoring -l app=suricata-forwarder --timeout=180s >/dev/null || true
kubectl wait --for=condition=ready pod -n monitoring -l app=grafana --timeout=180s >/dev/null || true
kubectl wait --for=condition=ready pod -n monitoring -l app=prometheus --timeout=180s >/dev/null || true

if [[ $ALLOW_SYNTHETIC_SEED -eq 1 ]]; then
    log_warn "Synthetic seed enabled: will post minimal /api/iot/sensor heartbeats if metrics show 0 devices"
else
    log_info "Synthetic seed disabled (default)"
fi
seed_demo_data_if_needed

log_section "Phase 4 - Readiness Checks"
bash "$SCRIPT_DIR/check-setup.sh" || true
bash "$SCRIPT_DIR/demo-readiness.sh" --quick || true
verify_api_key_consistency

print_endpoints
print_workload_summary

if [[ $NO_PORT_FORWARD -eq 0 ]]; then
    log_section "Phase 5 - Local Access"
    start_local_access
fi

if [[ $MONITOR -eq 1 ]]; then
    bash "$SCRIPT_DIR/tail-pipeline-pods.sh"
fi

log_info "One-command ready flow complete"
