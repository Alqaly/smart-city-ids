# Smart City IDS - Demo Cheat Sheet

> Quick note (current setup): login is `admin / admin`.
> Prefer `docs/reference/DEMO_DAY_RUNBOOK.md` for the latest validated demo flow.

## Quick Links
- **Dashboard**: http://localhost:30800/ui
- **API Docs**: http://localhost:30800/docs
- **Prometheus**: http://localhost:31106
- **Grafana**: http://localhost:30300

## Pre-Demo Checklist (Run These)

```bash
# 1. Check cluster is running
kubectl get nodes

# 2. Run readiness check
bash scripts/readiness-check.sh --quick

# 3. Verify key endpoints
curl -s http://localhost:30800/health | jq .status
curl -s http://localhost:30800/api/metrics | jq .total_alerts
```

## Demo Flow (5 Minutes)

### 1. System Overview (1 min)
**Open Dashboard → Overview Tab**

**Talking Points:**
- "We have 6,577 alerts processed from Suricata and Falco"
- "13 IoT devices monitored: cameras, healthcare APIs, parking systems"
- "The platform supports 5 LLM providers with automatic failover; current live availability depends on keys, quota, and billing."
- "PostgreSQL backend with memory fallback"

**Show:**
- Stat cards: Total Alerts, Critical, IoT Devices, Dedup Savings
- Pipeline Overview: All stages GREEN
- System Health: All components connected

### 2. LLM Provider Details (1 min)
**Click "AI Providers" panel → Switch to LLM Control tab**

**Talking Points:**
- "Multi-provider architecture: xAI, OpenAI, Anthropic, Gemini, Kimi"
- "Automatic failover: if Kimi fails, switches to next provider"
- "Cost tracking: $0.006 per 1K tokens for Kimi"
- "Circuit breakers: 5 failures → 30s cooldown"

**Show:**
- Provider health cards (all green)
- Failover chain visualization
- Provider breakdown table

### 3. Live Attack Demo (2 min)
**Terminal:**
```bash
# Run live attacks
bash scripts/run-live-attacks.sh --duration 20 --mode all
```

**Talking Points:**
- "Running real SQL injection attacks against healthcare API"
- "Suricata detects at network layer → IDS API analyzes with LLM"
- "Severity 9+ triggers automatic pod isolation"
- "All actions logged to PostgreSQL"

**Dashboard:**
- Switch to Alerts tab → Watch new alerts appear
- Check severity badges (red = critical)
- Show Live Pipeline Feed (bottom card)

### 4. Automation/Governance (1 min)
**Switch to Automation Tab**

**Talking Points:**
- "Three automation modes: Manual, Assisted, Autonomous"
- "Current: Assisted mode - high confidence auto-executes"
- "Low confidence actions queue for approval"
- "Demonstrate mode switching (Manual → Assisted → Autonomous)"

**Show:**
- Mode selection buttons
- Pending actions list
- Metrics: approved/rejected/pending counts

## Key Metrics to Highlight

| Metric | Current Value | What It Shows |
|--------|--------------|---------------|
| Total Alerts | 6,577+ | Real detection volume |
| IoT Devices | 13 | Monitored pods |
| LLM Providers | 5/5 | Redundancy |
| Dedup Savings | ~40% | Cost optimization |
| Pipeline Status | All GREEN | End-to-end health |

## Troubleshooting

**If dashboard shows old data:**
```bash
bash scripts/deploy-code.sh
```

**If no new alerts appearing:**
```bash
# Check Suricata/Falco are running
kubectl get pods -n monitoring
kubectl get pods -n falco-system

# Trigger manual attack
bash scripts/run-live-attacks.sh --duration 10
```

**If LLM shows 0 calls:**
- Stats reset on pod restart (expected)
- Run attacks to generate new LLM calls
- Costs are estimated from tokens × rate

## Architecture Diagram (Describe This)

```
Attack Traffic
     ↓
[Suricata/Falco] → Detection
     ↓
[IDS API] → LLM Analysis (Kimi → xAI → ... failover)
     ↓
[Governance] → Auto/Manual decision
     ↓
[K8s Actions] → Pod isolation, scaling
     ↓
[PostgreSQL] → Persistent storage
     ↓
[Dashboard] → Real-time visualization
```

## Q&A Preparation

**Q: How does failover work?**
A: Sequential retry. Tries Kimi first, if fails (timeout/error), tries xAI, then Anthropic, etc. Providers in cooldown (15min after auth error) are skipped.

**Q: Is cost data real?**
A: Estimated from token counts × provider rates. Not actual billing, accurate within ~20%. Kimi: $0.006/1K tokens.

**Q: Production readiness?**
A: Yes for academic/demo: HPA auto-scales (4 HPAs active), 5-provider redundancy, dedup saves ~40% costs, PostgreSQL persistence.

**Q: How many devices can it handle?**
A: Tested to 1000 emulated IoT devices. PostgreSQL is bottleneck; for >5K alerts/min would need read replicas.

**Q: What's the latency?**
A: Alert ingestion <100ms, LLM analysis 2-5s depending on provider, automated action <1s after decision.

## Emergency Fixes

**Dashboard not loading:**
```bash
kubectl rollout restart deployment/ids-api -n smart-city
```

**K3s cluster down:**
```bash
sudo systemctl restart k3s
```

**Need fresh data:**
```bash
bash scripts/run-live-attacks.sh --duration 30
```
