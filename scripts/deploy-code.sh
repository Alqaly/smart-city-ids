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

log "Deploying from: $PROJECT_ROOT"
echo ""

# ─── Full rebuild (only when --full or requirements changed) ────────────
if [[ "${1:-}" == "--full" ]]; then
    log "Full rebuild requested — building Docker image..."
    if command -v docker &>/dev/null; then
        docker build -t ids-api:latest -f docker/ids-api/Dockerfile . 2>&1 | tail -5
        docker save ids-api:latest -o /tmp/ids-api.tar
        sudo k3s ctr images import /tmp/ids-api.tar
        rm -f /tmp/ids-api.tar
        log "Docker image rebuilt and imported"
    else
        warn "Docker not found — skipping image rebuild"
        warn "Install Docker or use code-only deploy (no --full flag)"
    fi
    echo ""
fi

# ─── Update ConfigMaps (always — this is the fast path) ────────────────
log "Updating ConfigMap: ids-app-code"
kubectl delete configmap ids-app-code -n "$NAMESPACE" --ignore-not-found >/dev/null

# Build --from-file args for ALL .py and .txt files in src/
FROM_FILES=()
for f in "$SRC_DIR"/*.py "$SRC_DIR"/*.txt; do
    [[ -f "$f" ]] && FROM_FILES+=("--from-file=$f")
done

kubectl create configmap ids-app-code -n "$NAMESPACE" "${FROM_FILES[@]}" 2>/dev/null
log "✓ ids-app-code updated (${#FROM_FILES[@]} files)"

log "Updating ConfigMap: ids-app-static"
kubectl delete configmap ids-app-static -n "$NAMESPACE" --ignore-not-found >/dev/null
kubectl create configmap ids-app-static -n "$NAMESPACE" \
    --from-file="$STATIC_DIR/index.html" 2>/dev/null
log "✓ ids-app-static updated"
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
