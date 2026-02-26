# LLM Interface + Pipeline Observability Upgrade (2026-02-13)

> [!IMPORTANT]
> Historical / snapshot document. This file may contain time-bound results, legacy route names, or report-only summaries.
> Do not use it as the current API/runtime contract. Verify current behavior using `docs/INDEX.md`, `docs/API_REFERENCE.md`,
> and live checks (`/health`, `/api/alerts`, `/api/metrics`).


## Scope
This upgrade improves research-grade observability and analyst UX across IDS API and dashboard UI.

## Backend (`services/ids-api/src/main.py`)

### New Prometheus metrics
- `smartcity_ids_llm_tokens_total{engine,kind}`
- `smartcity_ids_alerts_raw_total{source}`
- `smartcity_ids_alerts_after_dedup_total`
- `smartcity_ids_llm_triaged_alerts_total`
- `smartcity_ids_human_review_required_total`

### New API endpoint
- `GET /api/pipeline-overview`
  - Returns stage-level rates/status for:
    - Falco alerts
    - Suricata alerts
    - IDS ingest + dedup
    - LLM/local analysis
    - Governance + K8s actions
  - Returns alert-fatigue summary (`raw_total`, `human_review_required_total`, reduction %).

### LLM stats export improvements
- `GET /api/llm-stats/export` now includes per-engine:
  - `prompt_tokens_total`
  - `completion_tokens_total`
  - `tokens_total`
  - `avg_tokens_per_request`
  - `avg_cost_per_request_usd`

### Traceability
- Added `trace_id` to `AlertResponse`.
- Added `trace_id` to SSE payloads from `/api/alerts` and `/api/alerts/internal`.
- `/api/alerts` now ensures every alert includes `trace_id` (derived from alert ID if missing).

## Frontend (`services/ids-api/static/index.html`)

### Overview tab
- Added **Pipeline Overview** 5-stage strip (rate/min + p95 + status dot).
- Added **Alert Fatigue** card (raw vs dedup vs human-review-required + reduction %).

### LLM tab
- Added **Tokens & Cost per Request** table by engine.

### Alert/trace UX
- Added `Trace` column to Alert History.
- Added trace ID in expanded alert details.
- Added trace ID to Live Pipeline Feed event log entries.

### Analyst-oriented language
- Added note under header:
  - "This dashboard helps security analysts triage and explain alerts, not replace them."
- Rewrote Attack Simulation description to explicitly mention:
  - behavior depends on LLM availability and governance mode,
  - end-to-end pipeline purpose.

## Architecture docs
- Updated `docs/ARCHITECTURE.md` with a **Pipeline-to-Metrics Mapping** section for the new dashboard pipeline row and observability metrics.

## Validation
- `python -m py_compile services/ids-api/src/main.py` ✅
- Targeted tests:
  - `test_internal_alert_controls.py` ✅
  - `test_llm_provider_manager.py` ✅
  - `test_operator_contracts.py` failed due environment auth credentials mismatch (configured credentials rejected), not due compile/runtime syntax.
