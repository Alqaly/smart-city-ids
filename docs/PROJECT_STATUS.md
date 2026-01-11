# Project status snapshot

**Date:** 2026-01-11  
**Status:** Core IDS API functional; setup & testing infrastructure added; docs organized.

## Elevator pitch
Smart City IDS is an LLM-driven Intrusion Detection System for a Smart City demo. It ingests security alerts (via Falco), analyzes them using Groq/OpenAI LLMs, and executes automated Kubernetes actions (pod isolation, service scaling). Recent work focused on making setup reproducible, adding safe DB migrations, docs validation, and smoke tests.

## Architecture snapshot
- **Core service:** `services/ids-api/src/main.py` (FastAPI) — alert ingestion, LLM analysis, K8s automation.
- **LLM analyzers:** `llm_engine_groq.py`, `llm_engine_openai.py` — parse alerts, call LLM, extract JSON.
- **K8s automation:** `k8s_automation.py` — scale deployments, evict pods based on severity thresholds.
- **Alert forwarder:** `services/forwarders/falco/src/main.py` — receives Falco alerts, maps priority to severity, forwards to IDS API.
- **Demo services:** `smart-city-services/*` — intentionally vulnerable Flask apps (traffic-light, camera, etc.) mounted via K3s ConfigMaps.
- **Falco:** Runtime security monitor deployed in K3s cluster; configured in `k8s-manifests/falco-*.yaml`.
- **Database:** PostgreSQL with encrypted alert storage, audit logs, and analysis results (migrations in `infrastructure/database/migrations/`).

## Recent changes (last sprint)
- ✅ Wrapped DB migrations in transaction; made pgcrypto creation non-fatal (handles missing superuser).
- ✅ Added migration runner script: `scripts/db/run_migrations.sh`.
- ✅ Added docs validation script: `scripts/docs/check-docs.sh` (markdownlint + link checks).
- ✅ Added Makefile targets: check, db-migrate, docs-check, smoke-test, ids-api-venv, start.
- ✅ Added pytest smoke tests: `tests/smoke/test_smoke_api.py` (mocks LLM & K8s calls).
- ✅ Added GitHub Actions CI: docs.yml (docs validation) and smoke-tests.yml (API smoke tests).
- ✅ Added docs checklist and smoke-test instructions.
- ✅ Organized all docs with INDEX.md.

## Key files to show instructor / LLM
1. **docs/PROJECT_STATUS.md** (this file) — current progress snapshot.
2. **docs/INDEX.md** — entry point for all documentation.
3. **docs/QUICK_START.md** — step-by-step local setup.
4. **docs/PROJECT_CONTEXT.md** — full architecture, demo runbook, troubleshooting.
5. **docs/DOCS_CHECKLIST.md** — validation checklist for PRs and demos.
6. **docs/SMOKE_TESTS.md** — how to run smoke tests.
7. **.github/copilot-instructions.md** — AI agent guidance, LLM contract, integration points.
8. **services/ids-api/src/main.py** — core alert processing and automation logic.
9. **services/ids-api/src/llm_engine_groq.py** — LLM integration (Groq example).
10. **services/ids-api/src/k8s_automation.py** — Kubernetes automation methods.

## How to reproduce / quick commands
```bash
# Validate environment
make check

# Validate docs
make docs-check

# Apply DB migrations (to a test DB)
export DATABASE_URL="postgres://user:pass@localhost:5432/smartcity_test"
make db-migrate

# Run IDS API locally
cd services/ids-api/src
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
export GROQ_API_KEY="gsk_..." # or OPENAI_API_KEY
uvicorn main:app --host 0.0.0.0 --port 8000

# Run smoke tests
make smoke-test

# Run full demo (K3s + all services)
./scripts/start-everything.sh
kubectl get pods -n smart-city -w
```

## Pipeline overview
1. **Developer** makes change → runs `make check`, `make docs-check`, local tests.
2. **Push** → GitHub Actions runs `docs.yml` (docs validation) and `smoke-tests.yml` (API smoke tests).
3. **If CI passes** → merge and deploy to demo environment via `./scripts/start-everything.sh`.
4. **Demo** → Falco detects attacks, forwards alerts to IDS API, LLM analyzes, K8s automation executes.

## Current capabilities
- ✅ Alert ingestion via HTTP POST (`/api/alerts`).
- ✅ LLM analysis via Groq or OpenAI (JSON extraction + fallback parsing).
- ✅ Severity-based automation: isolate pod (severity >= 8), scale service (severity >= 6).
- ✅ Encrypted alert storage in PostgreSQL.
- ✅ Audit logging of all actions.
- ✅ Falco integration (alert forwarding).
- ✅ K3s deployment with ConfigMap-based service injection.
- ✅ Smoke tests (API + LLM mocking).
- ✅ Docs validation (markdown lint + link checks).

## Next steps / Recommendations
- [ ] Expand unit tests for LLM parsing (test edge cases, malformed JSON).
- [ ] Add integration test that starts a real K3s cluster and posts alerts.
- [ ] Add monitoring dashboard (Prometheus + Grafana for alerts, latencies, automation outcomes).
- [ ] Document attack scenarios and expected automation responses.
- [ ] Add migration health checks (superuser detection, CREATE EXTENSION pgcrypto retries).
- [ ] Expand automated actions (e.g., update firewall rules, send alerts to SIEM).

## Blockers / Known issues
- **pgcrypto extension:** Requires DB superuser; migration now skips it gracefully if privileges are absent. Manual setup may be needed for encryption at rest.
- **K8s automation mock:** Smoke tests mock K8s calls; validate with real K3s cluster before demo.
- **Prometheus:** Referenced in some manifests but not fully wired; skip for now unless adding metrics.

---
**Last updated:** 2026-01-11  
**Next review:** After next major feature or infrastructure change.
