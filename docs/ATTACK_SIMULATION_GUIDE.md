# Attack Simulation & Governance Guide

## What this tab does

The Attack Simulation tab is a controlled test harness for the IDS pipeline:

1. Inject a realistic simulated alert
2. Run LLM threat analysis
3. Apply governance policy (manual / assisted / autonomous / emergency)
4. Trigger Kubernetes response actions only if governance allows

It is designed for demos, validation, and conference/public GitHub reproducibility.

---

## Scope of scenario applicability

The 67 scenarios are mapped to the current Smart City IDS emulated services (traffic camera, MQTT broker, healthcare API, parking system, environment sensor, street lighting, etc.).

They are **not automatically universal to any future IoT service** unless that service is mapped to:

- a target workload name,
- expected telemetry/rule patterns,
- and governance/automation actions.

To extend for new IoT services, add new scenario definitions in `attack-simulator/scenario_registry.py` and map target/rule semantics to the new workload.

---

## Governance mode (Human in the Loop)

The Governance tab controls action execution policy:

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

## Operational notes

- IoT fleet scaling is managed by scripts/operators, not from the Attack tab UI.
- If live SSE feed is unavailable, dashboard polling continues automatically.
- “Runs this session” and “Events this session” are UI session counters and reset on dashboard reload.
