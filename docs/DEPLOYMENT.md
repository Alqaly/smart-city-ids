# Deployment Guide

This document describes the current supported local deployment path for the Smart City IDS.

## Prerequisites

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 2 cores | 4 cores |
| RAM | 4 GB | 8 GB |
| Disk | 20 GB | 50 GB |
| Network | Internet access | Internet + static IP |

**Software**: Linux (tested on Kali/Ubuntu), K3s, curl, jq, git, sudo access.

**LLM keys**: At least one of `XAI_API_KEY` or `OPENAI_API_KEY` in `.env`.
See [LLM_CONFIGURATION.md](LLM_CONFIGURATION.md) for full provider list.

## Recommended path

Use these commands in order:

```bash
bash scripts/apply-llm-env-to-k8s-secret.sh .env
sudo bash scripts/start-everything.sh
bash scripts/deploy-code.sh
bash scripts/readiness-check.sh
```

This is the supported deployment path for the current repository.

## What gets deployed

### Namespaces
- `smart-city`
- `monitoring`
- `falco-system`

### Main workloads

| Namespace | Workload | Purpose |
|---|---|---|
| `smart-city` | `ids-api` | alert processing, API, dashboard, LLM analysis, governance |
| `smart-city` | `postgres` | persistent alert and audit storage |
| `smart-city` | `mqtt-broker` | MQTT workload used by IoT flows |
| `smart-city` | `traffic-camera` | IoT emulator workload |
| `smart-city` | `healthcare-api` | IoT emulator workload |
| `smart-city` | `parking-system` | IoT emulator workload |
| `smart-city` | `env-sensor` | IoT emulator workload |
| `smart-city` | `street-lighting` | IoT emulator workload |
| `monitoring` | `prometheus` | metrics collection |
| `monitoring` | `grafana` | dashboards |
| `monitoring` | `suricata` | network detection |
| `monitoring` | `suricata-forwarder` | forwards Suricata alerts into ids-api |
| `falco-system` | `falco` | runtime detection |
| `falco-system` | `falco-forwarder` | forwards Falco alerts into ids-api |

## What the startup script actually does

`scripts/start-everything.sh` is the full bring-up or recovery path.

Current phases:
1. check K3s status
2. start or reuse the local cluster
3. read LLM configuration from `.env`
4. build and import the shared emulator runtime image
5. apply the active Kubernetes manifests
6. wait for the main services to become ready

This is the current truth. It is not the older “wipe and rebuild everything unconditionally” flow.

## What the deploy script actually does

`scripts/deploy-code.sh` is the update path for a running cluster.

It:
- builds the shared emulator runtime image
- builds the `ids-api` image
- imports both into K3s
- refreshes mounted static ConfigMaps
- refreshes emulator code ConfigMaps
- reapplies the active manifests
- restarts the affected workloads
- waits for the IDS API health check

Use it after code changes.

## Active manifests

The current supported path uses:

```text
k8s-manifests/postgres-deployment.yaml
k8s-manifests/mqtt-broker.yaml
k8s-manifests/ids-api.yaml
k8s-manifests/smart-city-services.yaml
k8s-manifests/suricata.yaml
k8s-manifests/falco-forwarder.yaml
k8s-manifests/prometheus-deployment.yaml
k8s-manifests/grafana-deployment.yaml
```

## Access after deployment

Direct local NodePort path:
- IDS UI/API: `http://localhost:30800/ui`
- Prometheus: `http://localhost:31106`
- Grafana: `http://localhost:30300`

Stable forwarded access:

```bash
bash scripts/access-stack.sh start
bash scripts/access-stack.sh status
```

Forwarded endpoints:
- IDS UI/API: `http://localhost:8000`
- Grafana: `http://localhost:3000`
- Prometheus: `http://localhost:9090`

## Validation after deployment

Run:

```bash
bash scripts/readiness-check.sh
bash scripts/readiness-check.sh --quick
```

If you changed governance or LLM configuration:

```bash
bash scripts/llm-manager.sh check
bash scripts/test-governance-modes.sh
bash scripts/readiness-check.sh
```

## Manual deployment

Manual `kubectl apply` is possible, but it is no longer the recommended daily path.

If you use manual deployment, apply the active manifests listed above and then run:

```bash
bash scripts/readiness-check.sh
```

## Important boundaries

- This repo currently uses a single PostgreSQL deployment, not PostgreSQL HA.
- The current live attack path is CLI-driven through `scripts/run-live-attacks.sh`.
- Historical manifests and old attack registry flows should not be treated as the active deployment path.

## Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `XAI_API_KEY` | Yes* | - | xAI Grok API key |
| `OPENAI_API_KEY` | Yes* | - | OpenAI API key |
| `ANTHROPIC_API_KEY` | Yes* | - | Anthropic Claude API key |
| `GEMINI_API_KEY` | Yes* | - | Google Gemini API key |
| `KIMI_API_KEY` | Yes* | - | Moonshot Kimi API key |
| `KUBECONFIG` | No | /etc/rancher/k3s/k3s.yaml | Kubernetes config |
| `K8S_NAMESPACE` | No | smart-city | Target namespace |
| `POSTGRES_USER` | No | idsuser | Database user |
| `POSTGRES_PASSWORD` | No | idspassword | Database password |
| `IDS_USER_ADMIN` | No | admin | Dashboard admin username |
| `IDS_PASS_ADMIN` | No | admin | Dashboard admin password |
| `SECRET_KEY` | No | auto-generated | JWT signing key |

*At least one LLM API key is required.
