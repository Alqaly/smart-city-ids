#!/bin/bash
# =============================================================================
# Smart City IDS - Grafana Dashboard Loader
# Imports dashboards from infrastructure/monitoring/
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Dashboard locations (check multiple paths)
DASHBOARD_DIRS=(
    "${PROJECT_ROOT}/infrastructure/monitoring/grafana-dashboards"
    "${PROJECT_ROOT}/infrastructure/monitoring"
)

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
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
    
    # First check if Prometheus is accessible
    local prom_url="http://prometheus.monitoring.svc.cluster.local:9090"
    if ! curl -s --connect-timeout 5 "${prom_url}/-/healthy" | grep -q "Prometheus"; then
        log_warn "⚠️  Prometheus at ${prom_url} is not accessible"
        log_info "This is OK if Prometheus is still starting up. Will retry later."
    else
        log_info "✓ Prometheus is reachable at ${prom_url}"
    fi
    
    local datasource_config='{
        "name": "Prometheus",
        "type": "prometheus",
        "url": "http://prometheus.monitoring.svc.cluster.local:9090",
        "access": "proxy",
        "isDefault": true,
        "jsonData": {
            "httpMethod": "GET",
            "cacheTimeout": "60"
        }
    }'
    
    # Check if datasource already exists
    local existing=$(curl -s "${grafana_url}/api/datasources/name/Prometheus" \
        -H "Content-Type: application/json" \
        -u admin:admin)
    
    if echo "$existing" | grep -q '"id"'; then
        log_info "✓ Prometheus datasource already exists"
        # Verify it can connect
        local health=$(curl -s "${grafana_url}/api/datasources/uid/prometheus/health" \
            -H "Content-Type: application/json" \
            -u admin:admin)
        if echo "$health" | grep -q '"status":"ok"'; then
            log_info "✓ Datasource health check passed"
        else
            log_warn "⚠️  Datasource health check failed (might be normal if Prometheus starting)"
        fi
    else
        # Create new datasource
        local response=$(curl -s -X POST "${grafana_url}/api/datasources" \
            -H "Content-Type: application/json" \
            -u admin:admin \
            -d "$datasource_config")
        
        if echo "$response" | grep -q '"id"'; then
            log_info "✓ Created Prometheus datasource"
        elif echo "$response" | grep -q 'already exists'; then
            log_info "✓ Prometheus datasource already exists"
        else
            log_warn "⚠️  Unexpected response creating datasource: $response"
        fi
    fi
}

# Main
main() {
    echo ""
    echo -e "${CYAN}╔════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║     Grafana Dashboard & Datasource Loader      ║${NC}"
    echo -e "${CYAN}╚════════════════════════════════════════════════╝${NC}"
    echo ""
    
    local grafana_url=$(get_grafana_url)
    
    log_info "Grafana URL: $grafana_url"
    log_info "Credentials: admin / admin"
    echo ""
    
    # Wait for Grafana
    wait_for_grafana "$grafana_url"
    echo ""
    
    # Configure datasource
    configure_datasource "$grafana_url"
    echo ""
    
    # Find dashboard directory
    local dashboard_dir=""
    for dir in "${DASHBOARD_DIRS[@]}"; do
        if [[ -d "$dir" ]]; then
            dashboard_dir="$dir"
            break
        fi
    done
    
    # Find and import all dashboards
    local imported=0
    local failed=0
    
    log_info "Searching for dashboards..."
    
    # Check root monitoring directory (where they actually are)
    if [[ -n "$dashboard_dir" ]]; then
        log_info "Checking: $dashboard_dir"
        for dashboard in "$dashboard_dir"/grafana-dashboard-*.json; do
            if [[ -f "$dashboard" ]]; then
                if import_dashboard "$grafana_url" "$dashboard"; then
                    ((imported++))
                else
                    ((failed++))
                fi
            fi
        done
    fi
    
    # Also check alternate location
    for dashboard in "${PROJECT_ROOT}/infrastructure/monitoring"/grafana-dashboard-*.json; do
        if [[ -f "$dashboard" ]]; then
            # Skip if already imported from directory above
            if [[ -n "$dashboard_dir" ]] && [[ "$dashboard" == "$dashboard_dir"* ]]; then
                continue
            fi
            if import_dashboard "$grafana_url" "$dashboard"; then
                ((imported++))
            else
                ((failed++))
            fi
        fi
    done
    
    echo ""
    echo -e "${CYAN}════════════════════════════════════════════════${NC}"
    
    if [[ $imported -eq 0 ]]; then
        log_warn "⚠️  No dashboards found to import"
        log_info "Expected locations:"
        for dir in "${DASHBOARD_DIRS[@]}"; do
            echo "  - $dir/*.json"
        done
        echo "  - ${PROJECT_ROOT}/infrastructure/monitoring/grafana-dashboard-*.json"
    else
        log_info "✓ Successfully imported $imported dashboard(s)"
        if [[ $failed -gt 0 ]]; then
            log_warn "⚠️  $failed dashboard(s) had issues (may still be usable)"
        fi
    fi
    
    echo ""
    log_info "Access Grafana:"
    echo "  URL:         $grafana_url"
    echo "  Username:    admin"
    echo "  Password:    admin"
    echo ""
    
    log_info "Verify data is loading:"
    echo "  1. Go to $grafana_url"
    echo "  2. Click Configuration → Data Sources"
    echo "  3. Click 'Prometheus'"
    echo "  4. Click 'Test' button - should show 'Data source is working'"
    echo "  5. Open a dashboard and verify graphs populate with data"
    echo "  6. If no data:"
    echo "     - Check Prometheus targets: http://localhost:9090/targets"
    echo "     - Verify IDS API metrics exposed: curl http://localhost:30800/metrics"
    echo "     - Check ServiceMonitor exists: kubectl get servicemonitor -n smart-city"
    echo ""
    
    echo -e "${CYAN}════════════════════════════════════════════════${NC}"
main "$@"
