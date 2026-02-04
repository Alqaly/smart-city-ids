#!/bin/bash
# =============================================================================
# Smart City IDS - K3s Dynamic IP Configuration
# Auto-detects node IP and fixes kubeconfig for network changes
# Usage: bash scripts/k3s-dynamic-ip.sh [--verbose] [--help]
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")}" && pwd)"
source "$SCRIPT_DIR/lib/script-utils.sh"

init_script "$0" "K3s Dynamic IP Configuration"

K3S_KUBECONFIG="/etc/rancher/k3s/k3s.yaml"
LOCAL_KUBECONFIG="$HOME/.kube/config"
LOGFILE="/var/log/k3s-dynamic-ip.log"

ensure_root
ensure_file "$K3S_KUBECONFIG"

log_section "DETECTING NODE IP"

# Detect real IP (exclude loopback, docker, etc)
NODE_IP=$(ip -4 addr show scope global up 2>/dev/null | \
    grep -v ' lo ' | grep -v ' docker' | \
    awk '/inet / {print $2}' | cut -d/ -f1 | head -n1)

if [[ -z "$NODE_IP" ]]; then
    die "Could not detect valid node IP"
fi

log_info "Detected IP: $NODE_IP"
echo "$(date '+%Y-%m-%d %H:%M:%S') - Detected IP: $NODE_IP" >> "$LOGFILE"
echo ""

log_section "UPDATING KUBECONFIG"

mkdir -p "$(dirname "$LOCAL_KUBECONFIG")"
cp "$K3S_KUBECONFIG" "$LOCAL_KUBECONFIG"
chown "$(id -u):$(id -g)" "$LOCAL_KUBECONFIG"

# Update server address
sed -i "s|server: https://.*:6443|server: https://$NODE_IP:6443|g" "$LOCAL_KUBECONFIG"
log_info "Updated kubeconfig: https://$NODE_IP:6443"
echo ""

log_section "VERIFYING CONNECTION"

export KUBECONFIG="$LOCAL_KUBECONFIG"

if kubectl get nodes >/dev/null 2>&1; then
    log_info "✅ Cluster is reachable"
    kubectl get nodes -o wide
    echo "$(date '+%Y-%m-%d %H:%M:%S') - SUCCESS: Cluster reachable at $NODE_IP" >> "$LOGFILE"
else
    log_error "Could not reach cluster"
    echo "$(date '+%Y-%m-%d %H:%M:%S') - FAILED: Could not reach cluster" >> "$LOGFILE"
    exit 1
fi
echo ""
log_info "✅ Configuration complete"
