#!/bin/bash

echo "🚨 Generating Multiple Security Event Types..."

# Get a pod to test with
TEST_POD=$(kubectl get pods -n smart-city -l app=iot-device -o jsonpath='{.items[0].metadata.name}')

echo "Using pod: $TEST_POD"
echo ""

# 1. PRIVILEGE ESCALATION ATTEMPT
echo "1. 🔓 Privilege Escalation Attempt"
kubectl exec -n smart-city $TEST_POD -c iot-sensor -- sh -c 'sudo cat /etc/shadow 2>/dev/null || echo "Command blocked"'
echo ""

# 2. SUSPICIOUS PROCESS EXECUTION  
echo "2. ⚡ Suspicious Process Execution"
kubectl exec -n smart-city $TEST_POD -c iot-sensor -- sh -c 'curl -s http://google.com > /dev/null && echo "Network connection made"'
echo ""

# 3. FILE SYSTEM TAMPERING
echo "3. 📁 File System Tampering"
kubectl exec -n smart-city $TEST_POD -c iot-sensor -- sh -c 'touch /tmp/malicious_file && echo "File created in /tmp"'
echo ""

# 4. NETWORK SCAN ATTEMPT
echo "4. 🌐 Network Scan Simulation"
kubectl exec -n smart-city $TEST_POD -c iot-sensor -- sh -c 'ping -c 2 8.8.8.8 > /dev/null && echo "External network access"'
echo ""

# 5. CONTAINER ESCAPE ATTEMPT
echo "5. 🏃 Container Escape Attempt"
kubectl exec -n smart-city $TEST_POD -c iot-sensor -- sh -c 'ls /proc/1/root/etc/passwd > /dev/null && echo "Host filesystem access attempted"'
echo ""

# 6. CRYPTO MINING SUSPICION
echo "6. ⛏️ Crypto Mining Suspicion"
kubectl exec -n smart-city $TEST_POD -c iot-sensor -- sh -c 'echo "Simulating high CPU usage" && dd if=/dev/zero of=/dev/null bs=1M count=10 2>/dev/null'
echo ""

echo "✅ Multiple security event types generated!"
echo "Check Falco logs: kubectl logs -n falco-system -l app=falco --tail=20"

