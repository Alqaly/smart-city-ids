#!/bin/bash
# =============================================================================
# Smart City IDS - Cleanup & Shutdown Script
# Professional cleanup with safety checks, reversible modes, and verification.
#
# Modes:
#   --light   Delete namespaces and port-forwards only. Keep K3s and registry.
#   --full    Full wipe: namespaces + K3s stop + data dirs removed.
#   (default) Stop K3s + delete namespaces but preserve K3s data dirs.
#
# Usage:
#   sudo bash scripts/cleanup.sh                # standard cleanup
#   sudo bash scripts/cleanup.sh --light        # light cleanup (classroom-safe)
#   sudo bash scripts/cleanup.sh --full         # full wipe
#   sudo bash scripts/cleanup.sh --dry-run      # preview what would happen
#   sudo bash scripts/cleanup.sh --force        # skip confirmation prompts
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/script-utils.sh"

init_script "$0" "Smart City IDS - Cleanup & Shutdown"

# Parse arguments
DRY_RUN=0
MODE="standard"  # light | standard | full
FORCE=0

while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)  DRY_RUN=1; shift ;;
        --light)    MODE="light"; shift ;;
        --full)     MODE="full"; shift ;;
        --all)      MODE="full"; shift ;;   # backward compat
        --force)    FORCE=1; shift ;;
        --help)     print_help "cleanup.sh [--light|--full] [--dry-run] [--force]"; exit 0 ;;
        *)          die "Unknown option: $1" ;;
    esac
done

ensure_root

log_section "Cleanup Mode: ${MODE^^}"

# ── Explain what each mode does ──
case "$MODE" in
    light)
        echo ""
        echo "  LIGHT cleanup will:"
        echo "    - Stop all kubectl port-forwards"
        echo "    - Delete K8s namespaces: smart-city, monitoring, falco-system"
        echo "    - Leave K3s running and all data intact"
        echo "    - Safe to re-deploy with:  sudo bash scripts/start-everything.sh"
        echo ""
        ;;
    standard)
        echo ""
        echo "  STANDARD cleanup will:"
        echo "    - Stop all kubectl port-forwards"
        echo "    - Delete K8s namespaces: smart-city, monitoring, falco-system"
        echo "    - Stop K3s server"
        echo "    - Preserve K3s data (can restart with existing data)"
        echo ""
        ;;
    full)
        echo ""
        echo "  FULL cleanup will:"
        echo "    - Stop all kubectl port-forwards"
        echo "    - Delete K8s namespaces: smart-city, monitoring, falco-system"
        echo "    - Stop K3s server"
        echo "    - REMOVE all K3s data (/var/lib/rancher/k3s, /var/log/pods)"
        echo "    - REMOVE persistent storage (/mnt/smart-city)"
        echo "    - Full re-install required after this"
        echo ""
        ;;
esac

if [[ $DRY_RUN -eq 1 ]]; then
    log_warn "DRY-RUN MODE: No changes will be made"
fi

# Confirmation (unless --force)
if [[ $FORCE -eq 0 && $DRY_RUN -eq 0 ]]; then
    if [[ "$MODE" == "full" ]]; then
        confirm_destructive "This will DELETE all K3s data including databases, deployments, and volumes." || die "Cleanup cancelled"
    else
        confirm "Proceed with ${MODE} cleanup?" || die "Cleanup cancelled"
    fi
fi

# ── Phase 1: Stop port-forwards (all modes) ──
log_section "PHASE 1: Stopping Port Forwards"
if [[ $DRY_RUN -eq 0 ]]; then
    pkill_safe "kubectl port-forward.*ids-api"
    pkill_safe "kubectl port-forward.*grafana" 2>/dev/null || true
    pkill_safe "kubectl port-forward.*prometheus" 2>/dev/null || true
    rm -f /tmp/ids-api-portforward.pid /tmp/ids-api-portforward.log 2>/dev/null || true
    rm -f /tmp/smart-city-ids/pf-*.pid 2>/dev/null || true
    log_info "Port forwards stopped"
else
    log_warn "[DRY-RUN] Would stop all port-forwards"
fi

# ── Phase 2: Delete namespaces (all modes) ──
log_section "PHASE 2: Deleting Kubernetes Resources"
ensure_kubeconfig
if [[ $DRY_RUN -eq 0 ]]; then
    for ns in smart-city monitoring falco-system; do
        if kubectl get namespace "$ns" &>/dev/null 2>&1; then
            log_info "Deleting namespace: $ns"
            kubectl delete namespace "$ns" --ignore-not-found=true --wait=false 2>/dev/null || true
        else
            log_info "Namespace $ns not found — skipping"
        fi
    done
    sleep 3
    log_info "Namespace deletion initiated"
else
    log_warn "[DRY-RUN] Would delete namespaces: smart-city, monitoring, falco-system"
fi

# ── Light mode stops here ──
if [[ "$MODE" == "light" ]]; then
    log_section "Light Cleanup Complete"
    if [[ $DRY_RUN -eq 0 ]]; then
        log_info "K3s is still running. Namespaces and port-forwards removed."
        echo ""
        echo "To re-deploy:"
        echo "  sudo bash scripts/start-everything.sh"
    else
        log_warn "[DRY-RUN] Would keep K3s running"
    fi
    echo ""
    exit 0
fi

# ── Phase 3: Stop K3s (standard + full) ──
log_section "PHASE 3: Stopping K3s Services"
if [[ $DRY_RUN -eq 0 ]]; then
    log_info "Stopping K3s server..."
    systemctl stop k3s 2>/dev/null || true
    pkill_safe "k3s server" "TERM"
    sleep 2
    log_info "K3s stopped"
else
    log_warn "[DRY-RUN] Would stop K3s server"
fi

# ── Phase 4: Data cleanup (full mode only) ──
log_section "PHASE 4: Data Cleanup"
if [[ "$MODE" == "full" ]]; then
    if [[ $DRY_RUN -eq 0 ]]; then
        log_warn "Removing K3s data directory..."
        rm -rf /var/lib/rancher/k3s 2>/dev/null || true
        rm -rf /var/log/pods 2>/dev/null || true
        rm -rf /mnt/smart-city 2>/dev/null || true
        log_info "K3s data, logs, and persistent storage removed"
    else
        log_warn "[DRY-RUN] Would remove /var/lib/rancher/k3s, /var/log/pods, /mnt/smart-city"
    fi
else
    log_info "K3s data preserved (mode=standard). Can restart with existing data."
    if [[ $DRY_RUN -eq 0 ]]; then
        log_info "For full wipe: sudo bash scripts/cleanup.sh --full"
    fi
fi

# ── Phase 5: Cleanup verification ──
log_section "PHASE 5: Cleanup Verification"
if [[ $DRY_RUN -eq 0 ]]; then
    sleep 1
    if ! pgrep -f "k3s server" &>/dev/null; then
        log_info "K3s successfully stopped"
    else
        if [[ "$MODE" == "light" ]]; then
            log_info "K3s still running (expected in light mode)"
        else
            log_warn "K3s processes still running — may need manual kill"
        fi
    fi

    if ! pgrep -f "kubectl port-forward" &>/dev/null; then
        log_info "All port-forwards stopped"
    fi
else
    log_warn "[DRY-RUN] No verification performed"
fi

echo ""
if [[ $DRY_RUN -eq 1 ]]; then
    log_info "Dry-run complete. Run without --dry-run to apply changes."
else
    log_info "Cleanup complete (mode: ${MODE})"
    echo ""
    echo "To restart the system:"
    echo "  sudo bash scripts/start-everything.sh"
fi
echo ""
