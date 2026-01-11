#!/bin/bash

# 🎯 Smart City IDS - Attack Simulation Runner
# Runs all attack scenarios for demonstration

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

echo "🎯 Smart City IDS - Attack Simulation Suite"
echo "==========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo -e "${RED}❌ kubectl not found. Please install kubectl.${NC}"
    exit 1
fi

# Check if pods are running
PODS=$(kubectl get pods -n smart-city 2>/dev/null | grep -c "Running" || echo "0")
if [ "$PODS" -eq 0 ]; then
    echo -e "${RED}❌ No running pods found in smart-city namespace${NC}"
    echo "   Run ./scripts/start-everything.sh first"
    exit 1
fi

# Function to setup port forwarding
setup_port_forward() {
    local service_name=$1
    local local_port=$2
    local remote_port=$3
    
    echo -e "${YELLOW}⏳ Setting up port-forward for $service_name...${NC}"
    kubectl port-forward -n smart-city svc/$service_name $local_port:$remote_port > /dev/null 2>&1 &
    PF_PID=$!
    sleep 2
}

# Function to cleanup port forwards
cleanup_port_forwards() {
    echo ""
    echo -e "${YELLOW}🧹 Cleaning up port forwards...${NC}"
    pkill -f "kubectl port-forward" 2>/dev/null || true
    sleep 1
}

# Function to check Python requirements
check_requirements() {
    echo -e "${YELLOW}📦 Checking Python requirements...${NC}"
    
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}❌ python3 not found${NC}"
        exit 1
    fi
    
    # Try to import requests
    if ! python3 -c "import requests" 2>/dev/null; then
        echo -e "${YELLOW}📥 Installing Python requirements...${NC}"
        pip3 install -q requests
    fi
    
    echo -e "${GREEN}✅ Requirements OK${NC}"
}

# Main attack scenarios
run_traffic_camera_attacks() {
    echo ""
    echo -e "${YELLOW}═══════════════════════════════════════════${NC}"
    echo -e "${YELLOW}🎬 SCENARIO 1: Traffic Camera Attacks${NC}"
    echo -e "${YELLOW}═══════════════════════════════════════════${NC}"
    echo ""
    
    setup_port_forward "traffic-camera-service" 8001 80
    
    # Give it a moment
    sleep 2
    
    # Check service is accessible
    if curl -s http://localhost:8001/health > /dev/null; then
        echo -e "${GREEN}✅ Traffic Camera Service is accessible${NC}"
        echo ""
        
        # Test 1: Extract camera data
        echo -e "${YELLOW}[Attack 1] Extracting camera data...${NC}"
        RESULT=$(curl -s http://localhost:8001/api/cameras | python3 -m json.tool | head -10)
        echo "$RESULT"
        echo ""
        
        # Test 2: Extract analytics
        echo -e "${YELLOW}[Attack 2] Extracting traffic analytics...${NC}"
        RESULT=$(curl -s http://localhost:8001/api/analytics | python3 -m json.tool | head -15)
        echo "$RESULT"
        echo ""
        
        # Test 3: Modify admin config
        echo -e "${RED}[Attack 3] Modifying admin configuration (NO AUTH!)...${NC}"
        RESULT=$(curl -s -X PUT http://localhost:8001/admin/config \
            -H "Content-Type: application/json" \
            -d '{"recording_enabled": false, "alert_threshold": 0.1}' \
            | python3 -m json.tool)
        echo "$RESULT"
        echo ""
        
        echo -e "${GREEN}✅ Traffic Camera attacks completed${NC}"
    else
        echo -e "${RED}❌ Traffic Camera Service not accessible${NC}"
    fi
}

run_healthcare_attacks() {
    echo ""
    echo -e "${YELLOW}═══════════════════════════════════════════${NC}"
    echo -e "${YELLOW}🎬 SCENARIO 2: Healthcare Data Breach${NC}"
    echo -e "${YELLOW}═══════════════════════════════════════════${NC}"
    echo ""
    
    setup_port_forward "healthcare-api-service" 8002 80
    sleep 2
    
    if curl -s http://localhost:8002/health > /dev/null; then
        echo -e "${GREEN}✅ Healthcare API Service is accessible${NC}"
        echo ""
        
        # Test 1: Extract patient data (HIPAA violation!)
        echo -e "${RED}[Attack 1] HIPAA VIOLATION: Extracting patient data...${NC}"
        RESULT=$(curl -s http://localhost:8002/api/patients | python3 -m json.tool)
        echo "$RESULT"
        echo ""
        
        # Test 2: Add malicious prescription
        echo -e "${RED}[Attack 2] Injection: Adding unauthorized prescription...${NC}"
        RESULT=$(curl -s -X POST http://localhost:8002/api/prescriptions/P001 \
            -H "Content-Type: application/json" \
            -d '{"drug": "PlaceboX", "dosage": "999mg", "duration": "LIFETIME"}' \
            | python3 -m json.tool)
        echo "$RESULT"
        echo ""
        
        echo -e "${GREEN}✅ Healthcare attacks completed${NC}"
    else
        echo -e "${RED}❌ Healthcare API Service not accessible${NC}"
    fi
}

run_parking_attacks() {
    echo ""
    echo -e "${YELLOW}═══════════════════════════════════════════${NC}"
    echo -e "${YELLOW}🎬 SCENARIO 3: Payment System Breach${NC}"
    echo -e "${YELLOW}═══════════════════════════════════════════${NC}"
    echo ""
    
    setup_port_forward "parking-system-service" 8003 80
    sleep 2
    
    if curl -s http://localhost:8003/health > /dev/null; then
        echo -e "${GREEN}✅ Parking System Service is accessible${NC}"
        echo ""
        
        # Test 1: View transactions (no auth!)
        echo -e "${YELLOW}[Attack 1] Unauthorized access to payment transactions...${NC}"
        RESULT=$(curl -s http://localhost:8003/api/transactions | python3 -m json.tool)
        echo "$RESULT"
        echo ""
        
        # Test 2: Send fraudulent payment
        echo -e "${RED}[Attack 2] PCI-DSS VIOLATION: Sending credit card data...${NC}"
        RESULT=$(curl -s -X POST http://localhost:8003/api/payment \
            -H "Content-Type: application/json" \
            -d '{
                "card_number": "4532-1234-5678-9999",
                "cvv": "123",
                "amount": 50.00
            }' | python3 -m json.tool)
        echo "$RESULT"
        echo ""
        
        # Test 3: Access admin panel
        echo -e "${YELLOW}[Attack 3] Accessing admin system status...${NC}"
        RESULT=$(curl -s http://localhost:8003/admin/system-status | python3 -m json.tool)
        echo "$RESULT"
        echo ""
        
        echo -e "${GREEN}✅ Parking attacks completed${NC}"
    else
        echo -e "${RED}❌ Parking System Service not accessible${NC}"
    fi
}

run_ddos_attack() {
    echo ""
    echo -e "${YELLOW}═══════════════════════════════════════════${NC}"
    echo -e "${YELLOW}🎬 SCENARIO 4: DDoS Attack Simulation${NC}"
    echo -e "${YELLOW}═══════════════════════════════════════════${NC}"
    echo ""
    
    setup_port_forward "traffic-camera-service" 8001 80
    sleep 2
    
    if [ -f "attack-simulator/ddos_simulator.py" ]; then
        echo -e "${YELLOW}Running DDoS attack (10 threads, 15 seconds)...${NC}"
        python3 attack-simulator/ddos_simulator.py http://localhost:8001/api/cameras 10 15
    else
        echo -e "${RED}❌ DDoS simulator not found${NC}"
    fi
}

run_data_exfiltration() {
    echo ""
    echo -e "${YELLOW}═══════════════════════════════════════════${NC}"
    echo -e "${YELLOW}🎬 SCENARIO 5: Automated Attack Simulation${NC}"
    echo -e "${YELLOW}═══════════════════════════════════════════${NC}"
    echo ""
    
    if [ -f "attack-simulator/data_exfiltration.py" ]; then
        # Traffic camera attacks
        setup_port_forward "traffic-camera-service" 8001 80
        sleep 2
        
        echo -e "${YELLOW}Running data exfiltration attacks...${NC}"
        python3 attack-simulator/data_exfiltration.py http://localhost:8001
    else
        echo -e "${RED}❌ Data exfiltration simulator not found${NC}"
    fi
}

# Main menu
main_menu() {
    echo ""
    echo -e "${GREEN}════════════════════════════════════════════${NC}"
    echo -e "${GREEN}   Smart City IDS - Attack Simulations${NC}"
    echo -e "${GREEN}════════════════════════════════════════════${NC}"
    echo ""
    echo "Select attack scenario:"
    echo ""
    echo "  1) Traffic Camera Attacks (data extraction, config modification)"
    echo "  2) Healthcare Data Breach (HIPAA violations)"
    echo "  3) Payment System Breach (credit card theft)"
    echo "  4) DDoS Attack Simulation"
    echo "  5) Automated Data Exfiltration"
    echo "  6) Run ALL attacks in sequence"
    echo "  0) Exit"
    echo ""
}

# Main execution
check_requirements

if [ $# -gt 0 ]; then
    # Run specific scenario if provided as argument
    SCENARIO=$1
else
    # Interactive menu
    main_menu
    read -p "Enter your choice [0-6]: " SCENARIO
fi

case $SCENARIO in
    1)
        run_traffic_camera_attacks
        ;;
    2)
        run_healthcare_attacks
        ;;
    3)
        run_parking_attacks
        ;;
    4)
        run_ddos_attack
        ;;
    5)
        run_data_exfiltration
        ;;
    6)
        run_traffic_camera_attacks
        cleanup_port_forwards
        sleep 3
        
        run_healthcare_attacks
        cleanup_port_forwards
        sleep 3
        
        run_parking_attacks
        cleanup_port_forwards
        sleep 3
        
        run_ddos_attack
        cleanup_port_forwards
        sleep 3
        
        run_data_exfiltration
        cleanup_port_forwards
        
        echo ""
        echo -e "${GREEN}✅ All attack scenarios completed!${NC}"
        ;;
    0)
        echo "Exiting..."
        cleanup_port_forwards
        exit 0
        ;;
    *)
        echo -e "${RED}Invalid choice${NC}"
        exit 1
        ;;
esac

# Cleanup
cleanup_port_forwards

echo ""
echo -e "${GREEN}✅ Attack simulations completed!${NC}"
echo ""
echo "Next steps:"
echo "1. Review the IDS dashboard: kubectl port-forward svc/ids-api 8004:5003 -n smart-city"
echo "2. Check pod logs: kubectl logs -f <pod-name> -n smart-city"
echo "3. Monitor system: kubectl top pods -n smart-city"
echo ""
