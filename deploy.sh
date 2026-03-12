#!/bin/bash
# =============================================================================
# Smart City IDS - One-Click Deployment Script
# =============================================================================
#
# Usage: ./deploy.sh [OPTIONS]
#
# Options:
#   --skip-k3s          Skip k3s installation (if already installed)
#   --skip-build        Skip Docker image building
#   --skip-monitoring   Skip Prometheus/Grafana deployment
#   --clean             Clean up existing deployment first
#   --help              Show this help message
#
# Requirements:
#   - Ubuntu 20.04+ or similar Linux distribution
#   - sudo access
#   - Internet connection (for initial setup)
#   - Minimum 4GB RAM, 20GB disk
#
# Environment Variables (create .env file or export):
#   - XAI_API_KEY       (required) xAI Grok API key
#   - OPENAI_API_KEY    (optional) OpenAI API key as fallback
#
# =============================================================================

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
K3S_VERSION="v1.33.5+k3s1"
NAMESPACE_SMART_CITY="smart-city"
NAMESPACE_MONITORING="monitoring"
NAMESPACE_FALCO="falco-system"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Logging functions
log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step() { echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; echo -e "${CYAN}▶ $1${NC}"; echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; }

# Parse arguments
SKIP_K3S=false
SKIP_BUILD=false
SKIP_MONITORING=false
DO_CLEAN=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-k3s) SKIP_K3S=true; shift ;;
        --skip-build) SKIP_BUILD=true; shift ;;
        --skip-monitoring) SKIP_MONITORING=true; shift ;;
        --clean) DO_CLEAN=true; shift ;;
        --help)
            head -30 "$0" | tail -28
            exit 0
            ;;
        *) log_error "Unknown option: $1"; exit 1 ;;
    esac
done

# =============================================================================
# STEP 1: Prerequisites Check
# =============================================================================
check_prerequisites() {
    log_step "Step 1/7: Checking Prerequisites"
    
    local missing=()
    
    # Check OS
    if [[ ! -f /etc/os-release ]]; then
        log_error "Cannot detect OS. This script requires Linux."
        exit 1
    fi
    
    # Check sudo
    if ! sudo -n true 2>/dev/null; then
        log_warn "sudo access required. You may be prompted for password."
    fi
    
    # Check memory
    local mem_gb=$(free -g | awk '/^Mem:/{print $2}')
    if [[ $mem_gb -lt 3 ]]; then
        log_warn "Less than 4GB RAM detected ($mem_gb GB). Performance may be affected."
    fi
    
    # Check disk space
    local disk_gb=$(df -BG "$PROJECT_ROOT" | awk 'NR==2{print $4}' | tr -d 'G')
    if [[ $disk_gb -lt 10 ]]; then
        log_warn "Less than 10GB free disk space ($disk_gb GB)."
    fi
    
    # Check for curl
    if ! command -v curl &> /dev/null; then
        missing+=("curl")
    fi
    
    # Check for git
    if ! command -v git &> /dev/null; then
        missing+=("git")
    fi
    
    if [[ ${#missing[@]} -gt 0 ]]; then
        log_error "Missing required tools: ${missing[*]}"
        log_info "Install with: sudo apt-get install ${missing[*]}"
        exit 1
    fi
    
    log_info "✓ Prerequisites check passed"
}

# =============================================================================
# STEP 2: Environment Configuration
# =============================================================================
configure_environment() {
    log_step "Step 2/7: Configuring Environment"
    
    # Load .env file if exists
    if [[ -f "${PROJECT_ROOT}/.env" ]]; then
        log_info "Loading configuration from .env"
        set -a
        source "${PROJECT_ROOT}/.env"
        set +a
    fi
    
    # Check for required API keys
    if [[ -z "$XAI_API_KEY" && -z "$OPENAI_API_KEY" ]]; then
        log_error "No LLM API key configured!"
        log_info ""
        log_info "Please set at least one API key:"
        log_info "  export XAI_API_KEY='your-xai-api-key'"
        log_info "  export OPENAI_API_KEY='your-openai-api-key'"
        log_info ""
        log_info "Or create a .env file:"
        log_info "  cp .env.example .env"
        log_info "  # Edit .env with your API keys"
        exit 1
    fi
    
    # Set defaults
    export K8S_NAMESPACE="${K8S_NAMESPACE:-smart-city}"
    export POSTGRES_USER="${POSTGRES_USER:-idsuser}"
    export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-idspassword}"
    export POSTGRES_DB="${POSTGRES_DB:-idsdb}"
    
    log_info "✓ Environment configured"
    log_info "  - XAI_API_KEY: ${XAI_API_KEY:+configured}"
    log_info "  - OPENAI_API_KEY: ${OPENAI_API_KEY:+configured}"
}

# =============================================================================
# STEP 3: Install/Configure K3s
# =============================================================================
install_k3s() {
    log_step "Step 3/7: Installing K3s Kubernetes"
    
    if $SKIP_K3S; then
        log_info "Skipping k3s installation (--skip-k3s)"
        return
    fi
    
    if command -v k3s &> /dev/null && k3s kubectl get nodes &> /dev/null; then
        log_info "k3s already installed and running"
    else
        log_info "Installing k3s..."
        curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION="$K3S_VERSION" sh -s - \
            --write-kubeconfig-mode 644 \
            --disable traefik
        
        # Wait for k3s to be ready
        log_info "Waiting for k3s to be ready..."
        sleep 10
        
        local retries=30
        while ! k3s kubectl get nodes &> /dev/null && [[ $retries -gt 0 ]]; do
            sleep 2
            ((retries--))
        done
        
        if [[ $retries -eq 0 ]]; then
            log_error "k3s failed to start"
            exit 1
        fi
    fi
    
    # Configure kubeconfig
    export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
    
    # Ensure kubeconfig is readable
    sudo chmod 644 /etc/rancher/k3s/k3s.yaml 2>/dev/null || true
    
    # Add to bashrc if not present
    if ! grep -q "KUBECONFIG=/etc/rancher/k3s/k3s.yaml" ~/.bashrc 2>/dev/null; then
        echo 'export KUBECONFIG=/etc/rancher/k3s/k3s.yaml' >> ~/.bashrc
    fi
    
    log_info "✓ k3s is ready"
    kubectl get nodes
}

# =============================================================================
# STEP 4: Build Docker Images
# =============================================================================
build_images() {
    log_step "Step 4/7: Building Docker Images"
    
    if $SKIP_BUILD; then
        log_info "Skipping image build (--skip-build)"
        return
    fi
    
    # Check if container runtime is available
    local has_docker=false
    local has_nerdctl=false
    
    if command -v docker &> /dev/null; then
        has_docker=true
        log_info "Using Docker runtime"
    elif command -v nerdctl &> /dev/null; then
        has_nerdctl=true
        log_info "Using nerdctl runtime"
    fi
    
    if ! $has_docker && ! $has_nerdctl && ! command -v k3s &> /dev/null; then
        log_error "No container runtime found (Docker, nerdctl, or K3s required)"
        exit 1
    fi
    
    # Call build-images.sh - it will handle runtime detection
    log_info "Building Docker images..."
    if bash "${PROJECT_ROOT}/scripts/build-images.sh"; then
        log_info "✓ Docker images built successfully"
    else
        log_error "Docker image build failed - images must be pre-built or Docker installed"
        log_info "Install Docker with: curl -fsSL https://get.docker.com | sh"
        exit 1
    fi
}

# =============================================================================
# STEP 5: Deploy Kubernetes Manifests
# =============================================================================
deploy_manifests() {
    log_step "Step 5/7: Deploying to Kubernetes"
    
    cd "$PROJECT_ROOT"
    
    # Clean up if requested
    if $DO_CLEAN; then
        log_info "Cleaning up existing deployment..."
        kubectl delete namespace $NAMESPACE_SMART_CITY --ignore-not-found --wait=false
        kubectl delete namespace $NAMESPACE_MONITORING --ignore-not-found --wait=false
        sleep 5
    fi
    
    # Create namespaces
    log_info "Creating namespaces..."
    kubectl apply -f k8s-manifests/namespace.yaml
    
    # Create secrets for API keys (match ids-api deployment key names)
    log_info "Creating secrets..."
    kubectl create secret generic ids-secrets \
        --namespace=$NAMESPACE_SMART_CITY \
        --from-literal=xai-api-key="${XAI_API_KEY:-}" \
        --from-literal=openai-api-key="${OPENAI_API_KEY:-}" \
        --from-literal=anthropic-api-key="${ANTHROPIC_API_KEY:-}" \
        --from-literal=gemini-api-key="${GEMINI_API_KEY:-}" \
        --from-literal=kimi-api-key="${KIMI_API_KEY:-}" \
        --dry-run=client -o yaml | kubectl apply -f -
    
    # Deploy PostgreSQL (if using database)
    if [[ -f "k8s-manifests/postgres-deployment.yaml" ]]; then
        log_info "Deploying PostgreSQL..."
        kubectl apply -f k8s-manifests/postgres-deployment.yaml
        kubectl wait --for=condition=ready pod -l app=postgres -n $NAMESPACE_SMART_CITY --timeout=120s || true
    fi
    
    # Deploy RBAC
    log_info "Deploying RBAC..."
    kubectl apply -f k8s-manifests/rbac.yaml
    
    # Create ConfigMaps for smart city services
    log_info "Creating ConfigMaps for smart city services..."
    
    # Traffic Camera ConfigMap
    kubectl create configmap traffic-camera-code \
        --namespace=$NAMESPACE_SMART_CITY \
        --from-file=app.py=smart-city-services/traffic-camera/app.py \
        --dry-run=client -o yaml | kubectl apply -f -
    
    # Healthcare API ConfigMap
    kubectl create configmap healthcare-api-code \
        --namespace=$NAMESPACE_SMART_CITY \
        --from-file=app.py=smart-city-services/healthcare-api/app.py \
        --dry-run=client -o yaml | kubectl apply -f -
    
    # Parking System ConfigMap
    kubectl create configmap parking-system-code \
        --namespace=$NAMESPACE_SMART_CITY \
        --from-file=app.py=smart-city-services/parking-system/app.py \
        --dry-run=client -o yaml | kubectl apply -f -

    # IDS API code + operator UI
    log_info "Creating ConfigMaps for IDS API..."
    kubectl create configmap ids-app-code \
        --namespace=$NAMESPACE_SMART_CITY \
        --from-file=services/ids-api/src \
        --from-file=llm_providers=services/ids-api/src/llm_providers \
        --dry-run=client -o yaml | kubectl apply --server-side --force-conflicts -f -
    kubectl create configmap ids-app-static \
        --namespace=$NAMESPACE_SMART_CITY \
        --from-file=services/ids-api/static \
        --dry-run=client -o yaml | kubectl apply --server-side --force-conflicts -f -
    
    # Deploy smart city services
    log_info "Deploying smart city services..."
    kubectl apply -f k8s-manifests/services-no-build.yaml
    
    # Deploy IDS API
    log_info "Deploying IDS API..."
    kubectl apply -f k8s-manifests/ids-api-FINAL.yaml

    # Deploy Suricata + Forwarder (Option A: syslog → forwarder)
    if [[ -f "k8s-manifests/suricata-fixed.yaml" ]]; then
        log_info "Deploying Suricata (monitoring namespace)..."
        kubectl apply -f k8s-manifests/suricata-fixed.yaml
    fi
    if [[ -f "k8s-manifests/suricata-forwarder-deployment.yaml" ]]; then
        log_info "Deploying Suricata forwarder (monitoring namespace)..."
        kubectl apply -f k8s-manifests/suricata-forwarder-deployment.yaml
    fi

    # Deploy MQTT broker
    if [[ -f "k8s-manifests/mqtt-broker.yaml" ]]; then
        log_info "Deploying MQTT broker..."
        kubectl apply -f k8s-manifests/mqtt-broker.yaml
    fi
    
    # Deploy IoT simulator
    if [[ -f "k8s-manifests/iot-simulator.yaml" ]]; then
        log_info "Deploying IoT simulator..."
        kubectl apply -f k8s-manifests/iot-simulator.yaml
    fi
    
    log_info "✓ Core services deployed"
}

# =============================================================================
# STEP 6: Deploy Monitoring Stack
# =============================================================================
deploy_monitoring() {
    log_step "Step 6/7: Deploying Monitoring Stack"
    
    if $SKIP_MONITORING; then
        log_info "Skipping monitoring (--skip-monitoring)"
        return
    fi
    
    cd "$PROJECT_ROOT"
    
    # Create monitoring namespace
    kubectl create namespace $NAMESPACE_MONITORING --dry-run=client -o yaml | kubectl apply -f -
    
    # Generate Grafana provisioning ConfigMaps with all dashboards
    log_info "Generating Grafana provisioning ConfigMaps..."
    bash "${PROJECT_ROOT}/scripts/generate-grafana-provisioning.sh" 2>&1 | grep -E "✅|❌|Found|Error" || true
    
    # Apply the auto-generated dashboard ConfigMaps
    log_info "Deploying auto-generated Grafana dashboard ConfigMaps..."
    kubectl apply -f k8s-manifests/grafana-provisioning-dashboards.yaml || log_warn "Failed to apply dashboard ConfigMaps"
    
    # Deploy Prometheus
    log_info "Deploying Prometheus..."
    kubectl apply -f k8s-manifests/prometheus-deployment.yaml
    
    # Deploy Grafana (with provisioning volumes already mounted)
    log_info "Deploying Grafana with auto-provisioning..."
    kubectl apply -f k8s-manifests/grafana-deployment.yaml
    
    # Wait for Grafana to be ready
    log_info "Waiting for Grafana to be ready (dashboards auto-loading)..."
    kubectl wait --for=condition=ready pod -l app=grafana -n $NAMESPACE_MONITORING --timeout=120s || true
    
    # Notify user about provisioning
    log_info "✓ Monitoring stack deployed with auto-provisioned dashboards"
    log_info "  Grafana automatically loads all dashboards on startup"
    log_info "  No manual dashboard import scripts needed!"
}

# =============================================================================
# STEP 7: Verify Deployment
# =============================================================================
verify_deployment() {
    log_step "Step 7/7: Verifying Deployment"
    
    local all_healthy=true
    
    # Wait for pods to be ready
    log_info "Waiting for pods to be ready..."
    sleep 10
    
    # Check smart-city namespace
    log_info "Pods in $NAMESPACE_SMART_CITY namespace:"
    kubectl get pods -n $NAMESPACE_SMART_CITY
    
    # Check monitoring namespace
    if ! $SKIP_MONITORING; then
        log_info "Pods in $NAMESPACE_MONITORING namespace:"
        kubectl get pods -n $NAMESPACE_MONITORING
    fi
    
    # Wait for IDS API
    log_info "Waiting for IDS API to be ready..."
    local retries=30
    while ! kubectl get pods -n $NAMESPACE_SMART_CITY -l app=ids-api -o jsonpath='{.items[0].status.phase}' 2>/dev/null | grep -q Running && [[ $retries -gt 0 ]]; do
        sleep 5
        ((retries--))
    done
    
    # Get service URLs
    local NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')
    
    echo ""
    log_info "=========================================="
    log_info "DEPLOYMENT COMPLETE!"
    log_info "=========================================="
    echo ""
    log_info "Access URLs:"
    echo "  - IDS API:    http://${NODE_IP}:30800"
    echo "  - Grafana:    http://${NODE_IP}:30300  (admin/admin)"
    echo "  - Prometheus: http://${NODE_IP}:31701"
    echo ""
    log_info "Health Check:"
    curl -s "http://${NODE_IP}:30800/health" 2>/dev/null | head -c 200 || echo "  (API still starting...)"
    echo ""
    log_info "Quick Commands:"
    echo "  - View pods:     kubectl get pods -n smart-city"
    echo "  - View logs:     kubectl logs -n smart-city -l app=ids-api -f"
    echo "  - Run attack:    bash scripts/run-live-attacks.sh --duration 30"
    echo ""
    log_info "Dashboard: Open http://${NODE_IP}:30300 and import dashboard from:"
    echo "  infrastructure/monitoring/grafana-dashboards/"
    echo ""
}

# =============================================================================
# Main Execution
# =============================================================================
main() {
    echo ""
    echo -e "${CYAN}╔═══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║     Smart City IDS - One-Click Deployment                 ║${NC}"
    echo -e "${CYAN}║     LLM-Driven Intrusion Detection System                 ║${NC}"
    echo -e "${CYAN}╚═══════════════════════════════════════════════════════════╝${NC}"
    echo ""
    
    check_prerequisites
    configure_environment
    install_k3s
    build_images
    deploy_manifests
    deploy_monitoring
    verify_deployment
    
    echo ""
    log_info "🎉 Smart City IDS is now running!"
    echo ""
}

# Run main
main "$@"
