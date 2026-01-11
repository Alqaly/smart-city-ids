#!/bin/bash
# TMUX SPLIT DEMO - Attack + LLM Response

SESSION_NAME="smart-city-ids-demo"

# Kill existing session if it exists
tmux kill-session -t $SESSION_NAME 2>/dev/null

# Create new session
tmux new-session -d -s $SESSION_NAME

# Rename window
tmux rename-window -t $SESSION_NAME:0 'IDS-Demo'

# Split window vertically (left/right)
tmux split-window -h -t $SESSION_NAME:0

# Split right pane horizontally (top/bottom)
tmux split-window -v -t $SESSION_NAME:0.1

# Layout:
# ┌─────────────────┬─────────────────┐
# │                 │   IDS API       │
# │   ATTACK        │   LOGS          │
# │   EXECUTION     ├─────────────────┤
# │                 │   LIVE          │
# │                 │   ALERTS        │
# └─────────────────┴─────────────────┘

# Pane 0 (Left): Attack simulation
tmux send-keys -t $SESSION_NAME:0.0 'cd ~/smart-city-ids' Enter
tmux send-keys -t $SESSION_NAME:0.0 'clear' Enter
tmux send-keys -t $SESSION_NAME:0.0 'echo "╔════════════════════════════════════════════════════════╗"' Enter
tmux send-keys -t $SESSION_NAME:0.0 'echo "║           ATTACK EXECUTION PANEL                       ║"' Enter
tmux send-keys -t $SESSION_NAME:0.0 'echo "╚════════════════════════════════════════════════════════╝"' Enter
tmux send-keys -t $SESSION_NAME:0.0 'echo ""' Enter
tmux send-keys -t $SESSION_NAME:0.0 'echo "Ready to launch attacks..."' Enter
tmux send-keys -t $SESSION_NAME:0.0 'echo "Run: ./attack-simulation.sh"' Enter

# Pane 1 (Top Right): IDS API logs with LLM analysis
tmux send-keys -t $SESSION_NAME:0.1 'clear' Enter
tmux send-keys -t $SESSION_NAME:0.1 'echo "╔════════════════════════════════════════════════════════╗"' Enter
tmux send-keys -t $SESSION_NAME:0.1 'echo "║           IDS API - GROQ LLM ANALYSIS                  ║"' Enter
tmux send-keys -t $SESSION_NAME:0.1 'echo "╚════════════════════════════════════════════════════════╝"' Enter
tmux send-keys -t $SESSION_NAME:0.1 'echo ""' Enter
tmux send-keys -t $SESSION_NAME:0.1 'kubectl logs -n smart-city -l app=ids-api -f --tail=20' Enter

# Pane 2 (Bottom Right): Live alert monitoring
tmux send-keys -t $SESSION_NAME:0.2 'clear' Enter
tmux send-keys -t $SESSION_NAME:0.2 'echo "╔════════════════════════════════════════════════════════╗"' Enter
tmux send-keys -t $SESSION_NAME:0.2 'echo "║           LIVE ALERT MONITOR                           ║"' Enter
tmux send-keys -t $SESSION_NAME:0.2 'echo "╚════════════════════════════════════════════════════════╝"' Enter
tmux send-keys -t $SESSION_NAME:0.2 'echo ""' Enter
tmux send-keys -t $SESSION_NAME:0.2 'watch -n 2 -c "curl -s http://localhost:8000/api/alerts 2>/dev/null | jq -C \".alerts[-1] | {id, rule: .alert.rule, severity: .analysis.severity, threat: .analysis.threat_type, summary: .analysis.summary}\" 2>/dev/null || echo \"Waiting for alerts...\""'

# Select the attack pane (left)
tmux select-pane -t $SESSION_NAME:0.0

# Attach to session
tmux attach-session -t $SESSION_NAME
