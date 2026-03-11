# Security Model

This document describes the current security and attack-model assumptions for the Smart City IDS research testbed.

## 1. Scope

The system is designed to evaluate:
- runtime and network detection behavior
- LLM-supported alert analysis
- governance-controlled response automation
- protocol-aware IoT attack scenarios in a Kubernetes testbed

It is not designed to:
- attack real third-party systems
- emulate undisclosed exploits
- claim complete production hardening

## 2. Threat model

### Adversary behaviors in scope
- suspicious shell execution in containers
- credential/file access attempts
- protocol abuse against exposed smart-city services
- network flooding and repeated request pressure
- outbound connection patterns associated with exfiltration or command-and-control
- unauthorized control operations against IoT-facing services

### Adversary behaviors out of scope
- real zero-day weaponization
- physical hardware compromise chains
- full ICS/OT protocol fidelity for every service in the project

## 3. Detection model

### Falco
Falco covers runtime/syscall behaviors such as:
- shell spawns
- sensitive file reads
- downloader/package-manager execution
- suspicious tooling inside containers

### Suricata
Suricata covers network/protocol patterns such as:
- SQLi-like payload delivery
- HTTP flood behavior
- MQTT parking control abuse
- Modbus write tamper
- ONVIF enumeration and scraping patterns
- ANPR scraping

## 4. Reality boundary

### Real execution
The following are executed for real in the cluster:
- HTTP requests to live services
- MQTT traffic to the live broker
- state-changing protocol operations against emulator services
- `kubectl exec` runtime actions that trigger Falco telemetry
- IDS ingestion, LLM analysis, governance, and Kubernetes response logic

### Signature-driven validation
Some detections still validate recognizable malicious patterns rather than full backend exploitation. Examples include:
- SQLi string delivery without proving a real database compromise
- protocol misuse detection without a full long-lived adversary campaign

This is an accepted research-testbed approach if the limitation is stated explicitly.

## 5. Automation safety model

The system uses governance modes:
- `manual`
- `assisted`
- `autonomous`

Safety controls include:
- protected services
- approval queue in manual paths
- separable force-execution profile for full autonomy testing
- action audit traces

## 6. IoT realism model

The emulator fleet is best described as:
- protocol-faithful software emulation with state models

It is not accurate to describe the whole fleet as:
- purely physical-device emulation
- fully native industrial protocol deployment across all services

Current stronger realism areas:
- parking MQTT gateway behavior
- environmental sensor Modbus-style state tamper
- environmental sensor native OPC UA endpoint
- traffic camera ONVIF-like device/media/PTZ behavior
- street-lighting stateful control behavior

## 7. Verification sources

Runtime behavior should be verified from the live system, not assumed from documentation alone.

Use:
- `bash scripts/pre-demo-check.sh`
- `bash scripts/test-governance-modes.sh`
- `bash scripts/e2e-verbose-test.sh --quick`
- `bash scripts/run-live-attacks.sh --mode protocol --duration 30 --show-alerts 8 --verbose`

And inspect:
- `/api/alerts`

Governance and action-path validation depend on real LLM analysis. If all providers are unavailable, these checks cannot demonstrate mode gating.
- `/api/governance/status`
- `/api/llm/diagnostics`
- `/api/iot/telemetry`

## 8. Claims that are safe to make

- The system demonstrates end-to-end alert analysis and response control in a live Kubernetes testbed.
- The system mixes real detector telemetry with bounded signature-driven attack validation.
- The system supports protocol-aware emulation for selected smart-city workloads.
- The system includes explicit governance controls for automated actions.

## 9. Claims to avoid

- “Production ready” without qualification
- “All attacks are fully real exploit chains”
- “All emulators are equivalent to physical hardware”
- “All providers are operational” without current diagnostics
