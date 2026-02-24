# Scripts Reference

This folder contains deployment, demo, and validation helpers for the Smart City IDS.

## Recommended Demo Sequence

```bash
bash scripts/pre-demo-check.sh
bash scripts/run-live-attacks.sh --duration 30 --show-alerts 3
python scripts/demo-e2e-pipeline.py --api-url http://localhost:30800 --duration 5 --skip-provider-tests
```

## Core Scripts

- `scripts/pre-demo-check.sh` — Fast pre-demo health/auth/UI checks (recommended first step).
- `scripts/run-live-attacks.sh` — Runs live Suricata/Falco-triggering traffic and runtime behaviors.
- `scripts/demo-day.sh` — Combined demo flow wrapper for operator presentations.
- `scripts/demo-e2e-pipeline.py` — End-to-end pipeline validation (auth, ingest, analysis, actions view).
- `scripts/demo-readiness.sh` — Broader readiness checks (quick/full modes).
- `scripts/deploy-code.sh` — Rebuild/redeploy `ids-api` backend + static UI into K3s.
- `scripts/llm-manager.sh` — LLM diagnostics/credits/helper commands.
- `scripts/tail-pipeline-pods.sh` — Tails relevant pod logs during demos/debugging.
- `scripts/apply-llm-env-to-k8s-secret.sh` — Sync `.env` LLM keys into Kubernetes secret.

## Validation / Troubleshooting

- `scripts/e2e-verbose-test.sh` — Verbose UI/API smoke checks.
- `scripts/comprehensive-test.sh` — Broader script-based validations.
- `scripts/fix-and-redeploy.sh` — Convenience redeploy helper (use with caution; review before running).

## Deployment / Setup

- `scripts/check-setup.sh` — Local prerequisite checks.
- `scripts/start-everything.sh` — Full environment bootstrap (K3s stack deployment).
- `scripts/one-command-ready.sh` — Convenience wrapper for setup/demo prep.

## Disabled Legacy/Synthetic Scripts

These were disabled to avoid confusion during demos because they represent removed synthetic attack flows:

- `scripts/attack-iot-pipeline.sh.disabled`
- `scripts/attack-iot-pipeline-v3.sh.disabled`
- `scripts/run-all-attacks-e2e.sh.disabled`

They previously posted synthetic alerts or mixed legacy flows. Use `scripts/run-live-attacks.sh` instead.

## Notes

- Prefer live traffic/rule-trigger demos over synthetic alert injection.
- Use `http://localhost:30800/ui` for the K3s NodePort dashboard (or `http://localhost:8000/ui` only when running the API locally with Uvicorn).
