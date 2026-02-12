#!/bin/bash
# =============================================================================
# Smart City IDS - Cleanup & Shutdown Script
# Professional cleanup with safety checks and verification
# Usage: sudo bash scripts/cleanup.sh [--all]
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/script-utils.sh"

init_script "$0" "Smart City IDS - Cleanup & Shutdown"

# Parse arguments
DRY_RUN=0
FULL_CLEANUP=0
while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)  DRY_RUN=1; shift ;;
        --all)      FULL_CLEANUP=1; shift ;;
        --help)     print_help "cleanup.sh [--dry-run] [--all]"; exit 0 ;;
        *)          die "Unknown option: $1" ;;
    esac
done

ensure_root

log_section "PHASE 1: Pre-Cleanup Verification"
ensure_kubeconfig

if [[ $DRY_RUN -eq 1 ]]; then
    log_warn "DRY-RUN MODE: No changes will be made"
fi

# Confirmation
echo ""
if [[ $FULL_CLEANUP -eq 1 ]]; then
    confirm_destructive "This will DELETE all K3s data including databases, deployments, and volumes." || die "Cleanup cancelled"
else
    confirm "Proceed with cleanup?" || die "Cleanup cancelled"
fi

log_section "PHASE 2: Stopping Port Forwards"
if [[ $DRY_RUN -eq 0 ]]; then
    pkill_safe "kubectl port-forward.*ids-api"
    rm -f /tmp/ids-api-portforward.pid /tmp/ids-api-portforward.log 2>/dev/null || true
    log_info "Port forwards stopped"
else
    log_warn "[DRY-RUN] Would stop port forwards"
fi

log_section "PHASE 3: Deleting Kubernetes Resources"
if [[ $DRY_RUN -eq 0 ]]; then
    for ns in smart-city monitoring falco-system ingress-nginx kube-system; do
        if kubectl get namespace "$ns" &>/dev/null 2>&1; then
            log_info "Deleting namespace: $ns"
            kubectl delete namespace "$ns" --ignore-not-found=true --wait=true 2>/dev/null || true
        fi
    done
    sleep 3
    log_info "All namespaces deleted"
else
    log_warn "[DRY-RUN] Would delete namespaces: smart-city monitoring falco-system"
fi

log_section "PHASE 4: Stopping K3s Services"
if [[ $DRY_RUN -eq 0 ]]; then
    log_info "Stopping K3s server..."
    systemctl stop k3s 2>/dev/null || true
    pkill_safe "k3s server" "TERM"
    sleep 2
    log_info "K3s stopped"
else
    log_warn "[DRY-RUN] Would stop K3s server"
fi

log_section "PHASE 5: Data Cleanup"
if [[ $FULL_CLEANUP -eq 1 ]]; then
    if [[ $DRY_RUN -eq 0 ]]; then
        log_warn "Removing K3s data directory..."
        rm -rf /var/lib/rancher/k3s 2>/dev/null || true
        rm -rf /var/log/pods 2>/dev/null || true
        log_info "K3s data removed"
    else
        log_warn "[DRY-RUN] Would remove /var/lib/rancher/k3s"
    fi
else
    log_info "K3s data preserved (can restart with existing data)"
    if [[ $DRY_RUN -eq 0 ]]; then
        log_info "To remove all data, run: sudo bash scripts/cleanup.sh --all"
    fi
fi

log_section "PHASE 6: Cleanup Verification"
if [[ $DRY_RUN -eq 0 ]]; then
    sleep 1
    if ! pgrep -f "k3s server" &>/dev/null; then
        log_info "✅ K3s successfully stopped"
    else
        log_warn "K3s processes still running"
    fi
    
    if ! pgrep -f "kubectl port-forward" &>/dev/null; then
        log_info "✅ All port forwards stopped"
    fi
else
    log_warn "[DRY-RUN] No verification performed"
fi

echo ""
if [[ $DRY_RUN -eq 1 ]]; then
    log_info "Dry-run complete. Run without --dry-run to apply changes."
else
    log_info "✅ Cleanup complete"
    echo ""
    echo "To restart the system:"
    echo "  sudo bash scripts/start-everything.sh"
fi
echo ""
