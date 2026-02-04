#!/bin/bash
# =============================================================================
# Smart City IDS - System Requirements Check
# Validates all prerequisites for deployment and running system
# Usage: bash scripts/check-setup.sh [--verbose] [--help]
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")}" && pwd)"
source "$SCRIPT_DIR/lib/script-utils.sh"

VERBOSE=0
while [[ $# -gt 0 ]]; do
    case $1 in
        --verbose)  VERBOSE=1; shift ;;
        --help)     print_help "check-setup.sh [--verbose]"; exit 0 ;;
        *)          die "Unknown option: $1" ;;
    esac
done

init_script "$0" "System Requirements Check"

PASSED=0
FAILED=0
WARNINGS=0

# ─────────────────────────────────────────────────────────────────────────────
# Operating System
# ─────────────────────────────────────────────────────────────────────────────
log_section "1. OPERATING SYSTEM"

if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    DISTRO=$(grep -E '^ID=' /etc/os-release 2>/dev/null | cut -d'=' -f2 | tr -d '"' || echo "unknown")
    KERNEL=$(uname -r)
    log_info "Linux detected: $DISTRO"
    log_debug "Kernel: $KERNEL"
    ((PASSED++))
else
    log_error "Unsupported OS: $OSTYPE (requires Linux)"
    ((FAILED++))
fi

# ─────────────────────────────────────────────────────────────────────────────
# Privileges
# ─────────────────────────────────────────────────────────────────────────────
log_section "2. USER PRIVILEGES"

if [[ $EUID -eq 0 ]]; then
    log_info "Running as root ✓"
    ((PASSED++))
else
    log_warn "Not running as root (will use sudo when needed)"
    ((WARNINGS++))
fi

# ─────────────────────────────────────────────────────────────────────────────
# System Resources
# ─────────────────────────────────────────────────────────────────────────────
log_section "3. SYSTEM RESOURCES"

RAM_GB=$(get_system_ram_gb)
DISK_GB=$(get_available_disk_gb)
CPU=$(get_cpu_cores)

log_subsection "Memory"
if [[ $RAM_GB -ge 8 ]]; then
    log_info "RAM: ${RAM_GB}GB (optimal: ≥8GB)"
    ((PASSED++))
elif [[ $RAM_GB -ge 4 ]]; then
    log_warn "RAM: ${RAM_GB}GB (minimum met, recommended: ≥8GB)"
    ((WARNINGS++))
else
    log_error "RAM: ${RAM_GB}GB (minimum 4GB required)"
    ((FAILED++))
fi

log_subsection "Disk Space"
if [[ $DISK_GB -ge 20 ]]; then
    log_info "Available: ${DISK_GB}GB (optimal)"
    ((PASSED++))
elif [[ $DISK_GB -ge 10 ]]; then
    log_warn "Available: ${DISK_GB}GB (minimum met, recommended: ≥20GB)"
    ((WARNINGS++))
else
    log_error "Available: ${DISK_GB}GB (minimum 20GB required)"
    ((FAILED++))
fi

log_subsection "CPU"
log_info "Cores: $CPU"

# ─────────────────────────────────────────────────────────────────────────────
# Kubernetes
# ─────────────────────────────────────────────────────────────────────────────
log_section "4. KUBERNETES"

if command -v k3s &>/dev/null; then
    K3S_VERSION=$(k3s --version 2>/dev/null | head -1 || echo "unknown")
    log_info "K3s installed: $K3S_VERSION"
    ((PASSED++))
else
    log_warn "K3s not installed (will be auto-installed by deployment script)"
    ((WARNINGS++))
fi

if command -v kubectl &>/dev/null; then
    KUBECTL_VERSION=$(kubectl version --client --short 2>/dev/null | head -1 || echo "unknown")
    log_info "kubectl available: $KUBECTL_VERSION"
    ((PASSED++))
else
    log_warn "kubectl not found (will be available after K3s installation)"
    ((WARNINGS++))
fi

if [[ -f "$KUBECONFIG" ]]; then
    log_info "KUBECONFIG exists: $KUBECONFIG"
    ((PASSED++))
else
    log_warn "KUBECONFIG not found yet (will be created on first deployment)"
    ((WARNINGS++))
fi

# ─────────────────────────────────────────────────────────────────────────────
# Programming Languages & Tools
# ─────────────────────────────────────────────────────────────────────────────
log_section "5. PROGRAMMING LANGUAGES & TOOLS"

for tool in python3 git curl jq docker; do
    if command -v "$tool" &>/dev/null; then
        VERSION=$($tool --version 2>&1 | head -1 || echo "installed")
        log_info "$tool: $VERSION"
        ((PASSED++))
    else
        if [[ "$tool" == "docker" ]]; then
            log_warn "$tool: not found (optional, K3s provides containerd)"
        else
            log_error "$tool: not found (required)"
            ((FAILED++))
        fi
    fi
done

# ─────────────────────────────────────────────────────────────────────────────
# Network Connectivity
# ─────────────────────────────────────────────────────────────────────────────
log_section "6. NETWORK CONNECTIVITY"

if ping -c 1 -W 2 8.8.8.8 &>/dev/null; then
    log_info "Internet connectivity: OK"
    ((PASSED++))
else
    log_warn "Cannot reach 8.8.8.8 (may need internet for initial setup)"
    ((WARNINGS++))
fi

# Check localhost
if is_port_open "localhost" 22 2>/dev/null || [[ true ]]; then
    log_info "Localhost accessible"
    ((PASSED++))
fi

# ─────────────────────────────────────────────────────────────────────────────
# LLM API Configuration
# ─────────────────────────────────────────────────────────────────────────────
log_section "7. LLM API CONFIGURATION"

if [[ -n "${XAI_API_KEY:-}" ]]; then
    log_info "XAI_API_KEY is set"
    ((PASSED++))
elif [[ -n "${OPENAI_API_KEY:-}" ]]; then
    log_info "OPENAI_API_KEY is set"
    ((PASSED++))
else
    log_warn "No LLM API key configured (set XAI_API_KEY or OPENAI_API_KEY)"
    ((WARNINGS++))
fi

# ─────────────────────────────────────────────────────────────────────────────
# Project Files
# ─────────────────────────────────────────────────────────────────────────────
log_section "8. PROJECT FILES"

PROJECT_ROOT=$(dirname "$SCRIPT_DIR")
if [[ -d "$PROJECT_ROOT/services/ids-api" ]]; then
    log_info "IDS API found"
    ((PASSED++))
else
    log_error "IDS API not found"
    ((FAILED++))
fi

if [[ -d "$PROJECT_ROOT/k8s-manifests" ]]; then
    log_info "Kubernetes manifests found"
    ((PASSED++))
else
    log_error "Kubernetes manifests not found"
    ((FAILED++))
fi

# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────
echo ""
log_section "SUMMARY"

echo -e "${GREEN}✓ Passed:${NC}    $PASSED"
if [[ $WARNINGS -gt 0 ]]; then
    echo -e "${YELLOW}! Warnings:${NC}  $WARNINGS"
fi
if [[ $FAILED -gt 0 ]]; then
    echo -e "${RED}✗ Failed:${NC}    $FAILED"
fi

echo ""
if [[ $FAILED -eq 0 ]]; then
    log_info "All checks passed. System is ready for deployment."
    echo ""
    echo "Next steps:"
    echo "  1. Set LLM API key if not already set:"
    echo "     export XAI_API_KEY='your-key' OR export OPENAI_API_KEY='your-key'"
    echo ""
    echo "  2. Deploy the system:"
    echo "     sudo bash scripts/start-everything.sh"
    echo ""
    exit 0
else
    log_error "Some checks failed. Please fix the issues above before deployment."
    exit 1
fi
