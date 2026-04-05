# Smart City IDS Documentation Index

Main documentation entry point for the repository.

Start with the 5 core documents below, then refer to supporting material as needed.

## Start Here: 5 Documents

1. [../README.md](../README.md) — project overview, scope, quick start
2. [QUICKSTART.md](QUICKSTART.md) — first deployment and first checks
3. [ARCHITECTURE.md](ARCHITECTURE.md) — system layout and component boundaries
4. [HOW_IT_WORKS.md](HOW_IT_WORKS.md) — end-to-end processing flow
5. [OPERATIONS.md](OPERATIONS.md) — day-to-day use, checks, and recovery

Fast operational check:

```bash
bash scripts/readiness-check.sh
```

## What Belongs Where

- `docs/` (top-level): current operational, architecture, API, and troubleshooting docs
- `docs/reference/`: academic support material for technical review and report preparation
- `docs/SCENARIOS/`: attack scenario specifications

## Documentation Trust Model

- **Current / operational**: architecture, API, deployment, operations, troubleshooting, security model, LLM configuration
- **Validation / review prep**: runbooks, Q&A, readiness reports (useful but context-specific)
- **Academic / report support**: capstone blueprints, evidence matrices, notes (in `docs/reference/`)

When in doubt, validate runtime claims against:
- `GET /health`
- `GET /api/alerts`
- `GET /api/metrics`
- Kubernetes live state (`kubectl get pods -A`)

## Canonical Technical Docs

| Document | Purpose |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | System architecture, components, data flow |
| [QUICKSTART.md](QUICKSTART.md) | Fast bootstrap and stable localhost access path |
| [HOW_IT_WORKS.md](HOW_IT_WORKS.md) | End-to-end processing path (Falco/Suricata → IDS API → LLM → governance → actions) |
| [API_REFERENCE.md](API_REFERENCE.md) | API endpoints, auth, request/response contracts |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Deployment procedures, prerequisites, environment variables |
| [OPERATIONS.md](OPERATIONS.md) | Day-2 operations, checks, service management |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Recovery procedures and common failure modes |
| [SECURITY_MODEL.md](SECURITY_MODEL.md) | Security boundaries, threat model, auth, governance |
| [LLM_CONFIGURATION.md](LLM_CONFIGURATION.md) | LLM provider configuration, routing, diagnostics, and troubleshooting |
| [LLM_EVALUATION.md](LLM_EVALUATION.md) | LLM evaluation method, commands, measured results, artifacts |
| [IOT_INTEGRATION_SDK.md](IOT_INTEGRATION_SDK.md) | External device onboarding, telemetry, logical device registry |

## Current Dashboard Semantics

- Alert History groups repeated alerts into 5-minute incident buckets by detector, rule, severity, workload context, and threat signature.
- The detector summary above Alert History shows the source mix in the currently loaded window.
- LLM Provider Breakdown is DB-backed and counts only alert-analysis calls executed by the IDS pipeline.
- Manual provider probes and sanity tests update runtime status but do not increment DB-backed usage totals.

## Supporting Docs

| Document | Purpose |
|---|---|
| [LOG_FORMAT_GUIDE.md](LOG_FORMAT_GUIDE.md) | Alert/log schemas and examples |
| [METRICS_SPEC.md](METRICS_SPEC.md) | Metric names and semantics (frozen contract) |
| [ATTACK_SIMULATION_GUIDE.md](ATTACK_SIMULATION_GUIDE.md) | Attack simulation usage and constraints |
| [ATTACK_COVERAGE_MATRIX.csv](ATTACK_COVERAGE_MATRIX.csv) | Coverage artifact (generated) |
| [ATTACK_COVERAGE_MATRIX.json](ATTACK_COVERAGE_MATRIX.json) | Coverage artifact (generated) |
| [DEVELOPMENT.md](DEVELOPMENT.md) | Project layout, local dev, code architecture |
| [REVIEW_GUIDE.md](REVIEW_GUIDE.md) | System classification and evidence lens |
| [VALIDATION_CHECKLIST.md](VALIDATION_CHECKLIST.md) | 9-step validation path |

## Academic Support (docs/reference/)

Material for technical review, report writing, and evaluation preparation.
See [reference/README.md](reference/README.md) for the full index.

## Quick Runtime Verification

```bash
bash scripts/readiness-check.sh
curl -s http://localhost:30800/health | jq
curl -s http://localhost:30800/api/metrics | jq '{total_alerts,iot_devices_active}'
curl -s http://localhost:30800/api/iot/devices | jq '{total,logical_total,pod_backed_total,counting_mode}'
```
