# 🛡️ Smart City IDS - Installation on Kali Linux

## ✅ Quick Install (3 Steps)

### Step 1: Download the Setup Script

Download this file to your Kali machine:
```
setup-smart-city-ids.sh
```

### Step 2: Run the Setup Script

```bash
# Make it executable
chmod +x setup-smart-city-ids.sh

# Run it
./setup-smart-city-ids.sh
```

This will automatically create the entire project structure with all files!

### Step 3: Start Using It

```bash
cd ~/smart-city-ids
pip3 install -r requirements.txt
./scripts/start-everything.sh
```

## 📁 What Gets Created

The script creates in your home directory:

```
~/smart-city-ids/
├── src/main.py                    ← IDS Application
├── smart-city-services/           ← 3 Services
│   ├── traffic-camera/app.py
│   ├── healthcare-api/app.py
│   └── parking-system/app.py
├── attack-simulator/              ← Attack Tools
│   ├── ddos_simulator.py
│   └── data_exfiltration.py
├── k8s-manifests/                 ← Kubernetes
│   └── namespace.yaml
├── scripts/                       ← Automation
│   ├── start-everything.sh
│   ├── run-all-attacks.sh
│   └── cleanup.sh
├── QUICKSTART.md                  ← Read this!
├── requirements.txt
└── .env.example
```

## 🚀 After Installation

### Read First
```bash
cat ~/smart-city-ids/QUICKSTART.md
```

### Install Dependencies
```bash
pip3 install -r requirements.txt
```

### Start K3s Cluster
```bash
cd ~/smart-city-ids
./scripts/start-everything.sh
```

### Run Attacks
```bash
./scripts/run-all-attacks.sh
```

### View Pods
```bash
kubectl get pods -n smart-city
kubectl get pods -n smart-city -w  # Watch live
```

## 📋 Requirements

- Kali Linux (or any Linux distro)
- Python 3.9+
- Internet connection (for K3s download)
- ~2GB RAM minimum
- ~500MB disk space

## ⚠️ If You Don't Have K3s/kubectl

The setup script will try to auto-install them. If that fails:

```bash
# Install K3s
curl -sfL https://get.k3s.io | sh -

# K3s includes kubectl, it's available as:
k3s kubectl get nodes
```

## 🎯 Common Commands After Setup

```bash
# Start everything
./scripts/start-everything.sh

# Check pods
kubectl get pods -n smart-city

# Watch pods live
kubectl get pods -n smart-city -w

# View logs
kubectl logs -f <pod-name> -n smart-city

# Port forward a service
kubectl port-forward -n smart-city svc/traffic-camera-service 8001:80 &

# Test a service
curl http://localhost:8001/health

# Run attacks
./scripts/run-all-attacks.sh

# Clean up
./scripts/cleanup.sh
```

## 🔧 Troubleshooting

### K3s won't start
```bash
pkill -f "k3s server"
./scripts/start-everything.sh
```

### Permission denied on scripts
```bash
chmod +x scripts/*.sh
```

### kubectl not found
```bash
# K3s installs kubectl as:
alias kubectl='k3s kubectl'

# Or use full path:
/usr/local/bin/k3s kubectl get pods
```

### Pods won't start
```bash
kubectl describe pod <pod-name> -n smart-city
kubectl logs <pod-name> -n smart-city
```

## ✨ What You Get

- ✅ Complete IDS application
- ✅ 3 vulnerable services for demo
- ✅ DDoS & data exfiltration simulators
- ✅ Kubernetes deployment
- ✅ Automation scripts
- ✅ 5+ attack scenarios

## 📚 Learn More

After setup, read:

1. **QUICKSTART.md** - 5-minute guide
2. **README.md** - Complete reference (when created)
3. **INSTALLATION_GUIDE.txt** - Detailed setup

## 🎉 That's It!

Once setup completes, you have a production-ready Smart City IDS system ready to:
- Deploy
- Demonstrate
- Test
- Learn from

Happy hacking! 🚀

---

**Questions?** Run the setup script - it creates everything automatically!
