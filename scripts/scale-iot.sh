#!/bin/bash
# =============================================================================
# Smart City IDS — IoT Fleet Scaling Script
# =============================================================================
# Scale the 5 IoT emulator deployments up or down.
#
# Usage:
#   bash scripts/scale-iot.sh              # Show current replicas
#   bash scripts/scale-iot.sh 3            # Scale all services to 3 replicas
#   bash scripts/scale-iot.sh 5 traffic-camera  # Scale one service to 5
#   bash scripts/scale-iot.sh up           # Increase all by 1
#   bash scripts/scale-iot.sh down         # Decrease all by 1
# =============================================================================

set -euo pipefail

NAMESPACE="smart-city"
SERVICES=(traffic-camera parking-system healthcare-api env-sensor street-lighting)

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

export KUBECONFIG="${KUBECONFIG:-/etc/rancher/k3s/k3s.yaml}"

show_status() {
    echo -e "\n${BOLD}IoT Fleet Status${RESET} (namespace: ${NAMESPACE})"
    echo "──────────────────────────────────────────────"
    printf "%-20s %8s %8s %8s\n" "SERVICE" "DESIRED" "READY" "AVAIL"
    echo "──────────────────────────────────────────────"
    local total_desired=0
    local total_ready=0
    for svc in "${SERVICES[@]}"; do
        local desired ready avail
        desired=$(kubectl get deployment "$svc" -n "$NAMESPACE" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo 0)
        ready=$(kubectl get deployment "$svc" -n "$NAMESPACE" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo 0)
        avail=$(kubectl get deployment "$svc" -n "$NAMESPACE" -o jsonpath='{.status.availableReplicas}' 2>/dev/null || echo 0)
        ready=${ready:-0}; avail=${avail:-0}
        total_desired=$((total_desired + desired))
        total_ready=$((total_ready + ready))
        local color="$GREEN"
        [[ "$ready" -lt "$desired" ]] && color="$YELLOW"
        [[ "$ready" -eq 0 ]] && color="$RED"
        printf "%-20s ${color}%8s %8s %8s${RESET}\n" "$svc" "$desired" "$ready" "$avail"
    done
    echo "──────────────────────────────────────────────"
    printf "%-20s %8s %8s\n" "TOTAL" "$total_desired" "$total_ready"
    echo ""
}

scale_service() {
    local svc=$1 replicas=$2
    echo -e "${CYAN}Scaling ${BOLD}$svc${RESET}${CYAN} to $replicas replicas...${RESET}"
    kubectl scale deployment "$svc" -n "$NAMESPACE" --replicas="$replicas"
}

# Notify dashboard API so the web UI reflects the change
notify_dashboard() {
    local api_url="${IDS_API_URL:-http://localhost:30800}"
    curl -s -X POST "${api_url}/api/iot/scale" \
        -H "Content-Type: application/json" \
        -d '{"replicas": '"${1:-1}"'}' \
        >/dev/null 2>&1 || true
}

# ── Main ──
if [[ $# -eq 0 ]]; then
    show_status
    exit 0
fi

ARG1="${1:-}"
ARG2="${2:-}"

case "$ARG1" in
    up)
        echo -e "${GREEN}Scaling all IoT services UP (+1)${RESET}"
        for svc in "${SERVICES[@]}"; do
            current=$(kubectl get deployment "$svc" -n "$NAMESPACE" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo 1)
            new=$((current + 1))
            [[ $new -gt 10 ]] && new=10
            scale_service "$svc" "$new"
        done
        ;;
    down)
        echo -e "${YELLOW}Scaling all IoT services DOWN (-1)${RESET}"
        for svc in "${SERVICES[@]}"; do
            current=$(kubectl get deployment "$svc" -n "$NAMESPACE" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo 1)
            new=$((current - 1))
            [[ $new -lt 1 ]] && new=1
            scale_service "$svc" "$new"
        done
        ;;
    [0-9]*)
        REPLICAS=$ARG1
        [[ $REPLICAS -lt 1 ]] && REPLICAS=1
        [[ $REPLICAS -gt 10 ]] && REPLICAS=10
        if [[ -n "$ARG2" ]]; then
            echo -e "${GREEN}Scaling ${BOLD}$ARG2${RESET}${GREEN} to $REPLICAS replicas${RESET}"
            scale_service "$ARG2" "$REPLICAS"
        else
            echo -e "${GREEN}Scaling ALL IoT services to $REPLICAS replicas${RESET}"
            for svc in "${SERVICES[@]}"; do
                scale_service "$svc" "$REPLICAS"
            done
        fi
        ;;
    *)
        echo "Usage: $0 [replicas|up|down] [service]"
        echo ""
        echo "Examples:"
        echo "  $0           # Show current status"
        echo "  $0 3         # Scale all to 3 replicas"
        echo "  $0 5 env-sensor  # Scale one service"
        echo "  $0 up        # Increase all by 1"
        echo "  $0 down      # Decrease all by 1"
        exit 1
        ;;
esac

echo ""
sleep 2
show_status
notify_dashboard "${ARG1:-1}"
