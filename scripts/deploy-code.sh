#!/bin/bash
# =============================================================================
# Smart City IDS — Quick Code Deploy (NO Docker required)
# Updates ConfigMaps from source and restarts pods.
# Only rebuilds Docker image when requirements.txt changes.
#
# Usage:
#   ./scripts/deploy-code.sh              # Code-only update (fast, no Docker)
#   ./scripts/deploy-code.sh --full       # Full rebuild with Docker image
#   ./scripts/deploy-code.sh --status     # Show current pod status
# =============================================================================

set -euo pipefail
cd "$(dirname "$0")/.."
PROJECT_ROOT="$(pwd)"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
log()  { echo -e "${GREEN}[deploy]${NC} $*"; }
warn() { echo -e "${YELLOW}[deploy]${NC} $*"; }
err()  { echo -e "${RED}[deploy]${NC} $*"; }

NAMESPACE="smart-city"
DEPLOYMENT="ids-api"
SRC_DIR="$PROJECT_ROOT/services/ids-api/src"
STATIC_DIR="$PROJECT_ROOT/services/ids-api/static"
IDS_API_URL="${IDS_API_URL:-http://localhost:30800}"

check_llm_health() {
    log "Checking LLM provider status..."
    local llm_status providers_count
    llm_status="$(curl -s "${IDS_API_URL}/api/llm/status" 2>/dev/null || echo "{}")"

    if command -v jq >/dev/null 2>&1; then
        providers_count="$(echo "$llm_status" | jq -r '.providers | length // 0' 2>/dev/null || echo "0")"
    else
        providers_count="$(python3 -c 'import json,sys
try:
    d=json.loads(sys.stdin.read() or "{}")
    p=d.get("providers", [])
    print(len(p) if isinstance(p, list) else 0)
except Exception:
    print(0)' <<<"$llm_status")"
    fi

    if [[ "${providers_count:-0}" -le 0 ]]; then
        warn "⚠️  No LLM providers detected from ${IDS_API_URL}/api/llm/status"
        warn "   Ensure API keys exist in ids-secrets and pods have env vars."
        read -r -p "   Continue deployment? (y/N) " -n 1 REPLY
        echo
        if [[ ! "$REPLY" =~ ^[Yy]$ ]]; then
            err "Deployment cancelled."
            exit 1
        fi
    else
        log "✓ LLM providers configured: ${providers_count}"
    fi
}

# ─── Status check ───────────────────────────────────────────────────────
if [[ "${1:-}" == "--status" ]]; then
    echo ""
    log "Pod status:"
    kubectl get pods -n "$NAMESPACE" -l app=ids-api -o wide
    echo ""
    log "Service:"
    kubectl get svc -n "$NAMESPACE" ids-api-service
    echo ""
    log "Quick test:"
    HTTP=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:30800/health 2>/dev/null || echo "000")
    if [[ "$HTTP" == "200" ]]; then
        echo -e "  ${GREEN}✓${NC} http://localhost:30800/health → 200 OK"
        echo -e "  ${GREEN}✓${NC} Dashboard: http://localhost:30800/ui"
    else
        echo -e "  ${RED}✗${NC} http://localhost:30800/health → $HTTP"
    fi
    exit 0
fi

# ─── Validate source ────────────────────────────────────────────────────
[[ -f "$SRC_DIR/main.py" ]]        || { err "Missing $SRC_DIR/main.py"; exit 1; }
[[ -f "$STATIC_DIR/index.html" ]]  || { err "Missing $STATIC_DIR/index.html"; exit 1; }
check_llm_health

log "Deploying from: $PROJECT_ROOT"
echo ""

# ─── Full rebuild (always — Docker image is the deployment unit) ────────
log "Building Docker image (includes all source + static files)..."
if command -v docker &>/dev/null; then
    docker build -t ids-api:latest -f docker/ids-api/Dockerfile . 2>&1 | tail -5
    docker save ids-api:latest -o /tmp/ids-api.tar
    sudo k3s ctr images import /tmp/ids-api.tar
    rm -f /tmp/ids-api.tar
    log "Docker image rebuilt and imported"
else
    err "Docker not found — required for deployment"
    err "Install Docker to deploy: sudo apt install docker.io"
    exit 1
fi
echo ""

# ─── Restart pods ───────────────────────────────────────────────────────
log "Restarting pods..."
kubectl delete pods -n "$NAMESPACE" -l app=ids-api --force --grace-period=0 2>/dev/null || true
echo ""

# ─── Wait for ready ────────────────────────────────────────────────────
log "Waiting for pods..."
for i in $(seq 1 30); do
    READY=$(kubectl get pods -n "$NAMESPACE" -l app=ids-api --no-headers 2>/dev/null | grep -c "1/1.*Running" || true)
    TOTAL=$(kubectl get pods -n "$NAMESPACE" -l app=ids-api --no-headers 2>/dev/null | wc -l)
    if [[ "$READY" -ge 1 ]]; then
        echo ""
        log "✓ $READY/$TOTAL pods ready"
        break
    fi
    printf "."
    sleep 2
done
echo ""

# ─── Verify ─────────────────────────────────────────────────────────────
sleep 3
HTTP=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:30800/health 2>/dev/null || echo "000")
if [[ "$HTTP" == "200" ]]; then
    log "✓ Health check passed (200 OK)"
    log "✓ Dashboard: http://localhost:30800/ui"
    echo ""
    echo -e "${GREEN}Deploy complete!${NC}"
else
    warn "Health check returned $HTTP — pods may still be starting"
    warn "Run: kubectl get pods -n $NAMESPACE -l app=ids-api -w"
fi
