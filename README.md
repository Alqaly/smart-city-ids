# Smart City IDS

Kubernetes-native intrusion detection and response platform for smart-city-style IoT workloads, combining:

- **Falco** (runtime/container detection)
- **Suricata** (network detection)
- **LLM-assisted alert analysis** (multi-provider routing/failover)
- **Governance-controlled Kubernetes response actions** (manual / assisted / autonomous)

This repository contains both:
- a working research testbed, and
- technical report and supporting materials.

## Scope (Important for External Readers)

This is a **research prototype**, not a production SOC platform. Some components are evaluation-focused (IoT emulators, controlled attack scripts, review-support docs), while core runtime components are real and testable.

To avoid stale-claim confusion:
- Use this `README.md` + [`docs/INDEX.md`](docs/INDEX.md) as the **current entry points**
- Treat `docs/archive-legacy/` and `docs/archive/` as **historical**
- Validate runtime claims against live endpoints (`/health`, `/api/metrics`) and `kubectl`

## What the System Does

- Monitors IoT and platform workloads in Kubernetes
- Ingests alerts from Falco and Suricata forwarders
- Runs LLM analysis (provider failover supported; actual availability depends on keys/credits/quota)
- Applies governance policies before automation
- Stores alerts in PostgreSQL with memory fallback and auto-recovery to DB
- Exposes a web dashboard (`/ui`) and operational APIs

## IoT Inventory Semantics

The IoT fleet view is a **hybrid inventory**, not a flat list of guaranteed live hardware.

- **Pod-backed rows** come from running Kubernetes emulator workloads.
- **Logical registry rows** come from `register` / `heartbeat` onboarding for external devices.
- A logical registry row is an **inventory record**, not proof of a currently live physical device.
- To prove a device is currently active, use:
  - recent `last_seen`
  - recent heartbeat or telemetry
  - `source`
  - IP presence

Use `GET /api/iot/devices` as the authoritative fleet view:

```bash
curl -s http://localhost:30800/api/iot/devices | jq '{total,logical_total,pod_backed_total,counting_mode}'
```

Typical interpretation:
- `counting_mode = "hybrid_registry_plus_pods"` means the dashboard is combining logical inventory with Kubernetes-backed workloads.
- Rows marked `registered` are not currently treated as live hardware.
- Rows marked `healthy`, `online`, or `running` represent current live status.

## Quick Start (Research Validation / Local Validation)

### 0. Configure LLM keys and models

The project source of truth is the local `.env` file. The running cluster uses
those values only after you sync them into the Kubernetes secret and redeploy.

```bash
grep -E '^(LLM_PRIORITY|XAI_MODEL|OPENAI_MODEL|ANTHROPIC_MODEL|GEMINI_MODEL|KIMI_MODEL)=' .env
bash scripts/apply-llm-env-to-k8s-secret.sh .env
bash scripts/deploy-code.sh
```

`deploy-code.sh` is the canonical update path. It rebuilds/imports the active images, reapplies the current `ids-api`, service, Suricata, and Falco-forwarder manifests, refreshes mounted ConfigMaps, and restarts the affected workloads.

### 1. Pre-check the environment

```bash
sudo bash scripts/start-everything.sh
bash scripts/pre-demo-check.sh
```

This now verifies:
- cluster reachability
- core pods
- dashboard/API availability
- login
- **database persistence mode** (and detects `memory-fallback`)

The canonical Kubernetes deployment path uses a shared emulator runtime image plus ConfigMap-mounted emulator application code. `scripts/start-everything.sh` now builds/imports that shared emulator image, and normal emulator code updates are then applied through the existing startup/deploy scripts rather than rebuilding a separate image per emulator edit.

Current strongest protocol-faithful emulator paths:
- ONVIF traffic camera
- MQTT/SenML parking gateway
- HL7 FHIR healthcare gateway
- Modbus + native OPC UA environmental sensor
- DALI/TALQ street lighting

### 2. Open the dashboard

```bash
# Direct NodePort path on this host
xdg-open http://localhost:30800/ui 2>/dev/null || open http://localhost:30800/ui

# If localhost:30800 is not bound in your environment, use stable port-forwarded access
bash scripts/access-stack.sh start
xdg-open http://localhost:8000/ui 2>/dev/null || open http://localhost:8000/ui
```

Default local credentials (unless overridden by environment):
- `admin / admin`

### 3. Run a live attack exercise (optional)

```bash
bash scripts/run-live-attacks.sh --duration 30 --show-alerts 3
bash scripts/run-live-attacks.sh --mode protocol --duration 30 --show-alerts 5 --verbose
```

### 4. Validate LLM providers strictly

```bash
bash scripts/llm-manager.sh check

TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}' | jq -r '.access_token')

curl -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  "http://127.0.0.1:8000/api/llm/test/gemini?strict=true" \
  -d '{"prompt":"strict provider diagnostic"}' | jq .
```

Interpretation:
- `401` = invalid or revoked API key.
- `429` = quota / billing / provider-side rate limit.
- UI usage totals count alert-analysis calls only; manual tests do not increment those totals.
- `Hist` in provider success means historical DB usage exists, but live runtime success counters were reset after restart.

## Access Points (Typical K3s NodePort Setup)

| Service | URL |
|---|---|
| Dashboard | `http://localhost:30800/ui` |
| Health | `http://localhost:30800/health` |
| Metrics API | `http://localhost:30800/api/metrics` |
| Prometheus | `http://localhost:31106` |
| Grafana | `http://localhost:30300` |

If you run `ids-api` locally with `uvicorn` outside Kubernetes, the UI/API may be on `http://localhost:8000`. In the cluster-backed deployment, prefer `http://localhost:30800` or `bash scripts/access-stack.sh start`.

For portable local access across different Wi-Fi networks, use:

```bash
bash scripts/access-stack.sh start
```

This exposes stable localhost endpoints:
- IDS UI/API (port-forward fallback): `http://localhost:8000`
- Grafana: `http://localhost:3000`
- Prometheus: `http://localhost:9090`

## Canonical Script Surface

Use these scripts as the active operational surface of the repository.

### Startup / Deploy
- `bash scripts/start-everything.sh` — bootstrap or recover the Kubernetes stack
- `bash scripts/deploy-code.sh` — canonical code/config redeploy path
- `bash scripts/access-stack.sh start` — stable localhost access (`8000`, `3000`, `9090`) when NodePort is inconvenient

### Validation
- `bash scripts/pre-demo-check.sh` — fast readiness check
- `bash scripts/demo-readiness.sh --quick` — broader readiness audit
- `bash scripts/llm-manager.sh check` — LLM and end-to-end alert-analysis health
- `bash scripts/comprehensive-test.sh` — broader platform validation
- `bash scripts/test-governance-modes.sh` — manual/assisted/autonomous governance validation
- `bash scripts/e2e-verbose-test.sh --quick` — end-to-end pipeline validation

### Operations / Demo
- `bash scripts/run-live-attacks.sh --mode protocol --duration 30 --show-alerts 5 --verbose` — live protocol and runtime exercise
- `bash scripts/live-pipeline-log.sh --attacks` — processed IDS event feed for demos
- `SINCE=5m bash scripts/tail-pipeline-pods.sh` — raw pod logs for IoT services, broker, detectors, forwarders, and `ids-api`
- `bash scripts/scale-profile.sh small|medium|large|status` — repeatable scaling profiles
- `bash scripts/scale-iot.sh` — quick manual replica changes only

### What not to use as the primary workflow
- `scripts/archive/` — historical helpers
- `scripts/demos/` — old presentation-specific helpers
- `*.disabled` attack scripts — removed synthetic/legacy paths

## Project Layout (High Level)

| Path | Purpose |
|---|---|
| `services/` | IDS API, forwarders, service components |
| `smart-city-services/` | IoT emulators (traffic camera, healthcare, parking, etc.) |
| `k8s-manifests/` | Kubernetes manifests and platform config |
| `scripts/` | Deployment, validation, attack execution, and ops automation |
| `docs/` | Technical docs, runbooks, Q&A, academic support, archives |
| `CAPSTONE_2_REPORT.*` | Final report deliverables |

## Documentation (Authoritative Map)

Do not start by reading the whole `docs/` tree.

Use this smaller path first:

1. [`docs/INDEX.md`](docs/INDEX.md)
2. [`docs/QUICKSTART.md`](docs/QUICKSTART.md)
3. [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
4. [`docs/HOW_IT_WORKS.md`](docs/HOW_IT_WORKS.md)
5. [`docs/OPERATIONS.md`](docs/OPERATIONS.md)

Then go deeper only if needed:

- API and setup:
  - [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md)
  - [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)
  - [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md)
- LLM:
  - [`docs/LLM_CONFIGURATION.md`](docs/LLM_CONFIGURATION.md)
  - [`docs/LLM_CONTROL_AND_TROUBLESHOOTING.md`](docs/LLM_CONTROL_AND_TROUBLESHOOTING.md)
  - [`docs/LLM_EVALUATION.md`](docs/LLM_EVALUATION.md)
- IoT:
  - [`docs/IOT_INTEGRATION_SDK.md`](docs/IOT_INTEGRATION_SDK.md)
  - [`docs/IOT_EMULATION_REPORT.md`](docs/IOT_EMULATION_REPORT.md)

Reference and archive material are still kept under:
- `docs/reference/`
- `docs/archive/`
- `docs/archive-legacy/`

## Public LLM Evaluation Summary

The current artifact-backed LLM study evaluates providers on one fixed task: structured analysis of stored IDS alerts.

Primary completed comparison:
- artifact: `artifacts/llm-eval/strict-real-01`
- providers scored: `Kimi`, `OpenAI`, `xAI`
- distinct matched alerts: `14`
- provider-attempts: `42`
- successful strict evaluations: `41`
- scenario families: `7`

Measured outcomes from `strict-real-01`:
- `Kimi`
  - strongest measured quality-cost tradeoff
  - quality score: `70.86%`
  - cost: `$5.00` per 1000 alerts
- `OpenAI`
  - lowest measured latency
  - average latency: `2277.4 ms`
  - p95 latency: `3054.0 ms`
- `xAI`
  - operationally usable, but much slower
  - average latency: `25488.9 ms`
  - quality score: `62.77%`

Follow-up inclusion run:
- artifact: `artifacts/llm-eval/strict-real-02`
- `Anthropic` completed strict scored evaluation successfully

Expanded five-provider attempt:
- artifact: `artifacts/llm-eval/strict-real-03`
- `Anthropic`, `Gemini`, `OpenAI`, and `xAI` completed strict scored evaluation successfully
- `Kimi` failed all requested attempts because of provider overload
- dataset size: `16` matched alerts, `80` provider-attempts, `64` successful strict evaluations, `8` scenario families

Current boundary:
- the repository contains a real strict-evaluation pipeline and completed artifact-backed results
- it does **not** yet contain a stable completed `500 x 5-provider` study

## LLM Provider Notes (Operational Reality)

The system supports multiple providers (e.g., Kimi, xAI, OpenAI, Anthropic, Gemini), but runtime health depends on:
- valid API keys
- quota / billing
- model access permissions
- provider-side outages

The dashboard may show providers as:
- configured but unusable (invalid key/quota)
- in circuit breaker cooldown after repeated failures
- operational but idle

This is expected behavior in a multi-provider resilient design.

## Database Persistence Behavior (Important)

`ids-api` uses PostgreSQL as primary storage and can fall back to in-memory storage if DB is unavailable.

Recent fix:
- the service now **auto-retries DB connection and recovers back to PostgreSQL** after transient DB startup/race failures
- `scripts/pre-demo-check.sh` reports degraded persistence explicitly

Use this check before sharing screenshots/claims:

```bash
curl -s http://localhost:30800/health | jq '{status, storage_type, components}'
curl -s http://localhost:30800/api/iot/devices | jq '{total,logical_total,pod_backed_total,counting_mode}'
```

## Common Commands

```bash
# Deploy code changes (ConfigMap-based hot reload path)
bash scripts/deploy-code.sh

# Stable local access (independent of Wi-Fi/node IP)
bash scripts/access-stack.sh start

# Readiness checks (broader)
bash scripts/demo-readiness.sh --quick

# E2E validation (quick)
bash scripts/e2e-verbose-test.sh --quick

# Scale profile (small|medium|large)
bash scripts/scale-profile.sh status
bash scripts/scale-profile.sh medium

# Full scripted validation
bash scripts/comprehensive-test.sh
```

## Sharing This Repository (Recommended)

Before sharing with experts:

1. Run `bash scripts/pre-demo-check.sh` (name retained for compatibility)
2. Confirm DB is connected (not `memory-fallback`)
3. If discussing fleet size, use `/api/iot/devices`, not only `iot_devices_active`
4. If discussing a “real active device”, show `last_seen`, `source`, heartbeat/telemetry, and IP context
5. Use [`docs/INDEX.md`](docs/INDEX.md) to direct them to current docs
6. Avoid citing archived docs as current behavior

## License

See [`LICENSE`](LICENSE).
