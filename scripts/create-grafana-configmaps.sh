#!/bin/bash
# =============================================================================
# Smart City IDS - Create Grafana Provisioning ConfigMaps
# Embeds dashboard JSON files into Kubernetes ConfigMaps for auto-loading
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DASHBOARD_DIR="${PROJECT_ROOT}/infrastructure/monitoring"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

log_info "Creating Grafana provisioning ConfigMaps..."

# Function to escape JSON for YAML
escape_json() {
    local file=$1
    # Compact JSON and escape special characters
    jq -c . "$file" | sed 's/\\/\\\\/g; s/"/\\"/g; s/$/\\n/' | tr -d '\n'
}

# Create temporary YAML file
TEMP_CM="${PROJECT_ROOT}/k8s-manifests/grafana-provisioning-configmap.yaml"

cat > "$TEMP_CM" << 'EOF'
apiVersion: v1
kind: ConfigMap
metadata:
  name: grafana-provisioning
  namespace: monitoring
data:
  # Tells Grafana where to find dashboards (auto-loaded on startup)
  dashboards.yaml: |
    apiVersion: 1
    providers:
    - name: 'Smart City IDS'
      orgId: 1
      folder: ''
      type: file
      disableDeletion: false
      editable: true
      options:
        path: /var/lib/grafana/dashboards
  
  # Configures Prometheus datasource (auto-created on startup)
  datasources.yaml: |
    apiVersion: 1
    datasources:
    - name: Prometheus
      type: prometheus
      url: http://prometheus.monitoring.svc.cluster.local:9090
      access: proxy
      isDefault: true
      jsonData:
        httpMethod: GET
        cacheTimeout: '60'

---
apiVersion: v1
kind: ConfigMap
metadata:
  name: grafana-dashboards
  namespace: monitoring
data:
EOF

# Add all dashboard files
for dashboard in "$DASHBOARD_DIR"/grafana-dashboard-*.json; do
    if [[ -f "$dashboard" ]]; then
        dashboard_name=$(basename "$dashboard" .json)
        log_info "Adding dashboard: $dashboard_name"
        
        # Add filename and content
        echo "  ${dashboard_name}.json: |" >> "$TEMP_CM"
        
        # Indent JSON content (2 spaces)
        jq . "$dashboard" | sed 's/^/    /' >> "$TEMP_CM"
        
        # Add blank line between entries
        echo "" >> "$TEMP_CM"
    fi
done

log_info "✓ ConfigMap created: $TEMP_CM"
log_info "You can now deploy with: kubectl apply -f $TEMP_CM"
log_info ""
log_info "Or let deploy.sh do it automatically."
