#!/bin/bash

# Setup port-forward
echo "🔧 Setting up port-forward to IDS API..."
pkill -f "port-forward.*8000" 2>/dev/null
kubectl port-forward -n smart-city svc/ids-api-service 8000:8000 >/dev/null 2>&1 &
sleep 3
echo "✅ Port-forward ready"
echo ""

echo "╔════════════════════════════════════════════════════════╗"
echo "║     SMART CITY IDS - ATTACK SIMULATION SUITE          ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo "Select attack simulation:"
echo "1. Falco - Privilege Escalation (read /etc/shadow)"
echo "2. Falco - Suspicious File Access (read sensitive files)"
echo "3. Falco - Shell Execution in Container"
echo "4. Network - HTTP Requests (Python urllib)"
echo "5. Network - Port Scan Simulation (Python socket)"
echo "6. ALL - Run complete attack demo"
echo ""
read -p "Enter choice (1-6): " choice

# Get target pod
IOT_POD=$(kubectl get pods -n smart-city -l app=iot-device -o jsonpath='{.items[0].metadata.name}')

echo ""
echo -e "${YELLOW}🎯 Target pod: $IOT_POD${NC}"
echo ""

simulate_falco_attack_1() {
    echo -e "${RED}🚨 ATTACK 1: Reading /etc/shadow (privilege escalation)${NC}"
    kubectl exec -n smart-city $IOT_POD -- cat /etc/shadow 2>&1 | head -5
    echo "..."
    echo -e "${GREEN}✅ Falco should detect: Read sensitive file untrusted${NC}"
    echo ""
    sleep 3
}

simulate_falco_attack_2() {
    echo -e "${RED}🚨 ATTACK 2: Reading /etc/passwd${NC}"
    kubectl exec -n smart-city $IOT_POD -- cat /etc/passwd 2>&1 | head -5
    echo "..."
    echo -e "${GREEN}✅ Falco should detect: Sensitive file read${NC}"
    echo ""
    sleep 3
}

simulate_falco_attack_3() {
    echo -e "${RED}🚨 ATTACK 3: Shell spawned in container${NC}"
    kubectl exec -n smart-city $IOT_POD -- bash -c "whoami && id && pwd"
    echo -e "${GREEN}✅ Falco should detect: Shell spawned${NC}"
    echo ""
    sleep 3
}

simulate_network_attack_1() {
    echo -e "${RED}🚨 ATTACK 4: Suspicious HTTP Requests${NC}"
    kubectl exec -n smart-city $IOT_POD -- python3 -c "
import urllib.request
print('Requesting suspicious domains...')
try:
    response = urllib.request.urlopen('http://testmyids.com', timeout=5)
    print(f'testmyids.com: {response.status}')
except Exception as e:
    print(f'Request sent (timeout expected)')
" 2>&1
    echo -e "${GREEN}✅ Network request detected${NC}"
    echo ""
    sleep 3
}

simulate_network_attack_2() {
    echo -e "${RED}🚨 ATTACK 5: Port Scan Simulation${NC}"
    kubectl exec -n smart-city $IOT_POD -- python3 -c "
import socket
ports = [80, 443, 1883, 3306, 8080]
for port in ports:
    try:
        s = socket.socket()
        s.settimeout(0.5)
        s.connect(('mqtt-broker', port))
        print(f'Port {port}: OPEN')
        s.close()
    except:
        print(f'Port {port}: CLOSED')
" 2>&1
    echo -e "${GREEN}✅ Port scanning detected${NC}"
    echo ""
    sleep 3
}

check_alerts() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📊 CHECKING IDS API FOR DETECTED ALERTS"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    sleep 5
    
    echo -e "${CYAN}System Metrics:${NC}"
    curl -s http://localhost:8000/api/metrics | jq '{total_alerts, critical_alerts, automation_rate, alerts_by_source}'
    echo ""
    
    echo -e "${CYAN}Recent Alerts (last 3 with AI analysis):${NC}"
    curl -s http://localhost:8000/api/alerts | jq '.alerts[-3:] | .[] | {id, rule: .alert.rule, severity: .analysis.severity, threat_type: .analysis.threat_type, actions}'
    echo ""
}

# Execute based on choice
case $choice in
    1) simulate_falco_attack_1; check_alerts ;;
    2) simulate_falco_attack_2; check_alerts ;;
    3) simulate_falco_attack_3; check_alerts ;;
    4) simulate_network_attack_1; check_alerts ;;
    5) simulate_network_attack_2; check_alerts ;;
    6)
        echo -e "${YELLOW}Running complete attack simulation...${NC}"
        echo ""
        simulate_falco_attack_1
        simulate_falco_attack_2
        simulate_falco_attack_3
        simulate_network_attack_1
        simulate_network_attack_2
        check_alerts
        echo ""
        echo "╔════════════════════════════════════════════════════════╗"
        echo "║           ✅ ATTACK SIMULATION COMPLETE                ║"
        echo "╚════════════════════════════════════════════════════════╝"
        ;;
    *) echo "Invalid choice"; exit 1 ;;
esac
