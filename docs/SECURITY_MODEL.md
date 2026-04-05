# Security Model

Security boundaries, threat model, and governance controls for the Smart City IDS.

## Scope

The project is designed to evaluate:
- runtime and network detections
- LLM-assisted alert interpretation
- governance-controlled automated response
- protocol-aware IoT attack scenarios in Kubernetes

It is not designed to claim:
- full production hardening
- complete physical-device realism
- complete real-world exploit-chain coverage for every scenario

## Threat model

### In scope
- suspicious shell execution
- sensitive file access
- protocol misuse
- network flooding or repeated request pressure
- outbound behavior linked to exfiltration or command-and-control
- unauthorized control operations against IoT-facing services

### Out of scope
- real zero-day weaponization
- physical compromise chains for all devices
- full native ICS/OT fidelity across every service

## Detection model

### Falco
Covers runtime/container behavior such as:
- shell spawns
- sensitive file reads
- suspicious command execution

### Suricata
Covers network and protocol patterns such as:
- MQTT misuse
- Modbus-style tamper patterns
- ONVIF misuse and enumeration
- HTTP and other network signatures

## Reality boundary

### Real execution
Executed for real in the cluster:
- HTTP requests to live services
- MQTT traffic to the live broker
- state-changing actions against emulator services
- runtime actions that trigger Falco telemetry
- IDS ingestion, analysis, governance, and Kubernetes response logic

### Signature-driven validation
Some detections validate recognizable malicious patterns rather than full backend compromise. That is acceptable in this testbed if stated explicitly.

## Automation safety

Governance modes:
- `manual`
- `assisted`
- `autonomous`

Safety controls include:
- action approval paths
- protected services
- audit traces
- separable force-autonomy testing profile

## IoT realism model

The IoT layer is best described as:
- protocol-faithful software emulation with state models

It is not accurate to describe the full fleet as:
- a fully physical deployment
- a fully native industrial protocol deployment for every service

## Verification sources

Use live evidence, not assumptions:

```bash
bash scripts/readiness-check.sh
bash scripts/test-governance-modes.sh
bash scripts/readiness-check.sh
bash scripts/run-live-attacks.sh --mode protocol --duration 30 --show-alerts 8 --verbose
```

And inspect:
- `/api/alerts`
- `/api/governance/status`
- `/api/llm/diagnostics`
- `/api/iot/devices`

## Safe claims

- The system demonstrates end-to-end alert analysis and governed response in a live Kubernetes testbed.
- The system mixes real detector telemetry with bounded signature-driven validation.
- The system supports protocol-aware emulation for selected smart-city workloads.
- The system includes explicit governance controls for automated actions.

## Claims to avoid

- “Production ready” without qualification
- “All attacks are full real exploit chains”
- “All emulators are equivalent to physical hardware”
- “All providers are operational” without current diagnostics
