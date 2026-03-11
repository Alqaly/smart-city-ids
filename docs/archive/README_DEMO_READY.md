# Smart City IDS - Demo Ready Documentation

> Use the current validated runbook/checklist for the examiner demo:
> - `docs/reference/DEMO_DAY_RUNBOOK.md`
> - `docs/reference/DEMO_QA_CHECKLIST.md`
> - `docs/reference/DEMO_SCRIPT_VALIDATION_REPORT_2026-02-24.md`
>
> Demo login is now: `admin / admin`

## Quick Start (For Demo)

```bash
# 1. Access Dashboard
open http://localhost:30800/ui

# 2. Run readiness check
bash scripts/demo-readiness.sh

# 3. Run live attack demo
bash scripts/run-live-attacks.sh --duration 30
```

## System Status

| Component | Status | Details |
|-----------|--------|---------|
| Dashboard | ✅ LIVE | http://localhost:30800/ui |
| Database | ✅ Connected | PostgreSQL |
| K8s Cluster | ✅ Connected | K3s |
| IoT Devices | ✅ 13 pods | Cameras, sensors, APIs |
| LLM Providers | ✅ 5/5 | Kimi, xAI, Anthropic, OpenAI, Gemini |
| Falco | ✅ Enabled | Runtime detection |
| Suricata | ✅ Enabled | Network detection |

## Current Metrics

- **Total Alerts**: 6,577+ processed
- **IoT Devices**: 13 monitored
- **LLM Calls Today**: 0 (pod restarted, stats reset)
- **Governance Mode**: Assisted
- **Pipeline Status**: All GREEN

## Demo Flow

### 1. Overview Tab
Shows system health, pipeline status, recent alerts.

### 2. LLM Control Tab
- Provider health status (all operational)
- Failover chain visualization
- Cost tracking ($0.006/1K tokens for Kimi)
- Provider comparison

### 3. Live Attack
```bash
bash scripts/run-live-attacks.sh --duration 30
```
- Real SQL injection attacks
- Suricata detects → LLM analyzes → Actions triggered
- Watch alerts appear in dashboard

### 4. Automation Tab
- Mode selection: Manual/Assisted/Autonomous
- Pending actions queue
- Execution metrics

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│  Suricata   │────→│   IDS API    │────→│  PostgreSQL  │
│  (network)  │     │   (FastAPI)  │     │  (storage)   │
└─────────────┘     └──────────────┘     └──────────────┘
                           │
┌─────────────┐           ↓              ┌──────────────┐
│   Falco     │────→  LLM Analysis  ←────│   5 Providers│
│  (runtime)  │     │  (failover)   │    │   (Kimi→...) │
└─────────────┘     └──────────────┘     └──────────────┘
                           │
                           ↓
                    ┌──────────────┐
                    │  Governance  │
                    │Manual/Assisted│
                    └──────────────┘
                           │
                           ↓
                    ┌──────────────┐
                    │ K8s Actions  │
                    │isolate/scale │
                    └──────────────┘
```

## Key Files

| File | Purpose |
|------|---------|
| `DEMO_CHEAT_SHEET.md` | Full demo script |
| `services/ids-api/static/index.html` | Dashboard UI |
| `scripts/run-live-attacks.sh` | Attack simulator |
| `scripts/demo-readiness.sh` | Pre-flight check |

## How It Works

### Alert Processing
1. Suricata/Falco detect threats
2. Forwarders send to IDS API
3. Deduplication cache checks (300s TTL)
4. LLM analyzes severity (1-10)
5. Governance decides auto/manual action
6. K8s executes (isolate pod, scale up)
7. All logged to PostgreSQL

### LLM Failover
```
Priority: kimi → xai → anthropic → openai → gemini

If Kimi fails:
  1. Try xAI
  2. If xAI fails, try Anthropic
  3. Continue until success or exhaustion

Cooldown: 15min after auth/quota errors
```

### Add / Replace LLM API Key (During Demo Prep)

If the LLM Control tab shows providers as failed/circuit-open:

1. Update `.env` with the new key (`KIMI_API_KEY`, `OPENAI_API_KEY`, etc.)
2. Sync secret + restart IDS API:
```bash
bash scripts/apply-llm-env-to-k8s-secret.sh
bash scripts/deploy-code.sh
```
3. Reset provider states and test Kimi:
```bash
TOKEN=$(curl -s http://localhost:30800/api/auth/login -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin"}' | jq -r .access_token)

curl -s -X POST http://localhost:30800/api/llm/retry-all -H "Authorization: Bearer $TOKEN" | jq .
curl -s -X POST http://localhost:30800/api/llm/test/kimi \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"prompt":"Analyze: suspicious outbound connection"}' | jq .
```
4. Hard refresh dashboard (`Ctrl+Shift+R`)

Expected:
- At least one provider shows `Healthy` (usually Kimi if configured)
- `Risk Forecast` shows a score (not empty)
- Provider breakdown lists all 5 providers (zero-call rows are OK)

### Cost Tracking
```
Kimi:    $0.006 per 1K tokens
xAI:     $0.012 per 1K tokens
OpenAI:  $0.010 per 1K tokens
Anthropic: $0.016 per 1K tokens
Gemini:  $0.002 per 1K tokens
```

## Q&A for Examiner

**Q: How does failover work?**
A: Sequential retry through priority list. If Kimi timeout/error → try xAI → etc. 15min cooldown for providers with auth errors.

**Q: Is cost data real?**
A: Estimated from tokens × provider rates. Accurate trend, not exact billing.

**Q: Production ready?**
A: Yes for academic/demo. Real HPA, persistence, 5-provider redundancy.

**Q: Scalability?**
A: Tested to 1000 devices. PostgreSQL is bottleneck.

**Q: What's new in this version?**
A: 
- Fixed IoT device count (now shows 13)
- Fixed LLM status consistency
- Fixed governance auth issues
- Added "Click for details" navigation
- Improved live pipeline feed

## Emergency Commands

```bash
# Restart everything
bash scripts/start-everything.sh

# Deploy code changes
bash scripts/deploy-code.sh

# Check logs
kubectl logs -n smart-city deployment/ids-api --tail=50

# Run attacks
bash scripts/run-live-attacks.sh --duration 30
```
