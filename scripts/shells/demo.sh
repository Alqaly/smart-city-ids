#!/bin/bash
# SIMPLE CLEAN DEMO - Smart City IDS

echo "======================================================================"
echo "SMART CITY IDS - SIMPLE DEMONSTRATION"
echo "======================================================================"
echo ""

# Step 1: Show baseline
echo "1. BASELINE METRICS"
echo "----------------------------------------------------------------------"
curl -s http://localhost:8000/api/metrics | jq '{
  total_alerts,
  critical_alerts,
  automation_rate
}'
echo ""
read -p "Press Enter to execute attack..."
echo ""

# Step 2: Execute attack
echo "2. EXECUTING ATTACK"
echo "----------------------------------------------------------------------"
POD=$(kubectl get pods -n smart-city -l app=iot-device -o jsonpath='{.items[0].metadata.name}')
echo "Target: $POD"
echo "Attack: Reading /etc/shadow"
echo ""
kubectl exec -n smart-city $POD -- cat /etc/shadow | head -3
echo "..."
echo ""
echo "✓ Attack executed"
echo ""
echo "Waiting 8 seconds for detection and AI analysis..."
sleep 8
echo ""

# Step 3: Show detection
echo "3. FALCO DETECTION"
echo "----------------------------------------------------------------------"
kubectl logs -n falco-system -l app.kubernetes.io/name=falco --tail=5 | grep -E '^\{' | tail -1 | jq '{rule, priority, container: .output_fields."container.name"}'
echo ""

# Step 4: Show AI analysis
echo "4. GROQ AI ANALYSIS"
echo "----------------------------------------------------------------------"
curl -s http://localhost:8000/api/alerts | jq '.alerts[-1] | {
  id,
  rule: .alert.rule,
  severity: .analysis.severity,
  threat_type: .analysis.threat_type,
  summary: .analysis.summary,
  actions
}'
echo ""

# Step 5: Show updated metrics
echo "5. UPDATED METRICS"
echo "----------------------------------------------------------------------"
curl -s http://localhost:8000/api/metrics | jq '{
  total_alerts,
  critical_alerts,
  automation_rate
}'
echo ""

echo "======================================================================"
echo "✓ DEMO COMPLETE"
echo "======================================================================"
echo ""
echo "Pipeline: Attack → Falco → Forwarder → IDS API → Groq AI → Response"
echo "Time: ~8 seconds end-to-end"
echo ""
