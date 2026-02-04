#!/bin/bash
# =============================================================================
# Smart City IDS - Grafana Provisioning Generator
# Generates ConfigMaps from dashboard JSON files
# Usage: bash scripts/generate-grafana-provisioning.sh [--output FILE] [--help]
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")}" && pwd)"
source "$SCRIPT_DIR/lib/script-utils.sh"

init_script "$0" "Grafana Provisioning Generator"

REPO_ROOT=$(dirname "$SCRIPT_DIR")
DASHBOARDS_DIR="$REPO_ROOT/infrastructure/monitoring"
OUTPUT_FILE="${REPO_ROOT}/k8s-manifests/grafana-provisioning-dashboards.yaml"

while [[ $# -gt 0 ]]; do
    case $1 in
        --output)  OUTPUT_FILE="$2"; shift 2 ;;
        --help)    print_help "generate-grafana-provisioning.sh [--output FILE]"; exit 0 ;;
        *)         die "Unknown option: $1" ;;
    esac
done

ensure_command jq

log_section "CONFIGURATION"
log_info "Dashboards Directory: $DASHBOARDS_DIR"
log_info "Output File: $OUTPUT_FILE"
echo ""

if [[ ! -d "$DASHBOARDS_DIR" ]]; then
    die "Dashboards directory not found: $DASHBOARDS_DIR"
fi

log_section "GENERATING PROVISIONING"

mkdir -p "$(dirname "$OUTPUT_FILE")"

# Generate ConfigMaps
log_info "Scanning for dashboard files..."
DASHBOARD_COUNT=$(find "$DASHBOARDS_DIR" -name "*.json" 2>/dev/null | wc -l)
log_info "Found: $DASHBOARD_COUNT dashboard files"
echo ""

# Create provisioning YAML
{
    cat << 'EOF'
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
      type: file
      disableDeletion: false
      options:
        path: /var/lib/grafana/dashboards

---
apiVersion: v1
kind: ConfigMap
metadata:
  name: grafana-dashboards-generated
  namespace: monitoring
data:
EOF
    
    find "$DASHBOARDS_DIR" -name "*.json" -type f | while read -r dashboard; do
        name=$(basename "$dashboard" .json)
        echo "  ${name}.json: |"
        jq . "$dashboard" | sed 's/^/    /'
    done
} > "$OUTPUT_FILE"

log_info "✓ ConfigMap generated: $OUTPUT_FILE"
log_info "Dashboards embedded: $DASHBOARD_COUNT"
echo ""
log_section "NEXT STEPS"
echo "kubectl apply -f $OUTPUT_FILE"
echo ""
