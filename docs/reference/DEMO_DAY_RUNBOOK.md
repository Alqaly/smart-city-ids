# Demo Day Runbook (Examiner-Friendly)

Last updated: 2026-02-24

## Goal
Show a real Smart City IDS detecting attacks, analyzing alerts, and updating the dashboard in real time.

## Login
- Username: `admin`
- Password: `admin`

## 3-Minute Preflight (run before the examiner arrives)
```bash
bash scripts/pre-demo-check.sh
```

Expected result:
- `DEMO STATUS: READY`

If it fails:
- Read the failed line.
- Fix only that component (don’t restart everything unless needed).

## Demo Flow (Non-Technical Friendly)

### 1. Show the dashboard is live
- Open: `http://localhost:30800/ui`
- Login with `admin / admin`
- Explain:
  - This is a live IDS dashboard.
  - It receives alerts from runtime detection (Falco) and network detection (Suricata).
  - It uses LLM analysis and governance rules before automated actions.

### 2. Show system health quickly
- Point at:
  - Health / status panels
  - IoT inventory (`/api/iot/devices`: total, logical, pod-backed, counting mode)
  - Recent alert feed
  - Governance mode (`assisted`)

### 3. Run a real attack simulation (best demo moment)
```bash
bash scripts/run-live-attacks.sh --duration 30 --show-alerts 3
```

What to say while it runs:
- “This script generates real in-cluster attack behavior.”
- “Suricata sees network attacks; Falco sees suspicious runtime behavior.”
- “The IDS API ingests and counts the alerts live.”
- “This is not fake alert injection.”

### 4. Show evidence on dashboard
- Open Alerts tab
- Show new alerts arriving
- Show severity and source (`suricata` / `falco`)
- Show governance / action behavior (assisted mode)

### 5. Optional: Python verbose walkthrough (technical examiner)
```bash
python scripts/demo-e2e-pipeline.py --api-url http://localhost:30800 --duration 5 --skip-provider-tests
```

What it demonstrates:
- Health check
- LLM diagnostics
- Governance state
- Test alert submission
- Metrics updates

## Fast Recovery Commands (if something breaks)

### API/dashboard issue
```bash
bash scripts/deploy-code.sh
```

### Quick readiness re-check
```bash
bash scripts/pre-demo-check.sh
```

### If cluster issue
```bash
kubectl get pods -A
```

### If you need fresh alerts
```bash
bash scripts/run-live-attacks.sh --duration 10 --show-alerts 2
```

## What to Avoid During the Demo
- Don’t run long “full” test suites unless asked.
- Don’t wait on Prometheus/Grafana NodePort checks if dashboard + IDS are already working.
- Don’t test every LLM provider live (can hit quota/auth noise).
- Use `--skip-provider-tests` for Python verbose demo.

## Key Talking Points (Short, Accurate)
- Real detection sources: Falco + Suricata
- Real Kubernetes workloads and IoT pods
- Real-time dashboard updates
- Governance mode prevents unsafe auto-actions (`assisted`)
- `admin/admin` demo login is intentionally simplified for the defense
