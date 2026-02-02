#!/bin/bash

GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=========================================="
echo "  SMART CITY IDS - SYSTEM CHECK"
echo -e "==========================================${NC}\n"

echo -e "${BLUE}1. KUBERNETES CLUSTER${NC}"
kubectl get nodes
echo ""

echo -e "${BLUE}2. SMART CITY SERVICES${NC}"
kubectl get pods -n smart-city
SMART_COUNT=$(kubectl get pods -n smart-city --no-headers 2>/dev/null | grep -c Running)
echo "Running: $SMART_COUNT pods"
echo ""

echo -e "${BLUE}3. FALCO SECURITY${NC}"
kubectl get pods -n falco-system
echo ""

echo -e "${BLUE}4. SURICATA NETWORK IDS${NC}"
kubectl get pods -n suricata-system
echo ""

echo -e "${BLUE}5. MONITORING${NC}"
kubectl get pods -n monitoring
echo ""

echo -e "${GREEN}=========================================="
echo "  SUMMARY"
echo -e "==========================================${NC}"
echo "Smart City: $SMART_COUNT pods"
echo "Falco: $(kubectl get pods -n falco-system --no-headers 2>/dev/null | grep -c Running) pods"
echo "Suricata: $(kubectl get pods -n suricata-system --no-headers 2>/dev/null | grep -c Running) pods"
echo "Monitoring: $(kubectl get pods -n monitoring --no-headers 2>/dev/null | grep -c Running) pods"
echo ""

if [[ $SMART_COUNT -ge 12 ]]; then
    echo -e "${GREEN}✅ SYSTEM READY FOR DEMO!${NC}"
else
    echo -e "${RED}⚠️  Some services not running${NC}"
fi
