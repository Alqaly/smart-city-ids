# LLM Control & Troubleshooting Guide

This document explains the LLM provider dashboard behavior, failover chain, cooldown logic, cost math, and how to recover when providers are down.

## 1) Why header may show `0/N LLM Operational` while a provider has past successes

- `Operational` is **current runtime state**, not historical success count.
- A provider can have historical successes and still be `cooldown` now due to recent auth/quota failures.
- Past calls are kept in attempts/success/failure counters; status reflects **what can be used now**.

## 2) What `cooldown` means

- Cooldown is activated after non-retryable provider errors (401/403/429, quota/auth messages).
- Timer duration uses `LLM_PROVIDER_COOLDOWN_SECONDS` (default 900s).
- Remaining time is shown as `cooldown: <seconds> remaining`.

## 3) Why `Probe: not probed`

- Live probes are intentionally not run on every refresh to avoid cost/rate overhead.
- Probe results appear after:
  - LLM Control -> `Live Probe` click, or
  - explicit endpoint call with `probe=true`.

## 4) When `Active Provider` can become `NONE`/empty

- No configured/selectable providers available, or
- startup before first successful call and no forced provider, or
- all configured providers currently in unusable state.

## 5) Fallback chain behavior

- Default chain comes from runtime priority (`LLM_PRIORITY` + runtime updates).
- Alert execution tries providers in order, skipping cooldown/unavailable entries.
- Runtime chain can be changed from LLM Control (`Apply Priority`) or API.

## 6) Why `not_configured` appears

- Missing API key for that provider in environment.
- Example: no `ANTHROPIC_API_KEY` -> `anthropic` is `not_configured`.

## 7) Why `Credits: error` can happen while calls succeeded earlier

- Credit check endpoint is independent from inference call path.
- A provider may have succeeded earlier but credit-check API can still fail (network, auth scope, provider API difference).
- UI now treats missing credit data as `unavailable` rather than implying execution failure.

## 8) Cost formula (dashboard)

- Cost is token-based estimate:
  - `estimated_cost = (prompt_tokens + completion_tokens) / 1000 * provider_rate_per_1k`
- Token counts prefer provider-reported usage; fallback estimator is used only when missing.

## 9) Why `unknown` / `none` used to appear in provider comparison

- Those labels came from unresolved failed-call metadata.
- Metrics export now filters pseudo-engines (`unknown`, `none`, `cache`) from provider comparison.

## 10) Interactive Provider Test behavior

- Sends test prompt via `/api/llm/control/test`.
- Uses selected provider (or auto router) and returns status, latency, analysis/error payload.

---

## Recovery runbook (when providers are down)

1. **Fix credentials/credits** at provider side (API keys, billing/quota).
2. **Update `.env` and sync K8s secret** (project standard path):
   - `bash scripts/apply-llm-env-to-k8s-secret.sh`
3. **Restart/redeploy `ids-api`** so new env values are loaded.
4. **Reset provider state + breakers** via API/UI:
   - `POST /api/llm/retry-all` (preferred)
   - optional targeted breaker reset: `POST /api/circuit-breaker/reset`
5. **Probe/Test** a provider from LLM Control to verify runtime health.
6. **Set temporary fallback order** to most reliable providers until full recovery.

Notes:
- `retry-all` clears in-memory cooldown/circuit state; it does not fix invalid keys or exhausted credits.
- A provider can be `configured` but unusable due quota/billing/model-access issues.

---

## Scalability/sharability recommendations

- Keep per-provider credentials in secret manager (not static env in manifests).
- Export LLM diagnostics + routing state to shared ops dashboard.
- Use routing mode `severity_adaptive` in production for cost/perf balance.
- Keep assisted governance mode for critical actions.
- Add synthetic health probes with alerting (not continuous expensive probing).
