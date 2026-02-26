# API Reference — Smart City IDS

Complete endpoint reference for the IDS API (FastAPI). Base URL: `http://localhost:30800`.

---

## Authentication

Authentication requirements vary by route category below (each endpoint row specifies auth explicitly).

```bash
# Get a token (use credentials configured via IDS_USER_*/IDS_PASS_* env vars)
TOKEN=$(curl -s -X POST http://localhost:30800/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"<username>","password":"<password>"}' | jq -r .access_token)

# Use token
curl -H "Authorization: Bearer $TOKEN" http://localhost:30800/api/operator/dashboard
```

Tokens expire after 24 hours. `/api/alerts/internal` is cluster-internal and requires `X-IDS-Internal-Token` (shared secret) so it cannot be used for synthetic injection.

---

## Endpoints by Category

### Root & UI

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/` | No | Service info, version, available endpoints |
| GET | `/ui` | No | Operator dashboard (HTML SPA) |

### Authentication

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/auth/login` | No | Get JWT token. Body: `{"username":"<username>","password":"<password>"}` |
| POST | `/api/auth/logout` | No | Client-side logout (no server invalidation) |

### Health & Monitoring

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/health` | No | Component status (LLM, K8s, DB, Falco, Suricata), uptime, alert count |
| GET | `/api/safety` | No | Automation mode, protected services, thresholds, cache stats |
| GET | `/api/production-status` | No | Rate limiter, circuit breaker, queue, cache operational status |
| GET | `/api/pipeline-overview` | No | Pipeline-stage counters used by dashboard overview |
| GET | `/api/metrics` | No | Application metrics (JSON) |
| GET | `/metrics` | No | Prometheus text exposition format (metric set may evolve by release/config) |
| GET | `/api/db/stats` | No | Database statistics |

### Alert Processing

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/alerts/live` | No | Server-Sent Events stream for real-time alert updates |
| POST | `/api/alerts` | Yes | Main alert ingestion. Rate-limited, deduplicated, LLM-analyzed, auto-response |
| POST | `/api/alerts/internal` | Header | Same as above, for cluster-internal forwarders (Falco, Suricata). Requires `X-IDS-Internal-Token`. |
| GET | `/api/alerts` | No | Query processed alerts. Params: `limit` (default 10), `source` |
| POST | `/api/alerts/{alert_id}/reanalyze` | Yes | Re-run analysis for an existing alert record |

### Analyst Chat

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/analyst/session` | No | Bootstrap analyst session, returns `session_id` + available tools/providers |
| POST | `/api/analyst/chat` | No | Conversational SOC assistant endpoint; returns 429 when chat limiter is exceeded |
| POST | `/api/analyst/quick-analyze` | No | Fast one-shot threat analysis helper |
| POST | `/api/analyst/action/submit` | No | Submit explicit analyst action request |
| POST | `/api/analyst/action/pending-decision` | No | Submit/confirm pending action decision payload |
| GET | `/api/analyst/tools` | No | List tool functions available to analyst chat |
| WS | `/api/analyst/ws` | No | Real-time analyst WebSocket channel |

### Circuit Breaker

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/circuit-breaker/status` | No | Per-engine state (open/closed/half-open), failure counts |
| POST | `/api/circuit-breaker/reset` | No | Reset circuit breakers. Param: `engine` (optional, or resets all) |

### LLM Management

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/llm/status` | Yes | Active providers, priority order, circuit breaker state per engine |
| GET | `/api/llm/diagnostics` | No | Verbose per-provider diagnostics and summary |
| GET | `/api/llm/retry-queue` | Yes | View queued failed-analysis items |
| POST | `/api/llm/retry-queue/clear` | Yes | Clear queued failed-analysis items |
| GET | `/api/llm/providers` | No | Provider availability details |
| GET | `/api/llm/providers/comparison` | No | Comparative provider view |
| GET | `/api/llm/providers/health-summary` | No | Aggregated provider health summary |
| POST | `/api/llm/retry-all` | Yes | Reset provider states/cooldowns and breaker latches (operator recovery) |
| POST | `/api/llm/reset-cooldown` | Yes | Clear provider cooldown/auth-disable timers |
| POST | `/api/llm/test/{provider}` | Yes | Send probe/test request to provider |
| POST | `/api/llm/force/{provider}` | Yes | Force active provider selection |
| GET | `/api/llm/metrics/24h` | Yes | Runtime in-memory 24h-shaped metrics payload (resets on `ids-api` restart) |
| GET | `/api/metrics/llm-usage?window=today|7d|...` | Yes | DB-backed LLM usage/cost/tokens by provider (preferred for reporting) |
| GET | `/api/llm/routing/strategy` | Yes | Current routing strategy configuration |
| POST | `/api/llm/routing/strategy` | Yes | Update routing strategy configuration |
| GET | `/api/llm/predictive-risk` | Yes | Predictive risk analytics output |
| GET | `/api/llm/control/status` | No | LLM control-plane status |
| POST | `/api/llm/control/force` | Yes | Force control-plane provider |
| POST | `/api/llm/control/priority` | Yes | Update runtime provider priority |
| POST | `/api/llm/control/test` | Yes | Run control-plane test invocation |
| POST | `/api/llm/feedback` | No | Submit routing/analysis feedback sample |
| GET | `/api/llm/feedback/stats` | No | Feedback aggregate statistics |
| GET | `/api/llm-stats/export` | No | Export per-engine latency/cost/token aggregates |

### LLM Credits

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/llm/credits/` | No | Credit status across configured providers |
| GET | `/api/llm/credits/{provider}` | No | Credit status for one provider |

### Rate Limiter

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/rate-limiter/status` | No | Window config, throttle stats, per-rule/source/global counts |
| POST | `/api/rate-limiter/reset` | No | Reset all rate limiter counters |

### Deduplicator

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/deduplicator-stats` | No | Cache stats, hit rate, estimated cost savings |
| POST | `/api/deduplicator/clear` | Yes | Clear fingerprint cache |

### Governance (Human-in-the-Loop)

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/governance/status` | Yes | Current mode, pending count, decision metrics |
| GET | `/api/governance/mode` | Yes | Current automation mode |
| POST | `/api/governance/mode` | Yes | Set mode. Param: `mode` (`autonomous`/`assisted`/`manual`/`emergency`, depending policy/build) |
| GET | `/api/governance/pending` | Yes | List pending actions awaiting approval |
| POST | `/api/governance/approve/{action_id}` | Yes | Approve + execute pending action. Params: `operator`, `comment` |
| POST | `/api/governance/reject/{action_id}` | Yes | Reject pending action. Params: `operator`, `reason` |
| GET | `/api/governance/history` | Yes | Audit trail. Param: `limit` (default 50) |

### Operator Dashboard

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/operator/dashboard` | Yes | Full dashboard: stats, severity distribution, threat types, timeline |
| GET | `/api/operator/incidents` | Yes | Incident list with evidence, reasoning, actions. Param: `limit` |
| GET | `/api/operator/incident/{incident_id}` | Yes | Single incident full detail |
| GET | `/api/operator/evidence/{incident_id}` | Yes | Raw evidence excerpts for incident |
| GET | `/api/operator/reasoning/{incident_id}` | Yes | LLM reasoning chain, confidence, indicators |
| GET | `/api/operator/metrics` | Yes | Analysis time, confidence, approval/rejection rates |
| GET | `/api/operator/search` | Yes | Search incidents. Params: `query`, `severity_min/max`, `threat_type`, `limit` |

### IoT Sensors

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/iot/telemetry` | No | Current telemetry snapshot for discovered devices |
| POST | `/api/iot/sensor` | No | Receive sensor telemetry. Security events auto-create alerts |
| GET | `/api/iot/devices` | No | List registered IoT devices |
| GET | `/api/iot/pods` | No | List IoT pods and status metadata |
| GET | `/api/iot/events` | No | Recent IoT events. Params: `limit`, `device_id` |
| GET | `/api/iot/discover` | No | Discover IoT devices from cluster inventory |
| GET | `/api/iot/vulnerabilities` | No | Vulnerability summary for IoT services |

### Audit & Logs

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/audit/events` | No | Timeline/audit event stream (paged JSON) |
| GET | `/api/audit/trace/{trace_id}` | No | Correlated audit trail for one trace id |
| GET | `/api/audit/export` | No | Export audit records |
| GET | `/api/logs/events` | Yes | Unified SOC logs feed |

### Demo Controls

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/iot/scale` | No | Read current IoT scaling profile |
| POST | `/api/iot/scale` | No | Update IoT scaling profile |

Note: Synthetic “chaos” demo endpoints were removed. Live demo runs should use
real traffic/runtimes (Falco + Suricata) and the `scripts/run-live-attacks.sh`
runner.

Source inventory note: endpoint count and auth mix evolve as the operator UI/API changes. Treat the tables above as the maintained reference; verify against `services/ids-api/src/api/*.py` for exact route inventory.

---

## Alert Processing Detail

### Request (POST `/api/alerts` or `/api/alerts/internal`)

```json
{
  "output": "Sensitive file opened for reading (file=/etc/shadow)",
  "priority": "Critical",
  "rule": "Read sensitive file untrusted",
  "time": "2025-01-15T10:30:00Z",
  "output_fields": {
    "container.name": "traffic-camera-abc123",
    "proc.cmdline": "cat /etc/shadow",
    "fd.name": "/etc/shadow"
  }
}
```

**Field constraints:**
- `output`: 1–2048 characters
- `priority`: Emergency, Alert, Critical, Error, Warning, Notice, Informational, Debug
- `rule`: 1–512 characters
- `output_fields`: max 50 keys

### Response

```json
{
  "status": "success",
  "alert_id": 42,
  "analysis": {
    "summary": "Shadow file access detected in traffic-camera container",
    "severity": 8,
    "threat_type": "Data Exfiltration",
    "confidence": 0.85,
    "key_indicators": ["sensitive file path", "non-standard process"],
    "mitigating_factors": [],
    "business_impact": "Credential exposure risk",
    "reasoning": "Reading /etc/shadow indicates credential harvesting...",
    "recommendations": ["Isolate container", "Rotate credentials"],
    "automated_actions": ["isolate_pod"]
  },
  "actions_taken": [
    {
      "action": "isolate_pod",
      "target": "traffic-camera-abc123",
      "status": "executed"
    }
  ]
}
```

### Processing Pipeline

1. **Token bucket rate limiter** — 120 requests/min refill, 30 burst. Returns 429 if exceeded.
2. **Request queue** — max 100 concurrent. Returns 503 if full.
3. **Alert rate limiter** — per-rule (10/min), per-source (100/min), global (500/min). Returns 429.
4. **Dedup cache** — MD5(rule + proc.cmdline + container.name), 60s TTL. Cache hit returns previous analysis.
5. **LLM analysis** — tries engines in priority order, respects circuit breaker and cooldown.
6. **Automated response** — severity ≥ 8 → isolate pod, severity ≥ 6 → scale up. Governed by mode.
7. **Persistence** — PostgreSQL (or memory fallback).

---

## Data Models

### Alert

| Field | Type | Constraints |
|---|---|---|
| `output` | string | 1–2048 chars, required |
| `priority` | enum | Emergency/Alert/Critical/Error/Warning/Notice/Informational/Debug |
| `rule` | string | 1–512 chars, required |
| `time` | string | ISO 8601, required |
| `output_fields` | dict | Max 50 keys, required |

### IoTSensorData

| Field | Type | Required |
|---|---|---|
| `device_id` | string (1–64) | Yes |
| `device_type` | string | Yes |
| `event_type` | string | Yes |
| `value` | any | No |
| `timestamp` | string (ISO) | No |
| `metadata` | dict | No |

Security event types that auto-trigger alerts: `anomaly`, `intrusion`, `tampering`, `unauthorized`, `rapid_motion`.

### OperatorIncident

| Field | Type | Description |
|---|---|---|
| `incident_id` | int | Alert ID |
| `timestamp` | string | ISO 8601 |
| `incident_summary` | string | LLM-generated summary |
| `severity` | int | 1–10 |
| `evidence` | EvidenceItem[] | Source excerpts |
| `reasoning` | AnalysisReasoning | LLM reasoning chain |
| `recommended_actions` | RecommendedAction[] | Prioritized actions |
| `automation_governance` | AutomationGovernance | Mode, approval status |
| `business_impact` | string | Impact description |
| `llm_model_used` | string | Which engine analyzed |
| `analysis_duration_ms` | float | LLM latency |

---

## Configuration

All settings via environment variables. Source: `config.py` and `main.py`.

### LLM Provider Keys

| Variable | Default | Description |
|---|---|---|
| `XAI_API_KEY` | `""` | xAI Grok API key |
| `OPENAI_API_KEY` | `""` | OpenAI API key |
| `ANTHROPIC_API_KEY` | `""` | Anthropic Claude API key |
| `GEMINI_API_KEY` | `""` | Google Gemini API key |
| `KIMI_API_KEY` | `""` | Moonshot Kimi API key |

### LLM Settings

| Variable | Default | Description |
|---|---|---|
| `LLM_PRIORITY` | `kimi,xai,anthropic,openai` (default chain in current config) | Failover order (may be overridden by `LLM_PROVIDER_CHAIN`) |
| `LLM_TEMPERATURE` | `0.3` | Sampling temperature |
| `LLM_MAX_TOKENS` | `1000` | Max tokens per response |

### Kubernetes

| Variable | Default | Description |
|---|---|---|
| `K8S_NAMESPACE` | `smart-city` | Target namespace |
| `KUBECONFIG` | `/etc/rancher/k3s/k3s.yaml` | Kubeconfig path |

### Thresholds

| Variable | Default | Description |
|---|---|---|
| `CRITICAL_SEVERITY_THRESHOLD` | `8` | Severity ≥ value → isolate pod |
| `HIGH_SEVERITY_THRESHOLD` | `6` | Severity ≥ value → scale up |
| `AUTOMATION_MODE` | `assisted` | `autonomous` / `assisted` / `manual` / `emergency` (legacy aliases normalized) |
| `ASSISTED_THRESHOLD` | `8` | Severity ≥ value requires approval in assisted mode |
| `PROTECTED_SERVICES` | `healthcare-api,ids-api,postgres` | Never auto-isolated |
| `ACTION_EXPIRY_SECONDS` | `300` | Pending action TTL |

### Rate Limiting & Circuit Breaker

| Variable | Default | Description |
|---|---|---|
| `RATE_LIMIT_PER_MINUTE` | `120` | Token bucket refill rate |
| `RATE_LIMIT_BURST` | `30` | Token bucket burst size |
| `ALERT_RATE_LIMIT_WINDOW` | `60` | Alert rate limiter window (seconds) |
| `ALERT_RATE_LIMIT_PER_RULE` | `10` | Max per rule per window |
| `ALERT_RATE_LIMIT_PER_SOURCE` | `100` | Max per source per window |
| `ALERT_RATE_LIMIT_GLOBAL` | `500` | Global max per window |
| `CIRCUIT_BREAKER_THRESHOLD` | `5` | Failures before open |
| `CIRCUIT_BREAKER_TIMEOUT` | `30` | Recovery timeout (seconds) |
| `REQUEST_QUEUE_SIZE` | `100` | Max concurrent requests |

### Cache & Dedup

| Variable | Default | Description |
|---|---|---|
| `ALERT_CACHE_TTL_SECONDS` | `60` | LRU analysis cache TTL |
| `ALERT_CACHE_MAX_SIZE` | `100` | Max cached analyses |
| `DEDUPLICATOR_TTL_SECONDS` | `60` | Fingerprint dedup TTL |
| `DEDUPLICATOR_MAX_CACHE_SIZE` | `10000` | Max fingerprints |

### Database & Server

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://postgres:idspassword@postgres:5432/smartcity_ids` | PostgreSQL connection |
| `DB_RECONNECT_INTERVAL_SECONDS` | `10` | Background retry interval for auto-recovery from DB fallback |
| `SECRET_KEY` | `smart-city-ids-demo-secret-change-in-production` | JWT signing key |
| `APP_HOST` | `0.0.0.0` | Bind address |
| `APP_PORT` | `8000` | Listen port |
| `LOG_LEVEL` | `INFO` | Logging level |

---

## Error Responses

| HTTP | Cause | Body |
|---|---|---|
| 401 | Missing or invalid JWT | `{"detail":"Not authenticated"}` |
| 403 | Invalid credentials | `{"detail":"Invalid credentials"}` |
| 404 | Incident/action not found | `{"detail":"Incident X not found"}` |
| 429 | Rate limit exceeded | `{"status":"throttled","reason":"..."}` |
| 503 | Queue full | `{"status":"error","error":"Server overloaded"}` |
