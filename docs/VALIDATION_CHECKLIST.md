# Validation Checklist

This checklist covers the current supported validation path for the live Smart City IDS stack.

## 1. Bootstrap and access

```bash
bash scripts/apply-llm-env-to-k8s-secret.sh .env
sudo bash scripts/start-everything.sh
bash scripts/deploy-code.sh
bash scripts/access-stack.sh start
```

Expected local endpoints:
- direct NodePort: `http://localhost:30800`
- optional stable port-forward: `http://localhost:8000`
- Grafana: `http://localhost:3000`
- Prometheus: `http://localhost:9090`

## 2. Baseline health

```bash
bash scripts/readiness-check.sh --quick
bash scripts/readiness-check.sh
bash scripts/readiness-check.sh --quick
```

Pass criteria:
- IDS API healthy
- PostgreSQL connected
- Prometheus and Grafana reachable
- Falco and Suricata visible

## 3. Governance validation

```bash
bash scripts/test-governance-modes.sh
```

Prerequisite:
- at least one LLM provider must be operational; otherwise alert analysis cannot produce governance decisions

Pass criteria:
- manual mode creates pending approvals
- assisted mode auto-executes high-confidence actions
- autonomous benign case does not trigger destructive action
- original governance mode is restored
- no residual pending queue remains

## 4. End-to-end pipeline validation

```bash
bash scripts/readiness-check.sh
python scripts/eval-complete.py --api-url http://localhost:8000
```

If `GET /api/llm/diagnostics` reports `summary.operational = 0`, fix provider credentials or quota first and then rerun the governance/E2E checks.

Pass criteria:
- auth works
- health/metrics endpoints respond
- governance check passes
- dashboard/help endpoints are reachable
- IoT device count is readable

## 5. Protocol attack validation

### MQTT / Modbus / ONVIF path

```bash
bash scripts/run-live-attacks.sh --mode protocol --duration 30 --show-alerts 8 --verbose
```

Expected recent alert coverage includes some or all of:
- `SMARTCITY MQTT parking control topic abuse`
- `SMARTCITY MQTT parking fault-state tamper`
- `SMARTCITY MQTT parking occupancy spoof`
- `SMARTCITY Modbus write tamper`
- `SMARTCITY ONVIF capability enumeration`
- `SMARTCITY ONVIF profile enumeration`
- `SMARTCITY ONVIF PTZ control abuse`
- `SMARTCITY ONVIF snapshot scraping`
- `SMARTCITY ANPR data scraping`

### MQTT-specific path

```bash
bash scripts/run-live-attacks.sh --mode mqtt --duration 30 --show-alerts 5 --verbose
```

### Mixed network/runtime path

```bash
bash scripts/run-live-attacks.sh --mode all --duration 30 --show-alerts 5 --verbose
```

## 6. LLM provider validation

Login first:

```bash
TOKEN=$(curl -s -X POST http://localhost:30800/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin"}' | jq -r '.access_token')
```

Run strict diagnostics:

```bash
curl -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  'http://localhost:30800/api/llm/test/gemini?strict=true' \
  -d '{"prompt":"provider diagnostic"}' | jq .
```

Check health summary:

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  http://localhost:30800/api/llm/diagnostics | jq .
```

## 7. IoT emulation validation

```bash
curl -s http://localhost:30800/api/iot/telemetry | jq .
curl -s http://localhost:30800/api/iot/devices | jq .
```

Check for:
- parking MQTT runtime counters
- env-sensor OPC UA running state
- emulator stats present for active services
- `counting_mode` and fleet totals from `/api/iot/devices`

Interpretation:
- `iot_devices_active` in `/api/metrics` is an activity metric, not a guaranteed 1:1 pod count.
- `/api/iot/devices` is the authoritative inventory view for hybrid logical-device plus pod-backed counting.
- In the current active path, `counting_mode` may be `hybrid_registry_plus_pods`; this is expected.

## 8. Failure interpretation

Common non-code failures:
- provider auth failure -> invalid API key
- provider quota/rate failure -> billing/quota issue
- reduced IoT count -> active profile/registration drift, not necessarily pipeline failure
- protocol attacks visible in recent alerts but delta counters low -> detector/metric timing issue, not necessarily ingest failure

## 9. Minimum evidence bundle

For technical review, capture:
- output of `bash scripts/readiness-check.sh`
- output of `bash scripts/test-governance-modes.sh`
- output of `bash scripts/readiness-check.sh`
- one `run-live-attacks.sh` protocol run
- screenshots or JSON from:
  - `/api/alerts`
  - `/api/governance/status`
  - `/api/llm/diagnostics`
  - `/api/iot/telemetry`
