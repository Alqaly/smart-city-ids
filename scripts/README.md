# Scripts Guide — Smart City IDS

Commands-only cheat sheet and reference for all demo/deployment scripts.

---

## Recommended Sequence (Demo Day)

Run these in order for a reliable end-to-end demo:

```bash
# 1. Pre-flight environment check
bash scripts/check-setup.sh                          # → "X passed, 0 failed"

# 2. Deploy everything (K3s + services + monitoring + Falco)
sudo bash scripts/start-everything.sh                # → "Smart City IDS is now running!"

# 3. Watch system health (live refresh)
bash scripts/check-system.sh --watch                 # → all-green pod table

# 4. Full demo run (bootstrap + attacks + readiness)
bash scripts/demo-day.sh --profile full --runs 1     # → controlled attack + pipeline check

# 5. Taxonomy-grade attack pipeline (standalone)
bash scripts/attack-iot-pipeline.sh --quick --live    # → 5 attacks with real pod exec

# 6. (After demo) Light cleanup — keeps K3s running
sudo bash scripts/cleanup.sh --light                 # → namespaces + port-forwards removed
```

---

## Quick Command Cheat Sheet

### Bootstrap & Deploy

| Command | What it does | Time |
|---|---|---|
| `sudo bash scripts/start-everything.sh` | Full K3s + all manifests + port-forward | ~5 min |
| `bash scripts/one-command-ready.sh` | Quick bootstrap (assumes K3s up) | ~2 min |
| `bash scripts/check-setup.sh --verbose` | Validate prerequisites (K3s, RAM, keys) | 10s |
| `bash scripts/check-system.sh` | Pod health snapshot across all namespaces | 5s |
| `bash scripts/check-system.sh --watch` | Live health monitor (refreshes every 5s) | continuous |

### Demo & Attacks

| Command | What it does | Time |
|---|---|---|
| `bash scripts/demo-day.sh --profile minimal` | Minimal demo: bootstrap + 1 attack run | ~3 min |
| `bash scripts/demo-day.sh --profile standard` | Standard: + security event generators | ~5 min |
| `bash scripts/demo-day.sh --profile full` | Full: + network attacks + IoT pipeline | ~8 min |
| `bash scripts/demo.sh --attack-type shadow` | Single attack type (shadow/sudo/network) | ~1 min |
| `bash scripts/demo-walkthrough.sh` | Interactive step-by-step guided demo | ~10 min |
| `bash scripts/demo-walkthrough.sh --auto --speed 3` | Auto-advance walkthrough (3s between steps) | ~5 min |

### Attack Pipeline (v2 — Taxonomy-Grade)

| Command | What it does |
|---|---|
| `bash scripts/attack-iot-pipeline.sh` | All 13 attacks (12 malicious + 1 benign control) |
| `bash scripts/attack-iot-pipeline.sh --quick` | 5 fast attacks only |
| `bash scripts/attack-iot-pipeline.sh --live` | Real pod exec + alert injection |
| `bash scripts/attack-iot-pipeline.sh --scenario 3` | Run only scenario #3 (license plate exfil) |
| `bash scripts/attack-iot-pipeline.sh --list` | Print scenario table with ATT&CK metadata |
| `bash scripts/attack-iot-pipeline.sh --json` | Machine-readable JSON metadata for all scenarios |
| `bash scripts/attack-iot-pipeline.sh --describe` | Full metadata table (phase, technique, volume) |
| `bash scripts/attack-iot-pipeline.sh --url http://localhost:8000` | Target local port-forward |

**Metrics CSV**: Each run appends to `scripts/.attack-metrics.csv`:
```
run_id,scenario_id,scenario_name,severity,threat_type,engine,total_ms,llm_ms,status,confidence,timestamp
```

### Readiness & Validation

| Command | What it does |
|---|---|
| `bash scripts/demo-readiness.sh` | Full readiness check → "DEMO: READY" or "DEMO: NOT READY" |
| `bash scripts/demo-readiness.sh --quick` | Quick check (skip smoke tests) |

### Cleanup

| Command | What it does |
|---|---|
| `sudo bash scripts/cleanup.sh --light` | Remove namespaces + port-forwards only (K3s stays) |
| `sudo bash scripts/cleanup.sh` | Standard: stop K3s + delete namespaces (data preserved) |
| `sudo bash scripts/cleanup.sh --full` | Full wipe: K3s data + persistent storage removed |
| `sudo bash scripts/cleanup.sh --dry-run` | Preview what would be deleted |
| `sudo bash scripts/cleanup.sh --full --force` | No confirmation prompts |

---

## Attack Scenarios (13 total)

| # | Name | Severity | ATT&CK Phase | Technique | Kill Chain | Volume |
|---|---|---|---|---|---|---|
| 1 | Shell Spawn in Traffic Camera | Critical | execution | T1059.004 | exploitation | low |
| 2 | Read /etc/shadow in Healthcare Pod | Critical | credential_access | T1552.001 | exploitation | low |
| 3 | Data Exfil — License Plate Dump | Critical | exfiltration | T1041 | actions_on_objectives | medium |
| 4 | Data Exfil — Patient Records | Critical | exfiltration | T1530 | actions_on_objectives | medium |
| 5 | Privilege Escalation — SUID Binary | Critical | privilege_escalation | T1548.001 | exploitation | low |
| 6 | DDoS — NTP Amplification | Critical | impact | T1498.002 | actions_on_objectives | high |
| 7 | Network Recon — Port Scan | Warning | discovery | T1046 | reconnaissance | high |
| 8 | DNS-Based Data Exfiltration | Critical | exfiltration | T1048.001 | actions_on_objectives | low |
| 9 | Lateral Movement — Service Discovery | Warning | lateral_movement | T1046 | command_and_control | low |
| 10 | SQL Injection on Parking System | Critical | initial_access | T1190 | delivery | low |
| 11 | Cryptominer in IoT Pod | Critical | impact | T1496 | actions_on_objectives | low |
| 12 | MQTT Message Poisoning | Warning | persistence | T1565.002 | command_and_control | medium |
| 13 | Benign IoT Burst (control) | Notice | benign_test | N/A | N/A | high |

---

## Script Dependency Tree

```
sudo bash scripts/start-everything.sh (Main)
  ├── Phase 1: K3s install / verify
  ├── Phase 2: Clean existing K3s
  ├── Phase 3: Start K3s cluster
  ├── Phase 4: Deploy manifests (smart-city, monitoring, falco)
  ├── Phase 5: Falco (Helm)
  ├── Phase 6: IoT devices
  ├── Phase 7-8: Wait + verify
  ├── Phase 9: Print URLs
  └── Phase 10: Port-forward setup

bash scripts/demo-day.sh --profile full
  ├── one-command-ready.sh (bootstrap)
  ├── Port-forwards (IDS, Grafana, Prometheus)
  ├── API key validation (3 places)
  ├── LLM runtime status
  ├── demo.sh (runtime + network attacks)
  ├── generate-security-events.sh (standard+)
  ├── generate-network-attacks.sh (full)
  ├── generate-advanced-attacks.sh (full)
  ├── attack-iot-pipeline.sh --quick (full)
  ├── check-system.sh
  └── demo-readiness.sh --quick

bash scripts/attack-iot-pipeline.sh
  ├── 13 attack scenarios (ATT&CK classified)
  ├── IDS API alert injection
  ├── Latency metrics CSV collection
  └── Optional: --live pod exec

sudo bash scripts/cleanup.sh [--light|--full]
  ├── Phase 1: Port-forwards
  ├── Phase 2: K8s namespaces
  ├── Phase 3: K3s stop (standard/full)
  └── Phase 4: Data wipe (full only)
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `XAI_API_KEY` | Yes (one of) | — | xAI Grok-4 API key |
| `OPENAI_API_KEY` | Yes (one of) | — | OpenAI GPT-4 fallback |
| `KIMI_API_KEY` | Optional | — | Moonshot Kimi fallback |
| `ANTHROPIC_API_KEY` | Optional | — | Anthropic Claude fallback |
| `GEMINI_API_KEY` | Optional | — | Google Gemini fallback |
| `KUBECONFIG` | Auto | `~/.kube/config` | K8s config path |
| `IDS_API_URL` | Optional | `http://localhost:30800` | IDS API base URL |
| `ATTACK_DELAY` | Optional | `4` | Seconds between attacks |
| `AUTOMATION_MODE` | Optional | `assisted` | Governance mode |

---

## Access URLs

| Service | URL | Credentials |
|---|---|---|
| IDS Dashboard | `http://localhost:8000/ui` | operator / operator |
| IDS API Docs | `http://localhost:8000/docs` | — |
| Grafana | `http://localhost:3000` | admin / admin |
| Prometheus | `http://localhost:9090` | — |
| IDS NodePort | `http://<node-ip>:30800` | operator / operator |

---

## Troubleshooting

```bash
# K3s won't start
sudo systemctl restart k3s && sleep 15
sudo chmod 644 /etc/rancher/k3s/k3s.yaml
export KUBECONFIG=~/.kube/config

# Pods stuck in CrashLoopBackOff
kubectl logs -n smart-city -l app=ids-api --tail=30
kubectl describe pod -n smart-city -l app=ids-api

# Port-forward already in use
pkill -f "kubectl port-forward" && sleep 2
bash scripts/one-command-ready.sh

# No LLM responses (all local fallback)
kubectl exec -n smart-city deploy/ids-api -- printenv | grep API_KEY

# Metrics CSV not being written
cat scripts/.attack-metrics.csv  # check if header exists
bash scripts/attack-iot-pipeline.sh --scenario 1  # test single scenario

# View K3s logs
tail -50 /tmp/k3s.log
kubectl get events -A --sort-by='.lastTimestamp' | tail -20
```

---

For full architecture details, see [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md).
