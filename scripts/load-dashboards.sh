#!/bin/bash
# =============================================================================
# Smart City IDS - Grafana Dashboard Loader
# Imports dashboards from infrastructure/monitoring/grafana-dashboards/
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DASHBOARD_DIR="${PROJECT_ROOT}/infrastructure/monitoring/grafana-dashboards"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Get Grafana URL
get_grafana_url() {
    local NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}' 2>/dev/null)
    if [[ -z "$NODE_IP" ]]; then
        log_error "Could not determine node IP"
        exit 1
    fi
    echo "http://${NODE_IP}:30300"
}

# Wait for Grafana to be ready
wait_for_grafana() {
    local grafana_url=$1
    local retries=30
    
    log_info "Waiting for Grafana at ${grafana_url}..."
    
    while ! curl -s "${grafana_url}/api/health" | grep -q "ok" && [[ $retries -gt 0 ]]; do
        sleep 2
        ((retries--))
    done
    
    if [[ $retries -eq 0 ]]; then
        log_error "Grafana not ready after 60 seconds"
        exit 1
    fi
    
    log_info "Grafana is ready"
}

# Import a single dashboard
import_dashboard() {
    local grafana_url=$1
    local dashboard_file=$2
    local dashboard_name=$(basename "$dashboard_file" .json)
    
    if [[ ! -f "$dashboard_file" ]]; then
        log_warn "Dashboard file not found: $dashboard_file"
        return 1
    fi
    
    log_info "Importing dashboard: $dashboard_name"
    
    # Wrap dashboard in import format
    local import_payload=$(jq '{
        dashboard: .,
        overwrite: true,
        inputs: [],
        folderId: 0
    }' "$dashboard_file")
    
    # Import via Grafana API
    local response=$(curl -s -X POST "${grafana_url}/api/dashboards/db" \
        -H "Content-Type: application/json" \
        -u admin:admin \
        -d "$import_payload")
    
    if echo "$response" | grep -q '"status":"success"'; then
        log_info "Successfully imported: $dashboard_name"
    elif echo "$response" | grep -q '"uid"'; then
        log_info "Successfully imported: $dashboard_name"
    else
        log_warn "Import response: $response"
    fi
}

# Configure Prometheus data source
configure_datasource() {
    local grafana_url=$1
    
    log_info "Configuring Prometheus data source..."
    
    local datasource_config='{
        "name": "Prometheus",
        "type": "prometheus",
        "url": "http://prometheus.monitoring.svc.cluster.local:9090",
        "access": "proxy",
        "isDefault": true
    }'
    
    curl -s -X POST "${grafana_url}/api/datasources" \
        -H "Content-Type: application/json" \
        -u admin:admin \
        -d "$datasource_config" > /dev/null 2>&1 || true
    
    log_info "Data source configured"
}

# Main
main() {
    log_info "=========================================="
    log_info "Grafana Dashboard Loader"
    log_info "=========================================="
    
    local grafana_url=$(get_grafana_url)
    
    wait_for_grafana "$grafana_url"
    configure_datasource "$grafana_url"
    
    # Find and import all dashboards
    if [[ -d "$DASHBOARD_DIR" ]]; then
        for dashboard in "$DASHBOARD_DIR"/*.json; do
            if [[ -f "$dashboard" ]]; then
                import_dashboard "$grafana_url" "$dashboard"
            fi
        done
    else
        log_warn "Dashboard directory not found: $DASHBOARD_DIR"
        log_info "You can manually import dashboards via Grafana UI"
    fi
    
    echo ""
    log_info "=========================================="
    log_info "Dashboards loaded!"
    log_info "Access Grafana at: $grafana_url"
    log_info "Credentials: admin / admin"
    log_info "=========================================="
}

main "$@"
