#!/bin/bash
# Capstone I – LIVE OBSERVABILITY VIEW
# Opens 4-pane tmux for live demo monitoring

SESSION="capstone1-demo"

# Kill existing session
tmux kill-session -t $SESSION 2>/dev/null || true
tmux kill-server 2>/dev/null || true
sleep 1

echo "=== Capstone I Live Demo View ==="
echo "Checking prerequisites..."

# Quick checks
kubectl get pods -n smart-city -l app=ids-api 2>/dev/null | grep -q Running || { echo "ERROR: IDS API not running"; exit 1; }
kubectl get pods -n falco-system 2>/dev/null | grep -q Running || { echo "ERROR: Falco not running"; exit 1; }

SURICATA_CMD="echo '=== SURICATA (SCALED DOWN) ===' && echo 'Run: kubectl scale deploy/suricata -n suricata-system --replicas=1' && sleep 999999"
if kubectl get pods -n suricata-system -l app=suricata 2>/dev/null | grep -q Running; then
    SURICATA_CMD="echo '=== SURICATA ALERTS ===' && kubectl logs -n suricata-system -l app=suricata -c suricata -f --tail=50"
    echo "✓ Suricata: Running"
else
    echo "⚠ Suricata: Scaled down"
fi

echo "✓ IDS API: Running"
echo "✓ Falco: Running"
echo ""
echo "Starting 4-pane tmux..."
echo "Detach: Ctrl+B then D"
echo ""
sleep 2

# Create 4-pane layout using tmux directly
tmux new-session -d -s $SESSION -x 200 -y 50

# Pane 0: Falco (top-left)
tmux send-keys -t $SESSION "echo '=== FALCO RUNTIME ALERTS ===' && kubectl logs -n falco-system -l app.kubernetes.io/name=falco -c falco -f --tail=50" Enter

# Split horizontally: Pane 1 (top-right)
tmux split-window -h -t $SESSION
tmux send-keys -t $SESSION "$SURICATA_CMD" Enter

# Split Pane 0 vertically: Pane 2 (bottom-left)  
tmux select-pane -t $SESSION:0.0
tmux split-window -v -t $SESSION
tmux send-keys -t $SESSION "echo '=== IDS API + LLM ===' && kubectl logs -n smart-city deploy/ids-api -f --tail=50" Enter

# Split Pane 1 vertically: Pane 3 (bottom-right)
tmux select-pane -t $SESSION:0.1
tmux split-window -v -t $SESSION
tmux send-keys -t $SESSION "echo '=== METRICS ===' && watch -n 2 'kubectl exec -n smart-city deploy/ids-api -- curl -s localhost:8000/metrics 2>/dev/null | grep smartcity_ids | head -15'" Enter

# Balance panes
tmux select-layout -t $SESSION tiled

# Attach
exec tmux attach -t $SESSION
