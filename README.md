# Smart City IDS

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Kubernetes](https://img.shields.io/badge/Kubernetes-K3s-326CE5?logo=kubernetes)](https://k3s.io/)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python)](https://python.org/)

**LLM-Driven Intrusion Detection System for Smart City Infrastructure**

An autonomous security monitoring system that uses Large Language Models (xAI Grok, OpenAI GPT) to analyze security alerts from Falco and Suricata, providing intelligent threat assessment and automated Kubernetes responses.

---

## 🚀 Quick Start

```bash
# Clone the repository
git clone https://github.com/your-org/smart-city-ids.git
cd smart-city-ids

# Configure your API keys
cp .env.example .env
nano .env  # Add XAI_API_KEY or OPENAI_API_KEY

# Deploy everything (one command!)
./deploy.sh
```

**That's it!** The script installs K3s, builds images, deploys all services, and configures monitoring.

---

## 📋 Features

| Feature | Description |
|---------|-------------|
| **LLM-Powered Analysis** | Uses xAI Grok or OpenAI GPT to analyze security alerts |
| **Multi-Source Detection** | Integrates Falco (runtime) and Suricata (network) |
| **Automated Response** | Kubernetes actions based on threat severity |
| **Persistent Storage** | PostgreSQL for alert history and metric recovery |
| **Visual Dashboards** | Grafana dashboards for real-time monitoring |
| **Demo Environment** | Intentionally vulnerable services for testing |

---

## 🏗️ Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Smart City     │     │    Security     │     │    IDS API      │
│  Services       │────►│    Monitors     │────►│  (LLM Engine)   │
│  (IoT/Traffic)  │     │ (Falco/Suricata)│     │                 │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                        ┌────────────────────────────────┼────────────────┐
                        │                                ▼                │
                        │  ┌──────────────┐    ┌─────────────────────┐   │
                        │  │  PostgreSQL  │◄───│  Automated Actions  │   │
                        │  │  (History)   │    │  (Isolate/Scale)    │   │
                        │  └──────────────┘    └─────────────────────┘   │
                        │           │                                     │
                        │           ▼                                     │
                        │  ┌──────────────┐    ┌─────────────────────┐   │
                        │  │  Prometheus  │───►│      Grafana        │   │
                        │  │  (Metrics)   │    │   (Dashboards)      │   │
                        │  └──────────────┘    └─────────────────────┘   │
                        └─────────────────────────────────────────────────┘
```

---

## 📦 Components

| Component | Technology | Purpose |
|-----------|------------|---------|
| IDS API | FastAPI (Python) | Alert processing, LLM integration |
| LLM Engine | xAI Grok / OpenAI | Threat analysis and severity scoring |
| Falco | eBPF/Syscalls | Runtime security monitoring |
| Suricata | Network IDS | Traffic analysis |
| PostgreSQL | Database | Alert persistence |
| Prometheus | Metrics | Time-series data |
| Grafana | Visualization | Dashboards |
| K3s | Kubernetes | Container orchestration |

---

## 🔧 Requirements

- **OS:** Ubuntu 20.04+ (or similar Linux)
- **RAM:** 4GB minimum, 8GB recommended
- **Disk:** 20GB minimum
- **API Key:** xAI or OpenAI account

---

## 📖 Documentation

| Document | Description |
|----------|-------------|
| [SETUP.md](docs/SETUP.md) | Detailed installation guide |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design and data flow |
| [OPERATIONS.md](docs/OPERATIONS.md) | Day-to-day operations and demos |
| [PROJECT_AUDIT.md](docs/PROJECT_AUDIT.md) | Codebase assessment |

---

## 🎮 Demo

### Run Attack Simulation

```bash
# Get your node IP
NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')

# Run DDoS simulation
python attack-simulator/ddos_simulator.py http://${NODE_IP}:30800 5 10

# Watch IDS logs
kubectl logs -n smart-city -l app=ids-api -f
```

### Access Dashboards

| Service | URL | Credentials |
|---------|-----|-------------|
| IDS API | http://NODE_IP:30800 | - |
| Grafana | http://NODE_IP:30300 | admin / admin |
| Prometheus | http://NODE_IP:31701 | - |

---

## 📁 Project Structure

```
smart-city-ids/
├── deploy.sh                 # One-click deployment
├── services/
│   ├── ids-api/              # Core IDS API
│   ├── ids-operator/         # Kubernetes operator
│   └── forwarders/           # Alert forwarders
├── smart-city-services/      # Demo IoT services
├── k8s-manifests/            # Kubernetes manifests
├── infrastructure/
│   ├── monitoring/           # Prometheus/Grafana config
│   └── database/             # PostgreSQL migrations
├── attack-simulator/         # Attack simulation tools
├── scripts/                  # Utility scripts
├── docker/                   # Dockerfiles
├── docs/                     # Documentation
└── tests/                    # Test suites
```

---

## 🔒 Security Note

The `smart-city-services/` directory contains **intentionally vulnerable** applications for demonstration purposes. These should **never** be exposed to the internet in a production environment.

---

## 🎓 Academic Context

This project was developed as a Capstone project demonstrating:
- LLM integration for security analysis
- Kubernetes-native automation
- Real-time threat detection and response
- Cloud-native monitoring patterns

---

## 📜 License

MIT License - See [LICENSE](LICENSE) for details.

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes and test
4. Submit a pull request

See [docs/PROJECT_AUDIT.md](docs/PROJECT_AUDIT.md) for areas needing improvement.

---

## 📞 Support

- **Issues:** GitHub Issues
- **Documentation:** [docs/](docs/)
- **Email:** [your-email@example.com]
