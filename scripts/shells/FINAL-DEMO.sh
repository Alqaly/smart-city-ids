#!/bin/bash
echo "🎓 FINAL WORKING DEMO"
echo "===================="
echo ""

# Get IDS pod
IDS_POD=$(kubectl get pod -n smart-city -l app=ids-api -o jsonpath='{.items[0].metadata.name}')

# Show status
echo "✅ IDS Status:"
kubectl exec -n smart-city $IDS_POD -- python3 -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health').read().decode())" 2>/dev/null | grep -o '"groq":"connected"' && echo "Groq: CONNECTED" || echo "Groq: disconnected"
echo ""

# Trigger attack WITHOUT --rm flag
echo "🚨 Triggering Attack..."
kubectl run attack-test --image=busybox -n smart-city --restart=Never --overrides='{"spec":{"securityContext":{"runAsUser":0}}}' -- cat /etc/shadow
sleep 15

# Show results
echo ""
echo "📊 Results:"
kubectl logs -n falco-system -l app=falco-forwarder --tail=5 2>/dev/null | grep "Forwarded" && echo "✅ Alert forwarded"
kubectl logs -n smart-city -l app=ids-api --tail=20 2>/dev/null | grep "Groq analysis complete" && echo "✅ AI analyzed"

# Show alerts
kubectl exec -n smart-city $IDS_POD -- python3 -c "import urllib.request, json; data=json.loads(urllib.request.urlopen('http://localhost:8000/api/alerts').read()); print(f\"Alerts: {data['total']}\")" 2>/dev/null

# Cleanup
kubectl delete pod attack-test -n smart-city 2>/dev/null

echo ""
echo "✅ DONE!"
