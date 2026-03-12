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

# Load local .env for truthful key-status reporting during deploy. The Kubernetes
# secret remains the source consumed by the running pod, but operators expect
# deploy output to reflect the repo-local config they are about to apply.
if [[ -f "$PROJECT_ROOT/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$PROJECT_ROOT/.env"
    set +a
fi

# Colors
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
log()  { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}!${NC} $*"; }
err()  { echo -e "${RED}✗${NC} $*"; }

NAMESPACE="smart-city"

resolve_ids_api_health_url() {
    local local_url="http://127.0.0.1:8000/health"
    if curl -fsS "$local_url" >/dev/null 2>&1; then
        printf '%s\n' "$local_url"
        return 0
    fi

    local local_nodeport_url="http://127.0.0.1:30800/health"
    if curl -fsS "$local_nodeport_url" >/dev/null 2>&1; then
        printf '%s\n' "$local_nodeport_url"
        return 0
    fi

    local node_port node_ip
    node_port="$(kubectl get svc ids-api-service -n "$NAMESPACE" -o jsonpath='{.spec.ports[?(@.name=="http")].nodePort}' 2>/dev/null || true)"
    node_ip="$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}' 2>/dev/null || true)"
    if [[ -n "$node_ip" && -n "$node_port" ]]; then
        printf 'http://%s:%s/health\n' "$node_ip" "$node_port"
        return 0
    fi

    return 1
}

probe_ids_api_pod_local() {
    local pod_name
    pod_name="$(kubectl get pods -n "$NAMESPACE" -l app=ids-api --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
    [[ -n "$pod_name" ]] || return 1
    kubectl exec -n "$NAMESPACE" "$pod_name" -- sh -lc 'wget -qO- http://127.0.0.1:8000/health >/dev/null' >/dev/null 2>&1
}

refresh_emulator_code_configmaps() {
    declare -A maps=(
        ["traffic-camera-code"]="smart-city-services/traffic-camera/app.py"
        ["healthcare-api-code"]="smart-city-services/healthcare-api/app.py"
        ["parking-system-code"]="smart-city-services/parking-system/app.py"
        ["env-sensor-code"]="smart-city-services/environmental-sensor/app.py"
        ["street-lighting-code"]="smart-city-services/street-lighting/app.py"
    )

    local refreshed=0
    local cm
    for cm in "${!maps[@]}"; do
        local src="${maps[$cm]}"
        if [[ -f "$src" ]]; then
            kubectl create configmap "$cm" -n "$NAMESPACE" \
                --from-file=app.py="$src" \
                --dry-run=client -o yaml \
                | kubectl apply --server-side --force-conflicts -f - >/dev/null
            refreshed=$((refreshed + 1))
        fi
    done
    log "Refreshed ${refreshed} emulator code ConfigMaps"
}

apply_active_manifests() {
    local manifests=(
        "k8s-manifests/ids-api-FINAL.yaml"
        "k8s-manifests/services-no-build.yaml"
        "k8s-manifests/suricata-fixed.yaml"
        "k8s-manifests/falco-forwarder.yaml"
    )

    local manifest
    for manifest in "${manifests[@]}"; do
        [[ -f "$manifest" ]] || continue
        kubectl apply -f "$manifest" >/dev/null
    done
    log "Applied active manifests (ids-api, services, suricata, falco forwarder)"
}

normalize_ids_api_env() {
    local desired_env_json patch_payload
    desired_env_json="$(python - <<'PY'
import json
import yaml

with open("k8s-manifests/ids-api-FINAL.yaml", "r", encoding="utf-8") as fh:
    for doc in yaml.safe_load_all(fh):
        if doc and doc.get("kind") == "Deployment" and doc.get("metadata", {}).get("name") == "ids-api":
            print(json.dumps(doc["spec"]["template"]["spec"]["containers"][0]["env"]))
            break
PY
)"
    [[ -n "$desired_env_json" ]] || return 0
    patch_payload="$(jq -cn --argjson env "$desired_env_json" '[{"op":"replace","path":"/spec/template/spec/containers/0/env","value":$env}]')"
    kubectl patch deploy ids-api -n "$NAMESPACE" --type=json -p "$patch_payload" >/dev/null 2>&1 || true
}

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
        status_url="$(resolve_ids_api_health_url || true)"
        HTTP="000"
        if [[ -n "$status_url" ]]; then
            HTTP=$(curl -s -o /dev/null -w "%{http_code}" "$status_url" 2>/dev/null || echo "000")
        fi
        if [[ "$HTTP" == "200" ]]; then
            echo -e "${GREEN}OK${NC} (${status_url})"
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
        cat <<'EOF'
Usage:
  bash scripts/deploy-code.sh
  bash scripts/deploy-code.sh --status
  bash scripts/deploy-code.sh --llm-status

Purpose:
  Update the running local Smart City IDS code on an existing cluster.

What this script does:
  - builds the shared emulator runtime image
  - builds the ids-api image
  - imports both images into k3s
  - refreshes mounted static files and emulator ConfigMaps
  - reapplies the active manifests
  - restarts the affected workloads
  - waits for the IDS API health check

When to use it:
  - after backend code changes
  - after dashboard changes
  - after emulator service code changes

Options:
  --status       Show ids-api pod/service status and the detected live health URL
  --llm-status   Show provider status from the live API

Note:
  For a full cluster bring-up, use:
    sudo bash scripts/start-everything.sh
EOF
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

if ! command -v docker &>/dev/null; then
    err "Docker not found"
    exit 1
fi

log "Building smart-city-service image..."
if ! docker build -q -t smart-city-ids/smart-city-service:latest -f docker/smart-city-service/Dockerfile . >/dev/null 2>&1; then
    err "smart-city-service image build failed"
    exit 1
fi
log "smart-city-service image built"

log "Building ids-api image..."
if ! docker build -q -t ids-api:latest -f docker/ids-api/Dockerfile . >/dev/null 2>&1; then
    err "ids-api image build failed"
    exit 1
fi
log "ids-api image built"

log "Importing images to k3s..."
for img in smart-city-ids/smart-city-service:latest ids-api:latest; do
    local_tar="/tmp/$(echo "$img" | tr '/: ' '_').tar"
    docker save "$img" -o "$local_tar" 2>/dev/null
    sudo k3s ctr images import "$local_tar" >/dev/null 2>&1
    rm -f "$local_tar"
done
log "Images imported to k3s"

# If the live deployment overlays /app/static via ConfigMaps, the UI will NOT
# come from the container image. Refresh mounted static assets so /ui reflects
# the latest workspace changes.
if kubectl get deploy -n "$NAMESPACE" ids-api -o jsonpath='{..volumeMounts[*].mountPath}' 2>/dev/null | grep -q '/app/static'; then
    log "Refreshing UI ConfigMap (ids-app-static)..."
    STATIC_ARGS=(--from-file=index.html=services/ids-api/static/index.html)
    if [[ -f services/ids-api/static/help.html ]]; then
        STATIC_ARGS+=(--from-file=help.html=services/ids-api/static/help.html)
    fi
    kubectl create configmap ids-app-static -n "$NAMESPACE" \
        "${STATIC_ARGS[@]}" \
        --dry-run=client -o yaml \
        | kubectl apply --server-side --force-conflicts -f - >/dev/null
fi

if kubectl get deploy -n "$NAMESPACE" ids-api -o jsonpath='{..volumeMounts[*].mountPath}' 2>/dev/null | grep -q '/app/static/js'; then
    log "Refreshing UI JS ConfigMap (ids-app-static-js)..."
    kubectl create configmap ids-app-static-js -n "$NAMESPACE" \
        --from-file=services/ids-api/static/js \
        --dry-run=client -o yaml \
        | kubectl apply --server-side --force-conflicts -f - >/dev/null
fi

if kubectl get deploy -n "$NAMESPACE" ids-api -o jsonpath='{..volumeMounts[*].mountPath}' 2>/dev/null | grep -q '/app/static/js/modules'; then
    log "Refreshing UI JS modules ConfigMap (ids-app-static-js-modules)..."
    kubectl create configmap ids-app-static-js-modules -n "$NAMESPACE" \
        --from-file=services/ids-api/static/js/modules \
        --dry-run=client -o yaml \
        | kubectl apply --server-side --force-conflicts -f - >/dev/null
fi

normalize_ids_api_env
refresh_emulator_code_configmaps
apply_active_manifests
normalize_ids_api_env

log "Restarting pods..."
kubectl delete pods -n "$NAMESPACE" -l app=ids-api --force --grace-period=0 2>/dev/null || true
kubectl rollout restart deployment/traffic-camera -n "$NAMESPACE" >/dev/null 2>&1 || true
kubectl rollout restart deployment/healthcare-api -n "$NAMESPACE" >/dev/null 2>&1 || true
kubectl rollout restart deployment/parking-system -n "$NAMESPACE" >/dev/null 2>&1 || true
kubectl rollout restart deployment/env-sensor -n "$NAMESPACE" >/dev/null 2>&1 || true
kubectl rollout restart deployment/street-lighting -n "$NAMESPACE" >/dev/null 2>&1 || true
kubectl rollout restart deployment/suricata -n monitoring >/dev/null 2>&1 || true
kubectl rollout restart deployment/suricata-forwarder -n monitoring >/dev/null 2>&1 || true
kubectl rollout restart deployment/falco-forwarder -n falco-system >/dev/null 2>&1 || true
kubectl rollout restart daemonset/falco -n falco-system >/dev/null 2>&1 || true

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
HEALTH_URL=""
HTTP="000"
for _ in {1..15}; do
    HEALTH_URL="$(resolve_ids_api_health_url || true)"
    if [[ -n "$HEALTH_URL" ]]; then
        HTTP="$(curl -s -o /dev/null -w "%{http_code}" "$HEALTH_URL" 2>/dev/null || echo "000")"
        [[ "$HTTP" == "200" ]] && break
    fi
    sleep 2
done
if [[ "$HTTP" == "200" ]]; then
    log "Health check passed via ${HEALTH_URL}"
    if [[ "$HEALTH_URL" == "http://127.0.0.1:8000/health" ]]; then
        log "Dashboard: http://127.0.0.1:8000/ui"
    else
        log "Dashboard: ${HEALTH_URL%/health}/ui"
    fi
elif probe_ids_api_pod_local; then
    log "Health check passed via pod-local probe"
    warn "Service URL not reachable yet from this shell; use localhost port-forward or wait a few seconds for NodePort readiness"
else
    warn "Health check: HTTP $HTTP"
    warn "Pods may still be starting..."
fi

echo ""
