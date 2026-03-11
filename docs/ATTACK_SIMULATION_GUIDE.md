# Attack Simulation & Governance Guide

## Current deployment status (important)

In the current deployment, the **Attack Simulation UI tab/backend is not active**.

- The dashboard source indicates attack simulation UI was removed (`Attack Simulation removed: live attacks only`)
- `GET /api/attacks/registry` returns `404`
- `GET /api/demo/chaos/status` returns `404` (legacy route removed)

The supported and verified path for attack-chain evaluation is the CLI scenario runner:

- `scripts/run-live-attacks.sh`

This guide documents the **current operational path** (CLI-driven attacks + Governance controls + IDS API verification), not a removed UI feature.

---

## What is actually used for attack evaluation

The current attack-evaluation workflow is:

1. Generate attack-chain activity with `scripts/run-live-attacks.sh`
2. Let Suricata/Falco forwarders send detections to the IDS API
3. Process alerts through IDS pipeline (rate limiter -> dedup -> LLM -> governance)
4. Review outcomes in dashboard/API (`/api/alerts`, `/api/rate-limiter/status`, governance endpoints)

This is used for repeatable evaluation scenarios and validation runs in the smart-city IoT security testbed.

---

## Governance mode (Human in the Loop)

The Governance controls determine whether IDS-generated response actions execute automatically:

- **Manual**: every automated response requires approval
- **Assisted**: critical actions require approval; lower-risk actions can run automatically
- **Autonomous**: actions run automatically
- **Emergency**: threshold-based bypass for urgent containment

The queue view shows pending actions awaiting analyst approval/rejection.

---

## What “K8s automation” means

In this project, Kubernetes automation means response operations executed by the IDS API in-cluster, including:

- isolating suspicious pods,
- scaling selected workloads,
- and creating incident/response resources for traceability.

These actions are governed by mode and severity/confidence policy.

---

## How attacks are generated and how realistic they are

### Real execution vs. signature-driven simulation (honest model)

This project intentionally mixes **real cluster activity** with **detector-signature validation**. That is a valid research approach when the goal is to evaluate IDS pipeline behavior end-to-end without building unsafe production attack tooling.

#### Truly executed in the cluster

- Real HTTP requests to running IoT services (ClusterIP services such as traffic camera, healthcare API, parking system)
- Real `kubectl exec` commands inside running pods (shells, file reads, tooling probes) that generate Falco runtime telemetry
- Real MQTT publishes/subscribes against the live broker, including parking control-topic abuse
- Real state-changing protocol actions against emulator services:
  - Modbus-style register writes on environmental stations
  - DALI broadcast/off commands on street-lighting
  - ONVIF device/media/PTZ calls and snapshot scraping against traffic-camera
- Real Falco and Suricata detections (forwarded into the IDS API)
- Real IDS processing (rate limiting, deduplication, LLM analysis/cached analysis, governance, automation)

#### Signature/pattern validation (not a full exploit chain)

- Some Suricata detections are triggered by crafted payloads (e.g., SQLi strings) even if no real database exploit succeeds behind the endpoint
- Some attack-chain stages validate detection semantics (payload/rate/behavior) rather than persistence or destructive impact

### Why this is still realistic enough for a research testbed

- The telemetry and detections are generated from **real runtime/network activity**
- The scenarios map to real attacker goals (availability, confidentiality, integrity, operational disruption)
- The IDS response path (dedup -> LLM -> governance -> K8s actions) is exercised under live conditions
- Limitations are explicit and reproducible

## How to run each scenario step-by-step for an examiner

### Baseline verification (run first)

```bash
# Script name retained for compatibility
bash scripts/pre-demo-check.sh
curl -s http://localhost:30800/health | jq '{status,storage_type,components}'
```

Optional governance status check (auth required):

```bash
TOKEN=$(curl -s -X POST -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin"}' \
  http://localhost:30800/api/auth/login | jq -r '.access_token')
curl -s -H "Authorization: Bearer $TOKEN" \
  http://localhost:30800/api/governance/status | jq '{mode,metrics}'
```

### Scenario 1: Network pressure + SQLi indicators (Suricata-heavy)

**What it represents**
- High-rate HTTP pressure (availability attack behavior)
- SQL injection payload delivery attempts (application attack behavior)

**Targets**
- Traffic camera service (HTTP stream endpoint)
- Healthcare API (HTTP API routes)

**Command**
```bash
bash scripts/run-live-attacks.sh --mode all --duration 30 --show-alerts 3 --verbose
```

**What to watch**
- Suricata alerts in `/api/alerts`
- Dashboard live feed / alerts table
- Rate limiter status:
```bash
curl -s http://localhost:30800/api/rate-limiter/status | jq .
```

### Scenario 2: Runtime abuse / post-compromise behavior (Falco-heavy)

**What it represents**
- Shell usage in containers
- Sensitive file access
- Operator-tooling/package-manager probes (post-compromise activity patterns)

**Targets**
- Healthcare API, parking-system, traffic-camera pods

**Command**
```bash
bash scripts/run-live-attacks.sh --mode privesc --duration 20 --show-alerts 3 --verbose
```

**Expected detector**
- Falco

### Scenario 3: Collection / export behavior indicators

**What it represents**
- Suspicious export-style requests and collection attempts

**Targets**
- Parking/payment API paths

**Command**
```bash
bash scripts/run-live-attacks.sh --mode exfil --duration 20 --show-alerts 3 --verbose
```

### Scenario 4: Protocol-state tamper (MQTT / Modbus / DALI / ONVIF)

**What it represents**
- Unauthorized parking occupancy/fault control over MQTT
- Environmental AQI/status tamper through Modbus-style register writes
- Street-light blackout or forced dimming via DALI command abuse
- ONVIF camera enumeration, PTZ abuse, and snapshot scraping

**Targets**
- `mqtt-broker`
- `parking-system`
- `env-sensor`
- `street-lighting`
- `traffic-camera`

**Command**
```bash
bash scripts/run-live-attacks.sh --mode protocol --duration 30 --show-alerts 5 --verbose
```

**Expected detector**
- Suricata:
  - `SMARTCITY MQTT parking control topic abuse`
  - `SMARTCITY MQTT parking fault-state tamper`
  - `SMARTCITY MQTT parking occupancy spoof`
  - `SMARTCITY Modbus write tamper`
  - `SMARTCITY ONVIF capability enumeration`
  - `SMARTCITY ONVIF profile enumeration`
  - `SMARTCITY ONVIF PTZ control abuse`
  - `SMARTCITY ONVIF snapshot scraping`
  - `SMARTCITY ANPR data scraping`
- IDS API correlation / LLM analysis after detector ingestion

### Scenario 4: MQTT topic abuse / spoofed client behavior

**What it represents**
- MQTT wildcard traversal and unauthorized control-topic publish attempts
- Client-ID spoof/reconnect churn to emulate low-level broker abuse

**Targets**
- MQTT broker and MQTT-backed IoT services

**Command**
```bash
bash scripts/run-live-attacks.sh --mode mqtt --duration 30 --show-alerts 5 --verbose
```

**Expected detector**
- Suricata (network-pattern detections) and IDS API correlation output

### Safe rehearsal / examiner preview (no traffic execution)

Use `--dry-run` to print the planned steps and expected detections without executing cluster activity:

```bash
bash scripts/run-live-attacks.sh --mode all --duration 20 --dry-run --verbose
```

## Operational notes

- Attack execution is CLI-driven in the current deployment (`scripts/run-live-attacks.sh`), not from a dashboard attack tab.
- IoT fleet scaling is managed by scripts/operators, not from the dashboard.
- If live SSE feed is unavailable, dashboard polling continues automatically.
- “Runs this session” and “Events this session” are UI session counters and reset on dashboard reload.

## Historical note (to avoid confusion)

Older documentation or code comments may reference an Attack Simulation / Chaos UI and related backend routes. Those paths are not active in the current deployment. Use the CLI scenario runner and IDS API verification endpoints documented above.
