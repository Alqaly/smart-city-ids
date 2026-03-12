# Scripts

Operational and utility scripts for the Smart City IDS.

## Quick Start (3 commands)

```bash
# 1. Deploy (or recover) the cluster
sudo bash scripts/start-everything.sh

# 2. Validate the system
bash scripts/readiness-check.sh

# 3. Watch the live IDS feed while running attacks
bash scripts/live-pipeline-log.sh --attacks
```

## After Code Changes

```bash
bash scripts/deploy-code.sh
```

Hot-reloads code and static files into the running cluster.

## Script Reference

### Deployment & Lifecycle

| Script | Purpose |
|--------|---------|
| `start-everything.sh` | Full cluster bootstrap (K3s, namespaces, manifests, Falco, Suricata) |
| `deploy-code.sh` | Hot-reload code/static into running cluster via ConfigMaps |
| `cleanup.sh` | Cluster teardown (supports `--soft`, `--hard`, `--full`) |
| `access-stack.sh` | Port-forward IDS API, Grafana, Prometheus to localhost |

### Validation & Testing

| Script | Purpose |
|--------|---------|
| `readiness-check.sh` | Operational readiness (pods, services, endpoints, login, detectors) |
| `test-governance-modes.sh` | Validates manual / assisted / autonomous governance modes |
| `eval-complete.py` | Single-alert E2E evaluation (health → LLM → alert → governance → metrics) |
| `eval-day.sh` | Full evaluation orchestrator (bootstrap + attacks + validation) |

### Attack Simulation & Monitoring

| Script | Purpose |
|--------|---------|
| `run-live-attacks.sh` | In-cluster attack runner: HTTP, MQTT, protocol, and runtime vectors |
| `live-pipeline-log.sh` | Real-time SSE event observer (use `--attacks` for combined feed) |
| `tail-pipeline-pods.sh` | Raw pod log tailing (ids-api, IoT, MQTT, Suricata, Falco) |

### Scaling

| Script | Purpose |
|--------|---------|
| `scale-iot.sh` | Manual per-service scaling (`3`, `up`, `down`, or per-service) |
| `scale-profile.sh` | Named preset profiles (`small`, `medium`, `large`) |

### LLM Management

| Script | Purpose |
|--------|---------|
| `llm-manager.sh` | Provider health, credits, priority, interactive control |
| `apply-llm-env-to-k8s-secret.sh` | Sync `.env` API keys into K8s secrets and restart |

### Research & Reporting

| Script | Purpose |
|--------|---------|
| `scalability-test.sh` | Automated scale testing with metrics collection |
| `llm-compare-report.py` | Multi-provider LLM evaluation report |
| `render-figures.py` | Documentation figure renderer |

### Internal

| Script | Purpose |
|--------|---------|
| `lib/script-utils.sh` | Shared shell library (colors, logging, kubeconfig, port-forward) |
| `lib/llm-control.sh` | LLM credit/priority helpers |
| `db/run_migrations.sh` | PostgreSQL schema migrations |
