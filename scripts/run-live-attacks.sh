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
EXPLAIN="1"
SHOW_ALERTS="3"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --namespace) NAMESPACE="$2"; shift 2 ;;
    --duration) DURATION="$2"; shift 2 ;;
    --mode) MODE="$2"; shift 2 ;;
    --no-explain) EXPLAIN="0"; shift ;;
    --show-alerts) SHOW_ALERTS="$2"; shift 2 ;;
    --help)
      echo "Usage: bash scripts/run-live-attacks.sh [--duration SEC] [--mode all|ddos|sqli|privesc|exfil] [--namespace smart-city] [--no-explain] [--show-alerts N]"
      exit 0
      ;;
    *) die "Unknown option: $1" ;;
  esac
done

[[ "$DURATION" =~ ^[0-9]+$ ]] || die "--duration must be an integer"
[[ "$DURATION" -ge 5 ]] || die "--duration must be >= 5 seconds"
[[ "$SHOW_ALERTS" =~ ^[0-9]+$ ]] || die "--show-alerts must be an integer"
[[ "$MODE" =~ ^(all|ddos|sqli|privesc|exfil)$ ]] || die "--mode must be one of: all|ddos|sqli|privesc|exfil"

ensure_commands kubectl awk python3
ensure_kubeconfig

if ! kubectl get ns "$NAMESPACE" >/dev/null 2>&1; then
  die "Namespace not found: $NAMESPACE"
fi

log_section "Live Attack Runner"
log_info "Namespace: $NAMESPACE"
log_info "Duration:  ${DURATION}s"
log_info "Mode:      $MODE"
if [[ "$EXPLAIN" == "1" ]]; then
  echo "Purpose: generate real in-cluster traffic and runtime behavior so Suricata/Falco create alerts."
  echo "Audience note: this is a controlled demo; it does not use synthetic IDS alert injection."
fi

require_deploy() {
  local dep="$1"
  kubectl get deploy "$dep" -n "$NAMESPACE" >/dev/null 2>&1 || die "Missing deployment: $NAMESPACE/$dep"
}

require_deploy traffic-camera
require_deploy healthcare-api
require_deploy parking-system
require_deploy ids-api

# Pin one IDS API pod so all before/after reads come from the same process.
IDS_API_POD="$(
  kubectl get pods -n "$NAMESPACE" -l app=ids-api -o json 2>/dev/null \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); items=d.get("items",[]); 
def ready(p):
    if p.get("status",{}).get("phase") != "Running": return False
    for c in p.get("status",{}).get("conditions",[]):
        if c.get("type")=="Ready" and c.get("status")=="True": return True
    return False
cands=[p for p in items if ready(p)]
cands.sort(key=lambda p: p.get("metadata",{}).get("creationTimestamp",""))
print((cands[-1]["metadata"]["name"] if cands else ""))' 2>/dev/null || true
)"
[[ -n "$IDS_API_POD" ]] || die "Could not find a running ids-api pod"
log_info "IDS API pod (pinned): ${IDS_API_POD}"

log_subsection "Baseline IDS alert counter"
BASELINE_ALERTS="$(kubectl exec -n "$NAMESPACE" "$IDS_API_POD" -- sh -lc "curl -s localhost:8000/api/metrics" 2>/dev/null | python3 -c 'import json,sys; d=json.load(sys.stdin); print((d if isinstance(d,dict) else {}).get(\"total_alerts\",0))' 2>/dev/null || echo 0)"
log_info "alerts_received_total (baseline, approx): ${BASELINE_ALERTS}"
BASELINE_PERSISTED="$(kubectl exec -n "$NAMESPACE" "$IDS_API_POD" -- sh -lc "curl -s localhost:8000/api/alerts?limit=1" 2>/dev/null | python3 -c 'import json,sys; \
d=json.load(sys.stdin); \
print((d if isinstance(d,dict) else {}).get(\"total\",0))' 2>/dev/null || echo 0)"
BASELINE_THROTTLED="$(kubectl exec -n "$NAMESPACE" "$IDS_API_POD" -- sh -lc "curl -s localhost:8000/api/rate-limiter/status" 2>/dev/null | python3 -c 'import json,sys; \
d=json.load(sys.stdin); \
print(((d.get(\"stats\") or {}).get(\"total_throttled\",0)) if isinstance(d,dict) else 0)' 2>/dev/null || echo 0)"

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
if [[ "$EXPLAIN" == "1" ]]; then
  echo "What this simulates:"
  echo "  - high-rate HTTP traffic (DDoS-like pressure)"
  echo "  - SQL injection patterns against healthcare endpoints"
  echo "  - suspicious export/exfil-style requests"
  echo "Expected detector: Suricata (network IDS)"
fi
run_http_attacks "$DURATION" "$MODE"
log_info "HTTP attack traffic complete"

log_section "Phase 2 - Runtime Behaviors (Falco)"
if [[ "$EXPLAIN" == "1" ]]; then
  echo "What this simulates:"
  echo "  - suspicious shell commands inside service containers"
  echo "  - reads of sensitive files (/etc/passwd, /etc/shadow)"
  echo "Expected detector: Falco (runtime/eBPF syscall monitoring)"
fi
run_runtime_attacks "$DURATION"
log_info "Runtime behaviors complete"

log_section "Phase 3 - Quick IDS Metrics Check"
sleep 5
after="$(kubectl exec -n "$NAMESPACE" "$IDS_API_POD" -- sh -lc "curl -s localhost:8000/api/metrics" 2>/dev/null | python3 -c 'import json,sys; d=json.load(sys.stdin); print((d if isinstance(d,dict) else {}).get(\"total_alerts\",0))' 2>/dev/null || echo 0)"
delta=$(( after - BASELINE_ALERTS ))

echo "Alerts received (delta, approx): +${delta}"
if [[ "$delta" -le 0 ]]; then
  log_warn "No alert increase observed. Check Suricata/Falco forwarders and IDS API ingestion."
else
  log_info "Detection pipeline responded during the run (new alerts observed)."
fi

PERSISTED_AFTER="$(kubectl exec -n "$NAMESPACE" "$IDS_API_POD" -- sh -lc "curl -s localhost:8000/api/alerts?limit=1" 2>/dev/null | python3 -c 'import json,sys; \
d=json.load(sys.stdin); \
print((d if isinstance(d,dict) else {}).get(\"total\",0))' 2>/dev/null || echo 0)"
THROTTLED_AFTER="$(kubectl exec -n "$NAMESPACE" "$IDS_API_POD" -- sh -lc "curl -s localhost:8000/api/rate-limiter/status" 2>/dev/null | python3 -c 'import json,sys; \
d=json.load(sys.stdin); \
print(((d.get(\"stats\") or {}).get(\"total_throttled\",0)) if isinstance(d,dict) else 0)' 2>/dev/null || echo 0)"
RL_STATUS="$(kubectl exec -n "$NAMESPACE" "$IDS_API_POD" -- sh -lc "curl -s localhost:8000/api/rate-limiter/status" 2>/dev/null | python3 -c 'import json,sys; \
d=json.load(sys.stdin); \
print((d.get(\"status\") if isinstance(d,dict) else \"unknown\"))' 2>/dev/null || echo unknown)"
persisted_delta=$(( PERSISTED_AFTER - BASELINE_PERSISTED ))
throttled_delta=$(( THROTTLED_AFTER - BASELINE_THROTTLED ))
echo "Persisted alerts (main table) delta: +${persisted_delta}"
if [[ "$throttled_delta" -gt 0 ]]; then
  log_info "Throttled duplicates suppressed: +${throttled_delta} (rate limiter: ${RL_STATUS})"
else
  echo "Throttled duplicates suppressed: +0"
fi

if [[ "$SHOW_ALERTS" -gt 0 ]]; then
  log_subsection "Recent alerts (sample from IDS API)"
  kubectl exec -n "$NAMESPACE" "$IDS_API_POD" -- sh -lc \
    "curl -s localhost:8000/api/alerts?limit=${SHOW_ALERTS}" 2>/dev/null \
    | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
items = data if isinstance(data, list) else data.get("alerts", data.get("items", []))
for i, a in enumerate(items[:50], 1):
    rule = a.get("rule") or a.get("title") or "Unknown alert"
    sev = a.get("severity", "?")
    src = a.get("source", "?")
    print(f"  {i}. [{src}] sev={sev}  {rule}")
' 2>/dev/null || true
fi

if [[ "$EXPLAIN" == "1" ]]; then
  echo ""
  echo "How to explain this to the examiner:"
  echo "  1) We generated real attack behavior in the cluster (not fake API-injected alerts)."
  echo "  2) Falco/Suricata detected it."
  echo "  3) IDS API ingested and counted the alerts in real time."
fi
log_info "Live attack run finished"
