#!/bin/bash
# =============================================================================
# Smart City IDS - Create Grafana Provisioning ConfigMaps
# Generates Kubernetes ConfigMaps for automatic dashboard loading
# Usage: bash scripts/create-grafana-configmaps.sh [--namespace NS] [--output FILE]
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")}" && pwd)"
source "$SCRIPT_DIR/lib/script-utils.sh"

init_script "$0" "Grafana ConfigMap Generator"

NAMESPACE="monitoring"
OUTPUT_FILE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --namespace)  NAMESPACE="$2"; shift 2 ;;
        --output)     OUTPUT_FILE="$2"; shift 2 ;;
        --help)       print_help "create-grafana-configmaps.sh [--namespace NS]"; exit 0 ;;
        *)            die "Unknown option: $1" ;;
    esac
done

ensure_command kubectl
ensure_command jq

PROJECT_ROOT=$(dirname "$SCRIPT_DIR")
DASHBOARD_DIR="${PROJECT_ROOT}/infrastructure/monitoring"
OUTPUT_FILE="${OUTPUT_FILE:-${PROJECT_ROOT}/k8s-manifests/grafana-provisioning-configmap.yaml}"

log_section "CONFIGURATION"
log_info "Namespace: $NAMESPACE"
log_info "Dashboard Directory: $DASHBOARD_DIR"
log_info "Output: $OUTPUT_FILE"
echo ""

# Validate namespace
if kubectl get namespace "$NAMESPACE" &>/dev/null 2>&1; then
    log_info "✓ Namespace exists: $NAMESPACE"
else
    log_warn "Namespace does not exist yet: $NAMESPACE"
fi

log_section "GENERATING CONFIGMAPS"

# Create temporary YAML
TEMP_FILE=$(mktemp)
trap "rm -f $TEMP_FILE" EXIT

# Base provisioning config
cat > "$TEMP_FILE" << 'EOF'
apiVersion: v1
kind: ConfigMap
metadata:
  name: grafana-provisioning
  namespace: monitoring
data:
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
  
  datasources.yaml: |
    apiVersion: 1
    datasources:
    - name: Prometheus
      type: prometheus
      url: http://prometheus.monitoring.svc.cluster.local:9090
      access: proxy
      isDefault: true

---
apiVersion: v1
kind: ConfigMap
metadata:
  name: grafana-dashboards
  namespace: monitoring
data:
EOF

# Add dashboards
DASHBOARD_COUNT=0
if [[ -d "$DASHBOARD_DIR" ]]; then
    for dashboard in "$DASHBOARD_DIR"/grafana-dashboard-*.json; do
        if [[ -f "$dashboard" ]]; then
            dashboard_name=$(basename "$dashboard" .json)
            log_info "Adding: $dashboard_name"
            
            echo "  ${dashboard_name}.json: |" >> "$TEMP_FILE"
            jq . "$dashboard" | sed 's/^/    /' >> "$TEMP_FILE"
            echo "" >> "$TEMP_FILE"
            
            ((DASHBOARD_COUNT++))
        fi
    done
else
    log_warn "Dashboard directory not found: $DASHBOARD_DIR"
fi

# Create output directory if needed
mkdir -p "$(dirname "$OUTPUT_FILE")"

# Save
cp "$TEMP_FILE" "$OUTPUT_FILE"
log_info "✓ ConfigMap generated: $OUTPUT_FILE"
log_info "Dashboards included: $DASHBOARD_COUNT"
echo ""

log_section "NEXT STEPS"
echo "Deploy with:"
echo "  kubectl apply -f $OUTPUT_FILE"
echo ""
echo "Or verify syntax:"
echo "  kubectl apply -f $OUTPUT_FILE --dry-run=client"
echo ""
