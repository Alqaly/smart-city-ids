#!/bin/bash

echo "📊 REAL-TIME IDS MONITORING DASHBOARD"
echo "======================================"

# Function to display logs with highlighting
show_logs() {
    local system=$1
    local label=$2
    local command=$3
    
    echo ""
    echo "🛡️ $label"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    eval "$command" | head -8
}

while true; do
    clear
    echo "📊 SMART CITY IDS - LIVE MONITORING ($(date))"
    echo "=================================================================="
    
    # Falco Runtime Security
    show_logs "falco" "FALCO RUNTIME SECURITY" \
        "kubectl logs -n falco-system -l app=falco --tail=5 2>/dev/null | grep -E '(Warning|Error|Critical)' | tail -5"
    
    # Suricata Network IDS  
    show_logs "suricata" "SURICATA NETWORK IDS" \
        "kubectl logs -n monitoring -l app=suricata --tail=3 2>/dev/null | grep -E '(alert|ET.*)' | tail -3"
    
    # System Statistics
    echo ""
    echo "📈 SYSTEM STATISTICS"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Smart City Pods: $(kubectl get pods -n smart-city --no-headers 2>/dev/null | wc -l)"
    echo "Falco Alerts: $(kubectl logs -n falco-system -l app=falco --tail=50 2>/dev/null | grep -c 'Warning')"
    echo "Network Alerts: $(kubectl logs -n monitoring -l app=suricata --tail=50 2>/dev/null | grep -c 'alert')"
    
    echo ""
    echo "🔄 Refreshing in 5 seconds... (Press Ctrl+C to stop)"
    sleep 5
done

