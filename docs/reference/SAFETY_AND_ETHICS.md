# Safety, Ethics, and Containment (Cluster-Only Attacks)

This project contains intentionally malicious *simulated attack injections* for academic IDS evaluation. The safety goal is: **no impact outside the Kubernetes test environment**.

## Scope boundary

- Attacks are intended to execute **only inside the `smart-city` namespace**.
- No external targets should be contacted.
- Any “exfiltration” or “C2” is modeled as *telemetry* (alerts/log content) rather than real outbound data transfer.

## Network containment

Kubernetes NetworkPolicies are provided in:
- `k8s-manifests/network-policies.yaml`

Recommended audit procedure before demos / defenses:

1. Confirm policies exist and are applied:
   - `kubectl get networkpolicy -n smart-city`
2. Validate the intended pods are selected by policy selectors:
   - `kubectl describe networkpolicy -n smart-city <name>`
3. Confirm no broad “allow all egress” is present for IoT workloads.
4. If your cluster uses CNI that enforces NetworkPolicy (Calico/Cilium/etc), verify enforcement is enabled.

## Resource exhaustion safeguards

To avoid “demo attacks” turning into accidental denial-of-service:

- Prefer bounded loops and rate limits in scripts.
- Keep Kubernetes resource `requests/limits` on forwarders/monitoring components (many manifests already include them).
- For attack runners, use explicit caps (e.g., max duration, max packets, max concurrent workers) and log chosen parameters.

## Reset to baseline

For attacks that “tamper” with emulated state, provide a reset procedure.

Baseline practice in this repo:
- Re-deploy workloads from manifests (stateless services reset by pod restart)
- For stateful components (e.g., PostgreSQL), restore from seeded data or re-init the volume

If you add future attacks that mutate persisted datasets, document a specific reset script for that service.

## Ethics / IRB notes

For thesis defenses, the usual justification is:

- The system is deployed on an isolated test cluster.
- Attacks are performed on your own emulated services.
- No real personal data is processed.

If your institution requires an IRB/ethics submission, include this file and the NetworkPolicy audit steps as supporting evidence.

## Reproducibility

For external reviewers:

- Scenario registry is deterministic: `attack-simulator/scenario_registry.py`
- Coverage appendix can be regenerated:
  - `scripts/generate_attack_coverage_matrix.py`

If you need a “single command” reproducibility package (compose/vagrant), document it as a separate track because it changes deployment assumptions.

## Performance budgets

If LLM latency affects timing expectations, document baseline budgets (p50/p95/p99) for:

- alert ingestion → analysis completion
- governance decision latency
- action execution latency

This project’s attack simulation is primarily about **semantic detection and response**, not microsecond-accurate timing.
