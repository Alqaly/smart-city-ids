# Conference-Ready Runbook (Smart City IDS)

> [!IMPORTANT]
> Snapshot document for demo preparation. May contain time-bound results or legacy route names.
> Do not use it as the current API/runtime contract. Verify current behavior using `docs/INDEX.md`, `docs/API_REFERENCE.md`,
> and live checks (`/health`, `/api/alerts`, `/api/metrics`).


This runbook is for **end-to-end** validation and demo readiness:

- **Real detections**: Falco (runtime) + Suricata (network)
- **Real pipeline**: forwarders → IDS API → DB/metrics → Grafana
- **Bring Your Own IoT Device**: external device can send telemetry via REST

> Note: IoT *emulation* pods are optional. If they are absent, use the logical device registry path and be explicit that registry rows are inventory records, not proof of current live hardware.

---

## 0) Prerequisites (local machine)

- Linux host with K3s working
- `kubectl`, `curl`, `jq`
- Optional (for LLM analysis): set at least one API key in `.env`
  - `XAI_API_KEY=...` or `OPENAI_API_KEY=...` or `GEMINI_API_KEY=...` or `KIMI_API_KEY=...`

---

## 1) One-command deploy (recommended)

From repo root:

```bash
bash scripts/one-command-ready.sh
```

Defaults:
- Does **not** deploy IoT emulation pods.
- Does **not** send synthetic seed events.

If you *want* the IoT emulators:

```bash
bash scripts/one-command-ready.sh --with-iot-emulation
```

---

## 2) Validate everything is connected

Quick readiness check:

```bash
bash scripts/readiness-check.sh --quick
```

This checks:
- K8s connectivity + namespaces
- Workloads (IDS API, Suricata + forwarder, Falco + forwarder, Prometheus, Grafana)
- Prometheus scrapes (`up{job=...}=1`) for IDS + forwarders
- IDS API health + operator login

---

## 3) Run a live attack demo (real traffic)

Runs **in-cluster** traffic/runtimes (no synthetic alert injection):

```bash
bash scripts/run-live-attacks.sh --duration 30 --mode all
```

You can also run a narrower mode:

```bash
bash scripts/run-live-attacks.sh --duration 30 --mode sqli
```

---

## 4) Bring Your Own IoT Device (external)

### Option A (recommended): REST telemetry

Find the IDS API NodePort URL:

```bash
NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}' | tr ' ' '\n' | head -1)
IDS_PORT=$(kubectl -n smart-city get svc ids-api-service -o jsonpath='{.spec.ports[0].nodePort}')
echo "http://${NODE_IP}:${IDS_PORT}"
```

Send a heartbeat from *any* device:

```bash
curl -s -X POST "http://${NODE_IP}:${IDS_PORT}/api/iot/sensor" \
  -H 'Content-Type: application/json' \
  -d '{
    "device_id":"my-device-01",
    "device_type":"raspberry_pi",
    "event_type":"heartbeat",
    "value":{"status":"alive"}
  }'
```

### Option B: MQTT (optional)

MQTT exists in the demo stack, but MQTT messages are **not automatically ingested** into the IDS pipeline unless you add a bridge.
For a conference demo where anyone can connect quickly, use REST (`/api/iot/sensor`).

---

## 5) Useful URLs

These are typically printed by the scripts:

- IDS API: `http://<NODE_IP>:30800`
- IDS UI: `http://<NODE_IP>:30800/ui`
- Grafana: `http://<NODE_IP>:30300` (user/pass: `admin`/`admin`)
- Prometheus: `http://<NODE_IP>:31106`

---

## 6) If something fails

- Check readiness output first: `bash scripts/readiness-check.sh`
- Tail pipeline logs:

```bash
bash scripts/tail-pipeline-pods.sh
```
