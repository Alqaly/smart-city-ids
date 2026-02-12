# Smart City IDS — LLM-Powered Intrusion Detection System

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![K3s](https://img.shields.io/badge/K3s-1.28+-326CE5.svg)](https://k3s.io/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-009688.svg)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

An intrusion detection system for smart-city infrastructure that uses **LLM-powered threat analysis**, **automated Kubernetes responses**, and a **human-in-the-loop governance** workflow. Alerts from Falco (runtime) and Suricata (network) are analysed by up to 5 LLM providers with automatic failover, and defensive actions (pod isolation, scaling, IP blocking) are executed on a K3s cluster.

> Built as a capstone project demonstrating how large-language models can augment security operations in containerised IoT environments.

---

## Architecture

```
Smart City Services (traffic-camera, healthcare-api, parking-system, IoT simulators)
        │
  K3s Cluster ──── Falco (runtime) ────┐
        │                               │      ┌──────────────────────────────┐
        └──────── Suricata (network) ───┼─────▶│         IDS API (FastAPI)    │
                                        │      │                              │
                                        │      │  Rate Limiter → Dedup Cache  │
                                        │      │       → LLM Analysis         │
                                        │      │       → K8s Automation       │
                                        │      └──────┬───────────────────────┘
                                        │             │
                                  ┌─────┴─────────────┴──────────┐
                                  │   LLM Failover Chain         │
                                  │ xAI → Anthropic → OpenAI    │
                                  │ → Gemini → Kimi → Local     │
                                  └──────────────────────────────┘
```

**Alert flow:** Falco/Suricata detect suspicious activity → forwarder POSTs JSON to IDS API → rate-limited & deduplicated → LLM analyses threat → K8s automation executes response → alert stored & shown on dashboard.

---

## Features

| Area | Details |
|------|---------|
| **Detection** | Falco (syscall monitoring), Suricata (network IDS), custom alert injection |
| **LLM Analysis** | 5 cloud providers + local rule-based fallback, circuit breakers, automatic failover |
| **Automation** | Pod isolation, deployment scaling, IP blocking, node cordoning, rolling restart |
| **Governance** | 3 modes (Autopilot / Assisted / Manual), approval workflow, audit trail |
| **Dashboard** | 7-tab operator UI — overview, live alerts, Kubernetes, IoT fleet, LLM providers, governance, attack simulation |
| **Observability** | Prometheus metrics (50+), Grafana dashboards, PostgreSQL persistence (memory fallback) |
| **Deduplication** | Identical-alert caching with 60 s TTL, estimated cost savings tracking |
| **Attack Simulation** | Built-in demo scripts for shell-in-container, DDoS, data exfiltration, privilege escalation, and more |

---

## Quick Start

### Prerequisites

- **Linux** (tested on Kali 2025/Ubuntu 22.04)
- **K3s** (installed automatically by `start-everything.sh`, or bring your own cluster)
- **4 GB RAM** minimum (8 GB recommended)
- **One LLM API key** (optional — the system includes a local fallback engine for demos)

### 1. Clone

```bash
git clone https://github.com/<your-org>/smart-city-ids.git
cd smart-city-ids
```

### 2. (Optional) Set LLM API Keys

The system works **without any API keys** using the built-in local analysis engine.
For cloud LLM analysis, export at least one key:

```bash
# Pick one — Gemini has a free tier
export GEMINI_API_KEY="AIza..."
# or
export XAI_API_KEY="xai-..."
# or
export OPENAI_API_KEY="sk-..."
```

### 3. Deploy Everything

```bash
# Full deployment — installs K3s, deploys all services, Falco, Suricata, IDS API
sudo ./scripts/start-everything.sh

# Watch pods come up
kubectl get pods -A -w
```

### 4. Access the Dashboard

The IDS API is exposed via **NodePort 30800** — no port-forward needed:

```bash
# Health check
curl http://localhost:30800/health

# Operator Dashboard (open in browser)
open http://localhost:30800/ui
```

Other services:

| Service | URL |
|---------|-----|
| IDS Dashboard | http://localhost:30800/ui |
| IDS API | http://localhost:30800/health |
| Grafana | http://localhost:30300 (admin / admin) |
| Prometheus | http://localhost:31106 |

### 5. Run a Demo Attack

```bash
# 10-scenario automated demo (shell, DDoS, exfil, privesc, etc.)
python3 attack-simulator/demo_attack_runner.py

# Or manually inject one alert
curl -X POST http://localhost:30800/api/alerts/internal \
  -H "Content-Type: application/json" \
  -d '{
    "output": "Terminal shell in container: bash in traffic-camera",
    "priority": "Critical",
    "rule": "Terminal shell in container",
    "time": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
    "output_fields": {
      "container.name": "traffic-camera",
      "proc.cmdline": "bash"
    }
  }'
```

Then open **http://localhost:30800/ui** to see the alert on the dashboard.

---

## LLM Providers

| Priority | Provider | Model | Env Variable | Free Tier? |
|:--------:|----------|-------|--------------|:----------:|
| 1 | xAI | grok-4-latest | `XAI_API_KEY` | No |
| 2 | Anthropic | claude-3-5-sonnet | `ANTHROPIC_API_KEY` | Limited |
| 3 | OpenAI | gpt-4-turbo-preview | `OPENAI_API_KEY` | No |
| 4 | Google | gemini-2.0-flash | `GEMINI_API_KEY` | **Yes** |
| 5 | Moonshot | moonshot-v1-128k | `KIMI_API_KEY` | Limited |
| 6 | **Local** | rule-based | *none needed* | **Always** |

- The system tries providers in priority order. If one fails (quota, network, bad key), the next is tried automatically.
- **Circuit breakers** prevent repeated calls to a failing provider.
- The **local fallback engine** uses pattern-matching rules (crypto mining, SQL injection, DDoS, data exfiltration, etc.) and always works without any API key.

---

## Project Structure

```
smart-city-ids/
├── services/
│   └── ids-api/
│       ├── src/                       # IDS API source code
│       │   ├── main.py                # FastAPI application (alerts, automation, API)
│       │   ├── llm_manager.py         # Multi-LLM orchestration + local fallback
│       │   ├── llm_engine_*.py        # Individual LLM provider adapters (5 engines)
│       │   ├── k8s_automation.py      # Kubernetes defensive actions
│       │   ├── database.py            # PostgreSQL / memory-fallback storage
│       │   ├── governance.py          # Human-in-the-loop workflow
│       │   ├── alert_deduplicator.py  # Dedup cache
│       │   ├── alert_rate_limiter.py  # Rate limiting
│       │   ├── operator_interface.py  # Operator data aggregation
│       │   └── config.py              # All configuration / thresholds
│       └── static/
│           └── index.html             # Operator Dashboard (single-page app)
├── smart-city-services/               # Intentionally-vulnerable IoT services
│   ├── traffic-camera/                # Flask — surveillance camera service
│   ├── healthcare-api/                # Flask — patient data API
│   └── parking-system/                # Flask — parking sensor service
├── k8s-manifests/                     # Kubernetes deployment manifests
│   ├── ids-api-FINAL.yaml             # IDS API deployment + service
│   ├── services-no-build.yaml         # IoT services (ConfigMap-mounted)
│   ├── falco-values.yaml              # Falco Helm values
│   └── falco-forwarder.yaml           # Falco → IDS forwarder
├── attack-simulator/                  # Python attack simulation tools
│   ├── demo_attack_runner.py          # Main 10-scenario demo script
│   ├── ddos_simulator.py              # DDoS flood simulator
│   ├── privilege_escalation.py        # Privilege escalation simulator
│   └── data_exfiltration.py           # Data exfil simulator
├── attack-simulations/                # Bash demo scripts
│   ├── demo-showcase-full.sh          # Full 5-phase demo showcase
│   └── generate-security-events.sh    # kubectl exec + API reporting
├── scripts/
│   ├── start-everything.sh            # Full cluster bootstrap
│   ├── deploy-code.sh                 # Quick code deploy (no Docker needed)
│   └── k3s-dynamic-ip.sh             # Fix kubeconfig after network change
├── docker/ids-api/Dockerfile          # IDS API container image
├── iot-simulator/                     # MQTT IoT device simulators
├── infrastructure/                    # Database schemas, monitoring configs
├── tests/                             # Unit / smoke / stability tests
└── docs/                              # Extended documentation
```

---

## Deploying Code Changes

For **code-only changes** (no new Python dependencies), Docker is **not** needed:

```bash
# Fast deploy — updates ConfigMaps and restarts pods (~30 seconds)
./scripts/deploy-code.sh

# Check status
./scripts/deploy-code.sh --status
```

Only rebuild the Docker image when `requirements.txt` changes:

```bash
./scripts/deploy-code.sh --full
```

---

## API Reference

### Alert Endpoints

| Method | Path | Auth | Description |
|--------|------|:----:|-------------|
| POST | `/api/alerts/internal` | No | Submit a security alert for LLM analysis |
| GET | `/api/alerts?limit=N` | No | Retrieve recent analysed alerts |
| GET | `/api/metrics` | No | JSON metrics (uptime, alert counts, IoT devices) |
| GET | `/health` | No | Health check with component status |
| GET | `/metrics` | No | Prometheus exposition format |

### LLM & Circuit Breaker

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/circuit-breaker/status` | Circuit breaker states for all engines |
| GET | `/api/circuit-breaker/reset` | Reset all circuit breakers |
| GET | `/api/llm/status` | Configured LLM providers and active engine |
| GET | `/api/deduplicator-stats` | Dedup cache hit/miss/cost stats |

### Governance (requires auth token)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/governance/status` | Current mode, pending count, metrics |
| POST | `/api/governance/mode?mode=assisted` | Change governance mode |
| GET | `/api/governance/pending` | Actions awaiting operator approval |
| POST | `/api/governance/approve/{id}` | Approve a pending action |
| POST | `/api/governance/reject/{id}` | Reject a pending action |

### Dashboard & Auth

| Method | Path | Description |
|--------|------|-------------|
| GET | `/ui` | Operator Dashboard (HTML) |
| POST | `/api/auth/login` | Login (default: `operator` / `operator`) |

---

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `XAI_API_KEY` | xAI Grok API key | — |
| `ANTHROPIC_API_KEY` | Anthropic Claude key | — |
| `OPENAI_API_KEY` | OpenAI GPT key | — |
| `GEMINI_API_KEY` | Google Gemini key | — |
| `KIMI_API_KEY` | Moonshot Kimi key | — |
| `LLM_PRIORITY` | Engine priority order | `xai,anthropic,openai,gemini,kimi` |
| `AUTOMATION_MODE` | `autopilot` / `assisted` / `manual` | `assisted` |
| `PROTECTED_SERVICES` | Services exempt from automation | `postgres,grafana` |
| `KUBECONFIG` | Path to kubeconfig | `/etc/rancher/k3s/k3s.yaml` |

### Kubernetes Secret (for cluster deployment)

```bash
kubectl create secret generic ids-secrets -n smart-city \
  --from-literal=gemini-api-key="AIza..." \
  --from-literal=xai-api-key="xai-..."
```

---

## Governance Modes

| Mode | Behaviour |
|------|-----------|
| **Autopilot** | All K8s actions auto-execute (useful for demos) |
| **Assisted** | Severity < 8 auto-executes; severity >= 8 requires operator approval |
| **Manual** | All actions require explicit operator approval |

Change mode from the dashboard **Governance** tab or via API:
```bash
curl -X POST http://localhost:30800/api/governance/mode?mode=autopilot \
  -H "Authorization: Bearer <token>"
```

---

## Attack Simulation

Built-in tools for generating realistic security alerts during demos:

```bash
# Automated 10-scenario demo (recommended for presentations)
python3 attack-simulator/demo_attack_runner.py

# Options
python3 attack-simulator/demo_attack_runner.py --list            # List scenarios
python3 attack-simulator/demo_attack_runner.py --scenario ddos   # Run one scenario
python3 attack-simulator/demo_attack_runner.py --rapid           # Fast mode (no delays)

# Bash demo showcase (5 phases with narration)
bash attack-simulations/demo-showcase-full.sh

# Generate events via kubectl exec + API reporting
bash attack-simulations/generate-security-events.sh
```

The dashboard **Attack Simulation** tab also lets you inject alerts directly from the browser with one click.

---

## Troubleshooting

### NodePort not reachable

K3s binds NodePorts on **all interfaces including localhost**. Always use `localhost`:
```bash
curl http://localhost:30800/health    # Always works, any WiFi network
```

### K3s broken after network/WiFi change

The kubeconfig uses `127.0.0.1:6443` by default — WiFi changes should not affect it.
If issues persist:
```bash
sudo systemctl restart k3s && sleep 10
sudo chmod 644 /etc/rancher/k3s/k3s.yaml
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
kubectl get nodes
```

### All LLM providers failing

The local fallback engine handles this automatically — alerts will still be analysed.
To update cloud API keys:
```bash
kubectl delete secret ids-secrets -n smart-city
kubectl create secret generic ids-secrets -n smart-city \
  --from-literal=gemini-api-key="NEW_KEY"
kubectl delete pods -n smart-city -l app=ids-api --force --grace-period=0
```

### Check logs

```bash
kubectl logs -n smart-city -l app=ids-api --tail=100 -f
kubectl logs -n falco-system -l app.kubernetes.io/name=falco --tail=50
```

### Reset circuit breakers

```bash
curl http://localhost:30800/api/circuit-breaker/reset
```

---

## Testing

```bash
cd services/ids-api/src
pip install -r requirements.txt
pip install pytest

# Run unit tests
pytest ../../tests/ -v

# Smoke test against running cluster
curl -s http://localhost:30800/health | python3 -m json.tool
```

---

## Documentation

| Document | Description |
|----------|-------------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture deep-dive |
| [docs/API_REFERENCE.md](docs/API_REFERENCE.md) | Full API documentation |
| [docs/LLM_CONFIGURATION.md](docs/LLM_CONFIGURATION.md) | LLM setup and tuning |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Deployment guide |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Common issues |
| [docs/OPERATOR_INTERFACE.md](docs/OPERATOR_INTERFACE.md) | Dashboard usage |

---

## License

MIT — see [LICENSE](LICENSE)
