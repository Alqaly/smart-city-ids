# LLM Evaluation Canonical Method (Paper-Ready)

This is the canonical evaluation method for comparing LLM providers in Smart City IDS.
Use this document as the single source of truth for report tables/charts and supervisor evidence.

## 1) Scope and Truth Boundaries

- This is a **research testbed evaluation**, not a provider billing benchmark.
- All quality scores must be grounded in scenario expectations and analyst scoring rules.
- Cost values are **estimated** from token counts and configured per-1K token rates.
- Runtime availability can vary by key/quota/provider-side access; report the exact test date/time.

## 2) Active Data Sources (Current Implementation)

- Provider comparison: `GET /api/llm/providers/comparison`
- Provider status: `GET /api/llm/status` (auth)
- Usage/cost/tokens: `GET /api/metrics/llm-usage?window=today|7d|...` (auth)
- Alerts + parsed analysis: `GET /api/alerts?limit=N`
- Optional trace verification: `GET /api/audit/trace/<trace_id>`
- Export script: `scripts/llm-compare-report.py`
- Ground truth mappings: `docs/LLM_EVAL_GROUND_TRUTH_CORE.csv`

## 3) Required Metrics (Do Not Omit)

### Quality / Accuracy

- Severity range accuracy (`expected_severity_min/max` vs predicted severity)
- Threat-type correctness
- Action relevance score (1-5)
- Explanation usefulness score (1-5)

### Performance

- Average latency
- p50/p95 latency
- Timeout rate
- Throughput (alerts/min over test window)

### Reliability

- Success rate
- Error rate by taxonomy (401/429/5xx/timeout/network)
- Circuit breaker events / cooldown status
- Failover behavior evidence

### Cost

- Prompt tokens, completion tokens, total tokens
- Estimated cost per alert
- Estimated cost per 1000 alerts
- Cost-vs-latency tradeoff

### Operational Safety

- False-high severity rate
- False-low severity rate
- Unsafe automation recommendation rate
- Consistency on repeated alerts

## 4) Canonical Tables for the Paper

### Table A: Provider Summary

Columns:

- Provider
- Model
- Success Rate (runtime)
- Avg Latency (ms)
- p95 Latency (ms)
- Avg Tokens/Alert
- Avg Estimated Cost/Alert
- Severity Accuracy (%)
- Threat-Type Accuracy (%)
- Action Relevance (1-5)
- Safety Calibration Score (%)

### Table B: Scenario-Level Results

Rows are scenarios (for example: HTTP flood, SQLi payload, runtime shell abuse, MQTT topic traversal).

Columns:

- Expected severity range
- Expected threat type
- Provider outputs (severity / threat / action)
- Notes (over-escalated, under-escalated, best rationale)

### Table C: Reliability Under Failure

Columns:

- Provider
- Invalid key behavior
- Quota/rate-limit behavior
- Timeout behavior
- Circuit/cooldown observed
- Fallback successor success (Y/N)

## 5) Canonical Charts for the Paper

- Bar: average latency by provider
- Bar: success rate by provider
- Bar: estimated cost per 1000 alerts
- Scatter: estimated cost vs latency
- Stacked bar: error taxonomy by provider
- Heatmap: scenario family vs provider quality score

## 6) Fixed Execution Procedure

1. Ensure stack health:
   - `curl -s http://localhost:30800/health | jq .`
2. Run representative scenarios / ingest real alerts.
3. Export data:
   - `python3 scripts/llm-compare-report.py --api-url http://localhost:30800 --username admin --password admin --alerts-limit 300 --ground-truth docs/LLM_EVAL_GROUND_TRUTH_CORE.csv --out-dir artifacts/llm-eval/latest`
4. Use generated CSV outputs for report tables and chart generation.
5. Record test timestamp window in the report.

## 7) Strict Provider Diagnostics (Important)

Per-provider tests can silently pass due to fallback if strict mode is disabled.

- Use strict mode in diagnostics to verify true provider health:
  - `POST /api/llm/test/{provider}?strict=true`
- Expected evidence fields:
  - `strict_requested`
  - `strict_satisfied`
  - `failed_engines`
  - actual `provider` used

## 8) Reporting Language (Allowed vs Not Allowed)

Allowed:

- "Estimated cost based on token usage and configured rates"
- "Provider X configured but zero successful calls in this window"
- "Fallback to provider Y observed when strict test failed for provider X"

Not allowed:

- "All providers operational" without strict-test evidence
- "Real billing cost" when using estimates
- "Production-grade reliability" without long-run failure testing evidence
