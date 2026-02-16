# Development Guide — Smart City IDS

How to modify, test, and deploy code changes.

---

## Prerequisites

- **K3s** running on the node (`/etc/rancher/k3s/k3s.yaml` accessible)
- **Python 3.10+** with pip
- At least one LLM API key (`XAI_API_KEY`, `OPENAI_API_KEY`, etc.) — or use the local fallback engine with no key
- `kubectl` configured (`export KUBECONFIG=/etc/rancher/k3s/k3s.yaml`)
- `jq` for JSON processing in scripts

---

## Project Layout

```
services/ids-api/src/       Core IDS application (Python, FastAPI)
services/ids-api/static/    Operator dashboard (HTML/JS SPA)
services/forwarders/        Falco and Suricata alert forwarders
smart-city-services/        Intentionally vulnerable IoT apps (Flask)
k8s-manifests/              All Kubernetes manifests
scripts/                    Deployment, attack, and utility scripts
attack-simulator/           Standalone attack tools (Python)
attack-simulations/         Shell-based attack scripts
tests/                      Test suite (pytest)
docs/                       Technical documentation
config/                     Prometheus ServiceMonitor + sidecar configs
infrastructure/             Database and monitoring configs
```

---

## Running Locally (Outside K8s)

```bash
# Set at least one LLM key (or skip for local-only mode)
export XAI_API_KEY="xai-..."

# Create virtualenv and install dependencies
cd services/ids-api/src
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Start the API
uvicorn main:app --host 0.0.0.0 --port 8000

# Dashboard: http://localhost:8000/ui
# Health:    http://localhost:8000/health
```

Without any API key, the system uses only the local fallback engine (11 rule patterns, zero cost).

---

## Deploying to K3s

The project uses a **Docker-free deploy** pattern — code is mounted into pods via ConfigMaps. No container registry required.

### Full Cluster Setup

```bash
./scripts/start-everything.sh
```

This script:
1. Creates namespaces (smart-city, monitoring, falco-system)
2. Creates ConfigMaps from source files
3. Applies all K8s manifests
4. Waits for pods to be ready
5. Deploys Falco via Helm

### Code-Only Deploy (After Changes)

```bash
./scripts/deploy-code.sh
```

This script:
1. Deletes existing ConfigMaps for IDS API and forwarders
2. Recreates ConfigMaps from current source files on disk
3. Deletes pods to trigger re-pull of ConfigMap data
4. Waits for new pods to reach Ready state
5. Reports deployment status

Use `deploy-code.sh` after editing any file in `services/ids-api/src/`, `services/ids-api/static/`, or `services/forwarders/`.

### Deploying IoT Service Changes

IoT service code lives in `smart-city-services/<service>/app.py`. To deploy changes:

```bash
# Delete and recreate the ConfigMap
kubectl delete configmap <service>-code -n smart-city
kubectl create configmap <service>-code \
  --from-file=app.py=smart-city-services/<service>/app.py \
  -n smart-city

# Restart pods
kubectl delete pods -l app=<service> -n smart-city
```

---

## Code Architecture

### Main Application (main.py)

The FastAPI app initializes on startup:

1. Load configuration from environment (`config.py`)
2. Initialize database (PostgreSQL or memory fallback)
3. Create LLM manager with all configured providers
4. Initialize K8s automation client
5. Create governance controller
6. Start rate limiter, deduplicator, circuit breakers
7. Restore Prometheus counters from database
8. Register all route handlers

**Key entry point for alerts:** the `process_alert_pipeline()` function (called by both `/api/alerts` and `/api/alerts/internal`) handles the full flow: rate limit → dedup → LLM → governance → K8s action → persist.

### Adding a New LLM Provider

1. Create `services/ids-api/src/llm_engine_<name>.py` extending `BaseLLMEngine`
2. Implement `analyze_alert(alert_data: dict) -> dict` — must return the standard response schema
3. Register the engine in `llm_manager.py` (`ALL_PROVIDERS` list and initialization logic)
4. Add `<NAME>_API_KEY` to `config.py`
5. Add to `LLM_PRIORITY` default order
6. Deploy: `./scripts/deploy-code.sh`

### Adding a New K8s Automation Action

1. Add method to `k8s_automation.py`
2. Register the action name in `main.py`'s action dispatch (the `if action == "..."` block)
3. Add to `operator_models.py` `ActionType` enum
4. Update governance controller if the action needs approval logic
5. Add Prometheus counter if tracking is needed

### Adding a New API Endpoint

1. Add route handler in `main.py`
2. Add Pydantic models to `operator_models.py` if needed
3. Choose auth: wrap with `Depends(api_key_dependency)` for JWT-protected, or leave open
4. Add to the UI if user-facing (edit `static/index.html`)

---

## Testing

```bash
cd services/ids-api/src
source venv/bin/activate
pip install pytest pytest-asyncio httpx

# Run all tests
pytest -q

# Run specific test file
pytest tests/test_llm_parsing.py -v
```

### What to Test

| Area | How | Mock |
|---|---|---|
| LLM response parsing | Unit test JSON extraction and fallback | No mock needed (pure parsing) |
| K8s automation | Unit test action methods | Mock `kubernetes.client` |
| Alert rate limiter | Unit test window enforcement | No mock needed |
| Governance decisions | Unit test mode logic | No mock needed |
| API endpoints | Integration test with `httpx.AsyncClient` | Mock LLM + K8s |

### Example Test

```python
import pytest
from llm_engine_xai import XAIEngine

def test_parse_json_response():
    """LLM response with JSON fences should parse correctly."""
    raw = '```json\n{"severity": 8, "summary": "test", "threat_type": "Malware"}\n```'
    result = XAIEngine._parse_response(raw)
    assert result["severity"] == 8
    assert result["threat_type"] == "Malware"

def test_parse_fallback():
    """Unparseable response should return conservative fallback."""
    raw = "I cannot analyze this alert."
    result = XAIEngine._parse_response(raw)
    assert result["severity"] == 5
    assert result["threat_type"] == "Policy Violation"
```

---

## Debugging

### Pod Logs

```bash
# IDS API logs
kubectl logs -l app=ids-api -n smart-city --tail=100 -f

# Falco forwarder logs
kubectl logs -l app=falco-forwarder -n falco-system --tail=50 -f

# Suricata forwarder logs
kubectl logs -l app=suricata-forwarder -n monitoring --tail=50 -f
```

### Common Issues

| Problem | Cause | Fix |
|---|---|---|
| IDS API pods CrashLoopBackOff | Missing Python dependencies | Check `requirements.txt`, ensure ConfigMap has all source files |
| LLM returns "fallback analysis" | API key expired/invalid, circuit breaker open | Check `/health` → `llm_providers`, reset circuit breakers |
| K8s automation does nothing | Wrong KUBECONFIG, RBAC missing | `export KUBECONFIG=/etc/rancher/k3s/k3s.yaml`, check pod service account |
| Falco not forwarding | Forwarder can't reach IDS API | Check service DNS, `kubectl get svc -n smart-city` |
| Dashboard shows stale data | Browser cache | Hard refresh, check if pods are running |
| Rate limiter blocking everything | Thresholds too low for attack reproduction | Reset via `/api/rate-limiter/reset` or adjust env vars |
| PostgreSQL unavailable | Pod not ready, wrong connection string | Check `kubectl get pods -n smart-city`, verify `DATABASE_URL` |

### Health Check

```bash
# Quick system check
curl -s http://localhost:30800/health | jq .

# Check LLM providers (needs auth)
TOKEN=$(curl -s -X POST http://localhost:30800/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"operator","password":"operator"}' | jq -r .access_token)
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:30800/api/llm/status | jq .

# Check rate limiter
curl -s http://localhost:30800/api/rate-limiter/status | jq .

# Check circuit breakers
curl -s http://localhost:30800/api/circuit-breaker/status | jq .
```

### Smoke Test

```bash
# Send a test alert and verify full pipeline
curl -s -X POST http://localhost:30800/api/alerts/internal \
  -H "Content-Type: application/json" \
  -d '{
    "output": "Shell spawned in container",
    "priority": "Warning",
    "rule": "Terminal shell in container",
    "time": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
    "output_fields": {"container.name": "traffic-camera-test", "proc.cmdline": "/bin/bash"}
  }' | jq .
```

---

## Scripts Reference

| Script | Purpose |
|---|---|
| `scripts/start-everything.sh` | Full cluster deploy (namespaces → ConfigMaps → manifests → Falco) |
| `scripts/deploy-code.sh` | Quick code deploy (ConfigMap update + pod restart) |
| `scripts/attack-iot-pipeline.sh` | 12 real attack scenarios through full IDS pipeline |
| `attack-simulations/ids-demo-showcase.sh` | Guided demo walkthrough |
| `attack-simulations/generate-security-events.sh` | Generate Falco-style security events |
| `attack-simulations/generate-network-attacks.sh` | Generate network attack patterns |
| `attack-simulations/generate-advanced-attacks.sh` | Generate advanced multi-stage attacks |
| `attack-simulator/ddos_simulator.py` | Multi-threaded DDoS flood tool |
| `attack-simulator/data_exfiltration.py` | Data exfiltration simulator |
| `attack-simulator/privilege_escalation.py` | Privilege escalation simulator |

---

## Conventions

- **Do not remove** intentional vulnerabilities in `smart-city-services/` — they are the detection targets
- **Protected services** (`healthcare-api`, `ids-api`, `postgres`) are never auto-isolated
- **All external access** uses `localhost` NodePorts (30800, 30300, 31106) — no IP dependency
- **LLM response parsing** always has a fallback (severity 5, "Policy Violation") — never crashes on bad LLM output
- **ConfigMap-based deploys** — no Docker builds, no container registry, edit source files and run `deploy-code.sh`
- Update `docs/` when changing architecture, thresholds, or API contracts
