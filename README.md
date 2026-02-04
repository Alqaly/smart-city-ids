# Smart City IDS

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Kubernetes](https://img.shields.io/badge/Kubernetes-K3s-326CE5?logo=kubernetes)](https://k3s.io/)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python)](https://python.org/)

**LLM-Driven Intrusion Detection System for Smart City Infrastructure**

An autonomous security monitoring system that uses Large Language Models (xAI Grok, OpenAI GPT) to analyze security alerts from Falco and Suricata, providing intelligent threat assessment and automated Kubernetes responses.

---

## 🚀 Quick Start (5 Minutes)

**→ [Read the QUICK_START.md for step-by-step instructions](QUICK_START.md)**

### TL;DR
```bash
cd /home/kali/smart-city-ids
export XAI_API_KEY="your-key"  # or OPENAI_API_KEY
./scripts/start-everything.sh
# Then go to: http://localhost:8000/ui
# Login: operator / operator
```

### Full Guide

#### Prerequisites
- Linux (Kali, Ubuntu 22.04, Debian 12, or similar)
- 4GB RAM minimum (8GB recommended), 20GB disk
- Internet access (first-time K3s installation)
- **xAI or OpenAI API key** (at least one)

#### 1. Clone Repository
```bash
git clone https://github.com/Alqaly/smart-city-ids.git
cd smart-city-ids
```

#### 2. Set API Key
```bash
export XAI_API_KEY="your-xai-key-here"
# OR
export OPENAI_API_KEY="your-openai-key-here"
```

#### 3. Deploy (One Command)
```bash
sudo bash scripts/start-everything.sh
```

**That's it!** The script handles:
- K3s installation (if needed)
- Kubernetes cluster setup
- Persistent storage configuration
- All microservices deployment
- IoT emulation (100 devices)
- Prometheus & Grafana dashboards

#### Access Services
Once running, access your system at (replacing `IP` with your machine's IP):

| Service | URL | Default Creds |
|---------|-----|----------------|
| **Grafana** | `http://IP:30300` | admin / admin |
| **Prometheus** | `http://IP:31106` | - |
| **IDS API Docs** | `http://IP:30800/docs` | - |
| **Traffic Camera** | `http://IP:30100` | - |
| **Healthcare API** | `http://IP:30101` | - |
| **Parking System** | `http://IP:30102` | - |

---

## ✨ What's New

- **✅ Automatic Persistent Storage** - All data (Prometheus, Grafana) survives pod and K3s restarts
- **✅ Single-Command Deployment** - Everything in one script: `sudo bash scripts/start-everything.sh`
- **✅ Production-Ready** - Professional Kubernetes deployment with proper RBAC, resource limits, health checks
- **✅ Comprehensive Documentation** - 20+ guides covering setup, operations, architecture, and troubleshooting
- **✅ Conference-Ready** - Deploy live in 3-5 minutes for demos and presentations
- **✅ Self-Contained** - Works on any Linux machine worldwide, no external dependencies

---

## 💡 Why Smart City IDS?

| Feature | Description |
|---------|-------------|
| **LLM-Powered Analysis** | Uses xAI Grok or OpenAI GPT to analyze security alerts |
| **Multi-Source Detection** | Integrates Falco (runtime IDS) and Suricata (network IDS) - Both primary |
| **Automated Response** | Kubernetes actions based on threat severity |
| **Persistent Storage** | Prometheus and Grafana data survives pod restarts, K3s restarts, and redeployments automatically |
| **Visual Dashboards** | Grafana dashboards for real-time monitoring |
| **High-Fidelity Emulation** | Purpose-built IIoT environment with 30-100 realistic containerized services, network traffic, and security tooling |

## 🔬 System Overview: An IIoT Security Emulation

This project is an **implementation-level Industrial Internet of Things (IIoT) emulation** running on Kubernetes. It provides a high-fidelity environment for validating security monitoring strategies against realistic, containerized workloads.

It is **not a simulation**. Instead of abstract models, it uses:
- **Real Services**: Python applications (Flask, FastAPI) running in containers.
- **Real Network Traffic**: Genuine HTTP and MQTT protocol interactions.
- **Real Security Tooling**: The exact versions of Falco, Suricata, and Prometheus used in production environments.

This emulation-based approach is critical for security research, as it exposes an implementation-accurate attack surface and allows for the evaluation of kernel-level and network-level detection tools in a controlled, interactive cyber-range. For a detailed academic justification, see [docs/ACADEMIC_CONTEXT.md](docs/ACADEMIC_CONTEXT.md).

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
| [SECURITY_MODEL.md](docs/SECURITY_MODEL.md) | Threat analysis decisions |

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

## 📊 Monitoring Reality

**Implemented and visible in Grafana (source of truth: IDS API `/metrics`):**
- `smartcity_ids_alerts_received_total`, `smartcity_ids_severity_total`
- `smartcity_ids_llm_latency_seconds`, `smartcity_ids_llm_requests_total`
- `smartcity_ids_actions_executed_total`, `smartcity_ids_time_to_mitigation_seconds`
- `smartcity_ids_llm_decision_outcome_total`, `smartcity_ids_llm_failover_total`
- IoT simulator metrics: `iot_messages_sent_total`, `iot_device_active`, `iot_burst_factor`

**Future work (not claimed as implemented):**
- Cross-cluster correlation metrics
- Multi-tenant SOC baselining

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
- **Email:** [alqaly@example.com]

## 🔍 Dual-IDS Architecture

This system uses **both** Falco and Suricata as **primary IDS systems**:

- **Falco**: Runtime security monitoring (detects suspicious container behavior, syscall anomalies)
- **Suricata**: Network-level threat detection (analyzes traffic patterns, protocol violations)

Both work in **tandem** to provide comprehensive threat coverage at multiple layers:
- **Runtime Layer**: Falco monitors what containers are doing
- **Network Layer**: Suricata monitors network traffic
- **Analysis Layer**: LLM correlates and analyzes both sources

This dual-IDS approach ensures nothing slips through cracks—threats are caught either at the network boundary or at runtime.

---

## 🎯 GitHub Repository Settings

### Suggested About Section
For your GitHub repository "About" (Settings → About):

**Description:**
```
LLM-Driven Intrusion Detection System for Smart City Infrastructure.
Uses AI (xAI Grok/OpenAI) to analyze security alerts, detect threats,
and automate Kubernetes responses. Deploy in 5 minutes.
```

**Topics (Tags):**
```
kubernetes, security, ids, intrusion-detection, k3s, llm, ai,
smart-city, kubernetes-security, cybersecurity, iot, automation
```

**Website:**
```
https://github.com/Alqaly/smart-city-ids/blob/main/docs/README.md
```

---

## 🔗 Related Resources

- **Documentation Index:** [docs/INDEX.md](docs/INDEX.md)
- **Quick Start:** [docs/QUICKSTART.md](docs/QUICKSTART.md)
- **Deployment Guide:** [docs/SETUP.md](docs/SETUP.md)
- **Architecture Details:** [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- **Deployment Checklist:** [DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md)
