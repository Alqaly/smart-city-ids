#!/usr/bin/env bash
# =============================================================================
# Smart City IDS - System Check & URL Display
# =============================================================================
# Run after WiFi change, reboot, or to verify system status
# Usage: ./scripts/check-setup.sh
# =============================================================================

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}═══════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  SMART CITY IDS - SYSTEM CHECK${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════${NC}"
echo ""

# Fix K3s permissions first
echo -e "${YELLOW}🔧 Fixing K3s permissions...${NC}"
sudo chmod 644 /etc/rancher/k3s/k3s.yaml 2>/dev/null || true
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

# Check K3s status
echo -e "${YELLOW}🔄 Checking K3s status...${NC}"
if ! systemctl is-active --quiet k3s; then
    echo -e "${RED}⚠️  K3s not running. Starting...${NC}"
    sudo systemctl restart k3s
    sleep 15
    sudo chmod 644 /etc/rancher/k3s/k3s.yaml
fi

# Get current IP
NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}' 2>/dev/null | head -1 | grep -oE '^[0-9.]+' || hostname -I | awk '{print $1}')

echo ""
echo -e "${GREEN}✅ Required Commands:${NC}"
for cmd in python3 kubectl curl jq; do
  if command -v "$cmd" >/dev/null 2>&1; then
    echo -e "   ✅ $cmd"
  else
    echo -e "   ${RED}❌ $cmd not found${NC}"
  fi
done

echo ""
echo -e "${GREEN}✅ API Keys:${NC}"
if [ -n "${XAI_API_KEY:-}" ]; then
  echo -e "   ✅ XAI_API_KEY set"
else
  echo -e "   ${YELLOW}⚠️  XAI_API_KEY not set${NC}"
fi
if [ -n "${OPENAI_API_KEY:-}" ]; then
  echo -e "   ✅ OPENAI_API_KEY set"
else
  echo -e "   ${YELLOW}⚠️  OPENAI_API_KEY not set${NC}"
fi

echo ""
echo -e "${GREEN}✅ Cluster Status:${NC}"
kubectl get nodes 2>/dev/null || echo -e "${RED}   Cannot connect to cluster${NC}"

echo ""
echo -e "${GREEN}✅ Pods (smart-city):${NC}"
kubectl get pods -n smart-city --field-selector=status.phase=Running 2>/dev/null | head -8 || echo -e "${RED}   Cannot get pods${NC}"

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  SERVICE URLs (Current IP: ${NODE_IP})${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "📊 ${GREEN}Grafana:${NC}        http://${NODE_IP}:30300  (admin/admin)"
echo -e "📈 ${GREEN}Prometheus:${NC}     http://${NODE_IP}:31106"
echo -e "🛡️  ${GREEN}IDS API:${NC}        http://${NODE_IP}:30800/health"
echo -e "📋 ${GREEN}Alerts API:${NC}     http://${NODE_IP}:30800/api/alerts"
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  GRAFANA DASHBOARDS${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "   Motion Sensor: http://${NODE_IP}:30300/d/e3f63148-7e88-405a-adfb-8811f6041dc3/motion-sensor-alerts"
echo -e "   IEEE Capstone: http://${NODE_IP}:30300/d/smart-city-ids-ieee"
echo -e "   Smart City:    http://${NODE_IP}:30300/d/smart-city-ids"
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  RASPBERRY PI${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "   ${YELLOW}python3 motion_sensor.py --ids-url http://${NODE_IP}:30800${NC}"
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════${NC}"
echo ""
