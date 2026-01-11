#!/bin/bash

echo "🎓 SMART CITY IDS - COMPLETE DEMO SHOWCASE"
echo "==========================================="

echo ""
echo "1. 🏗️ INFRASTRUCTURE OVERVIEW"
kubectl get pods -n smart-city
echo ""

echo "2. 🛡️ SECURITY STACK STATUS"
kubectl get pods -n falco-system -n monitoring --selector=app.kubernetes.io/name=falco

echo ""
echo "3. 🚨 GENERATING SECURITY EVENTS..."
echo "   This will create multiple attack types for demonstration"

# Generate various security events
./generate-security-events.sh
sleep 2

echo ""
echo "4. 🌐 GENERATING NETWORK ATTACKS..."
./generate-network-attacks.sh  
sleep 2

echo ""
echo "5. 🎯 GENERATING ADVANCED ATTACK SCENARIOS..."
./generate-advanced-attacks.sh
sleep 2

echo ""
echo "6. 📊 LIVE MONITORING DASHBOARD"
echo "   Starting real-time IDS monitoring..."
echo "   Press Ctrl+C to stop monitoring and continue"
echo ""
./monitor-ids-logs.sh

