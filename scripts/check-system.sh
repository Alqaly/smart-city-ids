#!/bin/bash
# =============================================================================
# Smart City IDS - System Health Check
# Verifies all components are running and shows access URLs
# Usage: ./scripts/check-system.sh
# =============================================================================

set -euo pipefail

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Get node IP for URLs
NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}' 2>/dev/null || echo "localhost")

echo -e "${CYAN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║         SMART CITY IDS - SYSTEM HEALTH CHECK                   ║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# 1. KUBERNETES CLUSTER
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}┌─ 1. KUBERNETES CLUSTER ─────────────────────────────────────────┐${NC}"
kubectl get nodes -o wide 2>/dev/null || echo -e "${RED}❌ Cannot connect to cluster${NC}"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# 2. SMART CITY SERVICES
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}┌─ 2. SMART CITY SERVICES (namespace: smart-city) ────────────────┐${NC}"
kubectl get pods -n smart-city -o wide 2>/dev/null || echo "Namespace not found"

SMART_RUNNING=$(kubectl get pods -n smart-city --no-headers 2>/dev/null | grep -c "Running" || echo "0")
SMART_TOTAL=$(kubectl get pods -n smart-city --no-headers 2>/dev/null | wc -l || echo "0")

echo ""
echo -e "   ${GREEN}Running:${NC} $SMART_RUNNING / $SMART_TOTAL pods"

# Count by service type
IDS_API=$(kubectl get pods -n smart-city -l app=ids-api --no-headers 2>/dev/null | grep -c "Running" || echo "0")
TRAFFIC=$(kubectl get pods -n smart-city -l app=traffic-camera --no-headers 2>/dev/null | grep -c "Running" || echo "0")
HEALTHCARE=$(kubectl get pods -n smart-city -l app=healthcare-api --no-headers 2>/dev/null | grep -c "Running" || echo "0")
PARKING=$(kubectl get pods -n smart-city -l app=parking-system --no-headers 2>/dev/null | grep -c "Running" || echo "0")
POSTGRES=$(kubectl get pods -n smart-city -l app=postgres --no-headers 2>/dev/null | grep -c "Running" || echo "0")
MQTT=$(kubectl get pods -n smart-city -l app=mqtt-broker --no-headers 2>/dev/null | grep -c "Running" || echo "0")
IOT=$(kubectl get pods -n smart-city -l app=iot-device --no-headers 2>/dev/null | grep -c "Running" || echo "0")

echo ""
echo -e "   ${CYAN}Service Breakdown:${NC}"
echo "   ├── IDS API:        $IDS_API pod(s)"
echo "   ├── Traffic Camera: $TRAFFIC pod(s)"
echo "   ├── Healthcare API: $HEALTHCARE pod(s)"
echo "   ├── Parking System: $PARKING pod(s)"
echo "   ├── PostgreSQL:     $POSTGRES pod(s)"
echo "   ├── MQTT Broker:    $MQTT pod(s)"
echo "   └── IoT Devices:    $IOT pod(s)"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# 3. FALCO RUNTIME SECURITY
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}┌─ 3. FALCO RUNTIME SECURITY (namespace: falco-system) ───────────┐${NC}"
kubectl get pods -n falco-system 2>/dev/null || echo "Falco not deployed"

FALCO_RUNNING=$(kubectl get pods -n falco-system --no-headers 2>/dev/null | grep -c "Running" || echo "0")
FORWARDER_RUNNING=$(kubectl get pods -n falco-system -l app=falco-forwarder --no-headers 2>/dev/null | grep -c "Running" || echo "0")

echo ""
echo -e "   ${GREEN}Falco:${NC} $FALCO_RUNNING pod(s) | ${GREEN}Forwarder:${NC} $FORWARDER_RUNNING pod(s)"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# 4. SURICATA NETWORK IDS
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}┌─ 4. SURICATA NETWORK IDS (namespace: suricata-system) ──────────┐${NC}"
kubectl get pods -n suricata-system 2>/dev/null || echo "Suricata not deployed"

SURICATA_RUNNING=$(kubectl get pods -n suricata-system --no-headers 2>/dev/null | grep -c "Running" || echo "0")
echo ""
echo -e "   ${GREEN}Suricata:${NC} $SURICATA_RUNNING pod(s)"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# 5. MONITORING STACK
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}┌─ 5. MONITORING STACK (namespace: monitoring) ──────────────────┐${NC}"
kubectl get pods -n monitoring 2>/dev/null || echo "Monitoring not deployed"

PROMETHEUS=$(kubectl get pods -n monitoring -l app=prometheus --no-headers 2>/dev/null | grep -c "Running" || echo "0")
GRAFANA=$(kubectl get pods -n monitoring -l app=grafana --no-headers 2>/dev/null | grep -c "Running" || echo "0")

echo ""
echo -e "   ${GREEN}Prometheus:${NC} $PROMETHEUS pod(s) | ${GREEN}Grafana:${NC} $GRAFANA pod(s)"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# 6. ACCESS URLS
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}┌─ 6. ACCESS URLS ────────────────────────────────────────────────┐${NC}"
echo ""
echo -e "   ${CYAN}IDS API:${NC}      http://${NODE_IP}:30800"
echo -e "   ${CYAN}IDS API Docs:${NC} http://${NODE_IP}:30800/docs"
echo -e "   ${CYAN}Grafana:${NC}      http://${NODE_IP}:30300  (admin/admin)"
echo -e "   ${CYAN}Prometheus:${NC}   http://${NODE_IP}:31701"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${CYAN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║                         SUMMARY                                ║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

if [[ "$IDS_API" -ge 1 ]] && [[ "$FALCO_RUNNING" -ge 1 ]] && [[ "$FORWARDER_RUNNING" -ge 1 ]]; then
    echo -e "   ${GREEN}✅ CORE PIPELINE READY${NC}"
    echo "      IDS API → Falco → Forwarder → Detection Chain"
else
    echo -e "   ${RED}❌ CORE PIPELINE INCOMPLETE${NC}"
    [[ "$IDS_API" -lt 1 ]] && echo "      Missing: IDS API"
    [[ "$FALCO_RUNNING" -lt 1 ]] && echo "      Missing: Falco"
    [[ "$FORWARDER_RUNNING" -lt 1 ]] && echo "      Missing: Falco Forwarder"
fi

echo ""

if [[ "$GRAFANA" -ge 1 ]] && [[ "$PROMETHEUS" -ge 1 ]]; then
    echo -e "   ${GREEN}✅ MONITORING READY${NC}"
else
    echo -e "   ${YELLOW}⚠️  MONITORING INCOMPLETE${NC}"
fi

echo ""

if [[ "$SMART_RUNNING" -ge 10 ]]; then
    echo -e "   ${GREEN}✅ SYSTEM READY FOR DEMO${NC}"
else
    echo -e "   ${YELLOW}⚠️  Some services not running ($SMART_RUNNING pods)${NC}"
fi

echo ""
echo -e "${BLUE}─────────────────────────────────────────────────────────────────${NC}"
echo ""
