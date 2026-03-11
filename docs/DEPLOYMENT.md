# Deployment Guide

This document describes the current supported local deployment path for the Smart City IDS.

## Recommended path

Use these commands in order:

```bash
bash scripts/apply-llm-env-to-k8s-secret.sh .env
sudo bash scripts/start-everything.sh
bash scripts/deploy-code.sh
bash scripts/pre-demo-check.sh
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
k8s-manifests/ids-api-FINAL.yaml
k8s-manifests/services-no-build.yaml
k8s-manifests/suricata-fixed.yaml
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
bash scripts/pre-demo-check.sh
bash scripts/demo-readiness.sh --quick
```

If you changed governance or LLM configuration:

```bash
bash scripts/llm-manager.sh check
bash scripts/test-governance-modes.sh
bash scripts/e2e-verbose-test.sh --quick
```

## Manual deployment

Manual `kubectl apply` is possible, but it is no longer the recommended daily path.

If you use manual deployment, apply the active manifests listed above and then run:

```bash
bash scripts/pre-demo-check.sh
```

## Important boundaries

- This repo currently uses a single PostgreSQL deployment, not PostgreSQL HA.
- The current live attack path is CLI-driven through `scripts/run-live-attacks.sh`.
- Historical manifests and old attack registry flows should not be treated as the active deployment path.
