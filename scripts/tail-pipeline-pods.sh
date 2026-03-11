#!/usr/bin/env bash
set -euo pipefail

# Tail raw logs for the active Smart City IDS pipeline.
# Includes:
# - IoT services and MQTT broker
# - Falco and Falco forwarder
# - Suricata and Suricata forwarder
# - IDS API
#
# Usage:
#   bash scripts/tail-pipeline-pods.sh
#   SINCE=15m bash scripts/tail-pipeline-pods.sh
#   INCLUDE_IOT=false bash scripts/tail-pipeline-pods.sh

NS="${K8S_NAMESPACE:-smart-city}"
MON_NS="${MONITORING_NAMESPACE:-monitoring}"
FALCO_NS="${FALCO_NAMESPACE:-falco-system}"
SINCE="${SINCE:-10m}"
INCLUDE_IOT="${INCLUDE_IOT:-true}"

show_help() {
  cat <<'EOF'
Usage:
  bash scripts/tail-pipeline-pods.sh

Purpose:
  Stream raw logs from the live Smart City IDS components:
  - ids-api
  - MQTT broker and IoT emulator services
  - Suricata and Suricata forwarder
  - Falco and Falco forwarder

Environment overrides:
  SINCE=10m            How far back to read before following
  INCLUDE_IOT=true     Include IoT emulator and broker logs
  K8S_NAMESPACE=...    Override smart-city namespace

Examples:
  bash scripts/tail-pipeline-pods.sh
  SINCE=30m bash scripts/tail-pipeline-pods.sh
  INCLUDE_IOT=false bash scripts/tail-pipeline-pods.sh

Note:
  This is the raw component log view.
  For processed IDS events, use:
    bash scripts/live-pipeline-log.sh --attacks
EOF
}

case "${1:-}" in
  --help|-h)
    show_help
    exit 0
    ;;
esac

need() { command -v "$1" >/dev/null 2>&1 || { echo "Missing required command: $1" >&2; exit 1; }; }
need kubectl
need sed

prefix() { local pfx="$1"; sed -u "s/^/[${pfx}] /"; }
run_tail() { local pfx="$1"; shift; ( "$@" 2>&1 | prefix "$pfx" ) & echo $!; }
has() { kubectl -n "$1" get "$2" "$3" >/dev/null 2>&1; }

PIDS=()
cleanup() { for pid in "${PIDS[@]:-}"; do kill "$pid" >/dev/null 2>&1 || true; done; }
trap cleanup EXIT INT TERM

echo "Tailing pipeline pods (since=$SINCE)"
echo "- smart-city: $NS"
echo "- monitoring: $MON_NS"
echo "- falco:      $FALCO_NS"
echo "- include IoT workloads: $INCLUDE_IOT"
echo "(Ctrl+C to stop)"
echo "---"

if has "$NS" deploy ids-api; then
  PIDS+=("$(run_tail "IDS-API" kubectl -n "$NS" logs -f deploy/ids-api --since="$SINCE" --all-containers=true)")
fi

if has "$MON_NS" deploy suricata; then
  PIDS+=("$(run_tail "SURICATA" kubectl -n "$MON_NS" logs -f deploy/suricata --since="$SINCE" --all-containers=true)")
fi
if has "$MON_NS" deploy suricata-forwarder; then
  PIDS+=("$(run_tail "SUR-FWD" kubectl -n "$MON_NS" logs -f deploy/suricata-forwarder --since="$SINCE" --all-containers=true)")
fi
if has "$FALCO_NS" deploy falco-forwarder; then
  PIDS+=("$(run_tail "FAL-FWD" kubectl -n "$FALCO_NS" logs -f deploy/falco-forwarder --since="$SINCE" --all-containers=true)")
fi
PIDS+=("$(run_tail "FALCO" kubectl -n "$FALCO_NS" logs -f -l app.kubernetes.io/name=falco --since="$SINCE" --all-containers=true)")

if [[ "$INCLUDE_IOT" == "true" ]]; then
  for dep in mqtt-broker traffic-camera parking-system healthcare-api env-sensor street-lighting; do
    if has "$NS" deploy "$dep"; then
      PIDS+=("$(run_tail "${dep^^}" kubectl -n "$NS" logs -f deploy/$dep --since="$SINCE" --all-containers=true)")
    fi
  done
fi

wait
