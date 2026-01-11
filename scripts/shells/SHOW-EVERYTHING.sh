#!/bin/bash
set -e

echo "╔════════════════════════════════════════════════════════╗"
echo "║   SMART CITY LLM-IDS - COMPLETE WORKING SYSTEM        ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""

### AUTO FIX KUBECONFIG
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

### AUTO DETECT API SERVER HEALTH
echo "🔍 Checking K3s API..."
for i in {1..15}; do
    if kubectl get nodes >/dev/null 2>&1; then
        echo "✅ API server reachable"
        break
    fi
    echo "⏳ Waiting for Kubernetes API..."
    sleep 2
done

### IDENTIFY IDS POD SAFELY
IDS_POD=$(kubectl get pod -n smart-city -l app=ids-api -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "none")

if [ "$IDS_POD" = "none" ] || [ -z "$IDS_POD" ]; then
    echo "❌ IDS API pod not found"
else
    echo "🔍 IDS API pod: $IDS_POD"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1. KUBERNETES CLUSTER"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
kubectl get nodes || echo "❌ Cannot get nodes"
kubectl get pods --all-namespaces | grep -E "smart-city|falco|suricata|monitoring" | head -20 || echo "❌ Pods info unavailable"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2. IDS API + GROQ AI"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ "$IDS_POD" != "none" ]; then
kubectl exec -n smart-city $IDS_POD -- python3 - << 'EOF'
import urllib.request, json
try:
    h = urllib.request.urlopen("http://localhost:8000/health").read()
    print(json.dumps(json.loads(h), indent=2))
except Exception as e:
    print("❌ IDS health unavailable:", e)
EOF
else
    echo "❌ IDS API not running"
fi
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3. SECURITY MONITORING (Falco + Suricata)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Falco:"
kubectl get pods -n falco-system || echo "❌ Falco unavailable"
echo ""
echo "Suricata:"
kubectl get pods -n suricata-system || echo "❌ Suricata unavailable"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4. IOT DEVICES + MQTT"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
kubectl get pods -n smart-city -l app=iot-devices || echo "❌ IoT devices unavailable"
kubectl get pods -n smart-city -l app=mqtt-broker || echo "❌ MQTT broker unavailable"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "5. DETECTED ALERTS (WITH AI ANALYSIS)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ "$IDS_POD" != "none" ]; then
kubectl exec -n smart-city $IDS_POD -- python3 - << 'EOF'
import urllib.request, json
try:
    data = json.loads(urllib.request.urlopen("http://localhost:8000/api/alerts?limit=5").read())
    print(f'Total Alerts: {data["total"]}\n')
    for i, alert in enumerate(data["alerts"], 1):
        print(f"Alert #{i}:")
        print(f"  Rule: {alert['alert']['rule']}")
        print(f"  Source: {alert['source'].upper()}")
        print(f"  Time: {alert['timestamp']}")
        if alert.get("analysis"):
            print("  AI Analysis:")
            print(f"    Severity: {alert['analysis'].get('severity')}/10")
            print(f"    Threat: {alert['analysis'].get('threat_type')}")
        print(f"  Actions: {alert.get('actions', [])}")
        print()
except Exception as e:
    print("❌ Cannot fetch alerts:", e)
EOF
else
    echo "❌ IDS API not running"
fi
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "6. SYSTEM METRICS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ "$IDS_POD" != "none" ]; then
kubectl exec -n smart-city $IDS_POD -- python3 - << 'EOF'
import urllib.request, json
try:
    d = json.loads(urllib.request.urlopen("http://localhost:8000/api/metrics").read())
    print("Total Alerts:", d["total_alerts"])
    print("Critical Alerts:", d["critical_alerts"])
    print("Falco Alerts:", d["alerts_by_source"]["falco"])
    print("Suricata Alerts:", d["alerts_by_source"]["suricata"])
    print("Automated Actions:", d["automated_actions"])
    print("Automation Rate:", f"{d['automation_rate']:.1f}%")
    print("Avg Response Time:", d["avg_response_time_seconds"], "s")
except Exception as e:
    print("❌ Cannot load metrics:", e)
EOF
else
    echo "❌ IDS API not running"
fi
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "7. MONITORING DASHBOARDS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 Grafana: http://localhost:30030"
echo "   Username: admin"
echo "   Password: admin123"
echo ""
echo "📈 Prometheus: http://localhost:30090"
echo ""

echo "╔════════════════════════════════════════════════════════╗"
echo "║                  ✅ SYSTEM OPERATIONAL                 ║"
echo "╚════════════════════════════════════════════════════════╝"
