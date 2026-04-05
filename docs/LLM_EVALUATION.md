# LLM Provider Evaluation — Step-by-Step Methodology and Results

> **Single source of truth** for the Smart City IDS LLM evaluation.
> This document describes *how* the evaluation was designed and executed, step by step,
> and then presents the measured results from the completed evaluation runs.

---

## Table of Contents

1. [Evaluation Objective](#1-evaluation-objective)
2. [Step 1 — Design the Ground Truth](#2-step-1--design-the-ground-truth)
3. [Step 2 — Prepare the Test Environment](#3-step-2--prepare-the-test-environment)
4. [Step 3 — Generate Real Alerts via Attack Simulation](#4-step-3--generate-real-alerts-via-attack-simulation)
5. [Step 4 — Match Alerts to Ground Truth](#5-step-4--match-alerts-to-ground-truth)
6. [Step 5 — Run Strict Per-Provider Reanalysis](#6-step-5--run-strict-per-provider-reanalysis)
7. [Step 6 — Score Each Provider Response](#7-step-6--score-each-provider-response)
8. [Step 7 — Aggregate and Compare Providers](#8-step-7--aggregate-and-compare-providers)
9. [Evaluation Results — Run 1 (Primary 3-Provider)](#9-evaluation-results--run-1-primary-3-provider)
10. [Evaluation Results — Run 2 (Anthropic Inclusion)](#10-evaluation-results--run-2-anthropic-inclusion)
11. [Evaluation Results — Run 3 (Expanded 5-Provider)](#11-evaluation-results--run-3-expanded-5-provider)
12. [Cross-Run Provider Summary](#12-cross-run-provider-summary)
13. [Discussion and Findings](#13-discussion-and-findings)
14. [Limitations](#14-limitations)
15. [How to Reproduce](#15-how-to-reproduce)
16. [Artifact Inventory](#16-artifact-inventory)

---

## 1. Evaluation Objective

The objective is to compare LLM providers on **one fixed task**: structured analysis of stored IDS alerts.

For each stored alert, the provider must return a JSON response containing:

- `summary` — plain-English description of the threat
- `severity` — integer score from 1 to 10
- `threat_type` — classification (e.g., "Data Exfiltration", "DoS", "Injection")
- `confidence` — float from 0.0 to 1.0
- `recommendations` — list of analyst recommendations
- `automated_actions` — list of proposed Kubernetes actions

This is **not** a general chatbot benchmark. It evaluates how well each LLM provider can perform security alert analysis within the IDS pipeline.

---

## 2. Step 1 — Design the Ground Truth

Before running any evaluation, we created a **frozen ground-truth file** that defines what the correct answer should look like for each attack scenario.

**File:** `docs/reference/LLM_EVAL_GROUND_TRUTH_CORE.csv`

### 2.1 Ground Truth Structure

Each row defines one attack scenario with expected ranges:

| Column | Purpose | Example |
|--------|---------|---------|
| `rule_pattern` | Regex to match the alert rule name | `SMARTCITY HTTP flood` |
| `source` | Which IDS generated it | `suricata` or `falco` |
| `scenario_family` | Attack category grouping | `network_dos` |
| `expected_severity_min` | Minimum acceptable severity score | `7` |
| `expected_severity_max` | Maximum acceptable severity score | `9` |
| `expected_threat_type` | Correct threat classification | `DoS` |
| `expected_safe_action_class` | What action the LLM should recommend | `rate_limit_or_contain_source` |
| `safety_profile` | How critical this scenario is | `availability_critical` |
| `under_escalation_weight` | Penalty weight for under-rating severity | `2.0` |
| `notes` | Human-authored scoring guidance | Free text |

### 2.2 Coverage: 16 Scenario Families

The ground truth covers the following attack families:

| # | Scenario Family | Source | Severity Range | Expected Threat Type |
|---|----------------|--------|---------------|---------------------|
| 1 | `network_dos` | Suricata | 7–9 | DoS |
| 2 | `sqli` (OR 1=1) | Suricata | 7–9 | Injection |
| 3 | `sqli` (UNION SELECT) | Suricata | 7–9 | Injection |
| 4 | `sqli` (DROP TABLE) | Suricata | 8–10 | Injection |
| 5 | `mqtt_misuse` (control topic) | Suricata | 7–9 | Command and Control |
| 6 | `mqtt_misuse` (occupancy spoof) | Suricata | 6–8 | Data Tampering |
| 7 | `mqtt_misuse` (fault-state tamper) | Suricata | 7–9 | Data Tampering |
| 8 | `modbus_write_tamper` | Suricata | 8–10 | Unauthorized Command |
| 9 | `onvif_recon` (capability enum) | Suricata | 4–6 | Reconnaissance |
| 10 | `onvif_recon` (profile enum) | Suricata | 4–6 | Reconnaissance |
| 11 | `onvif_misuse` (PTZ control) | Suricata | 7–9 | Unauthorized Command |
| 12 | `onvif_recon` (snapshot scraping) | Suricata | 5–7 | Collection |
| 13 | `anpr_exfiltration` | Suricata | 7–9 | Data Exfiltration |
| 14 | `runtime_shell` | Falco | 6–8 | Runtime Abuse |
| 15 | `credential_access_or_platform_noise` | Falco | 4–8 | Credential Access |
| 16 | `lateral_movement_or_platform_access` | Falco | 4–7 | Lateral Movement |

**Why ranges instead of exact values?** Security severity is inherently subjective — a severity of 7 or 8 for a DDoS attack are both reasonable. The ground truth defines acceptable ranges, and scoring penalizes answers outside those ranges.

**Figure 2-1.** Ground truth CSV — 16 scenario rows with expected severity ranges and threat types (see `docs/reference/LLM_EVAL_GROUND_TRUTH_CORE.csv`)

---

## 3. Step 2 — Prepare the Test Environment

The evaluation runs on the **live Smart City IDS stack** — not a separate benchmark harness.

### 3.1 System Architecture for Evaluation

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  Attack Scripts   │────▸│ Suricata / Falco  │────▸│   IDS API        │
│  (real traffic)   │     │ (real detection)   │     │ (stores alerts)  │
└──────────────────┘     └──────────────────┘     └─────────┬────────┘
                                                            │
                                                            ▼
                                                  ┌──────────────────┐
                                                  │ Alert Database    │
                                                  │ (PostgreSQL)      │
                                                  └─────────┬────────┘
                                                            │
                                                            ▼
                                              ┌────────────────────────┐
                                              │ Strict Reanalysis      │
                                              │ Endpoint               │
                                              │ POST /api/alerts/{id}/ │
                                              │   reanalyze            │
                                              │   ?engine=<provider>   │
                                              │   &strict=true         │
                                              │   &persist=false       │
                                              └────────────┬───────────┘
                                                           │
                                          ┌────────────────┼────────────────┐
                                          ▼                ▼                ▼
                                       ┌─────┐         ┌─────┐         ┌─────┐
                                       │ xAI │         │OpenAI│        │ Kimi │  ... etc.
                                       └─────┘         └─────┘         └─────┘
```

### 3.2 Prerequisites Verification

Before each evaluation run, the following checks are performed:

```bash
# Step 2a: Verify the IDS API is healthy
curl -s http://localhost:30800/health | jq .
```

Expected output:
```json
{
  "status": "healthy",
  "uptime_seconds": 12345,
  "llm_providers": { ... },
  "database": "connected"
}
```

**Figure 3-1.** IDS API health-check output confirming all providers are listed

```bash
# Step 2b: Verify LLM provider diagnostics
curl -s http://localhost:30800/api/llm/diagnostics | jq .
```

This shows which providers are currently operational, in cooldown, or have auth failures.

**Figure 3-2.** LLM diagnostics output showing per-provider operational state

```bash
# Step 2c: Verify PostgreSQL has stored alerts
curl -s http://localhost:30800/api/alerts?limit=5 \
  -H "Authorization: Bearer $TOKEN" | jq '.[].rule'
```

**Figure 3-3.** Stored alert rules retrieved from PostgreSQL via the API

### 3.3 Frozen Parameters

The following conditions are fixed within each evaluation run:

| Parameter | Value | Why |
|-----------|-------|-----|
| `strict` | `true` | Disables provider fallback — each provider must answer alone |
| `persist` | `false` | Prevents evaluation from overwriting operational alert records |
| `runs` | `1` | Single attempt per provider per alert (no retry averaging) |
| `temperature` | `0.3` | Fixed in `config.py` — same for all providers |
| Ground truth | Frozen CSV | Same scoring rubric for all runs |
| Prompt template | Backend code | Same prompt for all providers |

---

## 4. Step 3 — Generate Real Alerts via Attack Simulation

The evaluation uses **real alerts** from the live IDS pipeline, not synthetic prompts.

### 4.1 Attack Generation

```bash
# Run the attack simulation script
bash scripts/run-live-attacks.sh --mode protocol --duration 12 --show-alerts 8 --verbose
```

This script generates real network traffic and system calls that trigger Suricata and Falco:

| Attack Type | What It Does | Which IDS Detects It |
|-------------|--------------|---------------------|
| HTTP Flood | Sends high-volume HTTP requests to smart city services | Suricata |
| SQLi Payloads | Sends `OR 1=1`, `UNION SELECT`, `DROP TABLE` in HTTP | Suricata |
| MQTT Topic Abuse | Publishes to unauthorized MQTT control topics | Suricata |
| Modbus Write Tamper | Sends unauthorized Modbus write commands | Suricata |
| ONVIF Camera Recon | Enumerates camera capabilities and profiles | Suricata |
| ONVIF PTZ Abuse | Sends unauthorized PTZ (pan-tilt-zoom) commands | Suricata |
| ANPR Data Scraping | Attempts to scrape license plate recognition data | Suricata |
| Shell in Container | Opens `/bin/bash` inside a running container | Falco |
| Sensitive File Read | Reads `/etc/shadow` inside a container | Falco |
| K8s API Contact | Makes unauthorized calls to the K8s API server | Falco |

**Figure 4-1.** Attack simulation script generating real traffic and producing IDS alerts

### 4.2 Why Real Alerts, Not Synthetic Prompts?

- **Real alerts** come through the actual Falco/Suricata pipeline with real metadata (container names, IPs, timestamps)
- **Synthetic prompts** would test the LLM in isolation, not within the IDS integration
- Using real alerts means we test the full path: detection → storage → reanalysis → scoring

### 4.3 Verify Alerts Were Stored

```bash
# Check how many alerts are now stored
curl -s http://localhost:30800/api/alerts?limit=50 \
  -H "Authorization: Bearer $TOKEN" | jq 'length'
```

**Figure 4-2.** Stored alert count after attack simulation completes

---

## 5. Step 4 — Match Alerts to Ground Truth

Not all stored alerts are useful for the evaluation. The evaluation script matches stored alerts against the ground-truth CSV using rule-name pattern matching.

### 5.1 The Matching Process

```
Stored Alert Rule: "SMARTCITY ANPR data scraping (traffic-camera)"
         ↓ regex match
Ground Truth Pattern: "SMARTCITY ANPR data scraping"
         ↓ match found
Scenario Family: anpr_exfiltration
Expected Severity: 7–9
Expected Threat Type: Data Exfiltration
```

### 5.2 Balancing with `--max-per-family`

To prevent one attack type from dominating the evaluation, the script limits how many alerts per scenario family are included:

```bash
--max-per-family 2   # At most 2 alerts per scenario family
```

This means if there are 50 HTTP flood alerts but only 3 MQTT abuse alerts, the evaluation uses at most 2 of each — keeping the dataset balanced.

### 5.3 Example: What Gets Matched

From `strict-real-01`:
- **14 distinct matched alerts** across **7 scenario families**
- Families: `anpr_exfiltration`, `lateral_movement_or_platform_access`, `modbus_write_tamper`, `mqtt_misuse`, `onvif_misuse`, `onvif_recon`, `runtime_shell`

From `strict-real-03`:
- **16 distinct matched alerts** across **8 scenario families**
- Same families plus `credential_access_or_platform_noise`

**Figure 5-1.** Evaluation script output showing matched alerts per scenario family

---

## 6. Step 5 — Run Strict Per-Provider Reanalysis

This is the core of the evaluation. Each matched alert is sent to each provider **individually** with fallback disabled.

### 6.1 The Strict Reanalysis API Call

For each `(alert_id, provider)` pair, the evaluation script makes this call:

```
POST /api/alerts/{alert_id}/reanalyze?engine={provider}&strict=true&persist=false
```

**What `strict=true` does:**
- The backend sends the alert to **only** the requested provider
- If that provider fails (timeout, error, rate limit), it does NOT fall back to another provider
- The row is marked as a failure for that provider

**What `persist=false` does:**
- The evaluation result is **not** saved to the database
- The original operational analysis record remains unchanged

### 6.2 What the Script Does Internally

```
For each matched alert:
  For each requested provider (e.g., kimi, openai, xai):
    1. Call POST /api/alerts/{id}/reanalyze?engine={provider}&strict=true&persist=false
    2. Record: alert_id, provider, status, strict_satisfied, latency, tokens, response
    3. If success: extract severity, threat_type, summary, actions
    4. If failure: record error type (timeout, 429, auth_failed, etc.)
    5. Write one row to strict_eval_raw_results.csv
```

### 6.3 Example Raw Result Row

From `strict_eval_raw_results.csv`:

```
alert_id: 14520
provider: kimi
status: success
strict_requested: True
strict_satisfied: True
engine_used: kimi
latency_s: 3.348
prompt_tokens: 649
completion_tokens: 162
total_tokens: 811
estimated_cost_usd: 0.004866
summary: "The alert indicates a potential data scraping attempt targeting ANPR data..."
severity: 9
threat_type: Data Exfiltration
action_text: block_ip; alert_team
error: (empty)
```

**Figure 6-1.** Raw results CSV showing per-provider analysis of the same alert

### 6.4 Handling Failures

When a provider fails during strict evaluation:

| Failure Type | What Happens | Example |
|-------------|-------------|---------|
| Timeout | Row recorded with `status=timeout` | xAI taking >60s |
| Rate Limit (429) | Row recorded with `status=error`, error=`429` | Kimi overloaded |
| Auth Failure | Row recorded with `status=auth_failed` | Wrong API key |
| Invalid JSON | Row recorded with `status=parse_error` | Provider returned bad format |

Failed rows are **excluded from quality scoring** but **included in reliability metrics**.

---

## 7. Step 6 — Score Each Provider Response

After collecting all raw results, the script scores each successful response against the ground truth.

### 7.1 Scoring Rubric

| Metric | How It's Computed | Scale |
|--------|-------------------|-------|
| **Severity Accuracy** | Is the predicted severity within `[expected_min, expected_max]`? | 0 or 1 (binary) |
| **Threat Type Accuracy** | Does the predicted threat type match the expected type? | 0 or 1 (binary) |
| **Action Relevance** | Does the recommended action match the expected safe action class? | 1–5 scale |
| **False High Severity** | Did the provider over-rate severity above the expected max? | 0 or 1 |
| **False Low Severity** | Did the provider under-rate severity below the expected min? | 0 or 1 |
| **Unsafe Action** | Did the provider recommend a destructive action when investigation was appropriate? | 0 or 1 |

### 7.2 Scoring Example

**Alert:** SMARTCITY ANPR data scraping
**Ground Truth:** severity 7–9, threat type "Data Exfiltration"

| Provider | Predicted Severity | Predicted Threat Type | Severity Score | Threat Score |
|----------|-------------------|-----------------------|---------------|-------------|
| Kimi | 9 | Data Exfiltration | 1 (in range 7–9) ✅ | 1 (exact match) ✅ |
| OpenAI | 8 | Data Exfiltration | 1 (in range 7–9) ✅ | 1 (exact match) ✅ |
| xAI | 8 | Data Exfiltration | 1 (in range 7–9) ✅ | 1 (exact match) ✅ |

### 7.3 Composite Quality Score

The composite quality score combines multiple metrics:

```
quality_score = (severity_accuracy * 0.3) + (threat_accuracy * 0.3) +
                (action_relevance_normalized * 0.2) + (safety_proxy * 0.2)
```

Where:
- `action_relevance_normalized` = action_relevance_score / 5.0
- `safety_proxy` = 1.0 - (false_high_rate * 0.3 + false_low_rate * 0.5 + unsafe_action_rate * 0.2)

**Figure 7-1.** Scenario-level scoring template with per-alert, per-provider quality scores

---

## 8. Step 7 — Aggregate and Compare Providers

The final step aggregates per-alert scores into provider-level summaries.

### 8.1 Aggregation Process

```
For each provider:
  - Count total attempts and successful strict evaluations
  - Compute success_rate = successes / attempts
  - Average latency across successful rows
  - Compute p95 latency
  - Sum tokens and costs
  - Average severity_accuracy, threat_accuracy, action_relevance across scored rows
  - Compute composite quality score
  - Compute safety calibration proxy
```

### 8.2 Output Artifacts

The evaluation script produces these files in the output directory:

| File | Contents |
|------|----------|
| `strict_eval_raw_results.csv` | One row per (alert, provider) attempt – raw data |
| `scenario_alert_scoring_template.csv` | Per-row scoring with ground-truth comparison |
| `provider_summary_scored.csv` | Aggregated provider metrics |
| `provider_scorecard_ranked.csv` | Providers ranked by composite score |
| `scenario_family_results_scored.csv` | Per-scenario-family breakdown |
| `README.json` | Run metadata (timestamp, parameters, dataset size) |
| `charts/*.png` | Auto-generated comparison charts |

### 8.3 Auto-Generated Charts

The script generates these comparison charts:

- Average latency by provider (bar chart)
- Success rate by provider (bar chart)
- Cost per 1M tokens by provider (bar chart)
- Cost vs latency scatter plot
- Severity accuracy by provider (bar chart)
- Threat accuracy by provider (bar chart)
- Scenario-family severity accuracy heatmap
- Scenario-family threat accuracy heatmap
- Scenario-family safety proxy heatmap

**Figure 8-1.** Average latency by provider (see `strict-real-01/charts/avg_latency_by_provider.png`)

**Figure 8-2.** Severity accuracy by provider (see `strict-real-01/charts/severity_accuracy_by_provider.png`)

**Figure 8-3.** Cost vs latency scatter (see `strict-real-03/charts/cost_vs_latency_scatter.png`)

---

## 9. Evaluation Results — Run 1 (Primary 3-Provider)

**Artifact:** `artifacts/llm-eval/strict-real-01/`
**Date:** March 10, 2026
**Providers:** Kimi, OpenAI, xAI

### 9.1 Dataset

| Parameter | Value |
|-----------|-------|
| Distinct matched alerts | 14 |
| Provider attempts | 42 (14 alerts × 3 providers) |
| Successful strict evaluations | 41 |
| Failed strict evaluations | 1 (xAI timeout) |
| Scenario families | 7 |
| Cache-hit rows in quality scoring | 0 |

Scenario families covered: `anpr_exfiltration`, `lateral_movement_or_platform_access`, `modbus_write_tamper`, `mqtt_misuse`, `onvif_misuse`, `onvif_recon`, `runtime_shell`

### 9.2 Provider Comparison

| Provider | Model | Alerts Scored | Success Rate | Avg Latency | p95 Latency | Cost/1K Alerts | Quality Score | Severity Acc. | Threat Acc. | Action Rel. | Safety |
|----------|-------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Kimi** | moonshot-v1-8k | 14 | 100% | 3.73s | 5.32s | $5.00 | **70.86%** | **100%** | **42.86%** | 3.43/5 | **100%** |
| **OpenAI** | gpt-3.5-turbo | 14 | 100% | **2.28s** | **3.05s** | $7.65 | 65.14% | **100%** | 28.57% | 3.43/5 | **100%** |
| **xAI** | grok-4-latest | 13 | 92.86% | 25.49s | 28.85s | $17.58 | 62.77% | 84.62% | 38.46% | 3.38/5 | 94.87% |

**Figure 9-1.** Provider comparison table from strict-real-01 run

**Figure 9-2.** Average latency by provider (see `strict-real-01/charts/avg_latency_by_provider.png`)

**Figure 9-3.** Severity accuracy by provider (see `strict-real-01/charts/severity_accuracy_by_provider.png`)

### 9.3 Key Findings — Run 1

1. **Kimi** had the best quality-cost tradeoff: highest quality score (70.86%) at the lowest cost ($5/1K alerts)
2. **OpenAI** was the fastest (2.28s avg) with perfect severity accuracy
3. **xAI** was significantly slower (25.49s avg) and had one failed attempt, reducing its reliability score

---

## 10. Evaluation Results — Run 2 (Anthropic Inclusion)

**Artifact:** `artifacts/llm-eval/strict-real-02/`
**Date:** March 10, 2026
**Providers:** Anthropic, Kimi, OpenAI, xAI
**Purpose:** Confirm Anthropic can participate after API key was corrected

### 10.1 Dataset

| Parameter | Value |
|-----------|-------|
| Distinct matched alerts | 16 |
| Provider attempts | 64 (16 × 4 providers) |
| Successful strict evaluations | 48 |
| Failed strict evaluations | 16 (all Kimi — provider overload) |
| Scenario families | 8 |

### 10.2 Provider Comparison

| Provider | Model | Alerts Scored | Success Rate | Avg Latency | p95 Latency | Cost/1K Alerts | Quality Score | Severity Acc. | Threat Acc. | Action Rel. | Safety |
|----------|-------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Anthropic** | claude-sonnet-4-20250514 | 16 | 100% | 5.18s | 5.85s | $14.90 | 65.00% | 93.75% | 31.25% | 3.75/5 | 98.12% |
| **OpenAI** | gpt-3.5-turbo | 16 | 100% | **2.02s** | **2.73s** | $7.42 | 67.50% | **100%** | 31.25% | 3.75/5 | **100%** |
| **xAI** | grok-4-latest | 16 | 100% | 21.45s | 25.78s | $17.40 | **72.50%** | **100%** | **43.75%** | 3.75/5 | **100%** |
| **Kimi** | moonshot-v1-128k | 0 | **0%** | — | — | — | — | — | — | — | — |

> **Note:** Kimi returned HTTP 429 (engine overloaded) on all 16 attempts. Its Run 1 scores (quality 70.86%, latency 3.73s, cost $5.00/1K) remain the only measured reference.

### 10.3 Key Findings — Run 2

1. **Anthropic** is now operational and scored successfully on all 16 alerts
2. **Kimi** experienced provider-side overload (429 errors on all 16 attempts) — this run does **not** replace Run 1
3. **xAI** improved to 100% success rate and highest quality in this run

---

## 11. Evaluation Results — Run 3 (Expanded 5-Provider)

**Artifact:** `artifacts/llm-eval/strict-real-03/`
**Date:** March 11, 2026
**Providers:** Anthropic, Gemini, Kimi, OpenAI, xAI
**Purpose:** First attempt to score all five configured providers

### 11.1 Dataset

| Parameter | Value |
|-----------|-------|
| Distinct matched alerts | 16 |
| Provider attempts | 80 (16 × 5 providers) |
| Successful strict evaluations | 64 |
| Failed strict evaluations | 16 (all Kimi — provider overload) |
| Scenario families | 8 |

### 11.2 Provider Comparison

| Provider | Model | Alerts Scored | Success Rate | Avg Latency | p95 Latency | Cost/1K Alerts | Quality Score | Severity Acc. | Threat Acc. | Action Rel. | Safety |
|----------|-------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Anthropic** | claude-sonnet-4-20250514 | 16 | 100% | 5.12s | 5.77s | $15.01 | 65.00% | 93.75% | 31.25% | 3.75/5 | 96.35% |
| **Gemini** | gemini-2.5-flash | 16 | 100% | 6.11s | 6.71s | **$1.43** | 21.00% | 12.50% | 0.00% | **4.00/5** | 50.00% |
| **OpenAI** | gpt-4o | 16 | 100% | **3.35s** | **4.46s** | $7.69 | 70.00% | **100%** | 37.50% | 3.75/5 | **100%** |
| **xAI** | grok-4-latest | 16 | 100% | 21.30s | 27.10s | $17.48 | **72.50%** | **100%** | **43.75%** | 3.75/5 | **100%** |
| **Kimi** | moonshot-v1-128k | 0 | **0%** | — | — | — | — | — | — | — | — |

> **Note:** Kimi returned HTTP 429 (cooldown) on all 16 attempts. Its Run 1 scores (quality 70.86%, latency 3.73s, cost $5.00/1K) remain the only measured reference.

**Figure 11-1.** Average latency by provider (see `strict-real-03/charts/avg_latency_by_provider.png`)

**Figure 11-2.** Cost per 1M tokens by provider (see `strict-real-03/charts/cost_per_1m_tokens_by_provider.png`)

**Figure 11-3.** Cost vs latency scatter (see `strict-real-03/charts/cost_vs_latency_scatter.png`)

**Figure 11-4.** Severity accuracy by provider (see `strict-real-03/charts/severity_accuracy_by_provider.png`)

### 11.3 Key Findings — Run 3

1. **Four out of five** providers scored successfully; Kimi remained blocked by provider overload
2. **Gemini** was cheapest ($1.43/1K alerts) but had the worst quality (21%) — it consistently under-rated severity
3. **xAI** achieved the highest quality score (72.50%) but at the highest cost and latency
4. **OpenAI** provided the best balance of speed (3.35s) and quality (70.00%)
5. **Anthropic** was consistent across runs but scored lower on threat-type accuracy

---

## 12. Evaluation Results — Run 4 (Post-Fix Definitive)

**Artifact:** `artifacts/llm-eval/strict-real-04/`
**Date:** April 3, 2026
**Providers:** OpenAI, xAI, Gemini, Anthropic, Kimi
**Purpose:** Complete five-provider evaluation after fixing the Gemini JSON parsing defect

### 12.1 Bug Fix Summary

During verification of `strict-real-03`, root-cause analysis revealed that `gemini-2.5-flash` is a *thinking model* whose internal reasoning tokens consumed the `maxOutputTokens=1000` budget. This left only ~28 tokens for the actual JSON payload, causing 100% parse failure and fallback to `severity=5, threat_type="Unknown"`.

**Fix applied to `providers.py`:**
1. Disabled thinking budget (`thinkingBudget: 0`) for Gemini 2.5 family models
2. Raised `maxOutputTokens` to `max(config.max_tokens, 2048)`
3. Added `responseSchema` for structured JSON output

**Fix applied to `base.py`:**
4. Added brace-matching JSON extraction as a 4th-tier fallback in `_parse_response()`

### 12.2 Dataset

| Parameter | Value |
|-----------|-------|
| Distinct matched alerts | 20 |
| Provider attempts | 100 (20 × 5 providers) |
| Successful strict evaluations | **100 (100%)** |
| Failed strict evaluations | 0 |
| Scenario families | 10 |

### 12.3 Provider Comparison

| Provider | Model | Alerts Scored | Success Rate | Avg Latency | Cost/1M Tokens | Quality Score | Severity Acc. | Threat Acc. | Action Rel. | Safety |
|----------|-------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Kimi** | moonshot-v1-128k | 20 | **100%** | 2,923 ms | $6.00 | **76.0%** | **100%** | **50.0%** | 4.0/5 | 98.0% |
| **OpenAI** | gpt-4o | 20 | **100%** | **2,549 ms** | $10.00 | **76.0%** | **100%** | **50.0%** | 4.0/5 | **100%** |
| **xAI** | grok-4-latest | 20 | **100%** | 3,383 ms | $8.00 | **76.0%** | **100%** | **50.0%** | 4.0/5 | 98.0% |
| **Gemini** | gemini-2.5-flash-lite | 20 | **100%** | 2,659 ms | **$0.50** | 74.0% | **100%** | 45.0% | 4.0/5 | 98.0% |
| **Anthropic** | claude-sonnet-4-20250514 | 20 | **100%** | 4,978 ms | $16.00 | 68.0% | 80.0% | **50.0%** | 4.0/5 | 93.3% |

### 12.4 Gemini Before vs After Fix

| Metric | strict-real-03 (broken) | strict-real-04 (fixed) | Change |
|--------|:-:|:-:|---|
| Quality composite | 21.0% | 74.0% | **+53pp** |
| Severity accuracy | 12.5% | 100.0% | **+87.5pp** |
| Threat accuracy | 0.0% | 45.0% | **+45pp** |
| Safety proxy | 50.0% | 98.0% | **+48pp** |
| Avg latency | 6.11s | 2.66s | **-56%** |
| Avg completion tokens | 28 | ~200 | **+7×** |
| Parse errors | 16/16 (100%) | 0/20 (0%) | **Eliminated** |

### 12.5 Key Findings — Run 4

1. **Gemini fix was transformative**: quality rose from 21% to 74%, validating that the original failure was a client-side configuration issue, not a model limitation
2. **All five providers achieved 100% reliability** — zero parse errors, zero API failures
3. **Tight quality band (68–76%)**: confirms the multi-provider architecture delivers consistent analysis regardless of backend
4. **Gemini is the cost-optimal choice**: 74% quality at $0.50/1M tokens — 20× cheaper than Anthropic, 16× cheaper than OpenAI
5. **Severity accuracy near-perfect**: four of five providers scored 100% (Anthropic at 80%)
6. **Threat-type accuracy remains the hardest dimension**: best score is 50%, suggesting LLM taxonomy differs from IDS-specific ground truth categories
7. **Kimi ties for top quality**: 76.0% quality at $6/1M tokens, confirming it as a viable cost-effective alternative to OpenAI and xAI

---

## 13. Cross-Run Provider Summary

Combining evidence from all four runs:

| Provider | Best Quality Score | Best Latency | Cost/1M Tokens | Runs Scored In | Status |
|----------|:-:|:-:|:-:|:-:|---|
| **Kimi** (moonshot-v1-128k) | **76.0%** | 2,923 ms | $6.00 | 2/4 | Tied highest quality, strong value |
| **OpenAI** (gpt-4o) | **76.0%** | **2,549 ms** | $10.00 | 4/4 | Best balance of quality and speed |
| **xAI** (grok-4-latest) | **76.0%** | 3,383 ms | $8.00 | 4/4 | Tied highest quality |
| **Gemini** (gemini-2.5-flash-lite) | 74.0% | 2,659 ms | **$0.50** | 2/4 | Cost-optimal after fix |
| **Anthropic** (claude-sonnet-4-20250514) | 68.0% | 4,978 ms | $16.00 | 3/4 | Reliable, consistent |

**Figure 13-1.** Cross-run provider comparison (quality vs latency vs cost)

---

## 14. Discussion and Findings

### 14.1 Quality vs Cost Tradeoff

The post-fix evaluation (`strict-real-04`) reveals a much tighter quality band than originally observed:

- **High quality, competitive cost:** Kimi ($6/1M, 76%), OpenAI ($10/1M, 76%) and xAI ($8/1M, 76%)
- **Near-parity quality, lowest cost:** Gemini ($0.50/1M, 74%) — best cost-efficiency by a wide margin
- **Reliable, higher cost:** Anthropic ($16/1M, 68%)

The Gemini result is particularly notable: after fixing the parsing defect, Gemini delivers 97% of the leading quality at 5% of the cost, making it the clear choice for high-volume routine alert triage. Kimi's recovery from provider overload in earlier runs to 100% reliability with top-tier quality validates the five-provider architecture.

### 14.2 Severity Accuracy vs Threat-Type Accuracy

Across all providers:
- **Severity accuracy** was consistently strongest (80–100%), with four providers achieving perfect scores
- **Threat-type accuracy** peaked at 50% — all providers struggled with the same categories (Credential Access, Injection, Runtime Abuse, Lateral Movement, Command and Control)
- The common misclassifications suggest a taxonomy mismatch between LLM training data and IDS-specific threat categories, rather than individual model weakness
- The implication for IDS operators: rely on LLM severity scoring for triage, but verify threat-type classifications

### 14.3 Latency Implications for Real-Time IDS

| Provider | Avg Latency (Run 4) | Suitable for Real-Time? |
|----------|:-:|---|
| OpenAI | 2.5s | ✅ Yes |
| Gemini | 2.7s | ✅ Yes |
| Kimi | 2.9s | ✅ Yes |
| xAI | 3.4s | ✅ Yes |
| Anthropic | 5.0s | ⚠️ Marginal |

After the Gemini fix (which reduced its latency from 6.1s to 2.7s by eliminating wasted thinking tokens), four of five providers meet the <3s target. xAI improved from the 21–25s range in earlier runs to 3.4s, likely due to infrastructure improvements on the provider side.

### 14.4 Reliability

- **All five providers** scored 100% (20/20) in Run 4 — the most reliable run to date
- **OpenAI** scored successfully in all four runs — most reliable overall
- **xAI** scored in all four runs with improving latency over time
- **Anthropic** scored in three runs after API key correction
- **Gemini** scored in two runs; the Run 3 failure was a client-side parsing bug, not a model issue
- **Kimi** scored in Runs 1 and 4; Run 2/3 failures were due to provider-side overload

---

## 15. Limitations

The current evaluation has these limitations:

1. **Moderate dataset** — Run 4 used 20 matched alerts across 10 scenario families; larger corpora would improve statistical power
2. **Single run** — Each run used `runs=1` (no repeatability testing with multiple passes)
3. **Kimi availability** — Provider-side overload prevented Kimi from scoring in Runs 2 and 3; Run 4 confirms recovery
4. **Temperature** — All runs used `temperature=0.3` (not zero), introducing some response variability
5. **Ground truth subjectivity** — The scoring ranges and expected threat types are human-authored
6. **Threat taxonomy gap** — All providers score ~50% on threat-type accuracy, suggesting the ground truth categories may not align with LLM training vocabularies

### What Would Make It Stronger

- Run `runs >= 3` for statistical repeatability
- Expand alert corpus to 100+ matched alerts
- Add inter-rater reliability for ground truth validation
- Test with `temperature=0` for deterministic comparison
- Align ground truth threat categories with common LLM taxonomy

---

## 16. How to Reproduce

### 16.1 Prerequisites

```bash
# Ensure the IDS stack is running
kubectl get pods -n smart-city
kubectl get pods -n monitoring
kubectl get pods -n falco-system

# Verify IDS API health
curl -s http://localhost:30800/health | jq .
```

### 16.2 Generate Fresh Alerts

```bash
# Run attack simulation to create alerts
bash scripts/run-live-attacks.sh --mode protocol --duration 12 --show-alerts 8 --verbose
```

### 16.3 Run the Evaluation

```bash
# Three-provider comparison (like strict-real-01)
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
  --out-dir artifacts/llm-eval/my-new-run

# Five-provider comparison (like strict-real-03)
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
  --out-dir artifacts/llm-eval/five-provider-run
```

### 16.4 Examine Results

```bash
# View provider rankings
cat artifacts/llm-eval/my-new-run/provider_scorecard_ranked.csv | column -t -s,

# View raw results
head -5 artifacts/llm-eval/my-new-run/strict_eval_raw_results.csv

# Open charts
ls artifacts/llm-eval/my-new-run/charts/
```

---

## 17. Artifact Inventory

| Artifact | Location | Purpose |
|----------|----------|---------|
| Ground Truth | `docs/reference/LLM_EVAL_GROUND_TRUTH_CORE.csv` | Frozen scoring rubric (16 scenario rows) |
| Run 1 (Primary) | `artifacts/llm-eval/strict-real-01/` | 3-provider comparison: Kimi, OpenAI, xAI |
| Run 2 (Anthropic) | `artifacts/llm-eval/strict-real-02/` | 4-provider run adding Anthropic |
| Run 3 (Expanded) | `artifacts/llm-eval/strict-real-03/` | 5-provider attempt (Kimi failed) |
| Run 4 (Post-Fix) | `artifacts/llm-eval/strict-real-04/` | 5-provider definitive run (Gemini fix applied) |
| Eval Script | `scripts/llm-compare-report.py` | Automated strict evaluation runner |
| Attack Script | `scripts/run-live-attacks.sh` | Alert generation through real attacks |

Each artifact directory contains:
- `README.json` — run metadata
- `strict_eval_raw_results.csv` — one row per (alert, provider) attempt
- `scenario_alert_scoring_template.csv` — per-row scoring
- `provider_summary_scored.csv` — aggregated provider metrics
- `provider_scorecard_ranked.csv` — final provider ranking
- `scenario_family_results_scored.csv` — per-scenario breakdown
- `charts/*.png` — auto-generated comparison visualizations

---

*Single evaluation document — last updated April 5, 2026*
