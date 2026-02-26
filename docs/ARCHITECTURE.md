# Architecture — Smart City IDS

Technical architecture reference for the LLM-driven Intrusion Detection System.

---

## System Overview

The Smart City IDS is a Kubernetes-native intrusion detection system that uses LLM-based threat analysis to monitor intentionally vulnerable IoT services. It runs on a single-node K3s cluster with four Kubernetes namespaces.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  K3s Cluster (single node)                                                   │
│                                                                              │
│  ┌─── smart-city ──────────────────────────────────────────────────────────┐ │
│  │  IoT Services (intentionally vulnerable)                                │ │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐  │ │
│  │  │traffic-camera│ │healthcare-api│ │parking-system│ │  mqtt-broker  │  │ │
│  │  │   (×2 pods)  │ │   (×2 pods)  │ │   (×2 pods)  │ │   (×1 pod)   │  │ │
│  │  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └──────┬───────┘  │ │
│  │         │                │                │                │           │ │
│  │  ┌──────┴────────────────┴────────────────┴────────────────┘           │ │
│  │  │  IoT Devices: enhanced(×10) + high(×4) + medium(×5) + burst(×1)     │ │
│  │  └────────────────────────────────────────────────────────────────┬──┐ │ │
│  │                                                                   │  │ │ │
│  │  ┌───────────────────────────────────────────┐  ┌──────────────┐  │  │ │ │
│  │  │           IDS API  (×1 pod demo-pinned)   │  │  PostgreSQL  │  │  │ │ │
│  │  │  FastAPI · LLM Analysis · K8s Automation  │──│  (persistence)│  │  │ │ │
│  │  │  NodePort 30800                           │  └──────────────┘  │  │ │ │
│  │  └──────────────┬────────────────────────────┘                    │  │ │ │
│  └─────────────────┼─────────────────────────────────────────────────┘  │ │ │
│                    │                                                     │ │
│  ┌─── falco-system ┼────────────────────────────────────────────────────┐│ │
│  │  ┌──────────┐   │   ┌───────────────────┐  ┌────────────────────┐   ││ │
│  │  │  Falco   │───┼──→│ Falco Forwarder   │─→│  IDS API /alerts   │   ││ │
│  │  │(DaemonSet│   │   │ (dedup + reshape) │  │                    │   ││ │
│  │  └──────────┘   │   └───────────────────┘  └────────────────────┘   ││ │
│  └─────────────────┼───────────────────────────────────────────────────┘│ │
│                    │                                                     │ │
│  ┌─── monitoring ──┼────────────────────────────────────────────────────┐│ │
│  │  ┌──────────┐   │   ┌───────────────────┐                           ││ │
│  │  │ Suricata │───┼──→│Suricata Forwarder │─→ IDS API                 ││ │
│  │  └──────────┘   │   └───────────────────┘                           ││ │
│  │  ┌──────────┐       ┌──────────────────┐                            ││ │
│  │  │Prometheus│       │     Grafana      │   NodePort 30300           ││ │
│  │  │ NP 31106 │       └──────────────────┘                            ││ │
│  │  └──────────┘                                                        ││ │
│  └──────────────────────────────────────────────────────────────────────┘│ │
└──────────────────────────────────────────────────────────────────────────┘ │
                     │                                                       │
              ┌──────┴──────┐                                                │
              │  LLM APIs   │  xAI Grok-4 · OpenAI GPT-4 · Anthropic Claude │
              │  (external) │  Google Gemini · Moonshot Kimi                 │
              └─────────────┘
```

---

## Current vs Target Architecture (Examiner Follow-Up)

This table is intentionally explicit: it separates what is implemented now from the next research-grade iteration.

| Area | Current (implemented) | Target (next iteration) | Why it matters |
|---|---|---|---|
| IoT device counting | Pod-derived / demo-profile count in IDS state | Persistent logical device registry (`register` / `heartbeat`) | Defensible fleet-size metrics at 100+ devices |
| IoT emulation scale | Pods emulate multiple devices; some services expose internal fleets | Explicit `device_count` per emulator + registry-backed inventory | Better realism without 1 pod = 1 device overhead |
| Dedup + alert throttling | In-memory in `ids-api` (demo pinned to 1 replica) | Shared state (Redis or equivalent) across replicas | Correct behavior when scaling `ids-api` > 1 |
| LLM provider resilience | Circuit breaker + cooldown + failover chain + operator reset/test UI | Same, plus stronger provider scoring / adaptive routing persistence | Improves reliability and explainability under quota/key failures |
| Telemetry ingest auth | Demo-friendly telemetry path; internal alert path uses shared token | Per-device API key/signed token; optional mTLS gateway | Real IoT onboarding security model |
| Scenario modeling | Attack scripts + detector rules + demo docs | ATT&CK-ICS staged scenario specs with expected telemetry + impact criteria | Research-grade methodology and examiner traceability |
| Impact representation | Security alerts + pipeline metrics + action/audit logs | Domain impact KPIs (availability/integrity/safety) per scenario | Stronger operational relevance for smart city use cases |

---

## Namespaces and Pod Inventory

| Namespace | Component | Replicas | Purpose |
|---|---|---|---|
| `smart-city` | ids-api | 1 (demo-pinned) | Core IDS: alert intake, LLM analysis, K8s automation |
| `smart-city` | postgres | 1 | Alert/action/audit persistence |
| `smart-city` | traffic-camera | 2 | Vulnerable Flask camera feed + license plate API |
| `smart-city` | healthcare-api | 2 | Vulnerable Flask patient record API |
| `smart-city` | parking-system | 2 | Vulnerable Flask parking reservation/payment API |
| `smart-city` | mqtt-broker | 1 | Mosquitto MQTT broker for IoT telemetry |
| `smart-city` | iot-devices-enhanced | 10 | MQTT sensor emulators (standard rate) |
| `smart-city` | iot-device-high | 4 | High-frequency MQTT emulators |
| `smart-city` | iot-device-medium | 5 | Medium-frequency MQTT emulators |
| `smart-city` | iot-device-burst | 1 | Bursty MQTT traffic emulator |
| `falco-system` | falco | 1 (DaemonSet) | Runtime syscall detection (eBPF) |
| `falco-system` | falco-forwarder | 1 | Deduplicates + reshapes Falco alerts → IDS API |
| `falco-system` | falco-k8s-metacollector | 1 | K8s metadata enrichment for Falco |
| `monitoring` | suricata | 1 | Network traffic IDS (signature-based) |
| `monitoring` | suricata-forwarder | 1 | Reshapes Suricata alerts → IDS API |
| `monitoring` | prometheus | 1 | Metrics collection (NodePort 31106) |
| `monitoring` | grafana | 1 | Dashboards (NodePort 30300) |

**Pod total is deployment-profile dependent across 4 namespaces** (+ kube-system pods managed by K3s).

---

## Alert Processing Pipeline

Every security event follows this path:

```
1. DETECTION
   Falco (runtime syscalls)  ──→  Falco Forwarder  ──→  POST /api/alerts/internal
   Suricata (network sigs)   ──→  Suricata Forwarder ─→  POST /api/alerts/internal
   (Removed) Synthetic dashboard/CLI injection path.

2. INTAKE (`api/alerts.py`)
   ├─ Rate limiter: per-rule / per-source / global limits (config-driven; see `/api/rate-limiter/status`)
   │  └─ Exceeds → HTTP 429, stored in throttled_alerts table
   ├─ Request queue: max 100 concurrent
   │  └─ Full → HTTP 503
   ├─ Source detection: classify alert as "falco" or "suricata"
   └─ Dedup cache: MD5(rule + proc.cmdline + container.name), 60s TTL
      └─ Cache hit → return cached analysis, skip LLM call

3. LLM ANALYSIS (`llm_providers/*` + `api/_state.py`)
   ├─ Circuit breaker check (per-engine, threshold=5 failures, 30s recovery)
   ├─ Cooldown check (15min after quota/auth errors)
   ├─ Try configured providers in priority order (`LLM_PRIORITY` / `LLM_PROVIDER_CHAIN`)
   │  └─ Each: build prompt → API call → parse JSON → validate
   └─ Output: {severity, threat_type, summary, recommendations, automated_actions}

4. AUTOMATED RESPONSE (k8s_automation.py + governance.py)
   ├─ severity ≥ 8 → isolate_pod (NetworkPolicy, unless protected service)
   ├─ severity ≥ 6 → scale_up (replicas to 5)
   └─ Governance: autonomous / assisted / manual (legacy aliases normalized)

5. PERSISTENCE (database.py)
   ├─ PostgreSQL: alerts, analysis_results, automation_actions, audit_logs
   ├─ Memory fallback if PostgreSQL unavailable
   ├─ Background DB reconnect monitor auto-recovers from fallback when PostgreSQL returns
   └─ Prometheus counters restored from DB on restart
```

### Pipeline-to-Metrics Mapping (Dashboard)

The Overview "Pipeline Overview" row maps each stage to concrete metrics:

| Stage | Metric / Source | Notes |
|---|---|---|
| Falco alerts | `smartcity_ids_alerts_raw_total{source="falco"}` | Raw ingress rate before dedup/throttling |
| Suricata alerts | `smartcity_ids_alerts_raw_total{source="suricata"}` | Raw network alert ingress |
| IDS ingest + dedup | `smartcity_ids_alerts_after_dedup_total`, `smartcity_ids_dedup_hit_rate_percent` | Shows analysis workload after dedup |
| LLM analysis | `smartcity_ids_llm_requests_total{engine,result}`, `smartcity_ids_llm_latency_seconds` | p95 latency and per-engine throughput |
| Governance + K8s actions | `smartcity_ids_human_review_required_total`, `smartcity_ids_actions_executed_total` | Analyst touch vs automated response |

Additional LLM observability exported by IDS API:

- `smartcity_ids_llm_tokens_total{engine,kind="prompt|completion"}` (estimated tokens)
- `smartcity_ids_llm_cost_usd_total{engine}` (estimated total cost)
- `/api/llm-stats/export` provides per-engine aggregate latency, token, and cost summaries used by UI tables.

---

## Source Code Structure

```
services/ids-api/
├── src/
│   ├── main.py                 (current)      FastAPI app bootstrap + router registration
│   ├── config.py               (current)      Environment-based configuration
│   ├── llm_manager.py          (current)      Legacy manager + compatibility path
│   ├── database.py             (current)      PostgreSQL + memory fallback
│   ├── operator_interface.py   (572 lines)   Incident transforms for dashboard
│   ├── governance.py           (507 lines)   HITL governance controller
│   ├── alert_rate_limiter.py   (287 lines)   Time-window rate limiter
│   ├── alert_deduplicator.py   (385 lines)   Alert dedup cache
│   ├── k8s_automation.py       (207 lines)   K8s defensive actions
│   ├── operator_models.py      (166 lines)   Pydantic data models
│   ├── llm_response_schema.py  (279 lines)   LLM response validation
│   ├── llm_retry.py            (381 lines)   Retry logic with backoff
│   ├── llm_base.py             (400 lines)   Base LLM engine class
│   ├── llm_engine_xai.py       (176 lines)   xAI Grok engine
│   ├── llm_engine_openai.py    (125 lines)   OpenAI GPT engine
│   ├── llm_engine_anthropic.py (148 lines)   Anthropic Claude engine
│   ├── llm_engine_gemini.py    (149 lines)   Google Gemini engine
│   └── llm_engine_kimi.py      (149 lines)   Moonshot Kimi engine
├── static/
│   └── index.html              (large single-file SPA; size changes frequently)  Operator dashboard SPA
└── requirements.txt

services/forwarders/
├── falco/src/main.py           (187 lines)   Falco alert forwarder
└── suricata/src/main.py        (453 lines)   Suricata EVE log forwarder

smart-city-services/
├── traffic-camera/app.py       Vulnerable camera API (Flask)
├── healthcare-api/app.py       Vulnerable patient API (Flask)
└── parking-system/app.py       Vulnerable parking API (Flask)
```

---

## LLM Provider Architecture

Cloud providers with priority-ordered failover:

| Provider | API Endpoint | Model (default) | Env Var |
|---|---|---|---|
| xAI Grok | `api.x.ai/v1/chat/completions` | `grok-4-latest` | `XAI_API_KEY` |
| Anthropic Claude | `api.anthropic.com/v1/messages` | `claude-3-5-sonnet-20241022` | `ANTHROPIC_API_KEY` |
| OpenAI GPT | `api.openai.com/v1/chat/completions` | `gpt-4-turbo-preview` | `OPENAI_API_KEY` |
| Google Gemini | `generativelanguage.googleapis.com` | `gemini-2.0-flash` | `GEMINI_API_KEY` |
| Moonshot Kimi | `api.moonshot.cn/v1/chat/completions` | `moonshot-v1-8k` | `KIMI_API_KEY` |

### Resilience

| Mechanism | Config | Behavior |
|---|---|---|
| Circuit Breaker | 5 failures → open, 30s recovery | Per-engine, half-open allows 3 test calls |
| Provider Cooldown | 15 minutes (env: `LLM_PROVIDER_COOLDOWN_SECONDS`) | After HTTP 401/403/429 or quota errors |
| Dedup Cache | 60s TTL, 100 max entries | MD5(rule+process+container), avoids duplicate LLM calls |

### LLM Key Management (Operational Procedure)

The IDS reads provider keys from environment variables injected into the `ids-api` pod via Kubernetes Secret.

Add/rotate a provider key:

1. Update project `.env` (single source of truth)
2. Sync to K8s secret (`ids-secrets`) via `scripts/apply-llm-env-to-k8s-secret.sh`
3. Restart/redeploy `ids-api` so the new env vars are loaded
4. Reset provider states (`/api/llm/retry-all`) to clear circuit breaker/cooldown latches
5. Probe/test the provider (`/api/llm/test/{provider}`) and verify `/api/llm/diagnostics`

Important:
- `retry-all` resets in-memory failure state, not provider billing/quota.
- Providers can be `configured` but still unusable due invalid keys, quota exhaustion, or model access restrictions.
- The dashboard LLM Control tab now exposes provider diagnostics, health, usage, and a manual reset/test flow.

### LLM Response Contract

```json
{
  "summary": "Human-readable 1-2 sentence explanation",
  "severity": 8,
  "threat_type": "Privilege Escalation",
  "confidence": 0.85,
  "key_indicators": ["rule match", "process name"],
  "mitigating_factors": ["single occurrence"],
  "business_impact": "Potential disruption to service X",
  "reasoning": "Step-by-step analysis logic",
  "recommendations": ["Isolate pod", "Collect logs"],
  "automated_actions": ["isolate_pod"]
}
```

Note: current startup validation requires at least one configured LLM API key; keyless local-only startup mode is not enabled in this branch.

---

## Kubernetes Automation

| Action | Trigger | K8s Operation |
|---|---|---|
| `isolate_pod` | severity ≥ 8 | Creates NetworkPolicy blocking all ingress/egress |
| `scale_up` | severity ≥ 6 | Patches deployment replicas to 5 |
| `block_ip` | manual/API | Creates NetworkPolicy blocking CIDR |
| `cordon_node` | manual/API | Sets node `unschedulable: True` |
| `restart_service` | manual/API | Deletes pods (rolling restart) |

**Protected services** (never auto-isolated): `healthcare-api`, `ids-api`, `postgres`

**Governance modes** (env: `AUTOMATION_MODE`, or `/api/governance/mode`):

| Mode | Behavior | Use Case |
|---|---|---|
| `autonomous` | High-confidence actions can execute automatically | Demo / controlled automation |
| `assisted` | Auto if severity < 8; otherwise queued | Default, production |
| `manual` | All actions require operator approval | Audit, investigation |

---

## Database Schema

PostgreSQL with automatic in-memory fallback. 8 tables:

| Table | Key Columns | Purpose |
|---|---|---|
| `alerts` | source, rule, severity, threat_type, analysis (JSONB) | Processed alerts |
| `analysis_results` | alert_id, model, analysis_time_ms, confidence | LLM results |
| `automation_actions` | alert_id, action_type, target, status, mode | K8s actions |
| `audit_logs` | action, actor, status, details (JSONB) | Governance audit |
| `iot_devices` | device_id (PK), type, first/last seen, event_count | Device registry |
| `iot_events` | device_id, event_type, value (JSONB) | Sensor telemetry |
| `system_logs` | level, component, message | App logs |
| `throttled_alerts` | source, rule, throttle_reason | Rate-limited alerts |

**Retention**: alerts 30d, IoT 30d, automation/audit 180d.

---

## Network Access

| Service | Port | Access |
|---|---|---|
| IDS API + Dashboard | `localhost:30800` | NodePort |
| Grafana | `localhost:30300` | NodePort |
| Prometheus | `localhost:31106` | NodePort |
| K8s API | `127.0.0.1:6443` | Direct (kubeconfig) |
| PostgreSQL | `postgres:5432` | ClusterIP (internal) |
| MQTT Broker | `mqtt-broker:1883` | ClusterIP (internal) |

All external access uses `localhost` — WiFi/IP-independent.

---

## Prometheus Metrics

**Core:** `ids_alerts_received_total`, `ids_alerts_processed_total`, `ids_automated_actions_total`, `ids_blocked_actions_total`, `ids_alert_processing_seconds`, `ids_uptime_seconds`

**LLM:** `ids_llm_requests_total`, `ids_llm_request_latency_seconds`, `ids_alert_cache_hits_total`

**Security:** `ids_severity_distribution`, `ids_threat_types_total`, `ids_critical_alerts_total`

**Governance:** `ids_decision_outcomes_total`, `ids_automated_decisions_total`, `ids_human_overrides_total`, `ids_blocked_by_policy_total`, `ids_time_to_mitigation_seconds`

**IoT:** `ids_iot_events_total`, `ids_iot_devices_active`, `ids_iot_security_events_total`, `ids_iot_heartbeats_total`

**K8s:** `ids_pods_isolated_total`, `ids_scale_operations_total`, `ids_protected_service_hits_total`

**Resilience:** `ids_rate_limit_requests_total`, `ids_circuit_breaker_state`, `ids_circuit_breaker_trips_total`, `ids_queue_size`, `ids_queue_rejected_total`
