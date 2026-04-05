#!/usr/bin/env bash
# =============================================================================
# Smart City IDS - Stable Local Access Helper
# Provides localhost access via managed port-forwards independent of Wi-Fi IP.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/script-utils.sh"

QUIET="${QUIET:-0}"
ACTION=""
for _arg in "$@"; do
    case "$_arg" in
        --quiet) QUIET=1 ;;
        --help|-h) ;;
        *) ACTION="$_arg" ;;
    esac
done
ACTION="${ACTION:-start}"
STATE_DIR="/tmp/smart-city-ids-access"

IDS_PID_FILE="${STATE_DIR}/pf-ids-api.pid"
GRAFANA_PID_FILE="${STATE_DIR}/pf-grafana.pid"
PROM_PID_FILE="${STATE_DIR}/pf-prometheus.pid"

IDS_LOG="/tmp/ids-api-portforward.log"
GRAFANA_LOG="/tmp/grafana-portforward.log"
PROM_LOG="/tmp/prometheus-portforward.log"

mkdir -p "$STATE_DIR"

quiet_log() {
    if [[ "$QUIET" != "1" ]]; then
        echo "$@"
    fi
}

service_exists() {
    local ns="$1"
    local svc="$2"
    kubectl get svc "$svc" -n "$ns" >/dev/null 2>&1
}

start_all() {
    ensure_commands kubectl curl
    ensure_kubeconfig

    if ! service_exists smart-city ids-api-service; then
        log_error "Missing service: smart-city/ids-api-service"
        log_error "Apply manifests first: kubectl apply -f k8s-manifests/ids-api.yaml"
        exit 1
    fi

    stop_all true

    start_port_forward_checked "smart-city" "ids-api-service" "8000:8000" \
        "http://127.0.0.1:8000/health" "$IDS_LOG" "$IDS_PID_FILE" 30 1

    if service_exists monitoring grafana; then
        start_port_forward_checked "monitoring" "grafana" "3000:3000" \
            "http://127.0.0.1:3000/api/health" "$GRAFANA_LOG" "$GRAFANA_PID_FILE" 20 0 || true
    fi

    if service_exists monitoring prometheus; then
        start_port_forward_checked "monitoring" "prometheus" "9090:9090" \
            "http://127.0.0.1:9090/-/healthy" "$PROM_LOG" "$PROM_PID_FILE" 20 0 || true
    fi

    status_all
}

stop_all() {
    local silent="${1:-false}"
    stop_port_forward_checked "$IDS_PID_FILE" "kubectl .*port-forward .*svc/ids-api-service .*8000:8000"
    stop_port_forward_checked "$GRAFANA_PID_FILE" "kubectl .*port-forward .*svc/grafana .*3000:3000"
    stop_port_forward_checked "$PROM_PID_FILE" "kubectl .*port-forward .*svc/prometheus .*9090:9090"

    if [[ "$silent" != "true" && "$QUIET" != "1" ]]; then
        log_info "Stopped Smart City IDS local access port-forwards"
    fi
}

status_line() {
    local name="$1"
    local url="$2"
    local code
    code="$(curl -s -o /dev/null -w "%{http_code}" "$url" || true)"
    if [[ "$code" == "200" ]]; then
        quiet_log "  ${name}: ${url} [OK]"
    else
        quiet_log "  ${name}: ${url} [DOWN:${code:-000}]"
    fi
}

status_all() {
    quiet_log ""
    quiet_log "Stable local URLs (independent of Wi-Fi IP):"
    status_line "IDS API" "http://127.0.0.1:8000/health"
    status_line "IDS UI" "http://127.0.0.1:8000/ui"
    status_line "Grafana" "http://127.0.0.1:3000/api/health"
    status_line "Prometheus" "http://127.0.0.1:9090/-/healthy"

    local node_ip ids_port
    node_ip="$(get_node_ip 2>/dev/null || echo "unknown")"
    ids_port="$(get_service_nodeport ids-api-service smart-city 30800 2>/dev/null || echo "30800")"
    quiet_log ""
    quiet_log "NodePort URL (changes with node network/IP): http://${node_ip}:${ids_port}"
    quiet_log ""
}

print_usage() {
    cat <<EOF
Usage: scripts/access-stack.sh [start|stop|status|restart] [--quiet]

Commands:
  start    Start/refresh managed localhost port-forwards
  stop     Stop managed port-forwards
  status   Show live health for localhost endpoints
  restart  Stop then start

Options:
  --quiet  Minimize output (also supported via QUIET=1)
EOF
}

for _a in "$@"; do
    case "$_a" in --help|-h) print_usage; exit 0 ;; esac
done

case "$ACTION" in
    start) start_all ;;
    stop) stop_all ;;
    status) status_all ;;
    restart) stop_all true; start_all ;;
    *) print_usage; exit 1 ;;
esac

