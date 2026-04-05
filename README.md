# Smart City IDS

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Kubernetes](https://img.shields.io/badge/Platform-K3s%20%2F%20Kubernetes-326CE5.svg)](https://k3s.io/)

> **UDST Capstone Project** — Ali Suhail (60106420), Khaled Rahman (60104156), Abdullah Mahmoud (60300336)
> Supervisor: Dr. Dana Haj Hussein

An intrusion detection system for smart-city IoT infrastructure, built on Kubernetes. It combines Falco and Suricata detection with LLM-powered alert analysis and governance-controlled automated response.

The IoT workloads are protocol-faithful software emulators running in the cluster, not physical hardware. This is a research prototype, not a production SOC platform.

## Architecture

```
IoT Workloads          Detection            IDS Backend             Response
+--------------+    +--------------+    +--------------------+    +--------------+
| traffic-cam  |    |              |    |                    |    |              |
| healthcare   |--->|    Falco     |--->|  Alert Intake      |    | Isolate Pod  |
| parking      |    |  (runtime)   |    |       |            |    | Scale Svc    |
| env-sensor   |    |              |    |  Rate Limit/Dedup  |--->| Block IP     |
| street-light |    +--------------+    |       |            |    | ThreatResp   |
| mqtt-broker  |--->|  Suricata    |--->|  LLM Analysis      |    |   CRD        |
|              |    |  (network)   |    |       |            |    |              |
+--------------+    +--------------+    |  Governance Gate   |    +--------------+
                                        |       |            |
                                        |  PostgreSQL + API  |
                                        +--------+-----------+
                                                 |
                                        +--------+-----------+
                                        | Dashboard / Metrics |
                                        | Prometheus / Grafana|
                                        +--------------------+
```

## Features

- **Dual detection engines** -- Falco for runtime/syscall monitoring, Suricata for network/protocol analysis
- **LLM-assisted alert analysis** -- Multi-provider support (xAI, OpenAI, Anthropic, Gemini, Kimi) with failover and circuit breakers
- **Governance-controlled response** -- Manual, assisted, and autonomous modes with approval workflows
- **Kubernetes-native actions** -- Pod isolation, service scaling, network policies, ThreatResponse CRDs
- **Protocol-aware IoT emulation** -- MQTT, Modbus, ONVIF, DALI/TALQ, and FHIR-style services with state models
- **Operator dashboard** -- Real-time alert feed, LLM provider status, governance queue, IoT fleet view
- **Comparative LLM evaluation** -- Strict per-provider scoring pipeline with artifact-backed results
- **Full observability** -- PostgreSQL persistence, Prometheus metrics, Grafana dashboards, audit traces

## Quick Start

**Prerequisites:** Linux (tested on Kali/Ubuntu), 4+ GB RAM, sudo access, `curl`, `jq`, `git`.

**1. Configure at least one LLM provider key:**

```bash
# Create .env with your key(s)
echo 'XAI_API_KEY=xai-...' > .env
# Sync to Kubernetes
bash scripts/apply-llm-env-to-k8s-secret.sh .env
```

See [docs/LLM_CONFIGURATION.md](docs/LLM_CONFIGURATION.md) for all supported providers.

**2. Deploy the cluster:**

```bash
sudo bash scripts/start-everything.sh
bash scripts/deploy-code.sh
```

**3. Verify and open the dashboard:**

```bash
bash scripts/readiness-check.sh
```

Open [http://localhost:30800/ui](http://localhost:30800/ui) (default login: `admin` / `admin`).

**4. Run a live attack exercise:**

```bash
bash scripts/run-live-attacks.sh --mode protocol --duration 30 --verbose
```

For stable localhost access when NodePort is inconvenient:

```bash
bash scripts/access-stack.sh start
# IDS: http://localhost:8000 | Grafana: http://localhost:3000 | Prometheus: http://localhost:9090
```

## Project Structure

| Path | Purpose |
|------|---------|
| `services/ids-api/` | Core IDS backend (FastAPI), dashboard, LLM engines, K8s automation |
| `services/forwarders/` | Falco and Suricata alert forwarders |
| `services/ids-operator/` | Kubernetes operator for ThreatResponse CRDs |
| `smart-city-services/` | IoT emulators: traffic camera, healthcare API, parking, env sensor, street lighting |
| `iot-simulator/` | MQTT-based IoT device simulator |
| `k8s-manifests/` | Kubernetes manifests for all workloads |
| `infrastructure/` | Grafana dashboards, Prometheus alerts, DB migrations |
| `scripts/` | Deployment, validation, attack simulation, and operations |
| `tests/` | Smoke tests, stability tests, unit tests |
| `docs/` | Technical documentation ([index](docs/INDEX.md)) |
| `docker/` | Dockerfiles for IDS API, forwarders, and smart-city services |

## Documentation

Start here, in order:

1. [docs/QUICKSTART.md](docs/QUICKSTART.md) -- First deployment and first checks
2. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) -- System layout and component boundaries
3. [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md) -- End-to-end processing flow
4. [docs/OPERATIONS.md](docs/OPERATIONS.md) -- Day-to-day operations and recovery

Then go deeper as needed:

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

## Tech Stack

| Component | Technology |
|-----------|------------|
| Orchestration | K3s / Kubernetes |
| IDS Backend | Python, FastAPI |
| Runtime Detection | Falco (eBPF) |
| Network Detection | Suricata |
| LLM Providers | xAI Grok, OpenAI GPT, Anthropic Claude, Google Gemini, Moonshot Kimi |
| Storage | PostgreSQL |
| Metrics | Prometheus |
| Dashboards | Grafana, built-in operator dashboard |
| IoT Protocols | MQTT, Modbus, ONVIF, DALI/TALQ, FHIR |
| Message Broker | Eclipse Mosquitto (MQTT) |

## License

[MIT](LICENSE) -- Ali Suhail, Khaled Rahman, Abdallahi Mahmoud
