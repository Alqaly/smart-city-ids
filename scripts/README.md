# Scripts Guide - Smart City IDS

This directory contains shell scripts for deploying, managing, and testing the Smart City IDS system.

---

## Use These 4 Scripts (Canonical)

You have many scripts. For demo day, use this minimal set only:

1. `scripts/demo-day.sh --profile minimal --runs 1`
2. `scripts/one-command-ready.sh`
3. `scripts/check-system.sh`
4. `scripts/cleanup.sh` (after demo if needed)

This avoids confusion and keeps the flow predictable.

---

## One-Command Run

For demo/meeting use (full consolidated flow):

```bash
bash scripts/demo-day.sh --profile minimal --runs 1
```

For quick bootstrap only:

```bash
bash scripts/one-command-ready.sh
```

`one-command-ready.sh` now starts/validates local port-forwards directly.

---

## Production Deployment Scripts

### 🚀 **deploy.sh** (Main Entry Point)
The primary one-click deployment script. Orchestrates the entire setup process.

**Usage:**
```bash
./deploy.sh [OPTIONS]
```

**Options:**
- `--skip-k3s` - Skip K3s installation (if already installed)
- `--skip-build` - Skip Docker image building  
- `--skip-monitoring` - Skip Prometheus/Grafana deployment
- `--clean` - Clean up existing deployment first
- `--help` - Show help message

**What it does:**
1. ✅ Checks prerequisites (Docker, kubectl, curl, git, sudo)
2. ✅ Configures environment (API keys, defaults)
3. ✅ Installs/checks K3s Kubernetes
4. ✅ Builds Docker images (calls `build-images.sh`)
5. ✅ Deploys K8s manifests (IDS API, services, MQTT, IoT simulator)
6. ✅ Deploys monitoring stack (Prometheus, Grafana)
7. ✅ Verifies deployment and shows access URLs

**Time:** ~5-10 minutes (K3s install) + 2-3 minutes (images+deployment)

**Example:**
```bash
export XAI_API_KEY="your-xai-key"  # or OPENAI_API_KEY
./deploy.sh
```

---

### 🔨 **scripts/build-images.sh**
Builds Docker images from Dockerfiles. Auto-detects and uses available runtime (Docker, nerdctl, or K3s containerd).

**Usage:**
```bash
./scripts/build-images.sh
```

**What it builds:**
- `smart-city-ids/ids-api:latest` - IDS API service
- `smart-city-ids/smart-city-service:latest` - Demo IoT services (traffic camera, healthcare, parking)
- `smart-city-ids/forwarder:latest` - Falco alert forwarder

**Called by:** `deploy.sh` (Step 4)

**Note:** Images are imported into K3s containerd for instant access without Docker Hub.

---

### 🧹 **scripts/cleanup.sh**
Completely removes all Smart City IDS resources from the cluster.

**Usage:**
```bash
./scripts/cleanup.sh
```

**What it does:**
- Stops port forwards
- Deletes K8s namespaces (smart-city, monitoring)
- Stops K3s server
- Optionally removes K3s data directory

**When to use:** Before redeploying or shutting down

---

### ✅ **scripts/check-system.sh**
Health check script that shows current system status and access URLs.

**Usage:**
```bash
./scripts/check-system.sh
```

**Shows:**
- Pod status across namespaces
- Service endpoints and URLs
- Database status
- Access credentials (Grafana, etc.)

**When to use:** After deployment, to verify everything is running

---

## Monitoring & Dashboard Scripts

### 📊 **scripts/load-dashboards.sh**
Loads pre-built Grafana dashboards after deployment.

**Usage:**
```bash
./scripts/load-dashboards.sh
```

**Called by:** `deploy.sh` (Step 6)

---

## Demo & Testing Scripts

### 🎓 **scripts/demo.sh** or **demos/demo.sh**
Proof-of-concept demonstration showing real detection, analysis, and response.

**Usage:**
```bash
./scripts/demo.sh
# or from demos folder:
./scripts/demos/demo.sh
```

**Demonstrates:**
- Falco rule detection (syscall monitoring)
- Alert forwarding to IDS API
- LLM analysis (xAI Grok or OpenAI)
- Kubernetes automation (pod isolation)
- Prometheus metrics (attacks counted)

**Time:** ~3-5 minutes

---

### 🎓 **demos/phase4-run-smart-city-attacks.sh**
Phase 4 attack simulation suite.

**Usage:**
```bash
./scripts/demos/phase4-run-smart-city-attacks.sh
```

---

### 🎓 **demos/capstone1-demo.sh** & **capstone1-live-view.sh**
Capstone project specific demonstrations (archived).

---

### 🧪 **scripts/scalability-test.sh**
Tests horizontal scaling of IDS API under load.

**Usage:**
```bash
./scripts/scalability-test.sh
```

---

## Prerequisite Checks

### 📋 **scripts/check-setup.sh**
Quick environment check before running `deploy.sh`.

**Usage:**
```bash
./scripts/check-setup.sh
```

**Checks:**
- Required commands: python, pip, kubectl, docker, git
- K8s cluster access
- LLM API key environment variables
- Database URL configuration

**Note:** `deploy.sh` includes comprehensive prerequisite checking, so this script is mainly for manual verification.

---

## Archive & Legacy Scripts

### 📦 **scripts/archive/**
Old scripts from previous development phases. Not part of current deployment.

### 📦 **scripts/db/**
Database initialization and migration scripts.

---

## Quick Start

### First Time Deployment (Recommended)
```bash
# 1. Set your API key
export XAI_API_KEY="your-key"  # or OPENAI_API_KEY

# 2. Run one-click deployment
./deploy.sh

# 3. Check status
./scripts/check-system.sh
```

### Manual K3s Startup (Advanced)
If you need to restart K3s separately:
```bash
# Stop and restart K3s, redeploy services
./scripts/start-everything.sh

# Or use deploy.sh with specific steps
./deploy.sh --skip-k3s --skip-build --clean
```

### Demo & Testing
```bash
# Run attack proof demo
./scripts/demo.sh

# Check system health
./scripts/check-system.sh

# View logs
kubectl logs -n smart-city -l app=ids-api -f
```

### Cleanup
```bash
# Remove all resources
./scripts/cleanup.sh
```

---

## Script Dependencies

```
deploy.sh (Main)
├── build-images.sh
├── k8s-manifests/*.yaml
├── load-dashboards.sh
└── cleanup.sh (user runs manually)

scripts/start-everything.sh (Alternative K3s startup)
├── K3s installation
└── k8s-manifests/*.yaml

demo.sh
├── attack-simulator/
└── kubectl commands

check-system.sh
└── kubectl commands
```

---

## Troubleshooting

### Deploy Fails
```bash
# Check what failed
tail -50 /tmp/k3s.log          # K3s logs
kubectl get events -A          # K8s events
docker images | grep smart-city # Built images?
```

### Pods Not Starting
```bash
# View pod logs
kubectl logs -n smart-city <pod-name>

# Describe pod for errors
kubectl describe pod -n smart-city <pod-name>

# Check image availability
k3s ctr images list
```

### Port Conflicts
```bash
# K3s uses port 6443
lsof -i :6443

# IDS API uses port 30800
lsof -i :30800
```

---

## Environment Variables

**Required for deployment:**
- `XAI_API_KEY` - xAI Grok-4 API key (preferred)
- `OPENAI_API_KEY` - OpenAI GPT-4 API key (fallback if XAI not set)

**Optional:**
- `K8S_NAMESPACE` - Kubernetes namespace (default: smart-city)
- `POSTGRES_USER` - Database user (default: idsuser)
- `POSTGRES_PASSWORD` - Database password (default: idspassword)
- `POSTGRES_DB` - Database name (default: idsdb)

**Set via:**
```bash
# Inline
export XAI_API_KEY="..." && ./deploy.sh

# Or in .env file (will be sourced by deploy.sh)
cp .env.example .env
# Edit .env with your values
./deploy.sh
```

---

## Performance Notes

### Pod Startup Time
With pre-built Docker images:
- **Expected:** 5-10 seconds per pod
- **Achieved:** ~5 seconds (vs 60-120 seconds with runtime pip install)

### Full Deployment Time
- K3s installation: 2-5 minutes (first time only)
- Docker image build: 3-5 minutes
- K8s manifests deployment: 30-60 seconds
- Monitoring stack: 1-2 minutes
- **Total first time:** ~10-15 minutes
- **Subsequent:** 2-3 minutes (skip K3s install)

---

## Contributing

When adding new scripts:
1. Follow bash best practices (use `set -euo pipefail`)
2. Add descriptive comments and usage documentation
3. Use consistent color/logging functions from `deploy.sh`
4. Test for common environments (Ubuntu 20.04+, CentOS, etc.)
5. Update this README with script description and usage

---

For detailed architecture and implementation, see [docs/README.md](../docs/README.md)
