# Grafana/Prometheus Data Audit (2026-02-11)

## Problem Reported
- Unified dashboard showed `gemini` usage even when `GEMINI_API_KEY` is not configured.
- Health cards showed contradictory UP/DOWN values on forwarder panels.

## Live Verification (Cluster)

1. Active API keys in IDS API pod
- `XAI_API_KEY` present
- `OPENAI_API_KEY` present
- `KIMI_API_KEY` present
- `GEMINI_API_KEY` absent
- `ANTHROPIC_API_KEY` absent

2. Health endpoint (`/health`) showed:
- `gemini: "no-api-key"`
- `active_llm_engines: ["xai","openai","kimi"]`

3. Prometheus current usage query
- `sum by(engine)(smartcity_ids_llm_requests_total)` returned only:
  - `xai`, `openai`, `kimi`

4. Prometheus historical max query
- `sum by(engine)(max_over_time(smartcity_ids_llm_requests_total[30d]))` returned historical series including:
  - `gemini`, `anthropic`, `xai-grok-4`, etc.

## Root Cause
- The dashboard in use was the **non-provisioned legacy dashboard** (`uid: smartcity-ids-unified`), not the newer provisioned improved dashboard.
- Legacy panels used cumulative/all-time style expressions and `lastNotNull` reductions.
- Some health panels used `... or vector(0)`, which can produce multiple series (real + fallback), causing mixed UP/DOWN display.

## Fixes Applied

Updated live Grafana dashboard `smartcity-ids-unified` (version 4) and repo file `infrastructure/monitoring/grafana-dashboard-unified.json`:

- `IoT Devices`:
  - `count(iot_device_status)` -> `smartcity_ids_iot_devices_active or vector(0)`
- `LLM Requests`:
  - `sum(smartcity_ids_llm_requests_total)` -> `sum(increase(smartcity_ids_llm_requests_total[15m]))`
  - title updated to `LLM Requests (15m)`
- `LLM Decision Outcomes`:
  - `sum by(outcome)(smartcity_ids_llm_decision_outcome_total)` -> `sum by(outcome) (increase(smartcity_ids_llm_decision_outcome_total[15m]))`
- `LLM Usage by Engine`:
  - `sum by(engine)(smartcity_ids_llm_requests_total)` ->
  - `sum by(engine) (increase(smartcity_ids_llm_requests_total{result="success"}[15m]))`
  - title updated to `LLM Successful Usage by Engine (15m)`
- Health status panels normalized to single-series:
  - `up{job="smart-city-ids"}` -> `max(up{job="smart-city-ids"})`
  - `up{job="suricata-forwarder"}` -> `max(up{job="suricata-forwarder"})`
  - `up{job="falco-forwarder"} or vector(0)` -> `max(up{job="falco-forwarder"})`
  - `suricata_forwarder_up or vector(0)` -> `max(suricata_forwarder_up)`

## Result
- Dashboard no longer reports Gemini as actively used when no key is configured.
- Forwarder/health cards now render a single authoritative UP/DOWN value.
