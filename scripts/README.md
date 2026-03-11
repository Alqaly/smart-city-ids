# Scripts Guide

This folder contains many scripts, but most users only need a small active set.

## Start Here: 3 Commands for Non-Technical Use

Use these three commands in order:

```bash
# 1. Start or recover the local Smart City IDS cluster
sudo bash scripts/start-everything.sh

# 2. Check that the system is ready
bash scripts/pre-demo-check.sh

# 3. Show a live demonstration feed
bash scripts/live-pipeline-log.sh --attacks
```

What they do:
- `start-everything.sh` brings up the local cluster and active services.
- `pre-demo-check.sh` confirms the API, dashboard, login, detectors, and core pods are healthy.
- `live-pipeline-log.sh --attacks` shows the processed IDS event stream while launching a short live attack run.

## If You Changed Code

After editing code, run:

```bash
bash scripts/deploy-code.sh
```

This updates the running cluster with the current code and static files.

## If You Want Raw Logs

Use this in a second terminal:

```bash
SINCE=5m bash scripts/tail-pipeline-pods.sh
```

This shows raw logs from:
- `ids-api`
- IoT services
- MQTT broker
- Suricata and Suricata forwarder
- Falco and Falco forwarder

## If You Want a Bigger Validation Check

Use these only when needed:

```bash
bash scripts/demo-readiness.sh --quick
bash scripts/llm-manager.sh check
bash scripts/comprehensive-test.sh
bash scripts/e2e-verbose-test.sh --quick
bash scripts/test-governance-modes.sh
```

## Active Scripts

These are the current scripts that belong to the active runtime path:

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
- `scripts/scale-iot.sh`
- `scripts/comprehensive-test.sh`
- `scripts/e2e-verbose-test.sh`
- `scripts/test-governance-modes.sh`
- `scripts/apply-llm-env-to-k8s-secret.sh`

## Historical / Do Not Use First

These paths are retained for history or old demos. They are not the primary workflow:

- `scripts/archive/`
- `scripts/demos/`
- `*.disabled`

If you are unsure, ignore them and stay on the active script list above.
