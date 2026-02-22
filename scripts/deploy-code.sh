#!/bin/bash
# =============================================================================
# Smart City IDS — Code Deploy (SIMPLE)
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."
PROJECT_ROOT="$(pwd)"

# Load library
source "$SCRIPT_DIR/lib/llm-control.sh"

# Colors
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
log()  { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}!${NC} $*"; }
err()  { echo -e "${RED}✗${NC} $*"; }

NAMESPACE="smart-city"

# Check what user wants
case "${1:-}" in
    --status)
        echo ""
        log "Pod Status:"
        kubectl get pods -n "$NAMESPACE" -l app=ids-api -o wide 2>/dev/null || echo "  No pods found"
        echo ""
        log "Service:"
        kubectl get svc -n "$NAMESPACE" ids-api-service 2>/dev/null || echo "  Service not found"
        echo ""
        
        # Quick health check
        echo -n "Health check: "
        HTTP=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health 2>/dev/null || echo "000")
        if [[ "$HTTP" == "200" ]]; then
            echo -e "${GREEN}OK${NC} (localhost:8000)"
        else
            echo -e "${YELLOW}Not ready${NC} (HTTP $HTTP)"
        fi
        exit 0
        ;;
    
    --llm-status)
        llm_show_status
        exit 0
        ;;
    
    --help|-h)
        echo "Usage: deploy-code.sh [--status|--llm-status]"
        echo ""
        echo "Builds and deploys the IDS API Docker image."
        echo ""
        echo "Options:"
        echo "  --status       Show current pod status"
        echo "  --llm-status   Show LLM provider status"
        exit 0
        ;;
esac

# Main deploy
echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}Smart City IDS — Code Deploy${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Check LLM status first
llm_check_env_keys || true
echo ""

# Validate source
[[ -f "services/ids-api/src/main.py" ]] || { err "Missing main.py"; exit 1; }

log "Building Docker image..."
if ! command -v docker &>/dev/null; then
    err "Docker not found"
    exit 1
fi

docker build -t ids-api:latest -f docker/ids-api/Dockerfile . 2>&1 | tail -5 || {
    err "Docker build failed"
    exit 1
}

log "Image built successfully"

log "Importing to k3s..."
docker save ids-api:latest -o /tmp/ids-api.tar
sudo k3s ctr images import /tmp/ids-api.tar
rm -f /tmp/ids-api.tar

# If the live deployment overlays /app/static via ConfigMaps, the UI will NOT
# come from the container image. Refresh the mounted index.html so /ui reflects
# the latest workspace changes (e.g., registry-backed attack scenarios).
if kubectl get deploy -n "$NAMESPACE" ids-api -o jsonpath='{..volumeMounts[*].mountPath}' 2>/dev/null | grep -q '/app/static'; then
    log "Refreshing UI ConfigMap (ids-app-static)..."
    kubectl create configmap ids-app-static -n "$NAMESPACE" \
        --from-file=index.html=services/ids-api/static/index.html \
        --dry-run=client -o yaml \
        | kubectl apply --server-side --force-conflicts -f - >/dev/null
fi

log "Restarting pods..."
kubectl delete pods -n "$NAMESPACE" -l app=ids-api --force --grace-period=0 2>/dev/null || true

log "Waiting for ready..."
for i in {1..30}; do
    READY=$(kubectl get pods -n "$NAMESPACE" -l app=ids-api --no-headers 2>/dev/null | grep -c "Running" || true)
    if [[ "$READY" -ge 1 ]]; then
        echo ""
        log "$READY pod(s) ready"
        break
    fi
    echo -n "."
    sleep 2
done
echo ""

# Verify
sleep 2
HTTP=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health 2>/dev/null || echo "000")
if [[ "$HTTP" == "200" ]]; then
    log "Health check passed"
    log "Dashboard: http://localhost:8000/ui"
else
    warn "Health check: HTTP $HTTP"
    warn "Pods may still be starting..."
fi

echo ""
