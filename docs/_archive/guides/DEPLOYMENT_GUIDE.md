# Smart City LLM-IDS Deployment Guide

## Project Information

**Project Title:** LLM-Driven Intrusion Detection for Edge-Enabled Smart Cities

**Project Team:**
1. Abdallahi Mahmoud
2. Khaled Rahman
3. Ali Suhail

---

## Prototype Timeline

| Week | Date | Task | Status |
|------|------|------|--------|
| 1 | 7 Jan 2026 | Set up baseline prototype: single-node K3s cluster, IDS API (FastAPI), Falco pod deployed and healthy. Confirm basic logs visible. | ✅ Complete |
| 2 | 14 Jan 2026 | Trigger real Falco runtime alerts (shell execution, sensitive file access). Verify alerts received by IDS API. Confirm detection pipeline functioning. | ✅ Complete |
| 3 | 21 Jan 2026 | Integrate xAI Grok-4 LLM with IDS pipeline. Validate alerts analyzed correctly with structured outputs (severity, threat type, recommendations). Save sample analysis as evidence. | ✅ Complete |
| 4 | 28 Jan 2026 | Acquire Raspberry Pi and sensor components. Prepare Pi OS and network configuration. Verify connectivity to IDS environment. No attack testing. | 🔄 In Progress |
| 5 | 4 Feb 2026 | Introduce Raspberry Pi + sensor as physical smart-city device. Verify sensor data transmission to edge system. Confirm Pi activity visible in IDS pipeline logs. | ⏳ Pending |
| 6 | 11 Feb 2026 | Enable Prometheus metrics for Pi-originated alerts/events. Verify metrics (alerts received, actions executed) update in real-time during sensor activity. | ⏳ Pending |
| 7 | 18 Feb 2026 | Configure Grafana dashboard for alerts, response latency, and Pi-related events. Ensure live updates during sensor data generation and attack scenarios. | ⏳ Pending |
| 8 | 25 Feb 2026 | Stability testing: run multiple alert/attack scenarios with Pi and sensor input. Verify reliable processing without crashes, consistent logging and responses. | ⏳ Pending |
| 9 | 4 Mar 2026 | Prepare complete system demo using Pi + sensor as physical device. Test end-to-end workflow: sensor activity → simulated attacks → LLM analysis → automated mitigation. | ⏳ Pending |
| 10 | 11 Mar 2026 | **Final Demo:** Live sensor data from Pi, real-time intrusion detection, LLM-based analysis, automated K8s responses. All hardware/software fully integrated. | ⏳ Pending |

---

## System Overview

This system consists of:
- **Kubernetes (K3s)**: Lightweight Kubernetes cluster
- **Falco**: Runtime security monitoring
- **Suricata**: Network intrusion detection
- **Prometheus**: Metrics collection
- **Grafana**: Visualization dashboards
- **Smart City Services**: Traffic cameras, healthcare APIs, parking systems
- **IoT Devices**: MQTT-based sensor simulation

## Quick Start

### Access the System

```bash

kubectl get pods -A

# View smart city services

kubectl get pods -n smart-city

# Run demo

./demo.sh
```bash

```bash

./scale-iot.sh 20

# Check status

kubectl get pods -n smart-city -l app=iot-device
```bash

#### Prometheus

```bash
kubectl port-forward -n monitoring svc/prometheus 9090:9090

# Open: <http://localhost:9090>

```bash

```bash
kubectl port-forward -n monitoring svc/grafana 3000:3000

# Open: <http://localhost:3000>

# Login: admin / admin123

```bash

### K3s not starting

```bash
sudo systemctl status k3s

sudo journalctl -u k3s -f
```bash

```bash
kubectl describe pod <pod-name> -n <namespace>

kubectl logs <pod-name> -n <namespace>
```bash

```bash
sudo /usr/local/bin/k3s-uninstall.sh

./complete-setup.sh
```bash

```bash
┌─────────────────────────────────────────────┐

│          Smart City Infrastructure           │
├─────────────────────────────────────────────┤
│                                             │
│  ┌───────────┐  ┌───────────┐  ┌─────────┐│
│  │  Traffic  │  │Healthcare │  │ Parking ││
│  │  Cameras  │  │    APIs   │  │ Systems ││
│  │   (x2)    │  │   (x2)    │  │  (x2)   ││
│  └───────────┘  └───────────┘  └─────────┘│
│                                             │
│  ┌────────────────────────────────────────┐│
│  │       IoT Devices (MQTT)               ││
│  │  Environmental Sensors, Smart Meters   ││
│  │            (x5-100)                    ││
│  └────────────────────────────────────────┘│
│                                             │
└─────────────────────────────────────────────┘
              ↓                ↓
    ┌──────────────┐  ┌───────────────┐
    │    Falco     │  │   Suricata    │
    │  (Runtime)   │  │   (Network)   │
    └──────────────┘  └───────────────┘
              ↓                ↓
       ┌──────────────────────────┐
       │    LLM Analysis Engine    │
       │  (xAI Grok-4 / OpenAI)   │
       └──────────────────────────┘
              ↓                ↓
    ┌──────────────┐  ┌───────────────┐
    │  Prometheus  │  │    Grafana    │
    │  (Metrics)   │  │ (Dashboards)  │
    └──────────────┘  └───────────────┘
```bash

### IoT Device Simulation

- **Protocol**: MQTT (Eclipse Mosquitto)
- **Behavior**: Periodic heartbeats (10s), event-driven alerts
- **Network**: Simulated latency (10-500ms), packet loss (10%)
- **Failures**: Random 40s outages (5% probability)
- **API**: REST endpoints on port 5000 (/status, /metrics)

### Security Monitoring

- **Falco**: Monitors system calls, file access, process execution
- **Suricata**: Monitors network traffic, applies IDS rules
- **Integration**: Both forward alerts to LLM for analysis

### Technologies Used

| Component | Technology | Version |
|-----------|------------|---------|
| Container Runtime | K3s | v1.33.5 |
| Security (Runtime) | Falco | Latest |
| Security (Network) | Suricata | Latest |
| MQTT Broker | Eclipse Mosquitto | 2.0 |
| IoT Language | Python | 3.11 |
| MQTT Client | Paho MQTT | Latest |
| Monitoring | Prometheus | Latest |
| Dashboards | Grafana | Latest |

## Realism Assessment

| Feature | Realism % | Notes |
|---------|-----------|-------|
| Communication Protocol | 100% | Real MQTT, not mocked |
| Message Format | 95% | Standard JSON telemetry |
| Network Behavior | 90% | Simulated latency/loss |
| Resource Profile | 100% | Matches embedded devices |
| Failure Modes | 85% | Random failures |
| Security Surface | 100% | Same as real IoT |
| **Overall** | **90-95%** | Excellent for IDS validation |

## Next Steps for Development

| Step | Description | Status |
|------|-------------|--------|
| ~~LLM Integration~~ | ~~Connect Falco/Suricata to xAI Grok-4/OpenAI~~ | ✅ Done (Week 3) |
| ~~Auto-Response~~ | ~~Automatic pod isolation on threats~~ | ✅ Done (Week 3) |
| ~~IoT Endpoints~~ | ~~REST API for Raspberry Pi sensors~~ | ✅ Done (Week 4) |
| ~~Safety Controls~~ | ~~Protected services, caching, dry-run mode~~ | ✅ Done (Week 4) |
| Pi Hardware Setup | Connect physical Raspberry Pi 5 + PIR sensor | 🔄 Week 4-5 |
| Prometheus Metrics | Real-time metrics for Pi events | ⏳ Week 6 |
| Grafana Dashboard | Real-time visualization of alerts | ⏳ Week 7 |
| Stability Testing | Multi-scenario attack testing | ⏳ Week 8 |
| Demo Preparation | End-to-end workflow validation | ⏳ Week 9 |
| **Final Demo** | Live demonstration with all components | ⏳ Week 10 |

---

## Safety Controls (Added Week 4)

The IDS API includes safety controls to prevent accidental service disruption during demos:

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTOMATION_MODE` | `live` | `live`, `dry-run`, or `approval-required` |
| `PROTECTED_SERVICES` | `healthcare-api,ids-api,postgres` | Services that cannot be isolated |
| `ALERT_CACHE_TTL_SECONDS` | `60` | Cache duration for duplicate alerts |
| `ALERT_CACHE_MAX_SIZE` | `100` | Maximum cached alerts |

### Usage

```bash
# For safe demos (no actual pod isolation)
export AUTOMATION_MODE=dry-run

# Check current safety status
curl http://localhost:30800/api/safety
```

### Protected Services

Critical services are protected from automated actions:
- `healthcare-api` - Critical citizen health data
- `ids-api` - The IDS system itself
- `postgres` - Database

If an attack targets a protected service, the action is **logged but not executed**.
