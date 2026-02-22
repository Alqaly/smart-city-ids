# Smart City IDS — Scripts Reference

Complete guide to all scripts in the Smart City IDS project.

## 🚀 Quick Start Commands

```bash
# Start everything (K3s + all services)
./scripts/start-everything.sh

# Check LLM credits before running attacks
./scripts/llm-manager.sh credits

# Run LIVE attacks (real traffic; no synthetic injection)
./scripts/run-live-attacks.sh --duration 30

# Deploy code changes
./scripts/deploy-code.sh
```

---

## 📋 Script Overview

### Main Control Scripts

| Script | Purpose | Key Features |
|--------|---------|--------------|
| `start-everything.sh` | Full cluster deployment | K3s setup, LLM credit check, auto port-forward |
| `llm-manager.sh` | LLM provider control | Interactive menu, credit monitoring, provider switching |
| `run-live-attacks.sh` | Security testing | LIVE attacks only (real traffic; no synthetic injection) |
| `deploy-code.sh` | Code deployment | Docker build, health checks, LLM status |
| `demo-day.sh` | Demo automation | One-command demo setup |
| `cleanup.sh` | Cluster cleanup | Safe teardown, data preservation |

---

## 🔧 LLM Manager (`llm-manager.sh`)

Interactive tool for controlling LLM providers and monitoring credits.

### Usage

```bash
# Interactive menu (default)
./scripts/llm-manager.sh

# Check credit status
./scripts/llm-manager.sh credits

# Show all provider status
./scripts/llm-manager.sh status

# Force specific provider
./scripts/llm-manager.sh force xai
./scripts/llm-manager.sh force gemini

# Set priority order
./scripts/llm-manager.sh priority xai,openai,gemini

# Restore auto failover
./scripts/llm-manager.sh auto

# Test LLM with specific provider
./scripts/llm-manager.sh test xai
```

### Interactive Menu Options

1. **Show Status & Credits** — Display all provider configuration and balances
2. **Check Credit Balances** — Verify sufficient credits before attacks
3. **Set Provider Priority** — Change the failover order
4. **Force Specific Provider** — Use only one provider (disables failover)
5. **Restore Auto Failover** — Return to default priority chain
6. **Test LLM Analysis** — Send test alert and verify response
7. **Show Configuration** — Display all settings and API keys

---

## 🎯 Live Attack Runner (`run-live-attacks.sh`)

Runs LIVE attacks only (real HTTP traffic against the running Smart City services).
There is no synthetic alert injection.

### Usage

```bash
# Run a full live suite (all attacks)
./scripts/run-live-attacks.sh --duration 30

# Run a specific live attack
./scripts/run-live-attacks.sh --service traffic-camera --attack ddos --duration 30
```

---

## 🚀 Deployment (`deploy-code.sh`)

Deploys code changes to the Kubernetes cluster.

### Usage

```bash
# Standard deployment (Docker build + restart)
./scripts/deploy-code.sh

# Show current status
./scripts/deploy-code.sh --status

# Check LLM provider status
./scripts/deploy-code.sh --llm-status

# Check credits
./scripts/deploy-code.sh --credits
```

### What It Does

1. Validates source files exist
2. Checks LLM provider health and credits
3. Builds Docker image with current source
4. Imports image into K3s
5. Restarts pods
6. Waits for readiness
7. Verifies health endpoint

---

## 🌟 Start Everything (`start-everything.sh`)

Complete system deployment from scratch.

### Phases

1. **K3s Installation** — Install if not present
2. **Cleanup** — Stop existing K3s processes
3. **K3s Startup** — Start fresh cluster
4. **Namespace & Services** — Deploy all K8s manifests
5. **Falco Security** — Deploy runtime security
6. **IoT Emulation** — Start device simulators
7. **Service Readiness** — Wait for all pods
8. **Health Check** — Verify system status
9. **LLM Status** — Check providers and credits ⭐ *NEW*
10. **Port Forwarding** — Setup local access

### Features

- **Automatic LLM Credit Check** — Verifies sufficient credits before starting
- **Provider Status Display** — Shows all configured LLM providers
- **Persistent KUBECONFIG** — Automatically configures kubeconfig
- **Port-forwarding** — Sets up localhost access

---

## 📊 Demo Day (`demo-day.sh`)

Automated demo setup and execution.

```bash
# Full demo setup
./scripts/demo-day.sh

# Minimal profile (faster)
./scripts/demo-day.sh --profile minimal

# With attacks
./scripts/demo-day.sh --with-attacks
```

---

## 🧹 Cleanup (`cleanup.sh`)

Safely teardown the cluster.

```bash
# Full cleanup (removes everything)
./scripts/cleanup.sh

# Keep data volumes
./scripts/cleanup.sh --keep-data

# Stop only (don't delete)
./scripts/cleanup.sh --stop-only
```

---

## 🔍 Check Setup (`check-setup.sh`)

Verify prerequisites before deployment.

```bash
./scripts/check-setup.sh
```

Checks:
- K3s installation
- Docker availability
- API keys configured
- Kubernetes connectivity
- Required ports

---

## 📚 Shared Library (`lib/llm-control.sh`)

Reusable functions for LLM management. Source in your own scripts:

```bash
source "$(dirname "$0")/lib/llm-control.sh"

# Now use:
llm_check_credits         # Verify credits
llm_show_provider_table   # Display status
llm_set_priority "xai"    # Change priority
llm_force_provider "xai"  # Force provider
llm_test_provider         # Test LLM
```

### Available Functions

| Function | Purpose |
|----------|---------|
| `llm_check_api()` | Test IDS API connectivity |
| `llm_get_status()` | Get LLM provider status |
| `llm_get_credits()` | Get credit balances |
| `llm_check_credits()` | Verify sufficient credits |
| `llm_show_provider_table()` | Display formatted table |
| `llm_set_priority()` | Set provider priority |
| `llm_force_provider()` | Force specific provider |
| `llm_test_provider()` | Send test alert |
| `llm_show_config()` | Show all configuration |

---

## 💡 Best Practices

### Before Running Attacks

1. **Check Credits First**
   ```bash
   ./scripts/llm-manager.sh credits
   ```

2. **Verify Provider Status**
   ```bash
   ./scripts/llm-manager.sh status
   ```

3. **Force Provider if Needed**
   ```bash
   ./scripts/llm-manager.sh force gemini  # Use Gemini only
   ```

### During Development

1. **Deploy Code Changes**
   ```bash
   ./scripts/deploy-code.sh
   ```

2. **Check Status**
   ```bash
   ./scripts/deploy-code.sh --status
   ./scripts/llm-manager.sh status
   ```

### For Demos

1. **Full Reset**
   ```bash
   ./scripts/cleanup.sh
   ./scripts/start-everything.sh
   ```

2. **Automated Demo**
   ```bash
   ./scripts/demo-day.sh --with-attacks
   ```

---

## 🔧 Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `IDS_API_URL` | `http://localhost:30800` | IDS API endpoint |
| `LLM_PRIORITY` | `kimi,xai,anthropic,openai,gemini` | Provider failover order |
| `XAI_API_KEY` | — | xAI Grok API key |
| `OPENAI_API_KEY` | — | OpenAI API key |
| `ANTHROPIC_API_KEY` | — | Anthropic Claude key |
| `GEMINI_API_KEY` | — | Google Gemini key |
| `KIMI_API_KEY` | — | Moonshot Kimi key |
| `ATTACK_DELAY` | `4` | Seconds between attacks |
| `CREDIT_WARNING_THRESHOLD` | `10.0` | Low credit warning level |
| `CREDIT_CRITICAL_THRESHOLD` | `2.0` | Critical credit level |

---

## 🐛 Troubleshooting

### LLM Credits Exhausted

```bash
# Check status
./scripts/llm-manager.sh credits

# Switch to provider with credits
./scripts/llm-manager.sh force gemini

# Generate live detections (no synthetic injection)
./scripts/run-live-attacks.sh --duration 20
```

### API Not Available

```bash
# Check if IDS API is running
./scripts/deploy-code.sh --status

# Check K3s status
kubectl get pods -A

# Restart port-forwarding
./scripts/start-everything.sh  # (re-runs port-forward setup)
```

### Provider Not Working

```bash
# Test specific provider
./scripts/llm-manager.sh test xai

# Check provider configuration
./scripts/llm-manager.sh config

# View detailed status
./scripts/llm-manager.sh status
```

---

## 📞 Support

For issues or questions:
1. Check the [main project README](../README.md)
2. Run `./scripts/check-setup.sh` for diagnostics
3. Check logs: `kubectl logs -n smart-city -l app=ids-api`
