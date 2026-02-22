#!/usr/bin/env bash
set -euo pipefail

# Tail the main IDS pipeline pod logs with clear prefixes.
#
# What you see:
# - Falco (runtime detection) logs
# - Falco forwarder logs (Falco JSON -> IDS API /api/alerts/internal)
# - Suricata forwarder logs (Eve JSON/syslog -> IDS API /api/alerts)
# - IDS API logs (ingest -> dedup -> LLM -> governance -> K8s actions)
#
# Usage:
#   bash scripts/tail-pipeline-pods.sh
#   SINCE=15m bash scripts/tail-pipeline-pods.sh
#   K8S_NAMESPACE=smart-city bash scripts/tail-pipeline-pods.sh
#

NS="${K8S_NAMESPACE:-smart-city}"
FALCO_NS="${FALCO_NAMESPACE:-falco-system}"
SINCE="${SINCE:-10m}"

need() {
  command -v "$1" >/dev/null 2>&1 || { echo "Missing required command: $1" >&2; exit 1; }
}
need kubectl
need sed

prefix() {
  local pfx="$1"
  sed -u "s/^/[${pfx}] /"
}

run_tail() {
  local pfx="$1"; shift
  # shellcheck disable=SC2090
  ( "$@" 2>&1 | prefix "$pfx" ) &
  echo $!
}

has() {
  kubectl -n "$1" get "$2" "$3" >/dev/null 2>&1
}

PIDS=()
cleanup() {
  for pid in "${PIDS[@]:-}"; do
    kill "$pid" >/dev/null 2>&1 || true
  done
}
trap cleanup EXIT INT TERM

echo "Tailing pipeline pods (since=$SINCE)"
echo "- smart-city namespace: $NS"
echo "- falco namespace:      $FALCO_NS"
echo "(Ctrl+C to stop)"
echo "---"

# IDS API
if has "$NS" deploy ids-api; then
  PIDS+=("$(run_tail "IDS-API" kubectl -n "$NS" logs -f deploy/ids-api --since="$SINCE" --all-containers=true)")
else
  PIDS+=("$(run_tail "IDS-API" kubectl -n "$NS" logs -f -l app=ids-api --since="$SINCE" --all-containers=true)")
fi

# Suricata forwarder
if has "$NS" deploy suricata-forwarder; then
  PIDS+=("$(run_tail "SUR-FWD" kubectl -n "$NS" logs -f deploy/suricata-forwarder --since="$SINCE" --all-containers=true)")
else
  PIDS+=("$(run_tail "SUR-FWD" kubectl -n "$NS" logs -f -l app=suricata-forwarder --since="$SINCE" --all-containers=true)")
fi

# Falco forwarder
if has "$FALCO_NS" deploy falco-forwarder; then
  PIDS+=("$(run_tail "FAL-FWD" kubectl -n "$FALCO_NS" logs -f deploy/falco-forwarder --since="$SINCE" --all-containers=true)")
else
  PIDS+=("$(run_tail "FAL-FWD" kubectl -n "$FALCO_NS" logs -f -l app=falco-forwarder --since="$SINCE" --all-containers=true)")
fi

# Falco itself (DaemonSet/Pods usually labeled app.kubernetes.io/name=falco)
PIDS+=("$(run_tail "FALCO" kubectl -n "$FALCO_NS" logs -f -l app.kubernetes.io/name=falco --since="$SINCE" --all-containers=true)")

# Keep parent alive
wait
