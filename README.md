# Smart City IDS

LLM-driven Intrusion Detection System for smart city IoT infrastructure. Runs on K3s with Falco + Suricata detection, multi-provider LLM analysis, and automated Kubernetes response.

---

## What This Is

A working IDS that:
- Monitors intentionally vulnerable IoT services (traffic cameras, healthcare APIs, parking systems)
- Detects threats via Falco (runtime syscalls) and Suricata (network signatures)
- Analyzes alerts using LLM providers (xAI Grok-4, OpenAI, Anthropic, Gemini, Kimi) with automatic failover
- Executes Kubernetes defensive actions (pod isolation, service scaling) based on severity
- Provides human-in-the-loop governance with configurable automation modes
- Includes a local fallback engine (11 rule patterns) that works with no API keys

## Architecture

```
Detection                    Analysis                    Response
┌─────────┐                 ┌──────────┐                ┌──────────────┐
│  Falco  │──→ Forwarder ──→│          │──→ severity≥8 →│ Isolate Pod  │
│ (eBPF)  │                 │  IDS API │                │(NetworkPolicy)│
└─────────┘                 │          │                └──────────────┘
┌─────────┐                 │  LLM     │                ┌──────────────┐
│Suricata │──→ Forwarder ──→│ Analysis │──→ severity≥6 →│  Scale Up    │
│(network)│                 │          │                │ (5 replicas) │
└─────────┘                 └──────────┘                └──────────────┘
                                 │
                            ┌────┴─────┐
                            │Governance│ autopilot / assisted / manual
                            └──────────┘
```

**4 namespaces · ~45 pods · 45 API endpoints · 38 Prometheus metrics · 6 LLM providers**

---

## Quick Start

### Full Cluster Deploy

```bash
# Set at least one LLM key (or skip for local-only mode)
export XAI_API_KEY="xai-..."

# Deploy everything
./scripts/start-everything.sh

# Verify
kubectl get pods -n smart-city -w
```

### Run IDS API Locally

```bash
export XAI_API_KEY="xai-..."
cd services/ids-api/src
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Access Points

| Service | URL |
|---|---|
| Operator Dashboard | http://localhost:30800/ui |
| Health Check | http://localhost:30800/health |
| Prometheus | http://localhost:31106 |
| Grafana | http://localhost:30300 |

**Demo credentials**: `operator` / `operator`

---

## Run Attack Pipeline

```bash
# Full pipeline: 13 scenarios (12 attacks + 1 benign control)
./scripts/attack-iot-pipeline.sh

# Quick mode: 5 scenarios
./scripts/attack-iot-pipeline.sh --quick

# Single scenario
./scripts/attack-iot-pipeline.sh --scenario 3
```

### Demo Day (all-in-one)

```bash
# Bootstrap + verify + run attacks + validate
./scripts/demo-day.sh --profile minimal
```

---

## Deploy Code Changes

No Docker builds required — code is mounted via ConfigMaps:

```bash
# Edit source files in services/ids-api/src/ or services/ids-api/static/
# Then deploy:
./scripts/deploy-code.sh
```

---

## Key Components

| Component | Location | Lines | Description |
|---|---|---|---|
| IDS API | `services/ids-api/src/main.py` | 3105 | FastAPI app, alert pipeline, 45 endpoints |
| LLM Manager | `services/ids-api/src/llm_manager.py` | 1091 | 6-provider failover with circuit breakers |
| K8s Automation | `services/ids-api/src/k8s_automation.py` | 207 | Pod isolation, scaling, IP blocking |
| Governance | `services/ids-api/src/governance.py` | 507 | HITL modes: autopilot/assisted/manual |
| Database | `services/ids-api/src/database.py` | 912 | PostgreSQL (8 tables) + memory fallback |
| Dashboard | `services/ids-api/static/index.html` | ~1700 | 7-tab operator SPA |
| Falco Forwarder | `services/forwarders/falco/src/main.py` | 187 | Alert dedup + reshape |
| Suricata Forwarder | `services/forwarders/suricata/src/main.py` | 453 | EVE log parsing + dedup |

---

## Scripts

| Script | Purpose |
|---|---|
| `start-everything.sh` | Deploy K3s cluster + all services |
| `deploy-code.sh` | Hot-reload code via ConfigMaps (no Docker) |
| `cleanup.sh` | Teardown and cleanup |
| `check-setup.sh` | Pre-deploy requirements validation |
| `demo-day.sh` | All-in-one: bootstrap + verify + attacks + validate |
| `demo-readiness.sh` | Pre-demo health checks |
| `one-command-ready.sh` | Bootstrap + seed demo data |
| `attack-iot-pipeline.sh` | 13-scenario MITRE ATT&CK pipeline with metrics CSV |
| `scalability-test.sh` | Scale testing (10→1000 devices) |
| `live-pipeline-log.sh` | Real-time pipeline observer |

---

## Documentation

Full technical docs in [docs/](docs/README.md):

- [Architecture](docs/ARCHITECTURE.md) — system design, pod inventory, database schema, metrics
- [API Reference](docs/API_REFERENCE.md) — all 37 endpoints, models, configuration
- [How It Works](docs/HOW_IT_WORKS.md) — end-to-end alert processing walkthrough
- [Development Guide](docs/DEVELOPMENT.md) — setup, testing, debugging, deployment

---

## Tech Stack

| Layer | Technology |
|---|---|
| Orchestration | K3s (lightweight Kubernetes) |
| Runtime Detection | Falco (eBPF) |
| Network Detection | Suricata (signature IDS) |
| API Framework | FastAPI (Python 3.10+) |
| LLM Providers | xAI Grok-4, OpenAI GPT-4, Anthropic Claude, Google Gemini, Moonshot Kimi |
| Database | PostgreSQL + automatic memory fallback |
| Monitoring | Prometheus + Grafana |
| IoT Protocol | MQTT (Mosquitto) |
| IoT Services | Flask (intentionally vulnerable) |

---

## License

See [LICENSE](LICENSE).
