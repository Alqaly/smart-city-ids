#!/bin/bash
# =============================================================================
# Smart City IDS - System Health Monitor
# Real-time status of all components with health indicators
# Usage: bash scripts/check-system.sh [--watch] [--help]
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")}" && pwd)"
source "$SCRIPT_DIR/lib/script-utils.sh"

WATCH_MODE=0
while [[ $# -gt 0 ]]; do
    case $1 in
        --watch)    WATCH_MODE=1; shift ;;
        --help)     print_help "check-system.sh [--watch]"; exit 0 ;;
        *)          die "Unknown option: $1" ;;
    esac
done

init_script "$0" "System Health Monitor"

# Function to collect and display health
show_health() {
    clear
    print_banner "System Health Monitor"
    
    ensure_kubeconfig
    
    NODE_IP=$(get_node_ip)
    
    # ─────────────────────────────────────────────────────────────────────────────
    # 1. KUBERNETES CLUSTER
    # ─────────────────────────────────────────────────────────────────────────────
    log_section "1. KUBERNETES CLUSTER"
    kubectl get nodes -o wide 2>/dev/null || log_error "Cannot connect to cluster"
    echo ""
    
    # ─────────────────────────────────────────────────────────────────────────────
    # 2. SMART CITY SERVICES
    # ─────────────────────────────────────────────────────────────────────────────
    log_section "2. SMART CITY SERVICES"
    
    if kubectl get namespace smart-city &>/dev/null; then
        kubectl get pods -n smart-city -o wide 2>/dev/null | head -15
        echo ""
        
        SMART_RUNNING=$(kubectl get pods -n smart-city --no-headers 2>/dev/null | grep -c "Running" || echo "0")
        SMART_TOTAL=$(kubectl get pods -n smart-city --no-headers 2>/dev/null | wc -l || echo "0")
        
        log_info "Running: $SMART_RUNNING / $SMART_TOTAL pods"
        
        # Service breakdown
        IDS_API=$(kubectl get pods -n smart-city -l app=ids-api --no-headers 2>/dev/null | grep -c "Running" || echo "0")
        TRAFFIC=$(kubectl get pods -n smart-city -l app=traffic-camera --no-headers 2>/dev/null | grep -c "Running" || echo "0")
        HEALTHCARE=$(kubectl get pods -n smart-city -l app=healthcare-api --no-headers 2>/dev/null | grep -c "Running" || echo "0")
        PARKING=$(kubectl get pods -n smart-city -l app=parking-system --no-headers 2>/dev/null | grep -c "Running" || echo "0")
        POSTGRES=$(kubectl get pods -n smart-city -l app=postgres --no-headers 2>/dev/null | grep -c "Running" || echo "0")
        MQTT=$(kubectl get pods -n smart-city -l app=mqtt-broker --no-headers 2>/dev/null | grep -c "Running" || echo "0")
        
        echo ""
        echo "Service Breakdown:"
        echo "  IDS API:        $IDS_API pod(s)"
        echo "  Traffic Camera: $TRAFFIC pod(s)"
        echo "  Healthcare API: $HEALTHCARE pod(s)"
        echo "  Parking System: $PARKING pod(s)"
        echo "  PostgreSQL:     $POSTGRES pod(s)"
        echo "  MQTT Broker:    $MQTT pod(s)"
    else
        log_warn "smart-city namespace not found"
    fi
    echo ""
    
    # ─────────────────────────────────────────────────────────────────────────────
    # 3. FALCO RUNTIME SECURITY
    # ─────────────────────────────────────────────────────────────────────────────
    log_section "3. FALCO RUNTIME SECURITY"
    
    if kubectl get namespace falco-system &>/dev/null; then
        FALCO_RUNNING=$(kubectl get pods -n falco-system --no-headers 2>/dev/null | grep -c "Running" || echo "0")
        FORWARDER_RUNNING=$(kubectl get pods -n falco-system -l app=falco-forwarder --no-headers 2>/dev/null | grep -c "Running" || echo "0")
        
        log_info "Falco: $FALCO_RUNNING pod(s) | Forwarder: $FORWARDER_RUNNING pod(s)"
        
        if [[ $FALCO_RUNNING -ge 1 ]]; then
            log_info "✓ Falco runtime detection active"
        else
            log_warn "Falco not running"
        fi
    else
        log_warn "Falco not deployed"
        FALCO_RUNNING=0
        FORWARDER_RUNNING=0
    fi
    echo ""
    
    # ─────────────────────────────────────────────────────────────────────────────
    # 4. MONITORING STACK
    # ─────────────────────────────────────────────────────────────────────────────
    log_section "4. MONITORING STACK"
    
    if kubectl get namespace monitoring &>/dev/null; then
        PROMETHEUS=$(kubectl get pods -n monitoring -l app=prometheus --no-headers 2>/dev/null | grep -c "Running" || echo "0")
        GRAFANA=$(kubectl get pods -n monitoring -l app=grafana --no-headers 2>/dev/null | grep -c "Running" || echo "0")
        
        log_info "Prometheus: $PROMETHEUS pod(s) | Grafana: $GRAFANA pod(s)"
    else
        log_warn "Monitoring namespace not found"
        PROMETHEUS=0
        GRAFANA=0
    fi
    echo ""
    
    # ─────────────────────────────────────────────────────────────────────────────
    # 5. ACCESS ENDPOINTS
    # ─────────────────────────────────────────────────────────────────────────────
    log_section "5. ACCESS ENDPOINTS"
    echo ""
    echo "  IDS API:      http://${NODE_IP}:30800  (or localhost:8000 if port-forwarded)"
    echo "  IDS API Docs: http://${NODE_IP}:30800/docs"
    echo "  Dashboard:    http://${NODE_IP}:8000/ui (localhost only)"
    echo "  Grafana:      http://${NODE_IP}:30300  (admin/admin)"
    echo "  Prometheus:   http://${NODE_IP}:31701"
    echo ""
    
    # ─────────────────────────────────────────────────────────────────────────────
    # 6. HEALTH SUMMARY
    # ─────────────────────────────────────────────────────────────────────────────
    log_section "6. HEALTH SUMMARY"
    echo ""
    
    if [[ $IDS_API -ge 1 ]] && [[ $FALCO_RUNNING -ge 1 ]] && [[ $FORWARDER_RUNNING -ge 1 ]]; then
        log_info "CORE PIPELINE: Ready (IDS API → Falco → Forwarder)"
        PIPELINE_OK=1
    else
        log_warn "CORE PIPELINE: Incomplete"
        PIPELINE_OK=0
    fi
    
    if [[ $PROMETHEUS -ge 1 ]] && [[ $GRAFANA -ge 1 ]]; then
        log_info "MONITORING: Ready (Prometheus & Grafana)"
    else
        log_warn "MONITORING: Incomplete"
    fi
    
    if [[ $SMART_RUNNING -ge 8 ]]; then
        log_info "SERVICES: Healthy ($SMART_RUNNING pods running)"
    else
        log_warn "SERVICES: Degraded ($SMART_RUNNING pods running)"
    fi
    
    echo ""
    
    if [[ $PIPELINE_OK -eq 0 ]]; then
        log_error "System not fully ready for operation"
        exit 1
    else
        log_info "✅ System ready for operation"
        echo ""
        echo "Quick commands:"
        echo "  Tail logs:  kubectl logs -f -n smart-city -l app=ids-api"
        echo "  Demo:       bash scripts/demo.sh"
        echo "  Check all:  bash scripts/check-setup.sh --verbose"
    fi
}

# Main loop
if [[ $WATCH_MODE -eq 1 ]]; then
    while true; do
        show_health
        echo ""
        echo "Updating in 5s (press Ctrl+C to exit)..."
        sleep 5
    done
else
    show_health
fi
