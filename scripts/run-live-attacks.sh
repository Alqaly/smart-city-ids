#!/usr/bin/env bash
# =============================================================================
# Smart City IDS - Live Attack Runner
#
# Runs REAL traffic + runtime behaviors inside the Kubernetes cluster to trigger
# Suricata (network) and Falco (runtime) detections end-to-end.
#
# No synthetic alert injection into the IDS API.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

source "$SCRIPT_DIR/lib/script-utils.sh"

NAMESPACE="smart-city"
DURATION="30"
MODE="all"   # all|ddos|sqli|privesc|exfil

while [[ $# -gt 0 ]]; do
  case "$1" in
    --namespace) NAMESPACE="$2"; shift 2 ;;
    --duration) DURATION="$2"; shift 2 ;;
    --mode) MODE="$2"; shift 2 ;;
    --help)
      echo "Usage: bash scripts/run-live-attacks.sh [--duration SEC] [--mode all|ddos|sqli|privesc|exfil] [--namespace smart-city]"
      exit 0
      ;;
    *) die "Unknown option: $1" ;;
  esac
done

[[ "$DURATION" =~ ^[0-9]+$ ]] || die "--duration must be an integer"
[[ "$DURATION" -ge 5 ]] || die "--duration must be >= 5 seconds"

ensure_commands kubectl awk
ensure_kubeconfig

log_section "Live Attack Runner"
log_info "Namespace: $NAMESPACE"
log_info "Duration:  ${DURATION}s"
log_info "Mode:      $MODE"

log_subsection "Baseline IDS alert counter"
BASELINE_ALERTS="$(kubectl exec -n "$NAMESPACE" deploy/ids-api -- sh -lc "curl -s localhost:8000/metrics | awk '/^smartcity_ids_alerts_received_total\\{/ {sum+=\$NF} END {print sum+0}'" 2>/dev/null || echo 0)"
log_info "alerts_received_total (baseline, approx): ${BASELINE_ALERTS}"

if ! kubectl get ns "$NAMESPACE" >/dev/null 2>&1; then
  die "Namespace not found: $NAMESPACE"
fi

require_deploy() {
  local dep="$1"
  kubectl get deploy "$dep" -n "$NAMESPACE" >/dev/null 2>&1 || die "Missing deployment: $NAMESPACE/$dep"
}

require_deploy traffic-camera
require_deploy healthcare-api
require_deploy parking-system
require_deploy ids-api

ATTACK_POD="live-attack-runner"

cleanup() {
  kubectl delete pod "$ATTACK_POD" -n "$NAMESPACE" --ignore-not-found >/dev/null 2>&1 || true
}
trap cleanup EXIT

log_subsection "Launching ephemeral in-cluster runner pod"
kubectl delete pod "$ATTACK_POD" -n "$NAMESPACE" --ignore-not-found >/dev/null 2>&1 || true

kubectl run "$ATTACK_POD" -n "$NAMESPACE" \
  --image=python:3.11-slim \
  --restart=Never \
  --labels=app=live-attack-runner \
  --command -- /bin/sh -lc 'sleep 3600' >/dev/null

kubectl wait --for=condition=Ready pod/$ATTACK_POD -n "$NAMESPACE" --timeout=120s >/dev/null || die "Attack runner pod failed to become Ready"

log_subsection "Installing in-pod deps (httpx)"
kubectl exec -n "$NAMESPACE" "$ATTACK_POD" -- /bin/sh -lc 'python -V && pip -q install --no-cache-dir httpx' >/dev/null

run_http_attacks() {
  local duration="$1"
  local mode="$2"

  # Run from inside the cluster so service DNS resolves (ClusterIP Services).
  kubectl exec -i -n "$NAMESPACE" "$ATTACK_POD" -- \
    env DURATION="$duration" MODE="$mode" \
    python - <<'PY' >/dev/null || true
import asyncio
import os
import time

import httpx

duration = int(os.environ.get("DURATION", "30"))
mode = os.environ.get("MODE", "all")

services = {
    # Use ClusterIP Services (stable DNS) rather than pod/deployment names.
    "traffic": "http://traffic-camera-service:80",
    "health": "http://healthcare-api-service:80",
    "park": "http://parking-system-service:80",
}


async def ddos() -> None:
    url = services["traffic"] + "/api/stream"
    end = time.time() + duration
    async with httpx.AsyncClient(timeout=2.0) as client:
        sent = 0
        while time.time() < end:
            tasks = [client.get(url, params={"frame_id": sent + i}) for i in range(60)]
            await asyncio.gather(*tasks, return_exceptions=True)
            sent += 60
            await asyncio.sleep(0.2)


async def sqli() -> None:
    url = services["health"] + "/api/patients"
    payloads = [
        "1' OR '1'='1",
        "admin'; DROP TABLE patients; --",
        "' OR 1=1 --",
        "1' UNION SELECT * FROM users --",
    ]
    end = time.time() + duration
    async with httpx.AsyncClient(timeout=3.0) as client:
        n = 0
        while time.time() < end:
            p = payloads[n % len(payloads)]
            try:
                await client.post(url, json={"patient_id": p, "query": p})
            except Exception:
                pass
            n += 1
            await asyncio.sleep(0.1)


async def exfil() -> None:
    url = services["park"] + "/api/payments"
    end = time.time() + duration
    async with httpx.AsyncClient(timeout=5.0) as client:
        while time.time() < end:
            try:
                await client.get(
                    url,
                    params={"action": "export_all", "format": "csv", "include_sensitive": "true"},
                )
            except Exception:
                pass
            await asyncio.sleep(0.5)


async def unauthorized() -> None:
    targets = [
        services["traffic"] + "/api/analyze",
        services["health"] + "/api/records",
        services["park"] + "/api/reservations",
    ]
    end = time.time() + duration
    async with httpx.AsyncClient(timeout=3.0) as client:
        while time.time() < end:
            await asyncio.gather(
                *[client.get(t, headers={"Authorization": "Bearer invalid"}) for t in targets],
                return_exceptions=True,
            )
            await asyncio.sleep(0.3)


async def main() -> None:
    tasks = []
    if mode in ("all", "ddos"):
        tasks.append(ddos())
    if mode in ("all", "sqli"):
        tasks.append(sqli())
    if mode in ("all", "exfil"):
        tasks.append(exfil())
    if mode == "all":
        tasks.append(unauthorized())
    await asyncio.gather(*tasks)


asyncio.run(main())
PY
}

run_runtime_attacks() {
  local duration="$1"
  local end
  end=$(( $(date +%s) + duration ))

  # Runtime behaviors intended to trip Falco rules (exec shells, read sensitive files).
  # These execute inside the service pods (real runtime telemetry), not via IDS API.
  local i=0
  while [[ $(date +%s) -lt $end ]]; do
    i=$((i+1))
    # Privilege escalation-ish behavior: spawn shell and read sensitive files
    if [[ "$MODE" == "all" || "$MODE" == "privesc" ]]; then
      kubectl exec -n "$NAMESPACE" deploy/healthcare-api -- /bin/sh -lc 'id; uname -a; cat /etc/shadow >/dev/null 2>&1 || true; cat /etc/passwd >/dev/null 2>&1 || true' >/dev/null 2>&1 || true
    fi

    # Exfil-ish behavior: list /tmp and read common files
    if [[ "$MODE" == "all" || "$MODE" == "exfil" ]]; then
      kubectl exec -n "$NAMESPACE" deploy/parking-system -- /bin/sh -lc 'ls -la /tmp >/dev/null 2>&1 || true; cat /etc/passwd >/dev/null 2>&1 || true' >/dev/null 2>&1 || true
    fi

    # Noise in traffic-camera
    if [[ "$MODE" == "all" || "$MODE" == "ddos" ]]; then
      kubectl exec -n "$NAMESPACE" deploy/traffic-camera -- /bin/sh -lc 'echo probe >/dev/null' >/dev/null 2>&1 || true
    fi
    sleep 2
  done
}

log_section "Phase 1 - Network Attacks (Suricata)"
run_http_attacks "$DURATION" "$MODE"
log_info "HTTP attack traffic complete"

log_section "Phase 2 - Runtime Behaviors (Falco)"
run_runtime_attacks "$DURATION"
log_info "Runtime behaviors complete"

log_section "Phase 3 - Quick IDS Metrics Check"
sleep 5
after="$(kubectl exec -n "$NAMESPACE" deploy/ids-api -- sh -lc "curl -s localhost:8000/metrics | awk '/^smartcity_ids_alerts_received_total\{/ {sum+=\$NF} END {print sum+0}'" 2>/dev/null || echo 0)"
delta=$(( after - BASELINE_ALERTS ))

echo "Alerts received (delta, approx): +${delta}"
log_info "Live attack run finished"
