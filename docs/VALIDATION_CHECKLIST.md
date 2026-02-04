# Validation Checklist

This checklist provides reproducible steps to validate IDS performance and run replay tests for the Capstone demonstration.

## Objectives
- Replay attack scenarios with ground-truth labels
- Measure IDS detection (precision, recall, F1, AUC)
- Validate automation safety (dry-run vs assisted vs autopilot)

## 1) Environment
- Ensure `KUBECONFIG` points to the demo cluster (single-node K3s)
- IDS API, Prometheus, and Grafana should be running

## 2) Set safe automation mode

```bash
export AUTOMATION_MODE=assisted
```

## 3) Replay attack scenarios (example)

Use the attack-simulations scripts to generate labeled traffic. Each run produces a ground-truth JSON file in `scalability-results/` when run with `--label <label>`.

Example: send 50 DDoS-like alerts

```bash
cd attack-simulations
./generate-network-attacks.sh --count 50 --label DDoS
```

## 4) Record ground-truth

Collect the generated ground-truth file (e.g. `scalability-results/ddos_2026-02-03.json`). This file contains timestamps and expected labels.

## 5) Query Prometheus for detected alerts

Prometheus can be queried via HTTP API or `kubectl port-forward`.

Example Prometheus query (last 10 minutes):

```
sum(ids_alerts_received_total{job="ids-api"})
```

Count alerts by threat type over last 10m:

```
sum by (threat_type) (ids_alerts_received_total{job="ids-api"}[10m])
```

## 6) Compute precision/recall (local script)

A simple Python script can compare ground-truth timestamps/labels with detected alerts pulled from the Prometheus API or IDS API `/api/alerts` history.

Example (pseudo):

1. Load ground-truth events -> list of (ts, label)
2. Load detected events -> list of (ts, predicted_label)
3. Match events within a time-window (e.g., ±5s)
4. Compute TP, FP, FN, precision, recall, F1

Save results to `scalability-results/metrics_summary.json`.

## 7) Expected outcomes (demo-level)
- Precision: >= 0.6 (varies by scenario)
- Recall: >= 0.5 (varies by scenario)
- LLM latency p95: < 2s for cached results, < 5s for cold calls
- Deduplicator hit-rate: >40% during storms

## 8) Safety checks
- Verify `AUTOMATION_MODE=assisted` prevents autopilot isolation without approval
- Check `k8s_automation` logs for `[DRY-RUN]` entries if using `dry-run`

## 9) Reporting
- Store all artifacts in `scalability-results/` and include in demo artifacts tarball
- Record Prometheus snapshot and Grafana dashboard image for slides

---

Notes:
- This is a reproducible checklist for Capstone-level evaluation. For rigorous academic experiments, increase repetitions, add cross-validation folds, and record resource usage (CPU, RAM) per run.
