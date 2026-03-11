# LLM Evaluation

## 1. Study Scope

This document is the canonical record of the LLM evaluation conducted for the Smart City IDS.
It documents the implemented evaluation path, the frozen parameters, the measured artifacts, the scoring method, and the limits of the current evidence.

The evaluation covers one task only:

- structured analysis of stored IDS alerts

It does not evaluate generic conversational quality.

## 2. Research Objective

The objective of the study is to compare LLM providers on the same IDS-analysis task under controlled conditions.
For each stored alert, the provider is expected to return a structured response containing:

- summary
- severity (`1` to `10`)
- threat type
- confidence
- reasoning
- analyst recommendations
- automated action proposals

The response schema is enforced by the live backend and is defined by the current implementation in:

- `services/ids-api/src/llm_manager.py`
- `services/ids-api/src/llm_response_schema.py`
- provider-specific prompt builders such as:
  - `services/ids-api/src/llm_engine_openai.py`
  - `services/ids-api/src/llm_engine_xai.py`
  - `services/ids-api/src/llm_engine_gemini.py`

## 3. Experimental Environment

The study uses the live Smart City IDS stack:

- IDS API at `http://localhost:30800`
- PostgreSQL-backed alert storage
- Falco and Suricata alert ingestion
- protocol-faithful IoT service emulation
- attack generation through `scripts/run-live-attacks.sh`
- strict alert reanalysis through `POST /api/alerts/{id}/reanalyze`
- frozen ground truth from `docs/reference/LLM_EVAL_GROUND_TRUTH_CORE.csv`

No separate benchmark harness or synthetic prompt-only testbed was used for the measured runs documented here.

## 4. Materials Used In The Study

The study used the following concrete project components.

| Component | Role In The Evaluation |
|---|---|
| `scripts/run-live-attacks.sh` | generates real cluster activity and fresh alerts |
| `scripts/llm-compare-report.py` | executes strict reanalysis and writes evaluation artifacts |
| `docs/reference/LLM_EVAL_GROUND_TRUTH_CORE.csv` | frozen ground-truth labels and scenario mappings |
| `POST /api/alerts/{id}/reanalyze` | strict, non-persistent per-provider evaluation path |
| `GET /api/alerts` | source of stored alerts used for provider comparison |
| `GET /api/llm/diagnostics` | provider readiness and runtime-state verification |
| `artifacts/llm-eval/strict-real-01` | primary completed comparison artifact |
| `artifacts/llm-eval/strict-real-02` | Anthropic inclusion follow-up artifact |

The study therefore depends on the real runtime stack, the stored alert corpus, the frozen ground-truth file, and the strict reanalysis endpoint.

## 5. Dataset Construction

The evaluation dataset is derived from the live IDS pipeline rather than from manually written prompts.
The process is:

1. `scripts/run-live-attacks.sh` generates real cluster activity.
2. Falco and Suricata produce alerts from that activity.
3. The IDS API stores those alerts and their analysis records.
4. The evaluation script reads stored alerts from the live backend.
5. Stored alerts are matched against the frozen ground-truth CSV.
6. Matching alerts are re-analyzed provider by provider in strict mode.

This design ensures that the evaluation is performed on the same alert objects used by the operational system.

## 6. Frozen Parameters

The following conditions were fixed within each strict evaluation run:

- same stored alert set for all providers included in that run
- same backend prompt/template path
- same response schema
- same ground-truth CSV
- same scoring rubric
- `strict=true`
- `persist=false`
- `runs=1`
- direct provider rows only for quality scoring
- cache-hit rows excluded from direct provider quality scoring

Important correction:

- the system was not evaluated at `temperature = 0`
- the configured runtime value is `LLM_TEMPERATURE=0.3`

## 7. Provider Invocation Protocol

The strict evaluation path uses:

```text
POST /api/alerts/{id}/reanalyze?engine=<provider>&strict=true&persist=false
```

Meaning:

- `strict=true`
  - disables provider fallback
  - the requested provider must answer directly
  - failed or fallback-contaminated rows are excluded from quality scoring

- `persist=false`
  - prevents the evaluation run from overwriting the original operational alert analysis in the database

This invocation contract is the basis for a defensible provider comparison.

## 8. Study Procedure

The completed study workflow was:

1. Verify that the live IDS API, authentication path, and provider diagnostics are reachable.
2. Refresh the recent alert window with controlled attack activity.
3. Pull recent stored alerts from the live IDS backend.
4. Match stored alerts against the frozen ground-truth CSV.
5. Balance the selected alerts with `--max-per-family`.
6. Re-analyze each alert against one provider at a time with fallback disabled.
7. Record one raw row per provider-attempt.
8. Compute per-row scoring fields.
9. Aggregate provider-level and scenario-level summaries.
10. Export CSV, JSON, and chart artifacts.

## 9. Evaluation Commands

### 9.1 Provider and platform readiness

```bash
bash scripts/llm-manager.sh check
curl -s http://localhost:30800/health | jq .
curl -s http://localhost:30800/api/llm/diagnostics | jq .
```

### 9.2 Alert-window refresh before strict comparison

```bash
bash scripts/run-live-attacks.sh --mode protocol --duration 12 --show-alerts 8 --verbose
```

### 9.3 Completed three-provider comparison

```bash
python3 scripts/llm-compare-report.py \
  --api-url http://localhost:30800 \
  --username admin \
  --password admin \
  --alerts-limit 400 \
  --ground-truth docs/reference/LLM_EVAL_GROUND_TRUTH_CORE.csv \
  --strict-eval \
  --providers kimi,openai,xai \
  --runs 1 \
  --max-per-family 2 \
  --out-dir artifacts/llm-eval/strict-real-01
```

### 9.4 Anthropic inclusion follow-up

```bash
python3 scripts/llm-compare-report.py \
  --api-url http://localhost:30800 \
  --username admin \
  --password admin \
  --alerts-limit 400 \
  --ground-truth docs/reference/LLM_EVAL_GROUND_TRUTH_CORE.csv \
  --strict-eval \
  --providers anthropic,kimi,openai,xai \
  --runs 1 \
  --max-per-family 2 \
  --out-dir artifacts/llm-eval/strict-real-02
```

### 9.5 Future five-provider target

```bash
python3 scripts/llm-compare-report.py \
  --api-url http://localhost:30800 \
  --username admin \
  --password admin \
  --alerts-limit 1200 \
  --ground-truth docs/reference/LLM_EVAL_GROUND_TRUTH_CORE.csv \
  --strict-eval \
  --providers anthropic,gemini,kimi,openai,xai \
  --runs 1 \
  --max-per-family 20 \
  --out-dir artifacts/llm-eval/strict-5providers-run
```

This command should not be cited as completed unless all five providers are simultaneously operational and the artifact is present.

## 10. What `scripts/llm-compare-report.py` Does

The evaluation script performs the following steps:

1. authenticates to the live IDS API
2. retrieves recent stored alerts
3. loads the frozen ground-truth CSV
4. matches alerts to ground-truth rule patterns
5. balances the selected set with `--max-per-family`
6. re-analyzes each alert against one provider at a time using strict mode
7. stores one raw row per provider-attempt in `strict_eval_raw_results.csv`
8. computes per-row scoring fields for successful strict rows
9. aggregates provider-level and scenario-level summaries
10. writes CSV tables, JSON summaries, and chart PNGs into the output directory

This is why the artifact directory is sufficient to defend the study: it contains both raw evidence and derived summaries.

## 11. Artifact Inventory

Each evaluation artifact directory contains:

- `README.json`
- `strict_eval_raw_results.csv`
- `scenario_alert_scoring_template.csv`
- `provider_summary_scored.csv`
- `provider_scorecard_ranked.csv`
- `scenario_family_results_scored.csv`
- `charts/*.png`

Completed runs also contain validation appendices:

- `VALIDATION_REPORT.md`
- `validation_evidence.json`
- `slide_alignment.json`

## 12. Metrics

### 12.1 Quality metrics

- severity accuracy
- threat-type accuracy
- action relevance score
- composite quality score

### 12.2 Performance metrics

- average latency
- p95 latency

### 12.3 Cost metrics

- total tokens
- estimated total cost
- estimated cost per alert
- estimated cost per 1000 alerts
- estimated cost per 1M tokens

### 12.4 Safety and reliability metrics

- strict success rate
- false-high severity rate
- false-low severity rate
- OT under-escalation rate
- unsafe action recommendation rate
- safety calibration proxy

## 13. Metric Computation

### 13.1 Provider attempts and success rate

Source file:

- `strict_eval_raw_results.csv`

Rules:

- attempt = one raw row
- success = `status == success` and `strict_satisfied == true`
- failure = any row not meeting the success rule
- success rate = `strict_success / attempts`

### 13.2 Latency

Source field:

- `latency_s`

Reported values are computed from successful strict rows only.

### 13.3 Token usage and cost

Source fields:

- `prompt_tokens`
- `completion_tokens`
- `total_tokens`
- `estimated_cost_usd`

Derived values:

- cost per alert = `estimated_cost_usd_total / strict_success`
- cost per 1000 alerts = `cost per alert * 1000`
- cost per 1M tokens = derived from the script's token-rate table

### 13.4 Quality scoring

Source file:

- `scenario_alert_scoring_template.csv`

Per-row fields:

- `severity_in_range_score_0_1`
- `threat_type_match_score_0_1`
- `action_relevance_score_1_to_5`
- `false_high_severity_0_1`
- `false_low_severity_0_1`
- `weighted_false_low_penalty`
- `unsafe_action_recommendation_0_1`

## 14. Current Runtime Readiness

At the time of the latest runtime verification, the provider states were:

- `anthropic`
  - strict test passed
  - provider operational
- `kimi`
  - operational
- `openai`
  - configured and unverified in the current process
- `xai`
  - configured and unverified in the current process
- `gemini`
  - strict test failed with `429 quota exceeded`

This means the current runtime state is sufficient for Anthropic-backed follow-up evaluation, but Gemini still cannot be treated as part of a completed scored comparison.

## 15. Primary Measured Run: `strict-real-01`

This is the primary completed artifact-backed comparison.

### 12.1 Dataset summary

Source:

- `artifacts/llm-eval/strict-real-01/README.json`

Measured values:

- distinct matched alerts used: `14`
- provider attempts: `42`
- successful strict evaluations: `41`
- failed strict evaluations: `1`
- scenario families scored: `7`
- cache-hit rows included in direct provider quality scoring: `0`

Scenario families:

- `anpr_exfiltration`
- `lateral_movement_or_platform_access`
- `modbus_write_tamper`
- `mqtt_misuse`
- `onvif_misuse`
- `onvif_recon`
- `runtime_shell`

### 12.2 Provider results

| Provider | Model | Distinct Alerts Scored | Success Rate | Avg Latency (ms) | P95 Latency (ms) | Cost / 1000 Alerts (USD) | Cost / 1M Tokens (USD) | Quality Score | Severity Accuracy | Threat Accuracy | Action Relevance | Safety Proxy |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Kimi | `moonshot-v1-8k` | 14 | 100.00% | 3729.6 | 5320.0 | 5.00 | 6.00 | 70.86% | 100.00% | 42.86% | 3.43 / 5 | 100.00% |
| OpenAI | `gpt-3.5-turbo` | 14 | 100.00% | 2277.4 | 3054.0 | 7.65 | 10.00 | 65.14% | 100.00% | 28.57% | 3.43 / 5 | 100.00% |
| xAI | `grok-4-latest` | 13 | 92.86% | 25488.9 | 28854.0 | 17.58 | 7.90 | 62.77% | 84.62% | 38.46% | 3.38 / 5 | 94.87% |

### 12.3 Interpretation

The primary completed run supports the following findings:

- Kimi produced the strongest measured quality-cost tradeoff.
- OpenAI produced the lowest measured latency.
- xAI remained usable, but was materially slower and less reliable than the other two scored providers.
- Severity accuracy was consistently stronger than threat-type accuracy across the scored providers.

## 16. Anthropic Inclusion Run: `strict-real-02`

This run was executed after the Anthropic API key was corrected.
It should be treated as an inclusion update rather than a replacement for `strict-real-01`.

### 13.1 Dataset summary

Source:

- `artifacts/llm-eval/strict-real-02/README.json`

Measured values:

- distinct matched alerts used: `16`
- provider attempts: `64`
- successful strict evaluations: `48`
- failed strict evaluations: `16`
- scenario families scored: `8`
- providers requested: `anthropic`, `kimi`, `openai`, `xai`
- providers with scored rows: `anthropic`, `openai`, `xai`

### 13.2 Provider results

| Provider | Model | Distinct Alerts Scored | Success Rate | Avg Latency (ms) | P95 Latency (ms) | Cost / 1000 Alerts (USD) | Cost / 1M Tokens (USD) | Quality Score | Severity Accuracy | Threat Accuracy | Action Relevance | Safety Proxy |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Anthropic | `claude-sonnet-4-20250514` | 16 | 100.00% | 5182.8 | 5851.0 | 14.90 | 16.00 | 65.00% | 93.75% | 31.25% | 3.75 / 5 | 98.12% |
| OpenAI | `gpt-3.5-turbo` | 16 | 100.00% | 2022.3 | 2733.0 | 7.42 | 10.00 | 67.50% | 100.00% | 31.25% | 3.75 / 5 | 100.00% |
| xAI | `grok-4-latest` | 16 | 100.00% | 21454.0 | 25781.0 | 17.40 | 7.88 | 72.50% | 100.00% | 43.75% | 3.75 / 5 | 100.00% |

### 13.3 Kimi status in this run

Kimi contributed zero scored rows in `strict-real-02`.
All 16 strict Kimi attempts failed with provider overload:

- `429 engine_overloaded_error`

This means:

- Anthropic can now be included in future strict comparisons
- `strict-real-02` does not replace `strict-real-01` as the main completed comparison artifact

## 17. Current Provider Framing

The current evidence supports the following provider status framing.

| Provider | Model Used | Evidence Status |
|---|---|---|
| Kimi | `moonshot-v1-8k` | scored successfully in `strict-real-01`; provider overload in `strict-real-02` |
| OpenAI | `gpt-3.5-turbo` | scored successfully in both strict artifacts |
| xAI | `grok-4-latest` | scored successfully in both strict artifacts |
| Anthropic | `claude-sonnet-4-20250514` | scored successfully in `strict-real-02` |
| Gemini | `gemini-2.0-flash` | not currently evaluable due quota/cooldown |

## 18. Limitations

The current study has the following limits.

- the main completed comparison covers `3` scored providers, not `5`
- `Gemini` was not usable during the evaluation window because of quota/cooldown
- Anthropic required a later inclusion run
- the completed runs used `runs=1`, not a repeatability design
- the main comparison used `14` distinct matched alerts across `7` scenario families, not a `500 x 5-provider` study
- some attack stages validate protocol-recognizable malicious behavior rather than full exploit chains
- the ground-truth rubric is explicit and frozen, but it remains a human-authored evaluation reference

## 19. Safe Conclusions

The current artifact-backed evidence supports these conclusions.

- Kimi is the strongest measured quality-cost tradeoff in `strict-real-01`.
- OpenAI is the fastest measured provider in the completed strict runs where it scored.
- xAI remains the slowest provider in the completed strict runs and should be treated cautiously in latency-sensitive workflows.
- Anthropic is now operational and can be included in future strict comparison runs.
- Gemini remains outside the completed evaluation because of quota/cooldown.

## 20. What Remains To Be Done

To complete the larger study, the following work remains:

- run a repeatability pass with `runs >= 3`
- stabilize Gemini and Kimi at the same time
- execute the full `500 x 5-provider` strict comparison
- expand the scenario set beyond the current completed coverage

## 21. Public Summary

The current artifact-backed LLM study compares providers on one fixed task: analysis of stored IDS alerts. The completed main comparison (`strict-real-01`) evaluated Kimi, OpenAI, and xAI against the same stored alert set with fallback disabled and database persistence disabled. In that run, Kimi produced the best measured quality-cost balance, OpenAI produced the lowest latency, and xAI remained usable but significantly slower. A later follow-up run (`strict-real-02`) confirmed that Anthropic can now participate in strict scored evaluation. Gemini is still excluded from the completed study because it was unavailable due quota/cooldown during the evaluation window.
