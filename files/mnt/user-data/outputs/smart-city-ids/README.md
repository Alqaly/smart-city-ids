# 🛡️ Smart City IDS - AI-Powered Intrusion Detection System

## 📋 Overview

A sophisticated **Intrusion Detection System** for Smart Cities that uses **Large Language Models (LLMs)** to analyze security alerts and automatically respond to threats. Built on **Kubernetes (K3s)** for edge computing deployments.

### Problem We Solve

- Smart Cities have thousands of IoT devices vulnerable to cyberattacks
- Traditional IDS systems generate **alert fatigue** (too many alerts)
- Security operators miss real threats due to information overload
- **Our Solution**: AI-powered threat analysis and automated responses

### Key Features

✅ **AI-Powered Threat Analysis** - Uses Groq LLM to explain security events  
✅ **Kubernetes-Native** - Runs on K3s for edge computing  
✅ **Automated Responses** - Automatically isolates compromised services  
✅ **Real-time Monitoring** - Integrates with Falco & Prometheus  
✅ **Demo-Ready** - Includes attack simulators and vulnerable services  

---

## 🚀 Quick Start

### Prerequisites

- Linux/WSL environment
- Root access (for K3s)
- kubectl installed (or will be installed automatically)

### Installation & Startup

```bash
# 1. Navigate to project directory
cd smart-city-ids

# 2. Run the startup script
./scripts/start-everything.sh

# This will:
# - Install K3s if needed
# - Start the Kubernetes cluster
# - Create the smart-city namespace
# - Deploy all services
```

### Verify Setup

```bash
# Check cluster status
kubectl get nodes

# Check pods in the smart-city namespace
kubectl get pods -n smart-city

# Watch pods starting (press Ctrl+C to exit)
kubectl get pods -n smart-city -w
```

---

## 📊 System Architecture

```
┌─────────────────────────────────────────────────────┐
│            SMART CITY SERVICES                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────┐  │
│  │   Traffic    │  │  Healthcare  │  │ Parking  │  │
│  │   Camera     │  │     API      │  │ System   │  │
│  └──────────────┘  └──────────────┘  └──────────┘  │
└─────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│         KUBERNETES CLUSTER (K3s)                    │
│  ┌───────────────────────────────────────────────┐ │
│  │    IDS Application (AI Analysis)              │ │
│  │  - Collects alerts from Falco/Prometheus     │ │
│  │  - Analyzes with Groq LLM                    │ │
│  │  - Executes automated responses              │ │
│  └───────────────────────────────────────────────┘ │
│  ┌───────────────────────────────────────────────┐ │
│  │    Monitoring Stack                           │ │
│  │  - Falco (Security events)                   │ │
│  │  - Prometheus (Metrics)                      │ │
│  │  - Grafana (Dashboards)                      │ │
│  └───────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
                         │
                         ▼
                    🤖 Groq LLM
            (Threat Analysis Engine)
```

---

## 🏗️ Project Structure

```
smart-city-ids/
│
├── src/                          # IDS Application
│   ├── main.py                   # FastAPI server
│   ├── security_monitor.py       # Alert collection
│   ├── llm_engine.py             # LLM integration
│   └── k8s_automation.py         # Automated responses
│
├── smart-city-services/          # Vulnerable Demo Services
│   ├── traffic-camera/           # Traffic monitoring (5000)
│   ├── healthcare-api/           # Patient data (5001)
│   └── parking-system/           # Parking management (5002)
│
├── attack-simulator/             # Attack Tools
│   ├── ddos_simulator.py         # DDoS attacks
│   ├── data_exfiltration.py      # Data theft simulation
│   └── privilege_escalation.py   # Privilege escalation tests
│
├── k8s-manifests/                # Kubernetes Configs
│   ├── namespace.yaml            # Namespace definition
│   └── services-no-build.yaml    # Deployments & Services
│
├── scripts/                      # Utility Scripts
│   ├── start-everything.sh       # Main startup script
│   ├── run-all-attacks.sh        # Run demo attacks
│   └── cleanup.sh                # Stop everything
│
└── monitoring/                   # Monitoring Configs
    ├── falco/                    # Security rules
    ├── prometheus/               # Metrics collection
    └── grafana/                  # Dashboard configs
```

---

## 🔍 Smart City Services (Intentionally Vulnerable)

### 1. Traffic Camera Service 📹

**Purpose**: Manages traffic cameras across the city

**Endpoints**:
```
GET  /health                     ✅ Status check
GET  /api/cameras                ⚠️  VULNERABLE: No auth
GET  /api/analytics              ⚠️  VULNERABLE: No rate limiting
POST /admin/config               🚨 VULNERABLE: NO AUTH!
```

**How to Access**:
```bash
# Port-forward the service
kubectl port-forward -n smart-city svc/traffic-camera-service 8001:80

# In another terminal:
curl http://localhost:8001/health
curl http://localhost:8001/api/cameras
```

---

### 2. Healthcare API Service 🏥

**Purpose**: Manages patient data and prescriptions

**Endpoints**:
```
GET  /health                     ✅ Status check
GET  /api/patients               🚨 HIPAA VIOLATION: Exposes patient data
POST /api/prescriptions/{id}     ⚠️  VULNERABLE: No input validation
```

**How to Access**:
```bash
kubectl port-forward -n smart-city svc/healthcare-api-service 8002:80

# In another terminal:
curl http://localhost:8002/health
curl http://localhost:8002/api/patients
```

---

### 3. Parking System Service 🚗

**Purpose**: Manages parking lots and payments

**Endpoints**:
```
GET  /api/lots                   ✅ Available lots
POST /api/payment                🚨 VULNERABLE: Logs credit card data!
GET  /api/transactions           ⚠️  VULNERABLE: No auth, exposes payments
```

**How to Access**:
```bash
kubectl port-forward -n smart-city svc/parking-system-service 8003:80

# In another terminal:
curl http://localhost:8003/health
```

---

## 🎯 Running Attack Simulations

### DDoS Attack

```bash
# First, port-forward the traffic camera service
kubectl port-forward -n smart-city svc/traffic-camera-service 8001:80 &

# Run DDoS attack (20 threads, 30 seconds)
python3 attack-simulator/ddos_simulator.py http://localhost:8001/api/cameras 20 30
```

**What it does**:
- Sends 20 concurrent requests/threads
- Measures requests per second (RPS)
- Simulates real DDoS attack
- Reports success rate and errors

### Data Exfiltration Attack

```bash
# Port-forward all services
kubectl port-forward -n smart-city svc/traffic-camera-service 8001:80 &
kubectl port-forward -n smart-city svc/healthcare-api-service 8002:80 &
kubectl port-forward -n smart-city svc/parking-system-service 8003:80 &

# Run data exfiltration simulation
python3 attack-simulator/data_exfiltration.py http://localhost:8001

# Run against healthcare
python3 attack-simulator/data_exfiltration.py http://localhost:8002
```

**What it does**:
- Extracts camera data
- Attempts admin config modification
- Steals patient data (HIPAA violation)
- Exfiltrates payment transactions

---

## 📊 IDS Application API

### Check IDS Health

```bash
# Port-forward IDS
kubectl port-forward -n smart-city svc/ids-api-service 8004:5003 &

# Health check
curl http://localhost:8004/health
```

### Create Alert

```bash
curl -X POST http://localhost:8004/api/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "source": "Falco",
    "severity": "high",
    "service": "traffic-camera",
    "message": "Suspicious process execution detected"
  }'
```

### Get All Alerts

```bash
curl http://localhost:8004/api/alerts
```

### Analyze Alert with LLM

```bash
curl -X POST http://localhost:8004/api/analyze/1
```

### Get Dashboard Summary

```bash
curl http://localhost:8004/api/dashboard
```

### Simulate Alert (Mock Mode)

```bash
curl -X POST http://localhost:8004/api/simulate-alert
```

---

## 🛠️ Common kubectl Commands

### View Pods
```bash
# List all pods in smart-city namespace
kubectl get pods -n smart-city

# Watch pods in real-time
kubectl get pods -n smart-city -w

# Show detailed pod info
kubectl describe pod <pod-name> -n smart-city
```

### View Logs
```bash
# View pod logs
kubectl logs <pod-name> -n smart-city

# Follow logs (tail -f)
kubectl logs -f <pod-name> -n smart-city

# Show last 100 lines
kubectl logs --tail=100 <pod-name> -n smart-city
```

### Port Forwarding
```bash
# Forward local port to service
kubectl port-forward -n smart-city svc/<service-name> <local-port>:<remote-port>

# Example: Access traffic camera on localhost:8001
kubectl port-forward -n smart-city svc/traffic-camera-service 8001:80
```

### Debugging
```bash
# Execute command in pod
kubectl exec -it <pod-name> -n smart-city -- /bin/bash

# Check pod events
kubectl describe pod <pod-name> -n smart-city
```

---

## 🔧 Configuration

### .env File

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

**Key Settings**:

```
MOCK_MODE=true                    # true = Demo mode, false = Real Groq API
GROQ_API_KEY=your-api-key-here   # Get from https://console.groq.com
K8S_NAMESPACE=smart-city          # Kubernetes namespace
```

### Groq LLM Setup (Production Mode)

1. Sign up at [Groq Console](https://console.groq.com)
2. Create an API key
3. Set in `.env`:
   ```
   MOCK_MODE=false
   GROQ_API_KEY=your-actual-key
   ```

---

## 📈 Performance Monitoring

### Check Cluster Resource Usage
```bash
# View node resource usage
kubectl top nodes

# View pod resource usage
kubectl top pods -n smart-city
```

### Check Pod Startup
```bash
# Watch pods become ready
watch kubectl get pods -n smart-city

# Check specific pod status
kubectl describe pod traffic-camera-xyz -n smart-city
```

---

## 🧹 Cleanup & Shutdown

### Stop Cluster
```bash
# Kill K3s server
pkill -f "k3s server"

# Verify it's stopped
ps aux | grep k3s
```

### Clean Everything
```bash
# Run cleanup script (if available)
./scripts/cleanup.sh

# Or manual cleanup:
pkill -f "k3s server"
rm -rf /var/lib/rancher/k3s
```

---

## 🐛 Troubleshooting

### K3s Not Starting
```bash
# Check K3s logs
journalctl -u k3s.service -n 100

# If systemd not available, try:
k3s server &
```

### Pods Not Starting
```bash
# Check pod status and events
kubectl describe pod <pod-name> -n smart-city

# Check logs for errors
kubectl logs <pod-name> -n smart-city
```

### Services Not Accessible
```bash
# Verify service exists
kubectl get svc -n smart-city

# Check endpoints
kubectl get endpoints -n smart-city

# Test with port-forward
kubectl port-forward -n smart-city svc/<service> 8000:80
curl http://localhost:8000/health
```

### ConfigMap Not Updating
```bash
# Delete and recreate ConfigMap
kubectl delete configmap <config-name> -n smart-city

kubectl create configmap <config-name> \
  --from-file=smart-city-services/<service>/app.py \
  -n smart-city
```

---

## 🎓 Learning Resources

### Understanding the Architecture

1. **Kubernetes Concepts**
   - Pods: Smallest deployable units
   - Services: Network endpoints
   - Deployments: Scaling and updates
   - ConfigMaps: Configuration storage

2. **Security Concepts**
   - Alert fatigue: Too many alerts = missed threats
   - Intrusion Detection: Monitoring for attacks
   - Automated Response: Rapid threat mitigation
   - Edge Computing: Processing at the network edge

3. **LLM Integration**
   - Why LLMs for security? Better context understanding
   - Groq API: Fast, efficient inference
   - Prompt engineering: Structuring queries for better results

---

## 📝 Demo Scenarios

### Scenario 1: DDoS Detection & Response

1. Start monitoring
2. Run DDoS attack
3. IDS detects anomaly
4. LLM analyzes threat
5. System auto-mitigates

### Scenario 2: Data Exfiltration Prevention

1. Attacker attempts to extract patient data
2. Falco detects unauthorized access
3. LLM confirms HIPAA violation
4. Service automatically isolated
5. Incident logged and reported

### Scenario 3: Privilege Escalation Block

1. Attacker attempts to gain root access
2. Security events detected
3. LLM explains threat chain
4. Pod terminated, node cordoned
5. Alert sent to operators

---

## 🤝 Contributing

Ideas for enhancements:

- Add Prometheus monitoring integration
- Create Grafana dashboards
- Implement real-time Falco integration
- Add more sophisticated attack simulators
- Build operator dashboard UI
- Add machine learning anomaly detection

---

## 📞 Support

For issues or questions:

1. Check the troubleshooting section
2. Review pod logs: `kubectl logs <pod> -n smart-city`
3. Describe resources: `kubectl describe pod <pod> -n smart-city`
4. Check service connectivity with port-forward

---

## 📄 License

This project is for educational purposes demonstrating:
- Kubernetes container orchestration
- Security monitoring and response
- LLM integration in security systems
- Edge computing for Smart Cities

---

**Last Updated**: November 3, 2025  
**Version**: 1.0.0  
**Environment**: Kubernetes (K3s) on Linux/WSL
