# LLM Configuration Guide

Current guide for configuring LLM providers in the Smart City IDS.

## Basic rule

You need at least one working provider key for live LLM analysis.

The project source of truth is the local `.env` file.  
The running cluster uses those values only after you sync them into Kubernetes and redeploy.

## Current workflow

```bash
bash scripts/apply-llm-env-to-k8s-secret.sh .env
bash scripts/deploy-code.sh
bash scripts/llm-manager.sh check
```

## Main environment variables

### Provider keys

```bash
XAI_API_KEY=...
ANTHROPIC_API_KEY=...
OPENAI_API_KEY=...
GEMINI_API_KEY=...
KIMI_API_KEY=...
```

### Model overrides

```bash
XAI_MODEL=grok-4-latest
ANTHROPIC_MODEL=claude-sonnet-4-20250514
OPENAI_MODEL=gpt-4o
GEMINI_MODEL=gemini-2.5-flash-lite
KIMI_MODEL=moonshot-v1-128k
```

### Behavior settings

```bash
LLM_PRIORITY=kimi,xai,anthropic,gemini,openai
LLM_TEMPERATURE=0.3
LLM_MAX_TOKENS=1000
LLM_TIMEOUT=30
```

Use the values in your local `.env` as the current truth.

## What “configured” means

A provider can be:
- configured
- unverified
- operational
- cooldown
- auth failed

Important:
- `configured` does not mean proven usable
- `unverified` means the provider is configured but has not completed a successful live call in the current process

Check current live state with:

```bash
curl -s http://localhost:30800/api/llm/diagnostics | jq .
```

## Strict provider test

Use strict mode when you want to test one provider without fallback contamination:

```bash
TOKEN=$(curl -s -X POST http://localhost:30800/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}' | jq -r '.access_token')

curl -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  "http://localhost:30800/api/llm/test/openai?strict=true" \
  -d '{"test_prompt":"provider strict diagnostic"}' | jq .
```

## Usage metrics

DB-backed usage metrics:

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:30800/api/metrics/llm-usage?window=today" | jq .
```

Important:
- this counts real alert-analysis calls
- manual provider tests and probes do not increment these totals

---

## Troubleshooting

### Recovery when providers are down

If providers are latched `auth_failed` after a bad startup probe or stale credentials:

```bash
curl -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  http://localhost:30800/api/llm/retry-all | jq .
```

Full recovery runbook:
1. Fix credentials/credits at provider side (API keys, billing/quota).
2. Update `.env` and sync K8s secret: `bash scripts/apply-llm-env-to-k8s-secret.sh`
3. Restart ids-api: `bash scripts/deploy-code.sh`
4. Reset provider state: `POST /api/llm/retry-all`
5. Probe a provider from LLM Control to verify runtime health.

### Status meanings

| Status | Meaning |
|--------|---------|
| `configured` | Key present but not yet proven usable |
| `unverified` | Configured but no successful live call in current process |
| `operational` | Working and available for routing |
| `cooldown` | Recent non-retryable error (401/403/429); timer-based recovery |
| `auth_failed` | Explicit auth failure; needs credential fix + retry-all |
| `not_configured` | Missing API key in environment |

### Fallback chain behavior

- Default chain comes from `LLM_PRIORITY` plus runtime updates.
- Alert execution tries providers in order, skipping cooldown/unavailable entries.
- Runtime chain can be changed from LLM Control (`Apply Priority`) or API.

### Provider card semantics

Provider cards separate three checks:
- **Analysis**: whether the provider can process IDS analysis calls
- **Billing endpoint**: whether the dashboard can reach the billing/credit path
- **Balance visibility**: whether a usable balance number is exposed

A provider can be operational for analysis while showing restricted billing or hidden balance.

### Cost formula

Token-based estimate: `estimated_cost = (prompt_tokens + completion_tokens) / 1000 * provider_rate_per_1k`

Token counts prefer provider-reported usage; fallback estimator is used only when actual counts are missing.

## Common problems

### 401
- invalid or revoked key
- wrong provider account/project

### 429
- quota exhausted
- billing problem
- provider-side rate limit

### Cooldown
- the IDS temporarily suppresses the provider after failures

## Operational note

Provider availability is a runtime condition.  
Do not claim that all configured providers are simultaneously operational unless the live diagnostics prove it.
