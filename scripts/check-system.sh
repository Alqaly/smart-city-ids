#!/bin/bash
# =============================================================================
# Smart City IDS - System Health Monitor
# Real-time status of all components with health indicators
# Usage: bash scripts/check-system.sh [--watch] [--help]
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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
ensure_commands kubectl

count_running_pods_by_label() {
    local ns="$1"
    local label="$2"
    kubectl get pods -n "$ns" -l "$label" --no-headers 2>/dev/null | awk '$3=="Running"{c++} END{print c+0}'
}

count_running_pods_in_ns() {
    local ns="$1"
    kubectl get pods -n "$ns" --no-headers 2>/dev/null | awk '$3=="Running"{c++} END{print c+0}'
}

count_total_pods_in_ns() {
    local ns="$1"
    kubectl get pods -n "$ns" --no-headers 2>/dev/null | awk 'END{print NR+0}'
}

# Function to collect and display health
show_health() {
    clear
    print_banner "System Health Monitor"
    
    ensure_kubeconfig
    
    local IDS_API=0
    local TRAFFIC=0
    local HEALTHCARE=0
    local PARKING=0
    local POSTGRES=0
    local MQTT=0
    local SMART_RUNNING=0
    local SMART_TOTAL=0
    local FALCO_RUNNING=0
    local FORWARDER_RUNNING=0
    local PROMETHEUS=0
    local GRAFANA=0
    local SURICATA=0
    local SURICATA_FORWARDER=0
    local PIPELINE_OK=0
    
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
        
        SMART_RUNNING=$(count_running_pods_in_ns "smart-city")
        SMART_TOTAL=$(count_total_pods_in_ns "smart-city")
        
        log_info "Running: $SMART_RUNNING / $SMART_TOTAL pods"
        
        # Service breakdown
        IDS_API=$(count_running_pods_by_label "smart-city" "app=ids-api")
        TRAFFIC=$(count_running_pods_by_label "smart-city" "app=traffic-camera")
        HEALTHCARE=$(count_running_pods_by_label "smart-city" "app=healthcare-api")
        PARKING=$(count_running_pods_by_label "smart-city" "app=parking-system")
        POSTGRES=$(count_running_pods_by_label "smart-city" "app=postgres")
        MQTT=$(count_running_pods_by_label "smart-city" "app=mqtt-broker")
        
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
        FALCO_RUNNING=$(kubectl get pods -n falco-system --no-headers 2>/dev/null | awk '$1 ~ /^falco-/ && $3=="Running"{c++} END{print c+0}')
        FORWARDER_RUNNING=$(count_running_pods_by_label "falco-system" "app=falco-forwarder")
        
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
        PROMETHEUS=$(count_running_pods_by_label "monitoring" "app=prometheus")
        GRAFANA=$(count_running_pods_by_label "monitoring" "app=grafana")
        SURICATA=$(count_running_pods_by_label "monitoring" "app=suricata")
        SURICATA_FORWARDER=$(count_running_pods_by_label "monitoring" "app=suricata-forwarder")
        
        log_info "Prometheus: $PROMETHEUS pod(s) | Grafana: $GRAFANA pod(s)"
        log_info "Suricata: $SURICATA pod(s) | Suricata Forwarder: $SURICATA_FORWARDER pod(s)"
    else
        log_warn "Monitoring namespace not found"
        PROMETHEUS=0
        GRAFANA=0
        SURICATA=0
        SURICATA_FORWARDER=0
    fi
    echo ""
    
    # ─────────────────────────────────────────────────────────────────────────────
    # 5. ACCESS ENDPOINTS
    # ─────────────────────────────────────────────────────────────────────────────
    log_section "5. ACCESS ENDPOINTS"
    local IDS_API_NODEPORT
    local GRAFANA_NODEPORT
    local PROM_NODEPORT
    IDS_API_NODEPORT=$(kubectl get svc -n smart-city ids-api-service -o jsonpath='{.spec.ports[0].nodePort}' 2>/dev/null || echo "30800")
    GRAFANA_NODEPORT=$(kubectl get svc -n monitoring grafana -o jsonpath='{.spec.ports[0].nodePort}' 2>/dev/null || echo "30300")
    PROM_NODEPORT=$(kubectl get svc -n monitoring prometheus -o jsonpath='{.spec.ports[0].nodePort}' 2>/dev/null || echo "31106")

    echo ""
    echo "  IDS API:      http://${NODE_IP}:${IDS_API_NODEPORT}  (or localhost:8000 if port-forwarded)"
    echo "  IDS API Docs: http://${NODE_IP}:${IDS_API_NODEPORT}/docs"
    echo "  IDS UI:       http://${NODE_IP}:${IDS_API_NODEPORT}/ui"
    echo "  Local UI:     http://localhost:8000/ui (when port-forward is active)"
    echo "  Grafana:      http://${NODE_IP}:${GRAFANA_NODEPORT}  (admin/admin)"
    echo "  Prometheus:   http://${NODE_IP}:${PROM_NODEPORT}"
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

    if [[ $SURICATA -ge 1 ]] && [[ $SURICATA_FORWARDER -ge 1 ]]; then
        log_info "NETWORK IDS: Ready (Suricata & Forwarder)"
    else
        log_warn "NETWORK IDS: Incomplete"
    fi
    
    if [[ $SMART_RUNNING -ge 8 ]]; then
        log_info "SERVICES: Healthy ($SMART_RUNNING pods running)"
    else
        log_warn "SERVICES: Degraded ($SMART_RUNNING pods running)"
    fi
    
    echo ""
    
    if [[ $PIPELINE_OK -eq 0 ]]; then
        log_error "System not fully ready for operation"
        return 1
    else
        log_info "✅ System ready for operation"
        echo ""
        echo "Quick commands:"
        echo "  Local API:  kubectl -n smart-city port-forward svc/ids-api-service 8000:8000"
        echo "  Tail logs:  kubectl logs -f -n smart-city -l app=ids-api"
        echo "  Demo:       bash scripts/demo.sh"
        echo "  Check all:  bash scripts/check-setup.sh --verbose"
    fi
    return 0
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
    show_health || exit 1
fi
