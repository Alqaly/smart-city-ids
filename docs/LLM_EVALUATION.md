# LLM Evaluation

## 1. Purpose

This document is the canonical record of the Smart City IDS LLM evaluation.
It explains:

- what was implemented
- how the evaluation was executed
- what `python3 scripts/llm-compare-report.py` actually does
- which parameters were frozen during the run
- which artifact directories contain the measured results
- what can be claimed safely in the report and presentation

This document uses only artifact-backed results.
It does not treat spreadsheet values or slide text as evidence.

## 2. Executive Summary

Two artifact-backed strict evaluation runs currently matter:

1. `artifacts/llm-eval/strict-real-01`
   - completed 3-provider comparison
   - included: `kimi`, `openai`, `xai`
   - 14 distinct matched alerts
   - 42 provider-attempts
   - 41 successful strict evaluations
   - 7 scenario families

2. `artifacts/llm-eval/strict-real-02`
   - Anthropic inclusion run
   - requested: `anthropic`, `kimi`, `openai`, `xai`
   - 16 distinct matched alerts
   - 64 provider-attempts
   - 48 successful strict evaluations
   - 8 scenario families
   - Anthropic, OpenAI, and xAI scored successfully
   - Kimi failed all 16 strict attempts in that run because the provider returned `429 engine_overloaded_error`

Current live readiness at the time of this update:

- `anthropic`: strict test passes
- `openai`: strict test passes
- `xai`: strict test passes
- `kimi`: operational but vulnerable to overload/cooldown under heavier evaluation load
- `gemini`: blocked by quota / cooldown

A complete `500 x 5-provider` study has not yet been completed.

## 3. What `python3 scripts/llm-compare-report.py` Means

This command runs the repository's LLM evaluation program.
It is not a generic Python command.
It is a project-specific script that:

1. logs into the live IDS API
2. reads recent stored alerts from the platform
3. matches those alerts against the frozen ground-truth CSV
4. optionally re-runs each stored alert against selected providers in strict mode
5. writes raw rows, scored CSV tables, JSON summaries, and chart PNGs into an artifact directory

In plain language:

- the script takes real alerts already stored by the IDS
- it sends the same alert to one provider at a time
- it records latency, tokens, estimated cost, and output fields
- it scores those outputs against the predefined ground truth
- it builds the tables and charts used in the report

## 4. System Components Used In The Evaluation

The evaluation uses the live Smart City IDS stack:

- IDS API at `http://localhost:30800`
- PostgreSQL-backed alert storage
- Falco and Suricata alert ingestion
- protocol-faithful service emulation and runtime attack generation
- the reanalysis endpoint in `services/ids-api/src/api/alerts.py`
- the evaluation script `scripts/llm-compare-report.py`
- the frozen ground truth file `docs/reference/LLM_EVAL_GROUND_TRUTH_CORE.csv`

No mock harness was used for the measured runs documented here.

## 5. Frozen Evaluation Parameters

These parameters were held fixed during the strict comparative runs.

Common fixed parameters:

- same stored alert records within a given artifact run
- same production alert-analysis path
- same prompt/template path used by the IDS backend
- same ground-truth CSV
- same scoring rubric
- `strict=true`
- `persist=false`
- `runs=1`
- no cache-hit rows included in direct provider quality scoring

Important correction:

- the system was **not** run at `temperature = 0`
- the current configured value is `LLM_TEMPERATURE=0.3`
- therefore the correct documentation is `temperature = 0.3`, not `temperature = 0`

## 6. Why `strict=true` and `persist=false` Matter

The evaluation depends on one API path:

```text
POST /api/alerts/{id}/reanalyze?engine=<provider>&strict=true&persist=false
```

Meaning:

- `strict=true`
  - disables provider fallback
  - the requested provider must answer itself
  - if fallback or failure occurs, the row is excluded from quality scoring

- `persist=false`
  - prevents the evaluation run from overwriting the original alert analysis stored in the operational database

This is what makes the evaluation safe and defensible.

## 7. Implementation Steps

The evaluation implementation followed these steps.

1. Verified that the IDS API and provider diagnostics were reachable:

```bash
bash scripts/llm-manager.sh check
curl -s http://localhost:30800/health | jq .
curl -s http://localhost:30800/api/llm/diagnostics | jq .
```

2. Confirmed that the reanalysis endpoint supported strict, non-persistent execution:

```bash
TOKEN=$(curl -s -X POST http://localhost:30800/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin"}' | jq -r '.access_token')

curl -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  'http://localhost:30800/api/alerts/1/reanalyze?engine=openai&strict=true&persist=false' \
  -d '{}' | jq .
```

3. Expanded the frozen ground-truth file so the current live protocol attack families were covered:

- MQTT misuse
- Modbus write tamper
- ONVIF reconnaissance
- ONVIF misuse
- ANPR exfiltration
- runtime shell / lateral-movement families
- SQLi / network DoS families where present in the live window

4. Refreshed the alert window with real attack activity before the strict runs:

```bash
bash scripts/run-live-attacks.sh --mode protocol --duration 12 --show-alerts 8 --verbose
```

5. Ran strict comparative evaluation through `scripts/llm-compare-report.py`.

6. Validated the generated artifact directories by recomputing counts and checking the raw rows.

## 8. Canonical Commands

### 8.1 Completed 3-provider comparison

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

### 8.2 Anthropic inclusion run

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

### 8.3 Large-scale target command

This is the real command structure for a future `500 x 5-provider` study:

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

This command is only valid for final reporting if all five providers are simultaneously operational.

## 9. Meaning Of Each Command Option

| Option | Meaning |
|---|---|
| `--api-url` | IDS API base URL |
| `--username`, `--password` | credentials used to obtain a bearer token |
| `--alerts-limit` | number of recent alerts pulled from the IDS before filtering |
| `--ground-truth` | frozen CSV used for matching and scoring |
| `--strict-eval` | re-runs stored alerts against selected providers with fallback disabled |
| `--providers` | comma-separated provider list for the strict comparison |
| `--runs` | repeat count per alert per provider |
| `--max-per-family` | maximum number of alerts retained per scenario family |
| `--out-dir` | output directory for CSV, JSON, and charts |

## 10. Artifact Contents

Each artifact directory contains:

- `README.json`
  - run summary
- `strict_eval_raw_results.csv`
  - one raw row per provider-attempt
- `scenario_alert_scoring_template.csv`
  - per-alert scored rows against ground truth
- `provider_summary_scored.csv`
  - provider summary table
- `provider_scorecard_ranked.csv`
  - ranked provider scorecard
- `scenario_family_results_scored.csv`
  - scenario-family summary table
- `charts/*.png`
  - chart outputs

Validation appendices are also present for the completed runs:

- `VALIDATION_REPORT.md`
- `validation_evidence.json`
- `slide_alignment.json`

## 11. How The Metrics Are Measured

### 11.1 Provider attempts and success rate

Source file:

- `strict_eval_raw_results.csv`

Rules:

- attempt = one raw row
- success = `status == success` and `strict_satisfied == true`
- failure = any row not meeting the success rule
- success rate = `strict_success / attempts`

### 11.2 Latency

Source field:

- `latency_s`

Reported values:

- average latency from successful strict rows only
- p95 latency from successful strict rows only

### 11.3 Token usage and cost

Source fields:

- `prompt_tokens`
- `completion_tokens`
- `total_tokens`
- `estimated_cost_usd`

Derived values:

- cost per alert = `estimated_cost_usd_total / strict_success`
- cost per 1000 alerts = `cost per alert * 1000`
- cost per 1M tokens = derived from the script's token-rate table, not manual spreadsheet numbers

### 11.4 Quality scoring

Source file:

- `scenario_alert_scoring_template.csv`

Per-row fields used:

- `severity_in_range_score_0_1`
- `threat_type_match_score_0_1`
- `action_relevance_score_1_to_5`
- `false_high_severity_0_1`
- `false_low_severity_0_1`
- `weighted_false_low_penalty`
- `unsafe_action_recommendation_0_1`

Composite quality score:

```text
severity accuracy * 0.4
+ threat accuracy * 0.4
+ normalized action relevance * 0.2
```

Safety proxy combines:

- under-escalation penalty
- false-high severity penalty
- unsafe-action penalty

## 12. Completed Run: `strict-real-01`

### 12.1 Dataset summary

Source:

- `artifacts/llm-eval/strict-real-01/README.json`

Measured values:

- distinct matched alerts used: `14`
- provider attempts: `42`
- successful strict evaluations: `41`
- failed strict evaluations: `1`
- scenario families: `7`
- providers scored: `kimi`, `openai`, `xai`

Scenario families:

- `anpr_exfiltration`
- `lateral_movement_or_platform_access`
- `modbus_write_tamper`
- `mqtt_misuse`
- `onvif_misuse`
- `onvif_recon`
- `runtime_shell`

### 12.2 Provider results

Source:

- `artifacts/llm-eval/strict-real-01/provider_summary_scored.csv`

| Provider | Model | Scored Alerts | Success Rate | Avg Latency | p95 Latency | Tokens | Cost / Alert | Cost / 1000 Alerts | Severity Accuracy | Threat Accuracy | Action Relevance | Quality Score | Safety Proxy |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Kimi | `moonshot-v1-8k` | 14 | 100.00% | 3.7296s | 5.32s | 11,667 | $0.005000 | $5.00 | 100.00% | 42.86% | 3.4286 / 5 | 70.86% | 100.00% |
| OpenAI | `gpt-3.5-turbo` | 14 | 100.00% | 2.2774s | 3.054s | 10,713 | $0.007652 | $7.65 | 100.00% | 28.57% | 3.4286 / 5 | 65.14% | 100.00% |
| xAI | `grok-4-latest` | 13 | 92.86% | 25.4889s | 28.854s | 28,943 | $0.017584 | $17.58 | 84.62% | 38.46% | 3.3846 / 5 | 62.77% | 94.87% |

### 12.3 Interpretation

This artifact supports these claims:

- Kimi provided the strongest quality-cost balance in the completed 3-provider run.
- OpenAI was the fastest successful provider.
- xAI was usable but much slower and less reliable than the other two providers.

This artifact does **not** support:

- a 5-provider comparison
- a 500-attempt study
- a repeatability study

## 13. Anthropic Inclusion Run: `strict-real-02`

### 13.1 Why this run exists

After the Anthropic API key was updated, a new strict comparison was executed to verify whether Anthropic could participate in a real scored evaluation.

### 13.2 Dataset summary

Source:

- `artifacts/llm-eval/strict-real-02/README.json`

Measured values:

- distinct matched alerts used: `16`
- provider attempts: `64`
- successful strict evaluations: `48`
- failed strict evaluations: `16`
- scenario families: `8`
- providers requested: `anthropic`, `kimi`, `openai`, `xai`
- providers that actually scored rows: `anthropic`, `openai`, `xai`

Scenario families:

- `anpr_exfiltration`
- `modbus_write_tamper`
- `mqtt_misuse`
- `network_dos`
- `onvif_misuse`
- `onvif_recon`
- `runtime_shell`
- `sqli`

### 13.3 Provider results

Source:

- `artifacts/llm-eval/strict-real-02/provider_summary_scored.csv`

| Provider | Model | Scored Alerts | Success Rate | Avg Latency | p95 Latency | Tokens | Cost / Alert | Cost / 1000 Alerts | Severity Accuracy | Threat Accuracy | Action Relevance | Quality Score | Safety Proxy |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Anthropic | `claude-sonnet-4-20250514` | 16 | 100.00% | 5.1828s | 5.851s | 14,897 | $0.014897 | $14.90 | 93.75% | 31.25% | 3.75 / 5 | 65.00% | 98.12% |
| OpenAI | `gpt-3.5-turbo` | 16 | 100.00% | 2.0223s | 2.733s | 11,875 | $0.007422 | $7.42 | 100.00% | 31.25% | 3.75 / 5 | 67.50% | 100.00% |
| xAI | `grok-4-latest` | 16 | 100.00% | 21.4540s | 25.781s | 35,334 | $0.017402 | $17.40 | 100.00% | 43.75% | 3.75 / 5 | 72.50% | 100.00% |

### 13.4 Kimi result in this run

Kimi was requested in `strict-real-02`, but contributed zero scored rows.
All 16 strict Kimi attempts failed with provider overload:

- provider-side error: `429 engine_overloaded_error`
- dashboard state during validation: `cooldown` / `circuit open`

Therefore:

- `strict-real-02` proves Anthropic is now able to score real alerts
- `strict-real-02` does **not** replace `strict-real-01` as the final Kimi comparison artifact

### 13.5 Interpretation

This artifact supports these claims:

- Anthropic is no longer only an infrastructure-failure case.
- Anthropic completed a strict scored run successfully.
- OpenAI and xAI remained operational in the same run.
- Kimi became an infrastructure failure in this specific run due provider overload, not due model-quality scoring.

## 14. Provider Overview For Reporting

This is the correct current provider framing.

| Provider | Model actually used | Current role in system | Evidence status |
|---|---|---|---|
| Anthropic | `claude-sonnet-4-20250514` | candidate analysis provider | scored successfully in `strict-real-02` |
| Gemini | `gemini-2.0-flash` | budget / optional provider | not currently evaluable due quota / cooldown |
| Kimi | `moonshot-v1-8k` | primary low-cost provider | scored successfully in `strict-real-01`; failed in `strict-real-02` due overload |
| OpenAI | `gpt-3.5-turbo` | low-latency fallback / comparison baseline | scored successfully in both strict artifacts |
| xAI | `grok-4-latest` | diversity / fallback provider | scored successfully in both strict artifacts, but with high latency |

Important distinction:

- Anthropic and Gemini should only be documented as infrastructure failures **when that is what the artifact shows**.
- Anthropic is no longer an infrastructure failure in the current state.
- Gemini remains an infrastructure failure because the live strict test still fails due quota / cooldown.

## 15. Corrections To The Current Study Plan

The proposed study structure is good, but several facts must be corrected before using it in the report or slides.

### 15.1 Correct items

These parts of the plan are structurally correct:

- provider overview by model and role
- frozen parameters section
- RQ1 quality
- RQ2 cost and latency
- RQ3 reliability
- RQ4 safety
- scenario-level discussion
- limitations section
- recommended configuration section
- future larger study section

### 15.2 Corrections required

1. **Do not say “same 41 alerts”.**
   - `strict-real-01` used 14 distinct matched alerts and produced 41 successful strict evaluations.
   - `strict-real-02` used 16 distinct matched alerts and produced 48 successful strict evaluations.

2. **Do not say “temperature = 0”.**
   - current configured value is `LLM_TEMPERATURE=0.3`

3. **Do not say Anthropic must be documented as an infrastructure failure.**
   - that was true for the older state
   - it is no longer true after the key update and `strict-real-02`

4. **Do not mix metrics from different artifacts as if they come from one run.**
   - Kimi's strongest evidence currently comes from `strict-real-01`
   - Anthropic's scored evidence currently comes from `strict-real-02`

5. **Do not present a 5-provider comparison yet.**
   - Gemini is still blocked
   - Kimi was unstable under the heavier 4-provider run

## 16. Recommended Report Framing

For the written report and viva, use this structure.

### 16.1 Completed scored comparison

Use `strict-real-01` as the fully completed comparison artifact.

Why:

- it is internally consistent
- it has validation appendices
- it supports a clean quality / latency / cost / safety comparison across three providers

### 16.2 Anthropic update

Use `strict-real-02` as the follow-up operational update.

Why:

- it proves Anthropic can now run strict scored evaluations
- it does not yet yield a stable 4-provider final scorecard because Kimi overloaded during that run

### 16.3 Current safest conclusion

Current defensible conclusion:

- Kimi remains the strongest completed quality-cost result in `strict-real-01`
- OpenAI remains the lowest-latency successful provider
- xAI remains operational but much slower
- Anthropic is now operational and should be included in the next clean comparative run
- Gemini remains excluded until quota/cooldown is fixed

## 17. Building Tables And Figures From The Artifacts

### 17.1 Tables

Use these files:

- main provider table:
  - `artifacts/llm-eval/strict-real-01/provider_summary_scored.csv`
- Anthropic update table:
  - `artifacts/llm-eval/strict-real-02/provider_summary_scored.csv`
- scenario-family table:
  - `artifacts/llm-eval/strict-real-01/scenario_family_results_scored.csv`
  - `artifacts/llm-eval/strict-real-02/scenario_family_results_scored.csv`
- raw evidence appendix:
  - `artifacts/llm-eval/strict-real-01/strict_eval_raw_results.csv`
  - `artifacts/llm-eval/strict-real-02/strict_eval_raw_results.csv`

### 17.2 Charts

Use:

- `artifacts/llm-eval/strict-real-01/charts/avg_latency_by_provider.png`
- `artifacts/llm-eval/strict-real-01/charts/cost_per_1m_tokens_by_provider.png`
- `artifacts/llm-eval/strict-real-01/charts/success_rate_runtime_by_provider.png`
- `artifacts/llm-eval/strict-real-01/charts/severity_accuracy_by_provider.png`
- `artifacts/llm-eval/strict-real-01/charts/threat_accuracy_by_provider.png`
- `artifacts/llm-eval/strict-real-01/charts/cost_vs_latency_scatter.png`

For Anthropic update material:

- `artifacts/llm-eval/strict-real-02/charts/avg_latency_by_provider.png`
- `artifacts/llm-eval/strict-real-02/charts/cost_vs_latency_scatter.png`
- `artifacts/llm-eval/strict-real-02/charts/severity_accuracy_by_provider.png`
- `artifacts/llm-eval/strict-real-02/charts/threat_accuracy_by_provider.png`

## 18. Commands To Inspect The Evidence

Open the canonical run summaries:

```bash
cat artifacts/llm-eval/strict-real-01/README.json | jq .
cat artifacts/llm-eval/strict-real-02/README.json | jq .
```

Open the scored provider tables:

```bash
column -s, -t < artifacts/llm-eval/strict-real-01/provider_summary_scored.csv
column -s, -t < artifacts/llm-eval/strict-real-02/provider_summary_scored.csv
```

Open the validation appendices:

```bash
sed -n '1,220p' artifacts/llm-eval/strict-real-01/VALIDATION_REPORT.md
sed -n '1,220p' artifacts/llm-eval/strict-real-02/VALIDATION_REPORT.md
```

Open the compact JSON proof for slides:

```bash
cat artifacts/llm-eval/strict-real-01/slide_alignment.json | jq .
cat artifacts/llm-eval/strict-real-02/slide_alignment.json | jq .
```

## 19. Gap To A Real 500 x 5-Provider Study

Definition:

- `500 x 5-provider` means 100 matched alerts evaluated across 5 providers, for 500 provider-attempts.

Current blockers:

- `gemini` still fails strict readiness due quota / cooldown
- `kimi` became unstable under the larger 4-provider run due overload
- the current completed artifacts are `runs=1`, not repeatability studies

Therefore the correct statement is:

- the project has a real, artifact-backed strict evaluation pipeline
- it has completed artifact-backed 3-provider and partial 4-provider evidence
- it does not yet have a completed 500 x 5-provider study

## 20. What Can Be Claimed Safely

Safe claims:

- strict single-provider evaluation was implemented and executed against real stored IDS alerts
- the evaluation used frozen ground truth and artifact-backed metrics
- `strict-real-01` is a completed 3-provider comparison
- `strict-real-02` proves Anthropic can now score real alerts in strict mode
- OpenAI is the fastest successful provider in both completed artifacts where it scored
- xAI remains operational but high-latency
- Gemini is currently excluded by quota / cooldown

Unsafe claims:

- 500 alerts evaluated across 5 providers
- all five providers were compared in one completed strict run
- temperature was 0
- Anthropic is still only an infrastructure failure

## 21. Report-Ready Text

The following text is formatted for direct inclusion in the report.

### 21.1 LLM Provider Evaluation

LLM provider evaluation was implemented using the live Smart City IDS backend rather than a separate benchmark harness. Stored IDS alerts were selected from the operational alert history, matched against the frozen ground-truth file `docs/reference/LLM_EVAL_GROUND_TRUTH_CORE.csv`, and re-run against one provider at a time through the reanalysis endpoint. Evaluation requests used `strict=true` to disable fallback and `persist=false` to prevent database overwrite. This ensured that the same alert could be tested across providers without contaminating operational records.

The evaluation program was executed by `scripts/llm-compare-report.py`. The script logs into the IDS API, retrieves recent alerts, matches them to ground truth, optionally applies a per-family balancing cap, re-runs selected alerts against the chosen providers in strict mode, writes one raw row per provider-attempt, then aggregates latency, token, cost, quality, and safety metrics into scored CSV summaries and charts.

The completed three-provider comparison is stored in `artifacts/llm-eval/strict-real-01`. That run used 14 distinct matched alerts, produced 42 provider-attempts, and retained 41 successful strict evaluations for scoring across seven scenario families. Kimi achieved the strongest quality-cost balance in that artifact with a composite quality score of 70.86%, 100.00% severity accuracy, and an estimated cost of approximately $5.00 per 1000 alerts. OpenAI was the fastest successful provider in the same artifact with 2.2774 seconds average latency and 3.054 seconds p95 latency. xAI remained usable, but was significantly slower and had the weakest overall score of the three providers.

After the Anthropic API key was updated, a second strict evaluation was executed and stored in `artifacts/llm-eval/strict-real-02`. This run requested Anthropic, Kimi, OpenAI, and xAI across 16 distinct matched alerts and 64 provider-attempts. Anthropic, OpenAI, and xAI all scored successfully, confirming that Anthropic is now able to participate in strict scored evaluation. However, Kimi failed all 16 strict attempts in that run due provider-side overload (`429 engine_overloaded_error`), so `strict-real-02` should be treated as an Anthropic inclusion run rather than a final four-provider scorecard.

Taken together, the current evidence supports a measured operational conclusion rather than an inflated five-provider claim. The project has a real strict-evaluation pipeline, a completed three-provider scored comparison, and a follow-up Anthropic inclusion run. It does not yet have a completed 500 x 5-provider evaluation because Gemini remains blocked by quota / cooldown and Kimi was unstable during the heavier four-provider run.
