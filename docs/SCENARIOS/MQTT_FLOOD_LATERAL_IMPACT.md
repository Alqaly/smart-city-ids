# Scenario Spec — MQTT Flood + Lateral Movement + Impact

Last updated: 2026-04-05

Examiner-defensible staged scenario spec using the current implementation (Suricata + Falco + IDS API + governance + dashboard), framed in a research-style structure.

## 1. Scenario Goal

Demonstrate that the Smart City IDS can:
- detect noisy IoT abuse (MQTT/HTTP flood-like behavior),
- identify runtime abuse in application containers (Falco),
- analyze alerts through the LLM pipeline,
- and show/justify defensive response decisions in governance mode.

This scenario is designed as a staged exercise, not a claim of full ICS attack emulation.

## 2. Scope (Current Components Used)

- `mqtt-broker` (Mosquitto in `smart-city` namespace)
- IoT services (`traffic-camera`, `parking-system`, `healthcare-api`, etc.) generating normal traffic/telemetry
- Suricata (`monitoring` namespace) + `suricata-forwarder`
- Falco (`falco-system` namespace) + `falco-forwarder`
- IDS API (`ids-api`) pipeline:
  - queue / request concurrency
  - alert throttling (rate limiter)
  - dedup cache
  - LLM analysis
  - governance / K8s automation
  - DB + SSE dashboard

## 3. ATT&CK-ICS / ATT&CK-Style Framing (Research Mapping)

This mapping is used for examiner discussion and scenario traceability. It is a staged interpretation of the current demo pipeline.

| Stage | Intent | Current project behavior |
|---|---|---|
| Initial abuse / execution | Adversary starts high-rate traffic from compromised source | `scripts/run-live-attacks.sh` generates network attack traffic observed by Suricata |
| Discovery / recon (optional) | Container/operator abuse inside app pod | Runtime shell / sensitive file access via `kubectl exec` paths in attack runner |
| Lateral movement signal | East-west service access attempts / unusual app-to-app activity | Cluster-internal service calls + Falco/Suricata telemetry + IDS correlation |
| Impact / disruption | Availability degradation / flood condition | Suricata `SMARTCITY HTTP flood` and dashboard pipeline metrics; governance actions may be proposed/executed |

Note:
- The current repo is strongest at **detection + analysis + response pipeline validation**.
- Full ATT&CK-ICS semantic protocol attacks (e.g., deep protocol state manipulation) are future work.

## 4. Stages (What to Run / What to Expect)

### Stage A — Baseline + Normal Telemetry

Objective:
- Establish that the system is live and dashboards are showing real data.

Expected observables:
- Dashboard reachable at `/ui`
- `ids-api` health is healthy
- IoT telemetry cards return normal readings
- LLM provider control shows at least one usable provider (typically Kimi in current environment)

Useful commands:
```bash
bash scripts/readiness-check.sh
curl -s http://localhost:30800/health | jq
curl -s http://localhost:30800/api/iot/telemetry | jq '.services | keys'
```

### Stage B — Network Abuse (MQTT/HTTP Flood-Like Traffic)

Objective:
- Trigger Suricata detections with enough volume to show flood handling without collapsing the dashboard.

Current implementation path:
- `scripts/run-live-attacks.sh` -> Phase 1 network attacks
- Suricata signatures + thresholds -> `suricata-forwarder` -> `/api/alerts/internal`

Expected telemetry:
- Suricata alerts in IDS (`SMARTCITY HTTP flood`, SQLi signatures depending on mode)
- Dedup hits increase
- Alert throttling counters increase
- Live feed shows representative alerts, not every duplicate (throttled duplicates are suppressed from SSE)

Useful commands:
```bash
bash scripts/run-live-attacks.sh --duration 10 --show-alerts 3
curl -s http://localhost:30800/api/deduplicator-stats | jq
curl -s http://localhost:30800/api/rate-limiter/status | jq
```

Success criteria:
- Alert flood is visible but controlled.
- IDS remains responsive.
- Dashboard does not get flooded with every duplicate row.

### Stage C — Runtime Abuse / Lateral-Movement Signal

Objective:
- Trigger Falco with runtime actions consistent with compromised-container behavior.

Current implementation path:
- `scripts/run-live-attacks.sh` Phase 2 uses `kubectl exec` to run commands inside IoT app pods
- Falco eBPF rules detect shell/file-read/runtime anomalies

Expected telemetry:
- Falco alerts for shell/file access / sensitive reads
- Forwarded alerts tagged as Falco source
- Dashboard grouped alerts show pod/container/namespace context

Useful commands:
```bash
# Manual demonstration variant (if needed)
kubectl exec -n smart-city deploy/healthcare-api -- /bin/sh -lc 'cat /etc/passwd >/dev/null; cat /etc/shadow >/dev/null || true'
kubectl logs -n falco-system daemonset/falco --since=2m
```

Success criteria:
- Falco alert appears in IDS API / dashboard
- Alert details include where it happened (namespace/pod/container)

### Stage D — LLM Analysis + Governance Decision

Objective:
- Show alert analysis and response recommendation path, including provider selection/failover diagnostics.

Current implementation path:
- IDS API analyzes alert with LLM provider manager
- Governance mode (`manual` / `assisted` / `autonomous`) controls action execution behavior
- Automation/audit state visible in Automation tab and governance endpoints

Expected telemetry:
- Alert has `analysis_present = true`
- `llm_engine` stored (`kimi`, `openai`, etc., or `cached`)
- LLM trace available for new alerts (prompt / raw response / parsed output)
- Governance status returns action counters and mode

Useful commands:
```bash
TOKEN=$(curl -s -X POST -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin"}' \
  http://localhost:30800/api/auth/login | jq -r '.access_token')

curl -s "http://localhost:30800/api/alerts?limit=5" | jq '.alerts[0]'
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:30800/api/governance/status | jq
curl -s http://localhost:30800/api/llm/diagnostics | jq
```

Success criteria:
- An analyzed alert shows provider/cached engine metadata
- Governance mode is visible and can be explained (manual/assisted/autonomous)
- LLM Control Center shows provider state (including failures/circuit breaker if present)

## 5. Expected Telemetry by Layer (Examiner Answer Cheat Sheet)

### Suricata (network)
- Signature alerts (e.g., `SMARTCITY HTTP flood`, SQLi signatures)
- Burst/flood behavior visible in alert volume
- Thresholding + IDS-side throttling prevent UI spam

### Falco (runtime)
- Container shell execution
- Sensitive file reads
- Other tuned runtime anomalies based on custom rules

### IDS API
- Alert source normalization (`falco` vs `suricata`)
- Dedup stats + throttling stats
- LLM analysis metadata (`llm_engine`, parsed output, trace)
- Governance mode + automation counters
- SSE live feed for operator UI

### Dashboard
- Grouped alerts table (duplicates collapsed)
- LLM Provider Control (health/usage/failover)
- Automation Control (mode and action counts)
- Live feed and pipeline overview metrics

## 6. Known Limitations (state this if pushed)

- The scenario currently mixes ATT&CK-style staging with demo attack scripts; not every stage is a protocol-semantic ICS exploit.
- Device count shown on dashboard is still demo-oriented / pod-derived, not a persistent logical fleet registry.
- Multi-replica `ids-api` requires shared dedup/throttle state (Redis or similar) for correct scaling behavior.

## 7. Next Upgrade Path (one scenario first, not all at once)

If expanding this scenario for research depth:
1. Formalize ATT&CK-ICS mappings per stage (with technique IDs and rationale).
2. Add protocol-correct MQTT reconnect storm vs malicious flood differentiation.
3. Add explicit domain impact KPI (e.g., telemetry ingestion delay / service availability degradation).
4. Add replayable scenario fixtures (same alert stream, same expected metrics).

