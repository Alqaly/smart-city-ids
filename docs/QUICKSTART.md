# Quick Start

Use this path if you want the fastest reliable way to get the current Smart City IDS running.

## 1. Sync LLM keys and model settings

The local `.env` file is the source of truth for provider keys and model names.

```bash
bash scripts/apply-llm-env-to-k8s-secret.sh .env
```

## 2. Start or recover the local cluster

```bash
sudo bash scripts/start-everything.sh
```

This script:
- reuses or starts the local K3s cluster
- builds and imports the shared emulator runtime image
- applies the active manifests
- waits for the main services to be ready

## 3. Apply the latest code

```bash
bash scripts/deploy-code.sh
```

Use this after code changes. It is the normal update path for a running local cluster.

## 4. Verify readiness

```bash
bash scripts/readiness-check.sh
bash scripts/readiness-check.sh --quick
```

Expected result:
- `READINESS STATUS: READY`
- `SYSTEM: READY`

## 5. Open the dashboard

Preferred direct local URL:

```text
http://localhost:30800/ui
```

If you want stable localhost access that does not depend on node IP changes:

```bash
bash scripts/access-stack.sh start
bash scripts/access-stack.sh status
```

Stable forwarded endpoints:
- IDS UI/API: `http://localhost:8000`
- Grafana: `http://localhost:3000`
- Prometheus: `http://localhost:9090`

## 6. Run a live exercise

Terminal 1:

```bash
bash scripts/live-pipeline-log.sh --attacks
```

Terminal 2:

```bash
SINCE=5m bash scripts/tail-pipeline-pods.sh
```

## 7. Optional deeper checks

```bash
bash scripts/llm-manager.sh check
bash scripts/test-governance-modes.sh
bash scripts/readiness-check.sh
```

These deeper checks require at least one operational LLM provider.

## Active runtime manifests

The supported deploy path applies these active manifests:
- `k8s-manifests/postgres-deployment.yaml`
- `k8s-manifests/mqtt-broker.yaml`
- `k8s-manifests/ids-api.yaml`
- `k8s-manifests/smart-city-services.yaml`
- `k8s-manifests/suricata.yaml`
- `k8s-manifests/falco-forwarder.yaml`
- `k8s-manifests/prometheus-deployment.yaml`
- `k8s-manifests/grafana-deployment.yaml`
