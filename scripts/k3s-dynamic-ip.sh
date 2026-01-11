#!/usr/bin/env bash
# ------------------------------------------------------------
# k3s-dynamic-ip.sh
# Purpose: Auto-detect REAL node IP (not 127.0.0.1) and fix kubeconfig
# Works on: Kali, Ubuntu, WSL2, laptops, WiFi changes
# ------------------------------------------------------------
set -euo pipefail

K3S_KUBECONFIG="/etc/rancher/k3s/k3s.yaml"
LOCAL_KUBECONFIG="$HOME/.kube/config"
LOGFILE="/var/log/k3s-dynamic-ip.log"
timestamp() { date '+%Y-%m-%d %H:%M:%S'; }

echo "$(timestamp) - Starting k3s-dynamic-ip" >> "$LOGFILE"

# === 1. DETECT REAL IP (SKIP loopback, docker, WSL fake) ===
NODE_IP=$(ip -4 addr show scope global up \
  | grep -v ' lo ' \
  | grep -v ' docker' \
  | awk '/inet / {print $2}' | cut -d/ -f1 | head -n1)

if [ -z "$NODE_IP" ]; then
  echo "$(timestamp) - ❌ ERROR: No valid IP found" | tee -a "$LOGFILE"
  exit 1
fi

echo "$(timestamp) - ✅ Detected node IP: $NODE_IP" | tee -a "$LOGFILE"

# === 2. Fix kubeconfig ===
if [ ! -f "$K3S_KUBECONFIG" ]; then
  echo "$(timestamp) - ❌ ERROR: $K3S_KUBECONFIG missing" | tee -a "$LOGFILE"
  exit 1
fi

mkdir -p "$(dirname "$LOCAL_KUBECONFIG")"
sudo cp "$K3S_KUBECONFIG" "$LOCAL_KUBECONFIG"
sudo chown "$(id -u):$(id -g)" "$LOCAL_KUBECONFIG"

# Replace ANY server with correct IP
sed -i "s|server: https://.*:6443|server: https://$NODE_IP:6443|g" "$LOCAL_KUBECONFIG"

echo "$(timestamp) - 🔄 Updated kubeconfig → https://$NODE_IP:6443" | tee -a "$LOGFILE"

# === 3. Set KUBECONFIG and test ===
export KUBECONFIG="$LOCAL_KUBECONFIG"
if kubectl get nodes >/dev/null 2>&1; then
  echo "$(timestamp) - ✅ kubectl WORKS! Cluster reachable" | tee -a "$LOGFILE"
  kubectl get nodes -o wide | tee -a "$LOGFILE"
else
  echo "$(timestamp) - ⚠️ kubectl FAILED → check K3s status" | tee -a "$LOGFILE"
fi
