# Smart City IDS

<p align="center">
  <strong>LLM-Driven Intrusion Detection System for Edge-Enabled Smart Cities</strong>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT"></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/Kubernetes-326CE5?logo=kubernetes&logoColor=white" alt="Kubernetes">
  <img src="https://img.shields.io/badge/Prometheus-E6522C?logo=prometheus&logoColor=white" alt="Prometheus">
  <img src="https://img.shields.io/badge/Grafana-F46800?logo=grafana&logoColor=white" alt="Grafana">
  <img src="https://img.shields.io/badge/PostgreSQL-4169E1?logo=postgresql&logoColor=white" alt="PostgreSQL">
  <img src="https://img.shields.io/badge/Falco-00AEC7?logo=falco&logoColor=white" alt="Falco">
</p>

> **UDST Capstone Project** — Ali Suhail (60106420), Khaled Rahman (60104156), Abdullah Mahmoud (60300336)
> Supervisor: Dr. Dana Haj Hussein

A Kubernetes-native intrusion detection system for smart-city IoT infrastructure. It combines **Falco** (runtime) and **Suricata** (network) detection with **LLM-powered alert analysis** across five providers, governed by configurable response automation that can isolate pods, scale services, and create ThreatResponse CRDs — all observable through **Prometheus**, **Grafana**, and a built-in operator dashboard.

The IoT workloads are protocol-faithful software emulators (MQTT, Modbus, ONVIF, DALI/TALQ, FHIR) running inside the Kubernetes cluster.

---

## Architecture

```
 ┌─────────────────┐     ┌────────────────┐     ┌────────────────────────┐     ┌─────────────────┐
 │  IoT Workloads  │     │   Detection    │     │      IDS Backend       │     │    Response      │
 ├─────────────────┤     ├────────────────┤     ├────────────────────────┤     ├─────────────────┤
 │ traffic-camera  │────▶│                │────▶│  Alert Intake          │     │ Isolate Pod     │
 │ healthcare-api  │     │  Falco (eBPF)  │     │       │                │     │ Scale Service   │
 │ parking-system  │     │   syscall +    │     │  Rate Limit / Dedup    │────▶│ Block IP        │
 │ env-sensor      │     │   runtime      │     │       │                │     │ ThreatResponse  │
 │ street-lighting │     ├────────────────┤     │  LLM Analysis (5)      │     │   CRD           │
 │ mqtt-broker     │────▶│  Suricata      │────▶│       │                │     └─────────────────┘
 └─────────────────┘     │   network +    │     │  Governance Gate       │
                         │   protocol     │     │       │                │
                         └────────────────┘     │  PostgreSQL (12 tbl)   │
                                                └───────────┬────────────┘
                                                            │
                                                ┌───────────┴────────────┐
                                                │   Observability        │
                                                │  Prometheus ─▶ Grafana │
                                                │  Operator Dashboard    │
                                                │  Audit Logs            │
                                                └────────────────────────┘
```

## Features

| Category | Details |
|----------|---------|
| **Detection** | Falco (runtime/syscall via eBPF) + Suricata (network/protocol IDS) |
| **LLM Analysis** | 5 providers (xAI Grok, OpenAI GPT-4o, Anthropic Claude, Google Gemini, Kimi) with failover, circuit breakers, and cost tracking |
| **Governance** | Manual, assisted, and autonomous modes with approval workflows and safety gates |
| **Automation** | Pod isolation, service scaling, network policies, ThreatResponse CRDs via K8s operator |
| **IoT Emulation** | MQTT, Modbus, ONVIF, DALI/TALQ, FHIR — protocol-faithful services with state models |
| **Dashboard** | Real-time alert feed, LLM status, governance queue, AI analyst chat, IoT fleet view |
| **Monitoring** | Prometheus (40+ metrics, alerting rules) → Grafana (IEEE + ops dashboards) |
| **Persistence** | PostgreSQL (12 tables): alerts, analysis, actions, audit, chat, IoT, LLM health |
| **Evaluation** | Comparative multi-provider LLM scoring pipeline with artifact-backed results |

---

## Quick Start

> **Prerequisites:** Linux (tested on Kali/Ubuntu), 4 GB+ RAM, `sudo`, `curl`, `jq`, `git`.

```bash
# 1. Configure at least one LLM provider key
echo 'ANTHROPIC_API_KEY=sk-ant-...' > .env            # or XAI, OPENAI, GEMINI, KIMI
bash scripts/apply-llm-env-to-k8s-secret.sh .env

# 2. Deploy the full stack (K3s, namespaces, Falco, Suricata, Prometheus, Grafana, IoT services)
sudo bash scripts/start-everything.sh
bash scripts/deploy-code.sh

# 3. Validate everything is up
bash scripts/readiness-check.sh

# 4. Open the operator dashboard
#    http://localhost:30800/ui  (login: admin / admin)

# 5. Run a live attack exercise
bash scripts/run-live-attacks.sh --mode protocol --duration 30 --verbose
```

For stable `localhost` access (survives Wi-Fi IP changes):

```bash
bash scripts/access-stack.sh start
# IDS API    →  http://localhost:8000
# Grafana    →  http://localhost:3000  (admin / admin)
# Prometheus →  http://localhost:9090
```

See [docs/LLM_CONFIGURATION.md](docs/LLM_CONFIGURATION.md) for all five supported providers.

---

## Monitoring Stack

Prometheus and Grafana are deployed automatically by `start-everything.sh` and wired together out of the box.

| Component | Access | Purpose |
|-----------|--------|---------|
| **Prometheus** | `localhost:9090` (port-forward) or NodePort 31106 | Scrapes IDS API, Suricata forwarder, Falco forwarder, and IoT pods every 5 s. 30 alerting rules across 8 groups. |
| **Grafana** | `localhost:3000` (port-forward) or NodePort 30300 | Two auto-provisioned dashboards: **IEEE Capstone** (6-row academic format) and **Unified Operations** (10-row full ops view). |
| **IDS `/metrics`** | `localhost:30800/metrics` | Prometheus text exposition — 40+ metric families covering alerts, LLM calls, governance, IoT, cost, circuit breakers. |

**How they connect:**

```
IDS API (/metrics)  ──┐
Suricata forwarder  ──┤──▶  Prometheus (scrape config)  ──▶  Grafana (datasource: Prometheus)
Falco forwarder     ──┤           │
IoT pods (DNS SD)   ──┘     Alert rules (8 groups, 30 rules)
```

Dashboards are auto-provisioned from `k8s-manifests/grafana-provisioning-dashboards.yaml` which embeds the JSON from `infrastructure/monitoring/`. The ConfigMap is applied during `start-everything.sh` alongside Prometheus and Grafana.

---

## Project Structure

| Path | Purpose |
|------|---------|
| `services/ids-api/` | Core IDS backend (FastAPI), dashboard UI, LLM engines, K8s automation |
| `services/forwarders/` | Falco and Suricata alert forwarders |
| `services/ids-operator/` | Kubernetes operator watching `ThreatResponse` CRDs |
| `smart-city-services/` | IoT emulators: traffic camera, healthcare API, parking, env sensor, street lighting |
| `iot-simulator/` | MQTT-based IoT device simulator |
| `k8s-manifests/` | All Kubernetes manifests (services, monitoring, RBAC, network policies) |
| `infrastructure/monitoring/` | Grafana dashboard JSON (source files for provisioning ConfigMap) |
| `infrastructure/database/` | PostgreSQL schema migrations |
| `scripts/` | Deployment, validation, attack simulation, scaling, and LLM management ([index](scripts/README.md)) |
| `tests/` | Smoke tests, stability tests, unit tests |
| `docs/` | Technical documentation ([index](docs/INDEX.md)) |
| `docker/` | Dockerfiles for IDS API, forwarders, and smart-city services |
| `artifacts/llm-eval/` | LLM evaluation run data (CSV, JSON) |

## Documentation

Start here, in order:

| # | Document | Description |
|---|----------|-------------|
| 1 | [QUICKSTART](docs/QUICKSTART.md) | First deployment and first checks |
| 2 | [ARCHITECTURE](docs/ARCHITECTURE.md) | System layout and component boundaries |
| 3 | [HOW_IT_WORKS](docs/HOW_IT_WORKS.md) | End-to-end alert processing flow |
| 4 | [OPERATIONS](docs/OPERATIONS.md) | Day-to-day operations and recovery |

Then go deeper:

| Topic | Document |
|-------|----------|
| API endpoints | [docs/API_REFERENCE.md](docs/API_REFERENCE.md) |
| Deployment procedures | [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) |
| LLM provider setup | [docs/LLM_CONFIGURATION.md](docs/LLM_CONFIGURATION.md) |
| LLM evaluation method | [docs/LLM_EVALUATION.md](docs/LLM_EVALUATION.md) |
| Attack scenarios | [docs/ATTACK_SIMULATION_GUIDE.md](docs/ATTACK_SIMULATION_GUIDE.md) |
| IoT device integration | [docs/IOT_INTEGRATION_SDK.md](docs/IOT_INTEGRATION_SDK.md) |
| Security model | [docs/SECURITY_MODEL.md](docs/SECURITY_MODEL.md) |
| Metrics contract | [docs/METRICS_SPEC.md](docs/METRICS_SPEC.md) |
| Troubleshooting | [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) |

Full index: [docs/INDEX.md](docs/INDEX.md)

## Scripts

All operational scripts live in `scripts/` and share a common library (`scripts/lib/`). See [scripts/README.md](scripts/README.md) for the full reference.

| Category | Scripts |
|----------|---------|
| **Deploy** | `start-everything.sh`, `deploy-code.sh`, `cleanup.sh` |
| **Validate** | `readiness-check.sh`, `test-governance-modes.sh`, `eval-complete.py` |
| **Attack** | `run-live-attacks.sh`, `live-pipeline-log.sh`, `tail-pipeline-pods.sh` |
| **Scale** | `scale-iot.sh`, `scale-profile.sh`, `scalability-test.sh` |
| **LLM** | `llm-manager.sh`, `apply-llm-env-to-k8s-secret.sh`, `llm-compare-report.py` |
| **Monitoring** | `access-stack.sh` (port-forward IDS + Grafana + Prometheus) |

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Orchestration** | K3s / Kubernetes |
| **IDS Backend** | Python 3.10+, FastAPI, Uvicorn |
| **Runtime Detection** | Falco (eBPF) |
| **Network Detection** | Suricata |
| **LLM Providers** | xAI Grok, OpenAI GPT-4o, Anthropic Claude, Google Gemini, Moonshot Kimi |
| **Storage** | PostgreSQL (12 tables) |
| **Metrics** | Prometheus (40+ metrics, 30 alert rules) |
| **Dashboards** | Grafana (auto-provisioned), built-in operator dashboard |
| **IoT Protocols** | MQTT (Mosquitto), Modbus, ONVIF, DALI/TALQ, FHIR |
| **Containerization** | Docker, K3s crictl |

---

## License

[MIT](LICENSE) — Ali Suhail, Khaled Rahman, Abdullah Mahmoud
