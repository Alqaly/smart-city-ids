# How It Works

End-to-end explanation of the current Smart City IDS pipeline.

## 1. Activity happens in the cluster

The cluster runs IoT-style workloads such as:
- traffic camera
- healthcare API
- parking system
- environmental sensor
- street lighting
- MQTT broker

These workloads generate normal traffic, protocol activity, and controlled attack behavior.

## 2. Detection engines observe that activity

### Falco
Falco detects runtime and syscall behavior such as:
- shell spawns
- sensitive file reads
- suspicious tooling inside containers

### Suricata
Suricata detects network and protocol patterns such as:
- MQTT misuse
- Modbus-style tamper patterns
- ONVIF enumeration or scraping
- HTTP abuse and other network signatures

## 3. Forwarders normalize the alerts

Falco and Suricata do not write directly into the dashboard.

Instead:
- Falco -> Falco forwarder -> ids-api
- Suricata -> Suricata forwarder -> ids-api

The forwarders reshape detector output into the IDS alert schema before sending it into the backend.

## 4. ids-api processes the alert

When an alert arrives, the IDS backend applies:
- intake validation
- rate limiting
- deduplication
- analysis routing

If the alert is a duplicate, the backend can reuse earlier analysis instead of calling an LLM again.

## 5. Analysis happens

If the alert is not served from dedup/cache, the backend tries to analyze it.

Possible analysis paths:
- live LLM provider
- cached result
- deterministic/rule-based fallback path where applicable

Provider behavior depends on live runtime state:
- operational
- unverified
- cooldown
- auth failed
- other error states

Check current state with:

```bash
curl -s http://localhost:30800/api/llm/diagnostics | jq .
```

## 6. Governance decides whether action is allowed

Governance modes:
- `manual`
- `assisted`
- `autonomous`

Meaning:
- manual -> actions wait for approval
- assisted -> policy-approved actions may run automatically, others wait
- autonomous -> policy-approved actions run automatically

Validate the real behavior with:

```bash
bash scripts/test-governance-modes.sh
```

## 7. Kubernetes actions may run

Examples:
- isolate a workload
- create a scoped block-IP policy
- alert the team

These actions are governed and audited. They are not executed blindly from the detector alone.

## 8. Everything is stored and displayed

Results are persisted in PostgreSQL and then exposed through:
- `/api/alerts`
- `/api/metrics`
- `/api/iot/devices`
- `/ui`

## 9. How to see it live

Fast readiness:

```bash
bash scripts/pre-demo-check.sh
```

Processed event stream:

```bash
bash scripts/live-pipeline-log.sh --attacks
```

Raw component logs:

```bash
SINCE=5m bash scripts/tail-pipeline-pods.sh
```

## 10. Important boundaries

- Not every alert is a full real exploit chain.
- Some protocol detections validate recognizable malicious behavior rather than full backend compromise.
- Logical IoT registry rows are not proof of live hardware.
- LLM availability is a live operational condition, not a fixed architectural guarantee.
