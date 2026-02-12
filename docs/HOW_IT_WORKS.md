# How It Works — Smart City IDS

End-to-end walkthrough of the system, from detection to automated response.

---

## 1. The Smart City Environment

The cluster runs intentionally vulnerable IoT services — simulating real smart-city infrastructure:

| Service | What It Does | Vulnerabilities (by design) |
|---|---|---|
| **traffic-camera** | License plate recognition, camera feeds | Command injection, path traversal, no auth |
| **healthcare-api** | Patient records, medical data | SQL injection, no input validation |
| **parking-system** | Reservations, payments | Injection, weak session handling |
| **mqtt-broker** | MQTT pub/sub for sensors | Unauthenticated, no TLS |
| **iot-simulators** | 20 pods generating sensor telemetry | High event volume for realism |

These services are deployed from `smart-city-services/` and mounted into Kubernetes via ConfigMaps — no Docker builds required.

---

## 2. Detection Layer

Two independent detection engines monitor the cluster:

### Falco (Runtime Detection)
- Runs as a DaemonSet using eBPF probes
- Detects syscall-level threats: shell spawns, sensitive file reads, privilege escalation
- Outputs structured JSON alerts with `rule`, `output`, `output_fields`, `priority`
- Configured via `k8s-manifests/falco-values.yaml`

### Suricata (Network Detection)
- Runs as a pod in the monitoring namespace
- Analyzes network traffic with signature rules
- Detects: port scans, DDoS patterns, DNS tunneling, known exploit signatures
- Outputs EVE JSON logs parsed by the Suricata forwarder

Both detectors feed their alerts through **forwarders** — lightweight Python services that:
1. Parse raw alert output into a normalized JSON shape
2. Deduplicate repeated alerts (fingerprint-based, 60s window)
3. Map priority strings to numeric severity (1–10)
4. POST to `http://ids-api:8000/api/alerts/internal`

---

## 3. Alert Intake

When an alert arrives at `/api/alerts/internal`, the IDS API applies multiple protective layers before any LLM call:

```
Incoming alert
    │
    ├─ Token bucket rate limiter (120/min refill, 30 burst)
    │   └─ Exceeded → HTTP 429
    │
    ├─ Request queue semaphore (max 100 concurrent)
    │   └─ Full → HTTP 503
    │
    ├─ Alert rate limiter (sliding window)
    │   ├─ Per-rule: max 10 per 60s
    │   ├─ Per-source: max 100 per 60s
    │   └─ Global: max 500 per 60s
    │       └─ Exceeded → stored in throttled_alerts table, HTTP 429
    │
    └─ Dedup cache (MD5 fingerprint, 60s TTL)
        └─ Cache hit → return previous analysis immediately, skip LLM
```

This stack prevents a flood of Falco alerts (common during active attacks) from overwhelming the LLM provider or running up API costs.

---

## 4. LLM Analysis

If the alert passes all filters (not rate-limited, not a duplicate), it goes to the LLM manager.

### Provider Selection

The manager maintains a priority-ordered list of LLM engines. For each call:

1. Check if engine's **circuit breaker** is open → skip if so
2. Check if engine is in **cooldown** (15min after auth/quota error) → skip if so
3. Attempt API call with the alert context

If the call fails, the manager tries the next provider. The local fallback engine always succeeds (no network call).

### The Prompt

Each engine sends a system prompt that instructs the LLM to act as a cybersecurity analyst. The prompt includes:

- The alert rule name, output text, and raw output fields
- Instructions to return **only** valid JSON
- The exact response schema (severity, threat_type, summary, recommendations, automated_actions)
- Constraint: severity 1–10, threat_type from a known set

### Response Parsing

The engine attempts to extract JSON from the response:
1. Look for ```json fences
2. Look for raw `{...}` JSON
3. Validate required fields (severity, summary, threat_type)
4. If parsing fails entirely → return conservative fallback analysis (severity 5, "Policy Violation")

### Local Fallback Engine

When no cloud LLM is available (all have open circuit breakers or no API keys), the local engine performs pattern matching against 11 rules:

- Matches keywords in the alert `output` and `rule` fields
- Returns pre-defined severity and threat type per pattern
- Zero latency, zero cost, always available
- Used as the last resort in the provider chain

---

## 5. Automated Response

After LLM analysis, the system decides what to do based on severity and governance mode:

### Severity Thresholds

| Severity | Action | Details |
|---|---|---|
| ≥ 8 (critical) | `isolate_pod` | Creates a deny-all NetworkPolicy for the pod's container |
| ≥ 6 (high) | `scale_up` | Patches the deployment to 5 replicas (absorb load) |
| < 6 | No automated action | Logged only |

### Protected Services

Some services are exempt from automated isolation to prevent self-disruption:
- `healthcare-api` — critical patient data
- `ids-api` — the IDS itself
- `postgres` — persistence layer

If a critical alert targets a protected service, the action is logged as `blocked_protected_service` instead of executed.

### Kubernetes Operations

`k8s_automation.py` uses the official Kubernetes Python client:

- **isolate_pod**: Creates a `NetworkPolicy` named `isolate-{pod-name}` with empty ingress/egress rules
- **scale_up**: Patches the deployment's replica count via the Apps V1 API
- **block_ip**: Creates a `NetworkPolicy` with a CIDR-based ingress deny rule
- **cordon_node**: Patches the node spec to set `unschedulable: True`
- **restart_service**: Deletes pods matching the deployment label (rolling restart)

---

## 6. Governance (Human-in-the-Loop)

The governance controller mediates between automated analysis and K8s actions:

### Modes

| Mode | Behavior |
|---|---|
| **Autopilot** | All actions execute immediately without approval |
| **Assisted** | Actions auto-execute if severity < 8; severity ≥ 8 queued for approval |
| **Manual** | All actions queued for operator approval |

### Approval Workflow

1. Action is proposed (isolate_pod, scale_up, etc.)
2. Governance controller evaluates: can it auto-execute?
   - If yes → execute immediately, log to audit
   - If no → add to pending queue with 5-minute expiry
3. Operator sees pending actions in the dashboard
4. Operator approves (executes + logs) or rejects (logs reason)
5. Expired actions are cleaned up automatically

### Audit Trail

Every governance decision is recorded in the `audit_logs` table:
- Action type, target, severity, mode at time of decision
- Who approved/rejected, when, with what comment
- Execution result (success/failure)

---

## 7. Persistence

### PostgreSQL (Primary)

8 tables store the full operational history:
- `alerts` — every processed alert with full LLM analysis (JSONB)
- `analysis_results` — LLM model used, analysis time, confidence
- `automation_actions` — K8s actions taken, status, governance mode
- `audit_logs` — governance decisions and operator actions
- `iot_devices` — device registry (auto-populated from sensor data)
- `iot_events` — telemetry history
- `system_logs` — application logs
- `throttled_alerts` — rate-limited alerts (for visibility)

### Memory Fallback

If PostgreSQL is unreachable at startup, the system falls back to in-memory storage:
- Same API, same data model
- Data is lost on pod restart
- The `/health` and `/api/metrics` endpoints report `storage_type: "memory"` vs `"postgresql"`

### Prometheus Counter Restoration

On startup, the database restores Prometheus counters from persisted data so metrics survive pod restarts. This prevents counter resets from appearing as drops in Grafana dashboards.

---

## 8. Operator Dashboard

A single-page HTML application served at `/ui` (NodePort 30800):

| Tab | Data Source | What It Shows |
|---|---|---|
| **Overview** | `/health`, `/api/metrics` | System status, alert counts, LLM engine health |
| **Incidents** | `/api/operator/incidents` | Alert feed with severity, evidence, actions |
| **Governance** | `/api/governance/*` | Mode control, pending approvals, audit history |
| **LLM Engines** | `/api/llm/status`, `/health` | Provider status, circuit breakers, cooldowns |
| **Kubernetes** | `/api/production-status` | Pod status, network policies, automation actions |
| **IoT Devices** | `/api/iot/devices`, `/api/iot/events` | Device registry, telemetry, security events |
| **Attack Simulation** | Client-side | One-click attack buttons + CLI script reference |

The dashboard auto-refreshes data every 30 seconds. Unauthenticated tabs (`/health`, `/api/metrics`) load immediately; authenticated tabs prompt for login.

---

## 9. Attack Simulation

### Dashboard Buttons

The Attack Simulation tab provides one-click attack triggers that POST pre-built alert payloads to `/api/alerts/internal`. These test the full pipeline without executing real attacks.

### CLI Pipeline Script

`scripts/attack-iot-pipeline.sh` executes 12 real attack scenarios against the running cluster:

1. Shell spawn in traffic-camera pod
2. `/etc/shadow` read in healthcare-api pod
3. License plate data exfiltration
4. Patient record exfiltration
5. SUID privilege escalation
6. DDoS flood simulation
7. Port scan detection
8. DNS exfiltration
9. Lateral movement
10. SQL injection probe
11. Cryptominer detection
12. MQTT message poisoning

Each scenario: executes the attack (or simulates it) → sends alert to IDS API → LLM analyzes → automated response applied. Run with `--quick` for a 5-scenario subset or `--scenario N` for a single test.

### External Attack Tools

`attack-simulator/` contains standalone Python scripts:
- `ddos_simulator.py` — multi-threaded HTTP flood
- `data_exfiltration.py` — simulated data theft
- `privilege_escalation.py` — container escape simulation
- `phase4-smart-city-attacks.py` — compound attack scenarios
