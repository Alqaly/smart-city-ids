#!/usr/bin/env bash
# =============================================================================
# Smart City IDS - Scale Profile Controller
# Applies repeatable scale profiles for emulator workloads and logical devices.
# =============================================================================

set -euo pipefail

PROFILE="${1:-status}"
NAMESPACE="${NAMESPACE:-smart-city}"
IDS_API_REPLICAS="${IDS_API_REPLICAS:-1}"

usage() {
    cat <<EOF
Usage: scripts/scale-profile.sh [status|small|medium|large]

Profiles:
  small   - laptop-friendly baseline
  medium  - stronger test load
  large   - high-load evaluator profile

Environment overrides:
  NAMESPACE=<ns>           (default: smart-city)
  IDS_API_REPLICAS=<n>     (default: 1)

Note:
  ids-api is kept at 1 by default due in-memory dedup/rate-limit state.
  Set IDS_API_REPLICAS>1 only if shared state is configured.
EOF
}

have_deploy() {
    kubectl -n "$NAMESPACE" get deploy "$1" >/dev/null 2>&1
}

scale_if_present() {
    local deploy="$1"
    local replicas="$2"
    if have_deploy "$deploy"; then
        kubectl -n "$NAMESPACE" scale deployment "$deploy" --replicas="$replicas" >/dev/null
        echo "scaled: $deploy -> $replicas"
    else
        echo "skip (missing): $deploy"
    fi
}

set_env_if_present() {
    local deploy="$1"
    local kv="$2"
    if have_deploy "$deploy"; then
        kubectl -n "$NAMESPACE" set env deployment/"$deploy" "$kv" >/dev/null
        echo "env: $deploy $kv"
    else
        echo "skip env (missing): $deploy"
    fi
}

status() {
    echo "Namespace: $NAMESPACE"
    kubectl -n "$NAMESPACE" get deploy \
        ids-api traffic-camera healthcare-api parking-system env-sensor street-lighting \
        -o custom-columns=NAME:.metadata.name,READY:.status.readyReplicas,DESIRED:.spec.replicas 2>/dev/null || true
    echo ""
    echo "Logical device scaling envs:"
    kubectl -n "$NAMESPACE" get deploy street-lighting -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="DEVICE_COUNT")].value}' 2>/dev/null | awk '{print "street-lighting DEVICE_COUNT=" $0}' || true
    kubectl -n "$NAMESPACE" get deploy env-sensor -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="ENV_SENSOR_STATION_COUNT")].value}' 2>/dev/null | awk '{print "env-sensor ENV_SENSOR_STATION_COUNT=" $0}' || true
    kubectl -n "$NAMESPACE" get deploy parking-system -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="PARKING_SLOT_MULTIPLIER")].value}' 2>/dev/null | awk '{print "parking-system PARKING_SLOT_MULTIPLIER=" $0}' || true
}

apply_profile() {
    local tc="$1" hc="$2" park="$3" env="$4" light="$5"
    local light_count="$6" env_count="$7" park_mult="$8"

    if [[ "$IDS_API_REPLICAS" -gt 1 ]]; then
        echo "warning: IDS_API_REPLICAS=$IDS_API_REPLICAS (>1) may require shared dedup/rate-limit state"
    fi

    scale_if_present ids-api "$IDS_API_REPLICAS"
    scale_if_present traffic-camera "$tc"
    scale_if_present healthcare-api "$hc"
    scale_if_present parking-system "$park"
    scale_if_present env-sensor "$env"
    scale_if_present street-lighting "$light"

    set_env_if_present street-lighting "DEVICE_COUNT=$light_count"
    set_env_if_present env-sensor "ENV_SENSOR_STATION_COUNT=$env_count"
    set_env_if_present parking-system "PARKING_SLOT_MULTIPLIER=$park_mult"

    echo ""
    echo "Profile applied. Current status:"
    status
}

case "$PROFILE" in
    status)
        status
        ;;
    small)
        apply_profile 2 2 2 2 2 120 10 1
        ;;
    medium)
        apply_profile 4 4 4 3 3 300 20 2
        ;;
    large)
        apply_profile 8 8 8 6 6 600 40 3
        ;;
    --help|-h|help)
        usage
        ;;
    *)
        echo "unknown profile: $PROFILE"
        usage
        exit 1
        ;;
esac

