# GitHub Copilot Instructions — Smart City IDS

Use this file as the default operating guide for AI coding agents in this repo.

## Core architecture
- Main backend: `services/ids-api/src/main.py` (FastAPI, modular routers under `api/`).
- Alert pipeline entry points: `POST /api/alerts` and `POST /api/alerts/internal` in `api/alerts.py`.
- Runtime automation: `services/ids-api/src/k8s_automation.py` (isolate pods, scale services, ThreatResponse CRD creation).
- LLM stack: multi-provider manager (`services/ids-api/src/llm_providers/*`) with fallback and local safe-mode behavior.
- Operator/CRD path: `services/ids-operator/` watches `ThreatResponse` resources.

## Behavior contracts to preserve
- Incoming alerts must keep Falco/Suricata shape (`output`, `rule`, `priority`, `output_fields`).
- Analysis contract must keep `{"status":"success","analysis":{...}}` with keys `severity`, `summary`, `threat_type`, `recommendations`, `automated_actions`.
- Severity-driven actions remain threshold-based (critical isolation and medium/high scaling paths).
- Safe mode must remain deterministic and operational without external LLM keys.
- Chat endpoint (`/api/analyst/chat`) must preserve explicit `HTTPException` behavior (e.g., 429 rate limits).

## Local workflows
- Full demo: `./scripts/start-everything.sh` then `kubectl get pods -n smart-city -w`.
- IDS API only:
  - `cd services/ids-api/src`
  - `python -m venv venv && source venv/bin/activate`
  - `pip install -r requirements.txt`
  - `uvicorn main:app --host 0.0.0.0 --port 8000`
- Hot code deploy (ConfigMap-based): `./scripts/deploy-code.sh`.
- Attack simulation: `./scripts/attack-iot-pipeline.sh --quick`.

## Validation expectations for code changes
- Prefer focused checks first (`pytest -q`, or targeted tests under `tests/`).
- For API changes, smoke-test at least:
  - `GET /health`
  - alert ingestion (`/api/alerts`)
  - analyst chat (`/api/analyst/chat`)
- For automation changes, verify Kubernetes side effects (`kubectl get threatresponses -n smart-city`, affected pods/deployments).

## Safety and scope boundaries
- Keep intentional vulnerabilities in `smart-city-services/*` unless explicitly asked to harden them.
- Do not change public API shapes, auth semantics, or dashboard contracts without updating docs and tests.
- Never commit secrets; use environment variables (`XAI_API_KEY`, `OPENAI_API_KEY`, etc.).
- Prefer minimal, surgical edits over broad refactors.

## High-value files to inspect first
- `services/ids-api/src/api/alerts.py`
- `services/ids-api/src/api/analyst.py`
- `services/ids-api/src/api/_state.py`
- `services/ids-api/src/config.py`
- `services/ids-api/src/k8s_automation.py`
- `services/forwarders/falco/src/main.py`
- `docs/API_REFERENCE.md` and `docs/ARCHITECTURE.md`
