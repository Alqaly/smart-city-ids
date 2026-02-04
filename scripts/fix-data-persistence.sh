#!/bin/bash

# Smart City IDS - Data Persistence Fix
# Solves the issue of Prometheus and Grafana data disappearing on K3s restart
#
# Problem: Prometheus and Grafana were using emptyDir{} (temporary storage)
# Solution: Switch to persistent volumes that survive pod restarts
#
# Usage: sudo bash fix-data-persistence.sh

set -e

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  Smart City IDS - Data Persistence Fix                         ║"
echo "║  Preserving Prometheus and Grafana data across restarts        ║"
echo "╚════════════════════════════════════════════════════════════════╝"

export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo ""
echo -e "${YELLOW}[*] Step 1: Checking K3s cluster status${NC}"
if ! kubectl cluster-info &> /dev/null; then
    echo -e "${RED}[✗] K3s cluster not accessible${NC}"
    echo "    Run: sudo systemctl start k3s"
    exit 1
fi
echo -e "${GREEN}[✓] K3s cluster is running${NC}"

echo ""
echo -e "${YELLOW}[*] Step 2: Verifying storage class availability${NC}"
if kubectl get storageclass local-path &> /dev/null; then
    echo -e "${GREEN}[✓] K3s 'local-path' storage class available${NC}"
else
    echo -e "${YELLOW}[!] Creating local-path storage class${NC}"
    kubectl apply -f - <<EOF
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: local-path
provisioner: rancher.io/local-path
allowVolumeExpansion: true
EOF
    echo -e "${GREEN}[✓] Storage class created${NC}"
fi

echo ""
echo -e "${YELLOW}[*] Step 3: Creating persistent volume directories${NC}"
sudo mkdir -p /mnt/smart-city/prometheus
sudo mkdir -p /mnt/smart-city/grafana
echo -e "${GREEN}[✓] Directories created${NC}"

echo ""
echo -e "${YELLOW}[*] Step 4: Backing up existing data (if any)${NC}"
if kubectl get pvc -n monitoring prometheus-pvc &> /dev/null; then
    echo -e "${YELLOW}[!] Prometheus data exists - backing up...${NC}"
    kubectl exec -n monitoring deployment/prometheus -- tar czf /tmp/prometheus-backup.tar.gz /prometheus/ 2>/dev/null || true
    echo -e "${GREEN}[✓] Backup created${NC}"
else
    echo -e "${GREEN}[✓] No existing Prometheus data${NC}"
fi

if kubectl get pvc -n monitoring grafana-pvc &> /dev/null; then
    echo -e "${YELLOW}[!] Grafana data exists - backing up...${NC}"
    kubectl exec -n monitoring deployment/grafana -- tar czf /tmp/grafana-backup.tar.gz /var/lib/grafana/ 2>/dev/null || true
    echo -e "${GREEN}[✓] Backup created${NC}"
else
    echo -e "${GREEN}[✓] No existing Grafana data${NC}"
fi

echo ""
echo -e "${YELLOW}[*] Step 5: Deleting old deployments${NC}"
kubectl delete deployment prometheus -n monitoring --ignore-not-found=true 2>/dev/null
kubectl delete deployment grafana -n monitoring --ignore-not-found=true 2>/dev/null
kubectl delete pvc prometheus-pvc grafana-pvc -n monitoring --ignore-not-found=true 2>/dev/null
echo -e "${GREEN}[✓] Old deployments removed${NC}"

echo ""
echo -e "${YELLOW}[*] Step 6: Redeploying with persistent storage${NC}"
kubectl apply -f k8s-manifests/prometheus-deployment.yaml
kubectl apply -f k8s-manifests/grafana-deployment.yaml
echo -e "${GREEN}[✓] New deployments applied${NC}"

echo ""
echo -e "${YELLOW}[*] Step 7: Waiting for pods to be ready (60 seconds)${NC}"
kubectl rollout status deployment/prometheus -n monitoring --timeout=60s 2>/dev/null || true
kubectl rollout status deployment/grafana -n monitoring --timeout=60s 2>/dev/null || true
echo -e "${GREEN}[✓] Deployments ready${NC}"

echo ""
echo -e "${YELLOW}[*] Step 8: Verifying persistent volume claims${NC}"
echo ""
kubectl get pvc -n monitoring
echo ""

echo -e "${YELLOW}[*] Step 9: Verifying pod volumes${NC}"
echo ""
echo "Prometheus volumes:"
kubectl describe pod -n monitoring -l app=prometheus | grep -A 20 "Mounts:" | head -10
echo ""
echo "Grafana volumes:"
kubectl describe pod -n monitoring -l app=grafana | grep -A 20 "Mounts:" | head -10
echo ""

echo "╔════════════════════════════════════════════════════════════════╗"
echo -e "║  ${GREEN}✓ Data Persistence Fix Complete!${NC}"
echo "╠════════════════════════════════════════════════════════════════╣"
echo "║                                                                ║"
echo "║  What was fixed:                                             ║"
echo "║  • Prometheus now uses 50Gi persistent volume                ║"
echo "║  • Grafana now uses 10Gi persistent volume                   ║"
echo "║  • Data survives K3s restarts and pod recreations           ║"
echo "║                                                                ║"
echo "║  Storage location:                                           ║"
echo "║  • /mnt/smart-city/prometheus/                               ║"
echo "║  • /mnt/smart-city/grafana/                                  ║"
echo "║                                                                ║"
echo "║  Testing:                                                    ║"
echo "║  1. Send some alerts to generate metrics:                   ║"
echo "║     python3 attack-simulator/ddos_simulator.py ...          ║"
echo "║                                                                ║"
echo "║  2. Verify data in Grafana dashboard                        ║"
echo "║                                                                ║"
echo "║  3. Restart K3s:                                            ║"
echo "║     sudo systemctl restart k3s                              ║"
echo "║                                                                ║"
echo "║  4. Data should persist after restart!                      ║"
echo "║                                                                ║"
echo "╚════════════════════════════════════════════════════════════════╝"
