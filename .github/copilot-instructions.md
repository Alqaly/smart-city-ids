# GitHub Copilot / AI Agent Instructions — Smart City IDS

Short, targeted guidance to help AI coding agents be productive immediately in this repo.

## Big picture (what matters)
- This project is an LLM-driven Intrusion Detection System for a Smart City demo (intentionally vulnerable IoT services + Falco + K3s + xAI Grok-4/OpenAI).
- Core service: `services/ids-api/src/main.py` (FastAPI). It ingests security alerts, calls an LLM analyzer (`llm_engine_xai.py` / `llm_engine_openai.py`) and executes Kubernetes actions via `k8s_automation.py`.
- Demo IoT services live in `smart-city-services/*` (Flask apps mounted into K8s via `k8s-manifests/services-no-build.yaml`).
- Falco forwards alerts (see `services/forwarders/falco/src/main.py`) in JSON form. Analyzer expects `output`, `rule`, `output_fields` and `container.name`.

## Key developer workflows (explicit commands)
- Full local demo (K3s + services):
  - ./scripts/start-everything.sh
  - Follow up: `kubectl get pods -n smart-city -w`
- Run only IDS API locally:
  - export XAI_API_KEY="..." (or OPENAI_API_KEY)
  - cd services/ids-api/src && python -m venv venv && source venv/bin/activate
  - pip install -r requirements.txt
  - uvicorn main:app --host 0.0.0.0 --port 8000
- Run attacks:
  - python attack-simulator/ddos_simulator.py <url> <threads> <duration>
  - or use scripts in `attack-simulations/` for demo scenarios
- Quick fixes for common infra issues (K3s permissions / kubeconfig): see `docs/PROJECT_CONTEXT.md` (KUBECONFIG export, `sudo systemctl restart k3s`).

## Project-specific conventions & patterns
- LLM integration: `llm_engine_xai.py` expects LLM output to be valid JSON with keys: `severity` (1-10), `summary`, `threat_type`, `recommendations`, `automated_actions`.
  - Example: analyzer returns `{"status":"success","analysis":{...}}`
- Automated actions in `main.py` are threshold-driven:
  - severity >= 8 → isolate pod (uses `container.name` from `alert.output_fields`)
  - severity >= 6 → scale service up
  - See `services/ids-api/src/main.py` for exact logic and where to change thresholds
- K8s manifests use ConfigMaps that mount service code. Update app source in `smart-city-services/<service>/app.py` and then recreate ConfigMap (see `scripts/start-everything.sh`).
- Falco alerts are parsed and mapped to a 1-10 severity using `_map_priority` in `services/forwarders/falco/src/main.py`.

## Integration points & required secrets
- LLM API keys required: `XAI_API_KEY` or `OPENAI_API_KEY` (at least one) — set in env or ~/.bashrc before running (see `docs/PROJECT_CONTEXT.md`).
- KUBECONFIG: the project uses `/etc/rancher/k3s/k3s.yaml` by default; export `KUBECONFIG` if different.
- Monitoring: Falco (runtime), Prometheus & Grafana are referenced but Prometheus may be incomplete — be careful when adding metrics.

## Tests & QA
- There are placeholders for tests in `tests/` but limited coverage currently. Use `pytest` after installing dev requirements.
- When adding tests, prefer small unit tests around `llm_engine_*` parsing and `k8s_automation` methods (mock K8s API calls).

## Safe-to-change / Do-not-change guidance
- Safe: refactors that keep existing API and alert JSON shape, improved error handling, adding tests and CI.
- Avoid: removing intentional vulnerabilities in `smart-city-services/*` unless the change is explicitly part of a non-demo task (these are purposefully insecure for demonstrations).

## Helpful files to inspect
- `services/ids-api/src/main.py` — alert processing + automation logic
- `services/ids-api/src/llm_engine_xai.py` — xAI Grok-4 prompt & JSON contract
- `services/ids-api/src/k8s_automation.py` — how automated K8s actions are applied
- `services/forwarders/falco/src/main.py` — Falco alert shaping
- `k8s-manifests/services-no-build.yaml` and `scripts/start-everything.sh` — deployment pattern and configmap workflow
- `docs/PROJECT_CONTEXT.md` & `docs/README.md` — architecture notes, recovery commands and demo checklists

## Small examples (copy/paste)
- Start IDS API locally:

  export XAI_API_KEY="xai-..."
  cd services/ids-api/src
  python -m venv venv && source venv/bin/activate
  pip install -r requirements.txt
  uvicorn main:app --host 0.0.0.0 --port 8000

- Example alert JSON expected by `/api/alerts` (partial):

  {
    "output": "Falco rule triggered ...",
    "priority": "Critical",
    "rule": "Unexpected process",
    "time": "2025-01-01T...",
    "output_fields": {"container.name": "traffic-camera-...", "proc.cmdline": "/bin/bash"}
  }

---
## Troubleshooting & common fixes
- K3s not starting: restart and fix permissions: `sudo systemctl restart k3s && sleep 15 && sudo chmod 644 /etc/rancher/k3s/k3s.yaml` then `export KUBECONFIG=/etc/rancher/k3s/k3s.yaml`.
- IDS API fails to start with config error: ensure at least one LLM key is set (`XAI_API_KEY` or `OPENAI_API_KEY`) and that `Config.validate()` passes; run inside a virtualenv and `pip install -r requirements.txt`.
- Falco not emitting alerts: check Falco pods and logs: `kubectl get pods -n falco-system` and `kubectl logs -n falco-system -l app=falco --tail=50`.
- xAI/OpenAI output not parsing: `services/ids-api/src/llm_engine_xai.py` attempts to extract JSON inside ```json fences and falls back to a conservative analysis object — add unit tests for parsing if you change the prompt.
- Kubernetes automation appears no-op: ensure `KUBECONFIG` is correct and the caller has RBAC permissions to scale/evict pods; see `services/ids-api/src/k8s_automation.py`.

## Contributor checklist (quick)
- Run tests: `pytest -q` (add focused tests for new behaviors; mock K8s client calls).
- Run the IDS API locally and smoke-test with a sample alert (see LLM contract below).
- Do not commit secrets — use environment variables or CI secrets, and add `.env` to `.gitignore` if needed.
- Update `docs/PROJECT_CONTEXT.md` when making infra or workflow changes.
- If you modify automation thresholds, update `services/ids-api/src/config.py` and document the rationale in the PR.

## LLM contract & example payloads (copy/paste)
- Sample incoming alert (what incoming forwarders send):

  {
    "output": "Falco rule triggered ...",
    "priority": "Critical",
    "rule": "Unexpected process",
    "time": "2025-01-01T...",
    "output_fields": {"container.name": "traffic-camera-...", "proc.cmdline": "/bin/bash"}
  }

- Expected analyzer response (from `llm_engine_*`):

  {
    "status": "success",
    "analysis": {
      "summary": "Short 1–2 sentence explanation",
      "severity": 8,
      "threat_type": "Privilege Escalation",
      "recommendations": ["Isolate pod", "Collect logs"],
      "automated_actions": ["isolate_pod"]
    }
  }

Notes:
- `llm_engine_xai.py` builds a system prompt (see file) and prefers JSON fenced responses. If parsing fails it returns a fallback analysis object to keep processing safe.
- When adding tests for LLM parsing, assert both successful JSON extraction and the fallback behavior to avoid regressions.

---
If anything here is unclear or you want more detail (e.g., a small starter task list for onboarding contributors, or a proposed tests/CI addition), tell me which part to expand and I'll iterate. (Ping: include your preferred local dev OS and whether you use Docker Desktop vs WSL/K3s.)
