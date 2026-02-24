# Scenario Spec — FHIR Tamper + Clinical Impact

Last updated: 2026-02-24

Purpose: provide a staged, examiner-defensible scenario around healthcare API misuse/tampering using the current Smart City IDS implementation (FHIR-like API emulator + Suricata/Falco + IDS pipeline + governance/dashboard).

## 1. Scenario Goal

Demonstrate that the Smart City IDS can:
- detect suspicious application-layer requests targeting the healthcare API,
- correlate network and runtime signals into a meaningful security event,
- analyze alerts with an LLM and produce an explainable severity/recommendation,
- and communicate **clinical impact risk** (integrity / patient safety concern) in the operator workflow.

This scenario focuses on detection + analysis + response pipeline evidence, not clinical system certification.

## 2. Scope (Current Components Used)

- `healthcare-api` deployment (FHIR R4-style vulnerable Flask API)
- Suricata + `suricata-forwarder` (HTTP attack pattern detection)
- Falco + `falco-forwarder` (runtime shell/file/tooling anomaly detection if runtime stage is included)
- IDS API (`/api/alerts/internal`, dedup, LLM, governance, persistence, SSE)
- Dashboard:
  - Alerts table (grouped + context)
  - LLM trace / parsed output
  - Automation control + governance mode

## 3. ATT&CK / ATT&CK-ICS Style Framing (Research Mapping)

| Stage | Intent | Current project behavior |
|---|---|---|
| Initial access / abuse | Malicious or malformed requests to healthcare API | `run-live-attacks.sh` SQLi/app-abuse traffic against healthcare endpoints |
| Execution / tampering attempt | Modify or query sensitive records with suspicious payloads | HTTP payloads and endpoint access patterns trigger Suricata signatures |
| Discovery / operator abuse (optional) | Compromised container inspection / data reads | Falco-triggering `kubectl exec` shell/file read behavior |
| Impact (clinical risk) | Integrity risk to patient treatment context | LLM analysis summarizes severity and recommends containment/investigation |

Note:
- The current emulator and IDS are strongest at **threat signal generation and response pipeline validation**.
- Fine-grained FHIR semantic validation (e.g., profile conformance / dosage rule engine) is a next-step enhancement.

## 4. Stages (What to Run / What to Expect)

### Stage A — Baseline Healthcare API + IDS Health

Objective:
- Confirm healthcare API and IDS pipeline are healthy before tamper simulation.

Useful commands:
```bash
curl -s http://localhost:30800/health | jq
kubectl get pods -n smart-city -l app=healthcare-api
kubectl exec -n smart-city deploy/ids-api -- sh -lc "curl -s localhost:8000/api/governance/status" | jq
```

Expected observables:
- `healthcare-api` pods running
- IDS API healthy
- Governance mode visible (`manual`, `assisted`, or `autonomous`)

### Stage B — Application-Layer Abuse Toward FHIR/Healthcare Endpoints

Objective:
- Trigger Suricata and application-layer detections against the healthcare API.

Current implementation path:
- `scripts/run-live-attacks.sh --mode sqli` (or `all`) sends suspicious payloads to healthcare endpoints
- Suricata signatures match SQLi-like request content and flood conditions if load is high

Useful commands:
```bash
bash scripts/run-live-attacks.sh --duration 10 --mode sqli --show-alerts 3
curl -s "http://localhost:30800/api/alerts?limit=20" | jq '.alerts[] | select((.source//\"\") == \"suricata\") | {time, rule, severity, source}'
```

Expected telemetry:
- `suricata` alerts referencing SQLi / healthcare-target requests
- dedup and/or rate-limiter activity if repeated payloads fire identical signatures

Success criteria:
- At least one healthcare-targeted Suricata alert persists in IDS
- The alert is visible in the dashboard alerts table with source + rule + summary

### Stage C — Runtime Abuse (Optional but Stronger Viva Demonstration)

Objective:
- Show a second signal source (Falco) tied to the healthcare app pod for correlation context.

Useful commands:
```bash
kubectl exec -n smart-city deploy/healthcare-api -- /bin/sh -lc 'id; cat /etc/passwd >/dev/null; env | head -5 >/dev/null'
kubectl logs -n falco-system daemonset/falco --since=2m | tail -n 20
```

Expected telemetry:
- Falco alerts for shell execution / sensitive file read / suspicious tooling behavior (depending on image contents and rules)

Success criteria:
- Falco alert appears in IDS and is distinguishable from Suricata (source field = `falco`)

### Stage D — LLM Analysis + Clinical Impact Narrative

Objective:
- Show the system converts low-level detections into a meaningful operator-facing explanation with healthcare context.

Expected IDS behavior:
- LLM (or cached analysis) assigns severity and threat type
- Recommendations include investigation/containment actions
- Governance mode determines whether action is proposed vs executed

Useful commands:
```bash
curl -s "http://localhost:30800/api/alerts?limit=10" | jq '.alerts[] | {rule, source, severity, llm_engine, analysis_present}'
TOKEN=$(curl -s -X POST -H 'Content-Type: application/json' -d '{"username":"admin","password":"admin"}' http://localhost:30800/api/auth/login | jq -r '.access_token')
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:30800/api/governance/status | jq
```

Dashboard talking point:
- “This is not only a SQLi signature. The IDS pipeline explains why this is a healthcare integrity risk and what containment steps are appropriate in the current governance mode.”

Success criteria:
- An analyzed alert exists (`analysis_present: true`)
- Provider/engine is visible (`llm_engine` or `cached`)
- Governance status can be shown and explained

## 5. Expected Telemetry by Layer

### Suricata
- SQLi-style rule hits against healthcare endpoints
- Possible flood signatures if repeated high-rate requests are used

### Falco (optional stage)
- Shell execution inside `healthcare-api` container
- Sensitive file reads or suspicious tooling execution

### IDS API
- Normalized alerts (`source`, `rule`, `severity`, `summary`)
- Dedup / throttling behavior under repeated patterns
- LLM analysis metadata and trace
- Governance action proposal/execution counters

### Dashboard
- Grouped alert row with source/rule/where-context
- LLM parsed output + raw trace (for new alerts)
- Automation mode and governance counters

## 6. Clinical Impact Framing (Examiner-Safe)

Current claim (accurate):
- The system demonstrates **detection + analysis + operator decision support** for healthcare API tampering risk.

Do not overclaim:
- It does **not** currently implement a full FHIR semantic validator or medication safety rules engine.

Research-grade next step:
- Add FHIR resource/profile validation and domain-specific anomaly checks (e.g., dosage bounds, schema/profile conformance) before action escalation.

## 7. Known Limitations

- Current attack traffic is adversarial application traffic against healthcare endpoints, not a complete FHIR workflow replay with clinician/user identity context.
- Clinical impact is inferred by alert context and LLM analysis, not computed by a dedicated medical safety engine.

## 8. Next Upgrade Path

1. Add FHIR resource-specific tamper fixtures (Patient, Observation, MedicationRequest).
2. Add semantic validation stage (schema/profile + dosage sanity checks).
3. Add explicit “clinical risk” dashboard metric (e.g., integrity-risk count / high-risk records impacted).
4. Add replayable evidence bundle (request -> alert -> LLM trace -> governance decision).

