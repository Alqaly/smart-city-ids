# Architecture

Current architecture reference for the Smart City IDS research testbed.

## System summary

The system runs on a local K3s cluster and combines:
- IoT emulator workloads
- Falco runtime detection
- Suricata network detection
- a FastAPI-based IDS backend
- PostgreSQL persistence
- LLM-assisted alert analysis
- governance-controlled Kubernetes actions
- a web dashboard and metrics stack

## Main namespaces

| Namespace | Purpose |
|---|---|
| `smart-city` | IDS API, PostgreSQL, MQTT broker, IoT emulator workloads |
| `monitoring` | Prometheus, Grafana, Suricata, Suricata forwarder |
| `falco-system` | Falco and Falco forwarder |

## Main workloads

| Workload | Role |
|---|---|
| `ids-api` | alert intake, analysis, governance, dashboard API |
| `postgres` | persistent storage for alerts, analysis, audit, and actions |
| `mqtt-broker` | MQTT traffic path for IoT workflows |
| `traffic-camera` | ONVIF-like / camera emulator workload |
| `healthcare-api` | FHIR-style healthcare emulator workload |
| `parking-system` | MQTT/SenML-style parking emulator workload |
| `env-sensor` | Modbus-style + OPC UA environmental sensor workload |
| `street-lighting` | DALI/TALQ-style lighting workload |
| `falco` | runtime/syscall detection |
| `falco-forwarder` | Falco alert forwarding into ids-api |
| `suricata` | network/protocol detection |
| `suricata-forwarder` | Suricata alert forwarding into ids-api |
| `prometheus` | metrics collection |
| `grafana` | dashboards |

## End-to-end flow

```text
IoT / platform activity
  -> Falco or Suricata detection
  -> forwarder normalization
  -> ids-api alert intake
  -> rate limiting and deduplication
  -> LLM analysis or cached/rule-based reuse
  -> governance decision
  -> optional Kubernetes action
  -> PostgreSQL persistence
  -> dashboard / API / metrics
```

## LLM layer

The IDS backend supports multiple providers with:
- runtime priority order
- strict single-provider testing
- cooldown handling
- circuit-breaker state
- DB-backed usage metrics for alert-analysis traffic

Current live provider state must be checked from:

```bash
curl -s http://localhost:30800/api/llm/diagnostics | jq .
```

Do not assume every configured provider is operational at the same time.

## IoT model

The project uses a hybrid IoT model:
- pod-backed emulator workloads
- externally registered logical devices

The authoritative fleet endpoint is:

```bash
curl -s http://localhost:30800/api/iot/devices | jq '{total,logical_total,pod_backed_total,counting_mode}'
```

Important:
- logical registry rows are inventory records
- they are not proof of active hardware unless recent heartbeat/telemetry exists

## Deployment model

The current supported deployment path is:

```bash
bash scripts/apply-llm-env-to-k8s-secret.sh .env
sudo bash scripts/start-everything.sh
bash scripts/deploy-code.sh
```

The active manifest set is:
- `k8s-manifests/postgres-deployment.yaml`
- `k8s-manifests/mqtt-broker.yaml`
- `k8s-manifests/ids-api-FINAL.yaml`
- `k8s-manifests/services-no-build.yaml`
- `k8s-manifests/suricata-fixed.yaml`
- `k8s-manifests/falco-forwarder.yaml`
- `k8s-manifests/prometheus-deployment.yaml`
- `k8s-manifests/grafana-deployment.yaml`

## Important boundaries

- This is a research testbed, not a production SOC platform.
- The current stack uses a single PostgreSQL deployment, not PostgreSQL HA.
- Attack generation is currently CLI-driven through `scripts/run-live-attacks.sh`, not a live `/api/attacks/registry` workflow.
- The IoT layer is best described as protocol-faithful software emulation, not a full physical-device fleet.
