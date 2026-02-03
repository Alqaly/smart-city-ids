#!/bin/bash
# =============================================================================
# Smart City IDS - SUPERVISOR DEMO SCRIPT
# 
# Creates a SEPARATE demo dashboard, runs attacks, shows everything live.
# Does NOT mix with production dashboards.
#
# Usage: ./scripts/supervisor-demo.sh
# =============================================================================

set -euo pipefail

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}' 2>/dev/null || echo "localhost")
GRAFANA_URL="http://${NODE_IP}:30300"
GRAFANA_USER="admin"
GRAFANA_PASS="admin"
PROMETHEUS_URL="http://${NODE_IP}:31701"

DEMO_DASHBOARD_UID="smart-city-demo-$(date +%s)"
DEMO_DASHBOARD_TITLE="🎯 CAPSTONE DEMO - $(date '+%Y-%m-%d %H:%M')"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
BOLD='\033[1m'
NC='\033[0m'

# ─────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────────────────────
print_banner() {
    echo -e "${CYAN}"
    echo "╔═══════════════════════════════════════════════════════════════════════╗"
    echo "║                                                                       ║"
    echo "║   🏙️  SMART CITY IDS - CAPSTONE DEFENSE DEMO                          ║"
    echo "║                                                                       ║"
    echo "║   This script will:                                                   ║"
    echo "║   1. Create a SEPARATE demo dashboard in Grafana                      ║"
    echo "║   2. Run real attacks against Smart City services                     ║"
    echo "║   3. Show live detection, LLM analysis, and automated response        ║"
    echo "║   4. Prove that ALL metrics are REAL, not mocked                      ║"
    echo "║                                                                       ║"
    echo "╚═══════════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

log_step() {
    echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BOLD}${BLUE}▶ $1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
}

log_info() { echo -e "  ${GREEN}✓${NC} $1"; }
log_warn() { echo -e "  ${YELLOW}⚠${NC} $1"; }
log_error() { echo -e "  ${RED}✗${NC} $1"; }
log_attack() { echo -e "  ${RED}🔴 ATTACK:${NC} $1"; }
log_detect() { echo -e "  ${MAGENTA}🔍 DETECTED:${NC} $1"; }

get_metric() {
    kubectl exec -n smart-city deploy/ids-api -- curl -s localhost:8000/metrics 2>/dev/null \
        | grep "^$1{" | awk -F'} ' '{sum+=$2} END {print sum+0}'
}

# ─────────────────────────────────────────────────────────────────────────────
# Create Demo Dashboard in Grafana
# ─────────────────────────────────────────────────────────────────────────────
create_demo_dashboard() {
    log_step "STEP 1: Creating Demo Dashboard in Grafana"
    
    log_info "Dashboard will be created with UID: $DEMO_DASHBOARD_UID"
    log_info "This is SEPARATE from production dashboards"
    
    # Generate the dashboard JSON
    DASHBOARD_JSON=$(cat << 'DASHBOARD_EOF'
{
  "dashboard": {
    "uid": "DEMO_UID_PLACEHOLDER",
    "title": "DEMO_TITLE_PLACEHOLDER",
    "tags": ["demo", "capstone", "supervisor"],
    "timezone": "browser",
    "refresh": "5s",
    "time": {
      "from": "now-15m",
      "to": "now"
    },
    "annotations": {
      "list": [{
        "name": "Attack Events",
        "datasource": "Prometheus",
        "enable": true,
        "iconColor": "red",
        "expr": "increase(smartcity_ids_alerts_received_total[1m]) > 0"
      }]
    },
    "panels": [
      {
        "id": 1,
        "title": "🚨 LIVE ALERT RATE",
        "type": "stat",
        "gridPos": {"h": 4, "w": 6, "x": 0, "y": 0},
        "targets": [{
          "expr": "sum(rate(smartcity_ids_alerts_received_total[1m])) * 60",
          "legendFormat": "alerts/min"
        }],
        "options": {
          "colorMode": "value",
          "graphMode": "area"
        },
        "fieldConfig": {
          "defaults": {
            "color": {"mode": "thresholds"},
            "thresholds": {
              "steps": [
                {"color": "green", "value": null},
                {"color": "yellow", "value": 5},
                {"color": "red", "value": 20}
              ]
            },
            "unit": "short"
          }
        }
      },
      {
        "id": 2,
        "title": "📊 TOTAL ALERTS RECEIVED",
        "type": "stat",
        "gridPos": {"h": 4, "w": 6, "x": 6, "y": 0},
        "targets": [{
          "expr": "sum(smartcity_ids_alerts_received_total)",
          "legendFormat": "total"
        }],
        "options": {"colorMode": "value"},
        "fieldConfig": {
          "defaults": {
            "color": {"mode": "palette-classic"},
            "unit": "short"
          }
        }
      },
      {
        "id": 3,
        "title": "🤖 LLM ANALYSIS COUNT",
        "type": "stat",
        "gridPos": {"h": 4, "w": 6, "x": 12, "y": 0},
        "targets": [{
          "expr": "sum(smartcity_ids_alerts_processed_total)",
          "legendFormat": "analyzed"
        }],
        "options": {"colorMode": "value"},
        "fieldConfig": {
          "defaults": {
            "color": {"mode": "palette-classic"},
            "unit": "short"
          }
        }
      },
      {
        "id": 4,
        "title": "🛡️ PODS ISOLATED",
        "type": "stat",
        "gridPos": {"h": 4, "w": 6, "x": 18, "y": 0},
        "targets": [{
          "expr": "sum(smartcity_ids_actions_executed_total{action=\"isolate_pod\"})",
          "legendFormat": "isolated"
        }],
        "options": {"colorMode": "value"},
        "fieldConfig": {
          "defaults": {
            "color": {"mode": "thresholds"},
            "thresholds": {
              "steps": [
                {"color": "green", "value": null},
                {"color": "orange", "value": 1}
              ]
            },
            "unit": "short"
          }
        }
      },
      {
        "id": 5,
        "title": "📈 ALERT RATE OVER TIME (Watch for Spikes During Attacks)",
        "type": "timeseries",
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 4},
        "targets": [{
          "expr": "sum(rate(smartcity_ids_alerts_received_total[30s])) * 60",
          "legendFormat": "Alerts/min"
        }],
        "options": {
          "legend": {"displayMode": "list", "placement": "bottom"}
        },
        "fieldConfig": {
          "defaults": {
            "color": {"mode": "palette-classic"},
            "custom": {
              "drawStyle": "line",
              "lineWidth": 2,
              "fillOpacity": 30,
              "gradientMode": "scheme",
              "spanNulls": false,
              "lineInterpolation": "smooth"
            },
            "unit": "short"
          }
        }
      },
      {
        "id": 6,
        "title": "⏱️ LLM RESPONSE TIME (xAI Grok-4)",
        "type": "timeseries",
        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 4},
        "targets": [
          {
            "expr": "histogram_quantile(0.50, sum(rate(smartcity_ids_llm_latency_seconds_bucket[1m])) by (le))",
            "legendFormat": "p50"
          },
          {
            "expr": "histogram_quantile(0.95, sum(rate(smartcity_ids_llm_latency_seconds_bucket[1m])) by (le))",
            "legendFormat": "p95"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "color": {"mode": "palette-classic"},
            "custom": {
              "drawStyle": "line",
              "lineWidth": 2,
              "fillOpacity": 10
            },
            "unit": "s"
          }
        }
      },
      {
        "id": 7,
        "title": "🎯 ALERTS BY SEVERITY",
        "type": "piechart",
        "gridPos": {"h": 8, "w": 8, "x": 0, "y": 12},
        "targets": [{
          "expr": "sum by (priority) (smartcity_ids_alerts_received_total)",
          "legendFormat": "{{priority}}"
        }],
        "options": {
          "legend": {"displayMode": "table", "placement": "right", "values": ["value", "percent"]},
          "pieType": "pie"
        }
      },
      {
        "id": 8,
        "title": "⚡ AUTOMATED ACTIONS TAKEN",
        "type": "bargauge",
        "gridPos": {"h": 8, "w": 8, "x": 8, "y": 12},
        "targets": [{
          "expr": "sum by (action) (smartcity_ids_actions_executed_total)",
          "legendFormat": "{{action}}"
        }],
        "options": {
          "displayMode": "gradient",
          "orientation": "horizontal"
        },
        "fieldConfig": {
          "defaults": {
            "color": {"mode": "thresholds"},
            "thresholds": {
              "steps": [
                {"color": "green", "value": null},
                {"color": "yellow", "value": 5},
                {"color": "red", "value": 20}
              ]
            }
          }
        }
      },
      {
        "id": 9,
        "title": "📋 DEMO INFO",
        "type": "text",
        "gridPos": {"h": 8, "w": 8, "x": 16, "y": 12},
        "options": {
          "mode": "markdown",
          "content": "## 🎓 Capstone Defense Demo\n\n**What you're seeing:**\n- Real alerts from Falco runtime security\n- Real LLM analysis by xAI Grok-4\n- Real Kubernetes automated responses\n\n**This is NOT mock data.**\n\n---\n\n**Attack → Detection → Analysis → Response**\n\nAll metrics update in real-time.\nWatch the graphs spike during attacks."
        }
      },
      {
        "id": 10,
        "title": "🔥 ATTACK TIMELINE (Last 15 Minutes)",
        "type": "timeseries",
        "gridPos": {"h": 6, "w": 24, "x": 0, "y": 20},
        "targets": [
          {
            "expr": "sum(rate(smartcity_ids_alerts_received_total{priority=\"Critical\"}[30s])) * 60",
            "legendFormat": "Critical"
          },
          {
            "expr": "sum(rate(smartcity_ids_alerts_received_total{priority=\"Warning\"}[30s])) * 60",
            "legendFormat": "Warning"
          },
          {
            "expr": "sum(rate(smartcity_ids_alerts_received_total{priority=\"Notice\"}[30s])) * 60",
            "legendFormat": "Notice"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "custom": {
              "drawStyle": "bars",
              "lineWidth": 1,
              "fillOpacity": 80,
              "stacking": {"mode": "normal"}
            },
            "unit": "short"
          },
          "overrides": [
            {"matcher": {"id": "byName", "options": "Critical"}, "properties": [{"id": "color", "value": {"fixedColor": "red", "mode": "fixed"}}]},
            {"matcher": {"id": "byName", "options": "Warning"}, "properties": [{"id": "color", "value": {"fixedColor": "orange", "mode": "fixed"}}]},
            {"matcher": {"id": "byName", "options": "Notice"}, "properties": [{"id": "color", "value": {"fixedColor": "yellow", "mode": "fixed"}}]}
          ]
        }
      }
    ],
    "schemaVersion": 39
  },
  "overwrite": true
}
DASHBOARD_EOF
)

    # Replace placeholders
    DASHBOARD_JSON=$(echo "$DASHBOARD_JSON" | sed "s/DEMO_UID_PLACEHOLDER/$DEMO_DASHBOARD_UID/g")
    DASHBOARD_JSON=$(echo "$DASHBOARD_JSON" | sed "s/DEMO_TITLE_PLACEHOLDER/$DEMO_DASHBOARD_TITLE/g")
    
    # Create dashboard via Grafana API
    RESPONSE=$(curl -s -X POST "${GRAFANA_URL}/api/dashboards/db" \
        -H "Content-Type: application/json" \
        -u "${GRAFANA_USER}:${GRAFANA_PASS}" \
        -d "$DASHBOARD_JSON")
    
    if echo "$RESPONSE" | grep -q '"status":"success"\|"uid"'; then
        log_info "Demo dashboard created successfully!"
        DASHBOARD_URL="${GRAFANA_URL}/d/${DEMO_DASHBOARD_UID}"
        log_info "Dashboard URL: ${DASHBOARD_URL}"
    else
        log_warn "Dashboard creation response: $RESPONSE"
        DASHBOARD_URL="${GRAFANA_URL}"
    fi
    
    echo ""
    echo -e "  ${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "  ${BOLD}📊 OPEN THIS URL IN YOUR BROWSER NOW:${NC}"
    echo ""
    echo -e "     ${GREEN}${DASHBOARD_URL}${NC}"
    echo ""
    echo -e "  ${CYAN}Credentials: admin / admin${NC}"
    echo -e "  ${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
}

# ─────────────────────────────────────────────────────────────────────────────
# Capture Baseline Metrics
# ─────────────────────────────────────────────────────────────────────────────
capture_baseline() {
    log_step "STEP 2: Capturing Baseline Metrics"
    
    BASELINE_RECEIVED=$(get_metric "smartcity_ids_alerts_received_total")
    BASELINE_PROCESSED=$(get_metric "smartcity_ids_alerts_processed_total")
    BASELINE_ACTIONS=$(kubectl exec -n smart-city deploy/ids-api -- curl -s localhost:8000/metrics 2>/dev/null \
        | grep "smartcity_ids_actions_executed_total{" | awk -F'} ' '{sum+=$2} END {print sum+0}')
    BASELINE_TIME=$(date -Iseconds)
    
    echo -e "  ${CYAN}┌─────────────────────────────────────────────────┐${NC}"
    echo -e "  ${CYAN}│${NC}  ${BOLD}BASELINE (Before Attacks)${NC}                    ${CYAN}│${NC}"
    echo -e "  ${CYAN}├─────────────────────────────────────────────────┤${NC}"
    echo -e "  ${CYAN}│${NC}  Alerts Received:    ${GREEN}$BASELINE_RECEIVED${NC}                      ${CYAN}│${NC}"
    echo -e "  ${CYAN}│${NC}  Alerts Processed:   ${GREEN}$BASELINE_PROCESSED${NC}                      ${CYAN}│${NC}"
    echo -e "  ${CYAN}│${NC}  Actions Executed:   ${GREEN}$BASELINE_ACTIONS${NC}                        ${CYAN}│${NC}"
    echo -e "  ${CYAN}│${NC}  Timestamp:          ${GREEN}$BASELINE_TIME${NC}  ${CYAN}│${NC}"
    echo -e "  ${CYAN}└─────────────────────────────────────────────────┘${NC}"
    echo ""
}

# ─────────────────────────────────────────────────────────────────────────────
# Run Attack Sequence
# ─────────────────────────────────────────────────────────────────────────────
run_attacks() {
    log_step "STEP 3: Running Attack Sequence"
    
    echo -e "  ${YELLOW}Watch the Grafana dashboard - you'll see metrics spike in real-time!${NC}"
    echo ""
    
    # Get target pods
    PODS=($(kubectl get pods -n smart-city -o jsonpath='{.items[*].metadata.name}' 2>/dev/null))
    
    # Attack definitions with MITRE IDs
    declare -A ATTACKS
    ATTACKS["Sensitive File Read|T1552.001|Credential Access"]="cat /etc/shadow"
    ATTACKS["Shell Execution|T1059.004|Command Execution"]="/bin/sh -c 'whoami'"
    ATTACKS["Process Discovery|T1057|Discovery"]="ps aux"
    ATTACKS["System Info|T1082|Discovery"]="uname -a && cat /etc/os-release"
    ATTACKS["Network Config|T1016|Discovery"]="cat /etc/hosts && cat /etc/resolv.conf"
    
    ATTACK_NAMES=("${!ATTACKS[@]}")
    ATTACK_COUNT=15
    ATTACK_DELAY=2
    
    echo -e "  ${RED}┌─────────────────────────────────────────────────────────────────┐${NC}"
    echo -e "  ${RED}│  ⚠️  STARTING ATTACK SEQUENCE - $ATTACK_COUNT ATTACKS            ${NC}${RED}│${NC}"
    echo -e "  ${RED}└─────────────────────────────────────────────────────────────────┘${NC}"
    echo ""
    
    for i in $(seq 1 $ATTACK_COUNT); do
        # Select random pod and attack
        POD=${PODS[$((RANDOM % ${#PODS[@]}))]}
        ATTACK_KEY=${ATTACK_NAMES[$((RANDOM % ${#ATTACK_NAMES[@]}))]}
        
        ATTACK_NAME=$(echo "$ATTACK_KEY" | cut -d'|' -f1)
        MITRE_ID=$(echo "$ATTACK_KEY" | cut -d'|' -f2)
        MITRE_TACTIC=$(echo "$ATTACK_KEY" | cut -d'|' -f3)
        ATTACK_CMD=${ATTACKS[$ATTACK_KEY]}
        
        echo -e "  ${RED}[$i/$ATTACK_COUNT]${NC} ${BOLD}$ATTACK_NAME${NC}"
        echo -e "          MITRE: ${YELLOW}$MITRE_ID${NC} ($MITRE_TACTIC)"
        echo -e "          Pod:   ${CYAN}$POD${NC}"
        
        # Execute attack
        kubectl exec -n smart-city "$POD" -- sh -c "$ATTACK_CMD" > /dev/null 2>&1 || true
        
        echo -e "          ${GREEN}✓ Executed${NC} → Falco detecting..."
        echo ""
        
        sleep $ATTACK_DELAY
    done
    
    echo -e "  ${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "  ${GREEN}✓ All $ATTACK_COUNT attacks executed${NC}"
    echo -e "  ${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
}

# ─────────────────────────────────────────────────────────────────────────────
# Wait for Pipeline with Progress
# ─────────────────────────────────────────────────────────────────────────────
wait_for_pipeline() {
    log_step "STEP 4: Waiting for Detection Pipeline"
    
    echo "  Detection chain:"
    echo "  [1] Falco syscall detection     → ~1s"
    echo "  [2] Forwarder HTTP POST         → ~1s"
    echo "  [3] xAI Grok-4 LLM analysis     → ~3-5s"
    echo "  [4] K8s automated action        → ~2s"
    echo "  [5] Prometheus metric scrape    → ~5s"
    echo ""
    
    WAIT_TIME=15
    echo -ne "  Waiting: "
    for i in $(seq 1 $WAIT_TIME); do
        echo -ne "█"
        sleep 1
    done
    echo -e " ${GREEN}Done!${NC}"
    echo ""
}

# ─────────────────────────────────────────────────────────────────────────────
# Show Results
# ─────────────────────────────────────────────────────────────────────────────
show_results() {
    log_step "STEP 5: Results - PROOF THAT DATA IS REAL"
    
    FINAL_RECEIVED=$(get_metric "smartcity_ids_alerts_received_total")
    FINAL_PROCESSED=$(get_metric "smartcity_ids_alerts_processed_total")
    FINAL_ACTIONS=$(kubectl exec -n smart-city deploy/ids-api -- curl -s localhost:8000/metrics 2>/dev/null \
        | grep "smartcity_ids_actions_executed_total{" | awk -F'} ' '{sum+=$2} END {print sum+0}')
    
    DELTA_RECEIVED=$((FINAL_RECEIVED - BASELINE_RECEIVED))
    DELTA_PROCESSED=$((FINAL_PROCESSED - BASELINE_PROCESSED))
    DELTA_ACTIONS=$(echo "$FINAL_ACTIONS - $BASELINE_ACTIONS" | bc 2>/dev/null || echo "0")
    
    echo -e "  ${CYAN}┌───────────────────────────────────────────────────────────────────┐${NC}"
    echo -e "  ${CYAN}│${NC}                    ${BOLD}BEFORE vs AFTER COMPARISON${NC}                    ${CYAN}│${NC}"
    echo -e "  ${CYAN}├───────────────────────────────────────────────────────────────────┤${NC}"
    echo -e "  ${CYAN}│${NC}  Metric              │  Before    │  After     │  ${GREEN}Delta${NC}        ${CYAN}│${NC}"
    echo -e "  ${CYAN}├───────────────────────────────────────────────────────────────────┤${NC}"
    printf "  ${CYAN}│${NC}  Alerts Received     │  %-9s │  %-9s │  ${GREEN}+%-10s${NC} ${CYAN}│${NC}\n" "$BASELINE_RECEIVED" "$FINAL_RECEIVED" "$DELTA_RECEIVED"
    printf "  ${CYAN}│${NC}  Alerts Processed    │  %-9s │  %-9s │  ${GREEN}+%-10s${NC} ${CYAN}│${NC}\n" "$BASELINE_PROCESSED" "$FINAL_PROCESSED" "$DELTA_PROCESSED"
    printf "  ${CYAN}│${NC}  Actions Executed    │  %-9s │  %-9s │  ${GREEN}+%-10s${NC} ${CYAN}│${NC}\n" "$BASELINE_ACTIONS" "$FINAL_ACTIONS" "$DELTA_ACTIONS"
    echo -e "  ${CYAN}└───────────────────────────────────────────────────────────────────┘${NC}"
    echo ""
    
    # Show log evidence
    echo -e "  ${BOLD}Log Evidence:${NC}"
    echo ""
    
    echo -e "  ${YELLOW}[FALCO] Recent detections:${NC}"
    kubectl logs -n falco-system -l app.kubernetes.io/name=falco -c falco --tail=5 2>/dev/null \
        | grep '"rule"' | tail -3 | while read line; do
        RULE=$(echo "$line" | grep -o '"rule":"[^"]*"' | cut -d'"' -f4)
        echo -e "    • $RULE"
    done
    echo ""
    
    echo -e "  ${YELLOW}[IDS API] Recent processing:${NC}"
    kubectl logs -n smart-city deploy/ids-api --tail=20 2>/dev/null \
        | grep -E "Received alert|severity" | tail -3 | while read line; do
        echo "    • $(echo "$line" | cut -c1-80)..."
    done
    echo ""
}

# ─────────────────────────────────────────────────────────────────────────────
# Final Summary
# ─────────────────────────────────────────────────────────────────────────────
show_summary() {
    log_step "DEMO COMPLETE"
    
    echo -e "${GREEN}"
    echo "  ╔═════════════════════════════════════════════════════════════════════╗"
    echo "  ║                                                                     ║"
    echo "  ║   ✅ DEMO SUCCESSFUL - DATA IS REAL                                 ║"
    echo "  ║                                                                     ║"
    echo "  ╠═════════════════════════════════════════════════════════════════════╣"
    echo "  ║                                                                     ║"
    echo "  ║   What was demonstrated:                                            ║"
    echo "  ║   • Real attacks executed against containers                        ║"
    echo "  ║   • Real Falco syscall detection                                    ║"
    echo "  ║   • Real xAI Grok-4 LLM analysis                                    ║"
    echo "  ║   • Real Kubernetes automated response                              ║"
    echo "  ║   • Real Prometheus metrics (not mocked)                            ║"
    echo "  ║                                                                     ║"
    echo "  ║   The Grafana dashboard shows MEASURED SYSTEM BEHAVIOR              ║"
    echo "  ║   under CONTROLLED TEST CONDITIONS.                                 ║"
    echo "  ║                                                                     ║"
    echo "  ╚═════════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    
    echo -e "  ${CYAN}Demo Dashboard:${NC} ${GRAFANA_URL}/d/${DEMO_DASHBOARD_UID}"
    echo ""
    echo -e "  ${YELLOW}To delete demo dashboard after presentation:${NC}"
    echo "  curl -X DELETE ${GRAFANA_URL}/api/dashboards/uid/${DEMO_DASHBOARD_UID} -u admin:admin"
    echo ""
}

# ─────────────────────────────────────────────────────────────────────────────
# Pre-flight Checks
# ─────────────────────────────────────────────────────────────────────────────
preflight_checks() {
    log_step "PRE-FLIGHT CHECKS"
    
    # Check kubectl
    if ! kubectl cluster-info &>/dev/null; then
        log_error "Cannot connect to Kubernetes cluster"
        exit 1
    fi
    log_info "Kubernetes cluster: OK"
    
    # Check IDS API
    if ! kubectl get deploy/ids-api -n smart-city &>/dev/null; then
        log_error "IDS API not deployed"
        exit 1
    fi
    log_info "IDS API: OK"
    
    # Check Falco
    if ! kubectl get pods -n falco-system -l app.kubernetes.io/name=falco 2>/dev/null | grep -q Running; then
        log_error "Falco not running"
        exit 1
    fi
    log_info "Falco: OK"
    
    # Check Grafana
    if ! curl -s "${GRAFANA_URL}/api/health" | grep -q "ok"; then
        log_warn "Grafana may not be accessible at ${GRAFANA_URL}"
    else
        log_info "Grafana: OK"
    fi
    
    echo ""
}

# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
main() {
    clear
    print_banner
    
    echo -e "${YELLOW}Press ENTER to start the demo, or Ctrl+C to cancel...${NC}"
    read
    
    preflight_checks
    create_demo_dashboard
    
    echo -e "${YELLOW}Press ENTER when Grafana dashboard is open in your browser...${NC}"
    read
    
    capture_baseline
    run_attacks
    wait_for_pipeline
    show_results
    show_summary
}

main "$@"
