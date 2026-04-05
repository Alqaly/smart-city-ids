#!/bin/bash
# =============================================================================
# Smart City IDS - K3s Startup (SMART VERSION)
# Only restarts K3s if needed. Shows clear status.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Load LLM library
source "$SCRIPT_DIR/lib/llm-control.sh"

# Colors
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
log_ok() { echo -e "${GREEN}✓${NC} $1"; }
log_warn() { echo -e "${YELLOW}!${NC} $1"; }
log_err() { echo -e "${RED}✗${NC} $1"; }
log_info() { echo -e "  $1"; }
section() {
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}$1${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

show_help() {
    cat <<'EOF'
Usage:
  sudo bash scripts/start-everything.sh

Purpose:
  Start or refresh the full Smart City IDS stack on the local K3s cluster.

Main phases:
  1. Check K3s status
  2. Start or reuse the cluster
  3. Read LLM configuration from .env
  4. Build and import the shared emulator image
  5. Apply the active Kubernetes manifests
  6. Wait for the main services to become ready

When to use it:
  - first-time startup
  - recovery after a broken local cluster
  - full environment rebuild

Notes:
  - This script requires sudo/root because it manages K3s
  - For code-only updates on a running cluster, use:
      bash scripts/deploy-code.sh
EOF
}

case "${1:-}" in
    --help|-h)
        show_help
        exit 0
        ;;
esac

# Check if root
if [[ $EUID -ne 0 ]]; then
    echo "This script requires root. Re-invoking with sudo..."
    exec sudo "$0" "$@"
fi

cd "$PROJECT_ROOT"

section "Smart City IDS - System Startup"

# =============================================================================
# Phase 1: Check K3s Status (Smart)
# =============================================================================
section "Phase 1: K3s Status Check"

NEEDS_RESTART=false
K3S_RUNNING=false

if pgrep -f "k3s server" > /dev/null 2>&1; then
    log_ok "K3s process found"
    
    # Test if cluster is responsive
    export KUBECONFIG="/etc/rancher/k3s/k3s.yaml"
    if kubectl cluster-info &>/dev/null 2>&1; then
        log_ok "K3s cluster is responsive"
        K3S_RUNNING=true
        
        # Check if all namespaces exist
        MISSING=0
        for ns in smart-city monitoring falco-system; do
            if kubectl get ns "$ns" &>/dev/null 2>&1; then
                log_ok "Namespace '$ns' exists"
            else
                log_warn "Namespace '$ns' missing"
                ((MISSING++))
            fi
        done
        
        if [[ $MISSING -eq 0 ]]; then
            log_ok "All required namespaces present"
        else
            log_warn "Some namespaces missing - will create them"
        fi
    else
        log_warn "K3s process exists but not responsive - will restart"
        NEEDS_RESTART=true
    fi
else
    log_info "K3s not running - will start fresh"
    NEEDS_RESTART=true
fi

# =============================================================================
# Phase 2: Start/Use K3s
# =============================================================================
section "Phase 2: K3s Cluster"

export KUBECONFIG="/etc/rancher/k3s/k3s.yaml"

if [[ "$K3S_RUNNING" == "true" && "$NEEDS_RESTART" == "false" ]]; then
    log_ok "Using existing K3s cluster (no restart needed)"
    log_info "To force restart: sudo systemctl stop k3s && sudo $0"
else
    # Stop any existing K3s
    if pgrep -f "k3s server" > /dev/null 2>&1; then
        log_info "Stopping existing K3s..."
        systemctl stop k3s 2>/dev/null || true
        pkill -f "k3s server" 2>/dev/null || true
        sleep 3
    fi
    
    # Check port
    if lsof -Pi :6443 -sTCP:LISTEN -t >/dev/null 2>&1; then
        log_err "Port 6443 already in use!"
        exit 1
    fi
    
    # Start K3s
    log_info "Starting K3s server..."
    k3s server \
        --write-kubeconfig-mode=644 \
        --write-kubeconfig=/etc/rancher/k3s/k3s.yaml \
        --disable=traefik \
        --disable=servicelb \
        > /tmp/k3s.log 2>&1 &
    
    # Wait for ready
    log_info "Waiting for K3s to be ready..."
    for i in {1..60}; do
        if kubectl cluster-info &>/dev/null 2>&1; then
            log_ok "K3s is ready!"
            break
        fi
        echo -ne "\r  Attempt $i/60..."
        sleep 2
    done
    
    if ! kubectl cluster-info &>/dev/null 2>&1; then
        log_err "K3s failed to start"
        tail -20 /tmp/k3s.log
        exit 1
    fi
fi

# Copy kubeconfig for user
mkdir -p ~/.kube
cp /etc/rancher/k3s/k3s.yaml ~/.kube/config 2>/dev/null || true
chmod 600 ~/.kube/config 2>/dev/null || true

log_ok "K3s ready: $(kubectl get nodes -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)"

# =============================================================================
# Phase 3: LLM Configuration Check
# =============================================================================
section "Phase 3: LLM Configuration"

# Load .env
if [[ -f "$PROJECT_ROOT/.env" ]]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

# Check API keys
CONFIGURED=0
for provider in xai anthropic openai gemini kimi; do
    var_name="${provider^^}_API_KEY"
    if [[ -n "${!var_name:-}" ]]; then
        log_ok "${LLM_NAMES[$provider]:-$provider}: API key configured"
        ((CONFIGURED++))
    else
        log_info "${LLM_NAMES[$provider]:-$provider}: No API key"
    fi
done

if [[ $CONFIGURED -eq 0 ]]; then
    log_warn "No LLM providers configured!"
    log_info "Set at least one API key in .env file:"
    log_info "  XAI_API_KEY=your-key"
    log_info "  OPENAI_API_KEY=your-key"
else
    log_ok "$CONFIGURED provider(s) configured"
fi

log_info "Priority: ${CYAN}${LLM_PRIORITY:-kimi,xai,anthropic,openai,gemini}${NC}"

# =============================================================================
# Phase 4: Build Shared Emulator Image
# =============================================================================
section "Phase 4: Building Shared Emulator Image"

if command -v docker >/dev/null 2>&1 && [[ -f "$PROJECT_ROOT/docker/smart-city-service/Dockerfile" ]]; then
    log_info "Building smart-city-ids/smart-city-service:latest..."
    if docker build -t smart-city-ids/smart-city-service:latest -f "$PROJECT_ROOT/docker/smart-city-service/Dockerfile" "$PROJECT_ROOT" >/tmp/smart-city-service.build.log 2>&1; then
        if sudo k3s ctr images import <(docker save smart-city-ids/smart-city-service:latest) >/dev/null 2>&1; then
            log_ok "Shared emulator image imported into k3s"
        else
            log_warn "Built shared emulator image but failed to import into k3s"
        fi
    else
        log_warn "Shared emulator image build failed; see /tmp/smart-city-service.build.log"
    fi
else
    log_warn "Docker or shared emulator Dockerfile not found; assuming image already exists in cluster runtime"
fi

# =============================================================================
# Phase 5: Deploy Services
# =============================================================================
section "Phase 5: Deploying Services"

log_info "Creating namespaces..."
for ns in smart-city monitoring falco-system; do
    kubectl create namespace "$ns" --dry-run=client -o yaml | kubectl apply -f - 2>/dev/null || true
done

log_info "Refreshing emulator code ConfigMaps..."
declare -A EMULATOR_CONFIGMAPS=(
    ["traffic-camera-code"]="$PROJECT_ROOT/smart-city-services/traffic-camera/app.py"
    ["healthcare-api-code"]="$PROJECT_ROOT/smart-city-services/healthcare-api/app.py"
    ["parking-system-code"]="$PROJECT_ROOT/smart-city-services/parking-system/app.py"
    ["env-sensor-code"]="$PROJECT_ROOT/smart-city-services/environmental-sensor/app.py"
    ["street-lighting-code"]="$PROJECT_ROOT/smart-city-services/street-lighting/app.py"
)
for cm in "${!EMULATOR_CONFIGMAPS[@]}"; do
    src="${EMULATOR_CONFIGMAPS[$cm]}"
    if [[ -f "$src" ]]; then
        kubectl create configmap "$cm" -n smart-city \
            --from-file=app.py="$src" \
            --dry-run=client -o yaml | kubectl apply -f - >/dev/null 2>&1 || true
    fi
done

log_info "Applying manifests..."
normalize_ids_api_env() {
    local desired_env_json patch_payload
    desired_env_json="$(python - <<'PY'
import json
import yaml

with open("k8s-manifests/ids-api.yaml", "r", encoding="utf-8") as fh:
    for doc in yaml.safe_load_all(fh):
        if doc and doc.get("kind") == "Deployment" and doc.get("metadata", {}).get("name") == "ids-api":
            print(json.dumps(doc["spec"]["template"]["spec"]["containers"][0]["env"]))
            break
PY
)"
    [[ -n "$desired_env_json" ]] || return 0
    patch_payload="$(jq -cn --argjson env "$desired_env_json" '[{"op":"replace","path":"/spec/template/spec/containers/0/env","value":$env}]')"
    kubectl patch deploy ids-api -n smart-city --type=json -p "$patch_payload" >/dev/null 2>&1 || true
}

normalize_ids_api_env

MANIFESTS=(
    "k8s-manifests/postgres-deployment.yaml"
    "k8s-manifests/mqtt-broker.yaml"
    "k8s-manifests/ids-api.yaml"
    "k8s-manifests/smart-city-services.yaml"
    "k8s-manifests/suricata.yaml"
    "k8s-manifests/falco-forwarder.yaml"
    "k8s-manifests/prometheus-deployment.yaml"
    "k8s-manifests/grafana-deployment.yaml"
)

for m in "${MANIFESTS[@]}"; do
    if [[ -f "$m" ]]; then
        kubectl apply -f "$m" 2>/dev/null && log_ok "Applied $(basename $m)" || log_warn "Failed: $(basename $m)"
    fi
done

# =============================================================================
# Phase 6: Wait for Ready
# =============================================================================
section "Phase 6: Waiting for Services"

echo ""
echo -n "  Waiting for IDS API..."
for i in {1..30}; do
    if kubectl get pods -n smart-city -l app=ids-api 2>/dev/null | grep -q Running; then
        echo " OK"
        break
    fi
    echo -n "."
    sleep 2
done

echo -n "  Waiting for Prometheus..."
for i in {1..20}; do
    if kubectl get pods -n monitoring -l app=prometheus 2>/dev/null | grep -q Running; then
        echo " OK"
        break
    fi
    echo -n "."
    sleep 2
done

echo -n "  Waiting for Grafana..."
for i in {1..20}; do
    if kubectl get pods -n monitoring -l app=grafana 2>/dev/null | grep -q Running; then
        echo " OK"
        break
    fi
    echo -n "."
    sleep 2
done

# =============================================================================
# Phase 7: Port Forwarding
# =============================================================================
section "Phase 7: Port Forwarding"

if bash "$SCRIPT_DIR/access-stack.sh" start; then
    log_ok "Managed localhost access is active"
else
    log_warn "Managed localhost access failed; NodePort may still be reachable via node IP"
fi

# =============================================================================
# Summary
# =============================================================================
section "System Ready"

echo ""
log_ok "Smart City IDS is running!"
echo ""
NODE_IP="$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}' 2>/dev/null | awk '{print $1}')"
IDS_PORT="$(kubectl -n smart-city get svc ids-api-service -o jsonpath='{.spec.ports[0].nodePort}' 2>/dev/null || echo 30800)"
GRAFANA_PORT="$(kubectl -n monitoring get svc grafana -o jsonpath='{.spec.ports[0].nodePort}' 2>/dev/null || echo 30300)"
PROM_PORT="$(kubectl -n monitoring get svc prometheus -o jsonpath='{.spec.ports[0].nodePort}' 2>/dev/null || echo 31106)"

echo -e "  ${CYAN}Local Dashboard:${NC} http://localhost:8000/ui"
echo -e "  ${CYAN}Local API Docs:${NC}  http://localhost:8000/docs"
echo -e "  ${CYAN}Local Grafana:${NC}   http://localhost:3000"
echo -e "  ${CYAN}Local Prometheus:${NC} http://localhost:9090"
if [[ -n "${NODE_IP:-}" ]]; then
    echo ""
    echo -e "  ${CYAN}NodePort Dashboard:${NC} http://${NODE_IP}:${IDS_PORT}/ui"
    echo -e "  ${CYAN}NodePort Grafana:${NC}   http://${NODE_IP}:${GRAFANA_PORT}"
    echo -e "  ${CYAN}NodePort Prometheus:${NC} http://${NODE_IP}:${PROM_PORT}"
fi
echo ""
echo -e "  ${YELLOW}Login:${NC}          operator / operator"
echo ""
echo -e "  ${CYAN}LLM Control:${NC}    ./scripts/llm-manager.sh status"
echo -e "  ${CYAN}Access Control:${NC} ./scripts/access-stack.sh [start|stop|status]"
echo ""
