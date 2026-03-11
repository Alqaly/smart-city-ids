# Review Guide

This document summarizes what the current Smart City IDS implementation does, what evidence exists in the live system, and what remains a research-testbed limitation.

## 1. System classification

The current system is best described as a:
- Kubernetes-based smart-city IoT security research testbed
- protocol-faithful software emulation environment
- IDS pipeline with governance-controlled response automation

It is not accurately described as:
- a production smart-city deployment
- a pure physical-device fleet
- a zero-trust or formally verified autonomous SOC

## 2. What is live and verifiable now

### Detection and ingestion
- Falco runtime detections are forwarded into the IDS pipeline.
- Suricata network detections are forwarded into the IDS pipeline.
- Alerts are persisted in PostgreSQL and exposed through the dashboard/API.
- Rate limiting, deduplication, LLM analysis, governance, and Kubernetes action execution are active.

### Governance and automation
- Governance modes `manual`, `assisted`, and `autonomous` are implemented and testable.
- Manual mode queues actions for approval.
- Assisted mode auto-executes high-confidence actions and leaves other actions gated.
- Autonomous mode can operate conservatively by default, with a separate force-execution profile exposed through governance controls.

### LLM analysis
- Multi-provider routing is implemented.
- Provider health, diagnostics, failover state, token/cost usage, and strict provider tests are exposed.
- In the current live stack, provider availability depends on real API keys and billing/quota status.

### IoT / protocol realism
- Parking system performs real MQTT broker interaction.
- Environmental sensor exposes Modbus-style write tamper behavior and a native OPC UA server endpoint.
- Traffic camera exposes ONVIF-like device/media/PTZ services and can be exercised through protocol-specific requests.
- Street-lighting exposes stateful DALI/TALQ-style control behavior.

## 3. What has been validated on the live stack

The following have been run against the live deployment during recent validation passes:

```bash
bash scripts/check-setup.sh
bash scripts/pre-demo-check.sh
bash scripts/demo-readiness.sh --quick
bash scripts/test-governance-modes.sh
bash scripts/e2e-verbose-test.sh --quick
bash scripts/run-live-attacks.sh --mode protocol --duration 10 --show-alerts 12 --verbose
```

Governance and end-to-end action validation require at least one operational LLM provider. If all providers are unavailable, these scripts fail early with the live diagnostics payload instead of producing a misleading governance result.

Observed live outcomes included:
- successful auth and protected-endpoint access
- readiness, auth, and protocol attack paths working on the live stack
- governance mode/action-path validation when at least one LLM provider is operational
- protocol-specific Suricata alerts for:
  - MQTT parking control abuse
  - MQTT occupancy/fault tamper
  - Modbus write tamper
  - ONVIF capability enumeration
  - ANPR data scraping

## 4. Claims that are justified

The following claims are supportable from the current implementation:
- The system demonstrates end-to-end IDS processing from detector alert to LLM-supported response decision.
- The system demonstrates human-in-the-loop governance over automated response actions.
- The system demonstrates protocol-aware IoT service emulation beyond generic random telemetry.
- The system supports comparative LLM evaluation using measurable quality, latency, reliability, cost, and safety fields.

## 5. Claims that should not be overstated

The following need careful wording:
- Do not claim full production readiness.
- Do not claim physical-device fidelity for the whole fleet.
- Do not claim zero-day detection.
- Do not claim all protocol attacks map to deep exploit chains; some are detector-oriented protocol abuse scenarios.
- Do not claim all five LLM providers are operational unless the live diagnostics currently show that.

## 6. Recommended evaluation framing

A defensible reviewer framing is:
- research-grade IDS and governance testbed
- real Kubernetes deployment
- real detector ingestion and response workflow
- protocol-faithful emulation for selected smart-city services
- bounded, explicitly documented realism limits

## 7. Current limitations

- `ids-api` is still effectively single-replica for correctness because key controls remain pod-local.
- Some forwarder components still install Python dependencies at startup, which is operationally inefficient.
- Logical IoT device persistence is improved but still depends on accurate device registration/heartbeat behavior.
- Several provider states are limited by external billing/quota/auth problems rather than code capability.

## 8. Current recommended deploy/update path

```bash
bash scripts/apply-llm-env-to-k8s-secret.sh .env
sudo bash scripts/start-everything.sh
bash scripts/deploy-code.sh
bash scripts/access-stack.sh start
bash scripts/pre-demo-check.sh
```

## 9. Evidence sources

Use these for technical review:
- `docs/API_REFERENCE.md`
- `docs/ATTACK_SIMULATION_GUIDE.md`
- `docs/reference/LLM_EVALUATION_CANONICAL.md`
- `docs/IOT_EMULATION_REPORT.md`
- live API:
  - `/health`
  - `/api/alerts`
  - `/api/governance/status`
  - `/api/llm/diagnostics`
  - `/api/iot/telemetry`
