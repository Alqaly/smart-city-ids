# Smart City IDS

Kubernetes-native intrusion detection and response platform for smart-city-style IoT workloads, combining:

- **Falco** (runtime/container detection)
- **Suricata** (network detection)
- **LLM-assisted alert analysis** (multi-provider routing/failover)
- **Governance-controlled Kubernetes response actions** (manual / assisted / autonomous)

This repository contains both:
- a working demonstrator/prototype system, and
- capstone/defense documentation and supporting materials.

## Scope (Important for External Reviewers)

This is a **research/capstone prototype**, not a production SOC platform. Some parts are intentionally demo-oriented (IoT emulators, attack scripts, examiner prep docs), while core runtime components are real and testable.

To avoid stale-claim confusion:
- Use this `README.md` + [`docs/INDEX.md`](docs/INDEX.md) as the **current entry points**
- Treat `docs/_archive/` and `docs/archive/` as **historical**
- Validate runtime claims against live endpoints (`/health`, `/api/metrics`) and `kubectl`

## What the System Does

- Monitors IoT and platform workloads in Kubernetes
- Ingests alerts from Falco and Suricata forwarders
- Runs LLM analysis (provider failover supported; actual availability depends on keys/credits/quota)
- Applies governance policies before automation
- Stores alerts in PostgreSQL with memory fallback and auto-recovery to DB
- Exposes a web dashboard (`/ui`) and operational APIs

## Quick Start (Demo / Local Validation)

### 1. Pre-check the environment

```bash
bash scripts/pre-demo-check.sh
```

This now verifies:
- cluster reachability
- core pods
- dashboard/API availability
- login
- **database persistence mode** (and detects `memory-fallback`)

### 2. Open the dashboard

```bash
xdg-open http://localhost:30800/ui 2>/dev/null || open http://localhost:30800/ui
```

Default demo credentials:
- `admin / admin`

### 3. Run a live attack demo (optional)

```bash
bash scripts/run-live-attacks.sh --duration 30 --show-alerts 3
```

## Access Points (Typical K3s NodePort Setup)

| Service | URL |
|---|---|
| Dashboard | `http://localhost:30800/ui` |
| Health | `http://localhost:30800/health` |
| Metrics API | `http://localhost:30800/api/metrics` |
| Prometheus | `http://localhost:31106` |
| Grafana | `http://localhost:30300` |

If you run `ids-api` locally with `uvicorn`, the UI/API may be on `http://localhost:8000`.

## Project Layout (High Level)

| Path | Purpose |
|---|---|
| `services/` | IDS API, forwarders, service components |
| `smart-city-services/` | IoT emulators (traffic camera, healthcare, parking, etc.) |
| `k8s-manifests/` | Kubernetes manifests and platform config |
| `scripts/` | Deployment, validation, demo, and ops automation |
| `docs/` | Technical docs, runbooks, Q&A, academic support, archives |
| `CAPSTONE_2_REPORT.*` | Final report deliverables |

## Documentation (Authoritative Map)

Start here:
- [`docs/INDEX.md`](docs/INDEX.md) — authoritative docs map + trust model

Key docs by audience:

### External expert / reviewer
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`docs/HOW_IT_WORKS.md`](docs/HOW_IT_WORKS.md)
- [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md)
- [`docs/SECURITY_MODEL.md`](docs/SECURITY_MODEL.md)
- [`docs/OPERATIONS.md`](docs/OPERATIONS.md)

### Demo / operator
- [`docs/DEMO_DAY_RUNBOOK.md`](docs/DEMO_DAY_RUNBOOK.md)
- [`docs/DEMO_QA_CHECKLIST.md`](docs/DEMO_QA_CHECKLIST.md)
- [`docs/DEMO_CHEAT_SHEET.md`](docs/DEMO_CHEAT_SHEET.md)
- [`docs/LLM_CONTROL_AND_TROUBLESHOOTING.md`](docs/LLM_CONTROL_AND_TROUBLESHOOTING.md)

### Academic / defense
- [`docs/EXAMINER_QA_30.md`](docs/EXAMINER_QA_30.md)
- [`docs/EXAMINER_IOT_QA_20.md`](docs/EXAMINER_IOT_QA_20.md)
- [`docs/ACADEMIC_CONTEXT.md`](docs/ACADEMIC_CONTEXT.md)
- [`docs/CAPSTONE_EVIDENCE_MATRIX.md`](docs/CAPSTONE_EVIDENCE_MATRIX.md)

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
```

## Common Commands

```bash
# Deploy code changes (ConfigMap-based hot reload path)
bash scripts/deploy-code.sh

# Demo readiness (broader checks)
bash scripts/demo-readiness.sh --quick

# E2E validation (quick)
bash scripts/e2e-verbose-test.sh --quick

# Full scripted validation
bash scripts/comprehensive-test.sh
```

## Sharing This Repository (Recommended)

Before sharing with experts:

1. Run `bash scripts/pre-demo-check.sh`
2. Confirm DB is connected (not `memory-fallback`)
3. Use [`docs/INDEX.md`](docs/INDEX.md) to direct them to current docs
4. Avoid citing archived docs as current behavior

## License

See [`LICENSE`](LICENSE).

