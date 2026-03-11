# Quick Start

Get the Smart City IDS running with the current active deployment path.

## 1. Configure LLM keys and models

The local `.env` file is the source of truth. Sync it into Kubernetes before deploy.

```bash
grep -E '^(LLM_PRIORITY|XAI_MODEL|OPENAI_MODEL|ANTHROPIC_MODEL|GEMINI_MODEL|KIMI_MODEL)=' .env
bash scripts/apply-llm-env-to-k8s-secret.sh .env
```

## 2. Bootstrap the platform

```bash
sudo bash scripts/start-everything.sh
```

This path initializes K3s if needed, builds/imports the shared emulator runtime image, refreshes emulator ConfigMaps, and applies the active manifests.

## 3. Apply current code and manifest changes

```bash
bash scripts/deploy-code.sh
```

`deploy-code.sh` is the canonical update path. It reapplies the active runtime manifests, refreshes mounted UI/code ConfigMaps, and restarts the affected workloads.

## 4. Start stable local access

```bash
bash scripts/access-stack.sh start
bash scripts/access-stack.sh status
```

Expected local URLs after `access-stack.sh start`:
- IDS UI/API: `http://localhost:8000`
- Grafana: `http://localhost:3000`
- Prometheus: `http://localhost:9090`

If direct NodePort access is already reachable in your environment, prefer `http://localhost:30800/ui` for the IDS UI/API.

## 5. Verify readiness

```bash
bash scripts/pre-demo-check.sh
bash scripts/llm-manager.sh check
```

## 6. Run live validation

```bash
bash scripts/test-governance-modes.sh
bash scripts/e2e-verbose-test.sh --quick
bash scripts/run-live-attacks.sh --mode protocol --duration 30 --show-alerts 5 --verbose
```

Governance and end-to-end action validation require at least one operational LLM provider. If all providers are unavailable, these scripts stop early and print the live diagnostics summary.

## 7. If localhost access is unavailable

Use the current node IP:

```bash
NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')
echo "http://${NODE_IP}:30800/ui"
```

## Active runtime manifests

These are the active manifests used by the supported deploy path:
- `k8s-manifests/ids-api-FINAL.yaml`
- `k8s-manifests/services-no-build.yaml`
- `k8s-manifests/suricata-fixed.yaml`
- `k8s-manifests/falco-forwarder.yaml`
- `k8s-manifests/postgres-deployment.yaml`
- `k8s-manifests/mqtt-broker.yaml`
- `k8s-manifests/prometheus-deployment.yaml`
- `k8s-manifests/grafana-deployment.yaml`
