# Scripts Reference

This folder contains the active deployment, validation, and operational helpers for the Smart City IDS.

Treat `scripts/archive/`, `scripts/demos/`, and `*.disabled` files as historical or non-canonical helpers, not the primary workflow.

## Recommended Startup Sequence

```bash
bash scripts/apply-llm-env-to-k8s-secret.sh .env
sudo bash scripts/start-everything.sh
bash scripts/deploy-code.sh
bash scripts/access-stack.sh start
bash scripts/pre-demo-check.sh
bash scripts/run-live-attacks.sh --duration 30 --show-alerts 3
bash scripts/run-live-attacks.sh --mode protocol --duration 30 --show-alerts 5 --verbose
python scripts/demo-e2e-pipeline.py --api-url http://localhost:8000 --duration 5 --skip-provider-tests
```

## Canonical Scripts

Use these first:

- `scripts/start-everything.sh`
- `scripts/deploy-code.sh`
- `scripts/access-stack.sh`
- `scripts/pre-demo-check.sh`
- `scripts/demo-readiness.sh`
- `scripts/llm-manager.sh`
- `scripts/run-live-attacks.sh`
- `scripts/live-pipeline-log.sh`
- `scripts/tail-pipeline-pods.sh`
- `scripts/scale-profile.sh`

## Core Scripts

- `scripts/pre-demo-check.sh` — Fast health/auth/UI checks (recommended first step).
- `scripts/run-live-attacks.sh` — Runs live Suricata/Falco-triggering traffic and runtime behaviors, including MQTT abuse and protocol-state tamper paths.
- `scripts/demo-day.sh` — Combined demo flow wrapper for operator presentations.
- `scripts/demo-e2e-pipeline.py` — End-to-end pipeline validation (auth, ingest, analysis, actions view).
- `scripts/demo-readiness.sh` — Broader readiness checks (quick/full modes).
- `scripts/deploy-code.sh` — Rebuild/redeploy active images, apply current runtime manifests, refresh code ConfigMaps, and restart the relevant workloads.
- `scripts/llm-manager.sh` — LLM diagnostics/credits/helper commands.
- `scripts/tail-pipeline-pods.sh` — Tails raw component logs for `ids-api`, IoT services, MQTT broker, Suricata, Suricata forwarder, Falco, and Falco forwarder.
- `scripts/apply-llm-env-to-k8s-secret.sh` — Sync `.env` LLM keys/models into the Kubernetes secret used by `ids-api`.

## Validation / Troubleshooting

- `scripts/e2e-verbose-test.sh` — Verbose UI/API smoke checks.
- `scripts/test-governance-modes.sh` and `scripts/e2e-verbose-test.sh` require at least one operational LLM provider; they fail early with live diagnostics if alert analysis is unavailable.
- `scripts/comprehensive-test.sh` — Broader script-based validations.
- `scripts/fix-and-redeploy.sh` — Convenience redeploy helper (use with caution; review before running).

## Deployment / Setup

- `scripts/check-setup.sh` — Local prerequisite checks.
- `scripts/start-everything.sh` — Full environment bootstrap (K3s stack deployment), including shared emulator image build/import and emulator code ConfigMap refresh.
- `scripts/one-command-ready.sh` — Convenience wrapper for setup/demo prep.

## Disabled Legacy/Synthetic Scripts

These were disabled to avoid confusion because they represent removed synthetic attack flows:

- `scripts/attack-iot-pipeline.sh.disabled`
- `scripts/attack-iot-pipeline-v3.sh.disabled`
- `scripts/run-all-attacks-e2e.sh.disabled`

They previously posted synthetic alerts or mixed legacy flows. Use `scripts/run-live-attacks.sh` instead.

## Notes

- Prefer live traffic/rule-trigger demos over synthetic alert injection.
- Prefer `bash scripts/access-stack.sh start` and use `http://localhost:8000/ui`.
- `http://<NODE_IP>:30800/ui` remains available through NodePort, but it changes with network/IP conditions.
- Provider usage tables count alert-analysis calls only. Manual test/probe actions are diagnostic traffic and do not increment DB-backed usage totals.


## Demo Log Views

Use two terminals during demos:

```bash
# Terminal 1: processed IDS events (detector -> analysis -> actions)
bash scripts/live-pipeline-log.sh --attacks

# Terminal 2: raw component logs (IoT services, broker, Falco, Suricata, forwarders, ids-api)
SINCE=5m bash scripts/tail-pipeline-pods.sh
```

Notes:
- `live-pipeline-log.sh` shows the processed event stream from `/api/alerts/live`.
- `tail-pipeline-pods.sh` shows raw pod logs and is the correct script for proving detector and service activity.
- `--attacks` on `live-pipeline-log.sh` launches `scripts/run-live-attacks.sh`, not the removed synthetic attack script.
