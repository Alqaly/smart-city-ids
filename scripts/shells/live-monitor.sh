#!/bin/bash
# Live Alert Monitor - Shows latest alerts with updates

echo "╔════════════════════════════════════════════════════════╗"
echo "║           LIVE ALERT MONITOR (Auto-refresh)            ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""

LAST_COUNT=0

while true; do
    clear
    echo "╔════════════════════════════════════════════════════════╗"
    echo "║           LIVE ALERT MONITOR                           ║"
    echo "╚════════════════════════════════════════════════════════╝"
    echo ""
    echo "🕒 $(date '+%H:%M:%S')"
    echo ""
    
    RESPONSE=$(curl -s http://localhost:8000/api/alerts 2>/dev/null)
    
    if [ -n "$RESPONSE" ]; then
        TOTAL=$(echo "$RESPONSE" | jq -r '.total // 0')
        
        echo "📊 Total Alerts: $TOTAL"
        
        if [ $TOTAL -gt $LAST_COUNT ]; then
            echo "🆕 NEW ALERT DETECTED! (+$((TOTAL - LAST_COUNT)))"
        fi
        
        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "LATEST 3 ALERTS:"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        
        echo "$RESPONSE" | jq -C '.alerts[-3:] | reverse | .[] | {
            id,
            rule: .alert.rule,
            severity: .analysis.severity,
            threat: .analysis.threat_type,
            summary: .analysis.summary | .[0:80]
        }' 2>/dev/null
        
        LAST_COUNT=$TOTAL
    else
        echo "⏳ Waiting for IDS API..."
    fi
    
    sleep 2
done
