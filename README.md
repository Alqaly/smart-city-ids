# Smart City IDS

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Kubernetes](https://img.shields.io/badge/Kubernetes-K3s-326CE5?logo=kubernetes)](https://k3s.io/)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python)](https://python.org/)

**LLM-Driven Intrusion Detection System for Smart City Infrastructure**

An autonomous security monitoring system that uses Large Language Models (xAI Grok, OpenAI GPT) to analyze security alerts from Falco and Suricata, providing intelligent threat assessment and automated Kubernetes responses.

---

## 🚀 Quick Start (5 Minutes)

### Prerequisites
- Ubuntu 20.04+ (or similar Linux)
- 4GB RAM, 20GB disk
- Internet (first-time only)
- xAI or OpenAI API key

### Deploy
```bash
git clone https://github.com/Alqaly/smart-city-ids.git
cd smart-city-ids
cp .env.example .env
nano .env  # Add your XAI_API_KEY or OPENAI_API_KEY
./deploy.sh
```

### Check It Works
```bash
kubectl get pods -n smart-city          # Should see 10+ pods running
kubectl logs -n smart-city -l app=ids-api --tail=20
```

Grafana: `http://localhost:30300`  
IDS API: `http://localhost:30800/docs`

---

## 📋 Features

| Feature | Description |
|---------|-------------|
| **LLM-Powered Analysis** | Uses xAI Grok or OpenAI GPT to analyze security alerts |
| **Multi-Source Detection** | Integrates Falco (runtime IDS) and Suricata (network IDS) - Both primary |
| **Automated Response** | Kubernetes actions based on threat severity |
| **Persistent Storage** | PostgreSQL for alert history and metric recovery |
| **Visual Dashboards** | Grafana dashboards for real-time monitoring |
| **High-Fidelity Emulation** | A purpose-built IIoT emulation environment with realistic, containerized services and network traffic for security testing. |

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
