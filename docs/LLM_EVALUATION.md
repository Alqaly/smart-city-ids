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

This means the current runtime state is sufficient for expanded strict comparison runs that include Anthropic and Gemini, but runtime stability must still be checked at run time because provider availability can change between executions.

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

## 17. Expanded Five-Provider Attempt: `strict-real-03`

This run was executed after the Gemini model was corrected to `gemini-2.5-flash` and Anthropic was already operational. It is the current largest artifact-backed strict comparison attempt in the repository.

### 17.1 Dataset summary

Source:

- `artifacts/llm-eval/strict-real-03/README.json`

Measured values:

- distinct matched alerts used: `16`
- provider attempts: `80`
- successful strict evaluations: `64`
- failed strict evaluations: `16`
- scenario families scored: `8`
- providers requested: `anthropic`, `gemini`, `kimi`, `openai`, `xai`
- providers with scored rows: `anthropic`, `gemini`, `openai`, `xai`

### 17.2 Provider results

| Provider | Model | Distinct Alerts Scored | Success Rate | Avg Latency (ms) | P95 Latency (ms) | Cost / 1000 Alerts (USD) | Cost / 1M Tokens (USD) | Quality Score | Severity Accuracy | Threat Accuracy | Action Relevance | Safety Proxy |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Anthropic | `claude-sonnet-4-20250514` | 16 | 100.00% | 5122.4 | 5770.0 | 15.01 | 16.00 | 65.00% | 93.75% | 31.25% | 3.75 / 5 | 96.35% |
| Gemini | `gemini-2.5-flash` | 16 | 100.00% | 6108.6 | 6711.0 | 1.43 | 0.87 | 21.00% | 12.50% | 0.00% | 4.00 / 5 | 50.00% |
| OpenAI | `gpt-4o` | 16 | 100.00% | 3347.1 | 4459.0 | 7.69 | 10.00 | 70.00% | 100.00% | 37.50% | 3.75 / 5 | 100.00% |
| xAI | `grok-4-latest` | 16 | 100.00% | 21304.9 | 27096.0 | 17.48 | 7.72 | 72.50% | 100.00% | 43.75% | 3.75 / 5 | 100.00% |
| Kimi | `moonshot-v1-128k` | 0 | 0.00% | N/A | N/A | N/A | 0.00 | N/A | N/A | N/A | N/A | N/A |

### 17.3 Interpretation

The expanded five-provider attempt supports the following findings:

- Anthropic and Gemini now complete strict scored evaluation successfully against the live backend.
- OpenAI remains the fastest of the scored providers in this expanded run.
- xAI again shows the strongest measured quality score, but at much higher latency.
- Gemini is inexpensive and reliable in this run, but its scored output quality is materially weaker than the other successful providers.
- Kimi contributed zero scored rows because all 16 strict attempts failed with provider overload.

This means `strict-real-03` is useful as a current five-provider attempt, but it does not replace `strict-real-01` as the primary balanced comparison artifact because one requested provider failed all attempts.

## 18. Current Provider Framing

The current evidence supports the following provider status framing.

| Provider | Model Used | Evidence Status |
|---|---|---|
| Kimi | `moonshot-v1-128k` | scored successfully in `strict-real-01`; provider overload in `strict-real-02` and `strict-real-03` |
| OpenAI | `gpt-4o` | scored successfully in `strict-real-03`; earlier artifacts used `gpt-3.5-turbo` |
| xAI | `grok-4-latest` | scored successfully in all strict artifacts where it was requested |
| Anthropic | `claude-sonnet-4-20250514` | scored successfully in `strict-real-02` and `strict-real-03` |
| Gemini | `gemini-2.5-flash` | scored successfully in `strict-real-03` after the live model/config fix |

## 19. Limitations

The current study has the following limits.

- the primary balanced comparison (`strict-real-01`) still covers `3` scored providers, not `5`
- the expanded five-provider attempt (`strict-real-03`) scored `4` providers; Kimi failed all requested attempts under provider overload
- Anthropic and Gemini required later follow-up runs to appear in scored artifacts
- the completed runs used `runs=1`, not a repeatability design
- the largest current strict attempt used `16` distinct matched alerts across `8` scenario families, not a `500 x 5-provider` study
- some attack stages validate protocol-recognizable malicious behavior rather than full exploit chains
- the ground-truth rubric is explicit and frozen, but it remains a human-authored evaluation reference

## 20. Safe Conclusions

The current artifact-backed evidence supports these conclusions.

- Kimi is the strongest measured quality-cost tradeoff in `strict-real-01`.
- OpenAI is the fastest measured provider in the current expanded strict run where Anthropic and Gemini also scored.
- xAI remains the slowest provider in every strict run where it scored and should be treated cautiously in latency-sensitive workflows.
- Anthropic and Gemini are now both operational and can be included in future strict comparison runs.
- Kimi is currently the main blocker to a stable five-provider comparison because of provider-side overload during longer strict runs.

## 21. What Remains To Be Done

To complete the larger study, the following work remains:

- run a repeatability pass with `runs >= 3`
- stabilize Kimi so that all five requested providers score in the same artifact
- execute the full `500 x 5-provider` strict comparison
- expand the scenario set beyond the current completed coverage

## 22. Public Summary

The current artifact-backed LLM study compares providers on one fixed task: analysis of stored IDS alerts. The primary balanced comparison (`strict-real-01`) evaluated Kimi, OpenAI, and xAI against the same stored alert set with fallback disabled and database persistence disabled. A later inclusion run (`strict-real-02`) confirmed that Anthropic can score successfully. The latest expanded attempt (`strict-real-03`) requested all five providers and produced scored rows for Anthropic, Gemini, OpenAI, and xAI across 16 matched alerts and 8 scenario families, while Kimi failed all attempts because of provider overload. This means the repository now contains a real five-provider attempt, but not yet a stable five-provider completed comparison.
