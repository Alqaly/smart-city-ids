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
    echo -e "${CYAN}$1${RESET}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

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
# Phase 4: Deploy Services
# =============================================================================
section "Phase 4: Deploying Services"

log_info "Creating namespaces..."
for ns in smart-city monitoring falco-system; do
    kubectl create namespace "$ns" --dry-run=client -o yaml | kubectl apply -f - 2>/dev/null || true
done

log_info "Applying manifests..."
MANIFESTS=(
    "k8s-manifests/postgres-deployment.yaml"
    "k8s-manifests/mqtt-broker.yaml"
    "k8s-manifests/ids-api-FINAL.yaml"
    "k8s-manifests/services-no-build.yaml"
    "k8s-manifests/prometheus-deployment.yaml"
    "k8s-manifests/grafana-deployment.yaml"
)

for m in "${MANIFESTS[@]}"; do
    if [[ -f "$m" ]]; then
        kubectl apply -f "$m" 2>/dev/null && log_ok "Applied $(basename $m)" || log_warn "Failed: $(basename $m)"
    fi
done

# =============================================================================
# Phase 5: Wait for Ready
# =============================================================================
section "Phase 5: Waiting for Services"

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
# Phase 6: Port Forwarding
# =============================================================================
section "Phase 6: Port Forwarding"

# Kill old port-forwards
pkill -f "kubectl.*port-forward.*ids-api" 2>/dev/null || true
sleep 1

# Start new port-forward
log_info "Starting port-forward (localhost:8000)..."
kubectl -n smart-city port-forward svc/ids-api-service 8000:8000 --address 127.0.0.1 > /tmp/pf.log 2>&1 &
PF_PID=$!
sleep 3

if kill -0 $PF_PID 2>/dev/null; then
    log_ok "Port-forward active (PID: $PF_PID)"
else
    log_warn "Port-forward failed - use NodePort: http://localhost:30800"
fi

# =============================================================================
# Summary
# =============================================================================
section "System Ready"

echo ""
log_ok "Smart City IDS is running!"
echo ""
echo -e "  ${CYAN}Dashboard:${NC}      http://localhost:8000/ui"
echo -e "  ${CYAN}API Docs:${NC}       http://localhost:8000/docs"
echo -e "  ${CYAN}Grafana:${NC}        http://localhost:30300"
echo -e "  ${CYAN}Prometheus:${NC}     http://localhost:31106"
echo ""
echo -e "  ${YELLOW}Login:${NC}          operator / operator"
echo ""
echo -e "  ${CYAN}LLM Control:${NC}    ./scripts/llm-manager.sh status"
echo ""
