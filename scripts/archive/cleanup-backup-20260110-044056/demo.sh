#!/bin/bash

GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=============================================="
echo "  SMART CITY LLM-IDS DEMO"
echo -e "==============================================\n${NC}"

echo -e "${GREEN}📊 INFRASTRUCTURE${NC}"
kubectl get pods -n smart-city

echo -e "\n${GREEN}📈 STATISTICS${NC}"
echo "Traffic Cameras: $(kubectl get pods -n smart-city -l app=traffic-camera --no-headers | wc -l)"
echo "Healthcare APIs: $(kubectl get pods -n smart-city -l app=healthcare-api --no-headers | wc -l)"
echo "Parking Systems: $(kubectl get pods -n smart-city -l app=parking-system --no-headers | wc -l)"
echo "IoT Devices: $(kubectl get pods -n smart-city -l app=iot-device --no-headers | wc -l)"
echo "MQTT Broker: $(kubectl get pods -n smart-city -l app=mqtt-broker --no-headers | wc -l)"
echo "TOTAL: $(kubectl get pods -n smart-city --no-headers | wc -l) pods"

echo -e "\n${GREEN}🔌 IOT DEVICE TEST${NC}"
IOT_POD=$(kubectl get pods -n smart-city -l app=iot-device -o jsonpath='{.items[0].metadata.name}')
if [[ -n "$IOT_POD" ]]; then
    pkill -f "port-forward.*5000" 2>/dev/null
    kubectl port-forward -n smart-city $IOT_POD 5000:5000 > /dev/null 2>&1 &
    PF_PID=$!
    sleep 3
    echo "Device: $IOT_POD"
    curl -s http://localhost:5000/status | jq '.'
    curl -s http://localhost:5000/metrics | jq '. | {sent, received, avg_latency}'
    kill $PF_PID 2>/dev/null
fi

echo -e "\n${GREEN}🚨 SECURITY ALERT TEST${NC}"
echo "Triggering: kubectl exec $IOT_POD -- cat /etc/shadow"
kubectl exec -n smart-city $IOT_POD -- cat /etc/shadow 2>&1 | head -n 2

echo -e "\n${GREEN}🛡️  FALCO DETECTION${NC}"
sleep 2
FALCO_POD=$(kubectl get pods -n falco-system -l app.kubernetes.io/name=falco -o jsonpath='{.items[0].metadata.name}')
kubectl logs -n falco-system $FALCO_POD --tail=5 | grep -i "sensitive" || echo "Check: kubectl logs -n falco-system $FALCO_POD"

echo -e "\n${GREEN}✅ DEMO COMPLETE!${NC}"
