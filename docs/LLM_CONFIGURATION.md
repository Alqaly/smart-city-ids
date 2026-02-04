# LLM API Configuration Guide

This guide explains how to configure LLM providers for the Smart City IDS.

## Quick Start (Single Provider)

You only need **ONE** working API key. The system auto-detects available providers.

### Option 1: Google Gemini (Recommended - Free Tier Available)

```bash
# Get free API key at: https://aistudio.google.com/apikey
export GEMINI_API_KEY="AIza..."

# For Kubernetes:
kubectl create secret generic ids-secrets -n smart-city \
  --from-literal=gemini-api-key="AIza..." \
  --dry-run=client -o yaml | kubectl apply -f -
```

### Option 2: Anthropic Claude

```bash
# Get API key at: https://console.anthropic.com/
export ANTHROPIC_API_KEY="sk-ant-..."

kubectl create secret generic ids-secrets -n smart-city \
  --from-literal=anthropic-api-key="sk-ant-..." \
  --dry-run=client -o yaml | kubectl apply -f -
```

### Option 3: OpenAI GPT-4

```bash
# Get API key at: https://platform.openai.com/api-keys
export OPENAI_API_KEY="sk-proj-..."

kubectl create secret generic ids-secrets -n smart-city \
  --from-literal=openai-api-key="sk-proj-..." \
  --dry-run=client -o yaml | kubectl apply -f -
```

### Option 4: xAI Grok

```bash
# Get API key at: https://console.x.ai/
export XAI_API_KEY="xai-..."

kubectl create secret generic ids-secrets -n smart-city \
  --from-literal=xai-api-key="xai-..." \
  --dry-run=client -o yaml | kubectl apply -f -
```

---

## Production Setup (Multiple Providers)

For production, configure multiple providers for failover:

```bash
# Set all available keys
kubectl create secret generic ids-secrets -n smart-city \
  --from-literal=xai-api-key="xai-..." \
  --from-literal=anthropic-api-key="sk-ant-..." \
  --from-literal=openai-api-key="sk-proj-..." \
  --from-literal=gemini-api-key="AIza..." \
  --from-literal=kimi-api-key="sk-..." \
  --dry-run=client -o yaml | kubectl apply -f -

# Restart IDS API to pick up new keys
kubectl rollout restart deployment/ids-api -n smart-city
```

### Configure Failover Priority

```bash
# In ConfigMap or environment:
LLM_PRIORITY=xai,anthropic,openai,gemini,kimi
```

Default order: xai → anthropic → openai → gemini → kimi

---

## Provider Comparison

| Provider | Model | Speed | Cost | Free Tier | Best For |
|----------|-------|-------|------|-----------|----------|
| **xAI Grok** | grok-4-latest | ⚡ Fast | $$ | No | Primary engine |
| **Anthropic** | claude-3-5-sonnet | ⚡ Fast | $$$ | Limited | Strong reasoning |
| **OpenAI** | gpt-4-turbo | ⚡ Fast | $$$ | No | Reliability |
| **Gemini** | gemini-2.0-flash | ⚡⚡ Fastest | $ | **Yes** | Cost-effective |
| **Kimi** | moonshot-v1-128k | 🐢 Slower | $ | Limited | Long context |

---

## Environment Variables Reference

```bash
# API Keys (at least one required)
XAI_API_KEY=xai-...
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-proj-...
GEMINI_API_KEY=AIza...
KIMI_API_KEY=sk-...

# Model overrides (optional)
XAI_MODEL=grok-4-latest
ANTHROPIC_MODEL=claude-3-5-sonnet-20241022
OPENAI_MODEL=gpt-4-turbo-preview
GEMINI_MODEL=gemini-2.0-flash
KIMI_MODEL=moonshot-v1-128k

# Behavior settings (optional)
LLM_PRIORITY=xai,anthropic,openai,gemini,kimi
LLM_TEMPERATURE=0.3      # 0.0-1.0, lower = more consistent
LLM_MAX_TOKENS=1000      # Max response length
LLM_TIMEOUT=30           # API timeout in seconds
```

---

## Verifying Configuration

After setting up, verify the IDS API detected your keys:

```bash
# Check IDS API logs
kubectl logs -n smart-city -l app=ids-api --tail=20 | grep -i "llm\|engine"

# Expected output:
# LLM Manager initialized: engines=['gemini'], priority=['gemini']
```

Or check the health endpoint:

```bash
curl -s http://localhost:8000/health | jq '.llm_engines'
# Expected: ["gemini"] or ["xai", "anthropic", "openai", "gemini"]
```

---

## Troubleshooting

### "No LLM API keys configured"

```bash
# Check secret exists
kubectl get secret ids-secrets -n smart-city -o yaml

# Check keys are set (shows first 10 chars)
kubectl get secret ids-secrets -n smart-city -o jsonpath='{.data.gemini-api-key}' | base64 -d | head -c 10
```

### "API error 429: Rate limited"

Your API key has exhausted its quota. Either:
1. Add billing/credits to the account
2. Configure a different provider
3. Wait for rate limit reset

### "API error 401: Unauthorized"

Invalid API key. Verify:
1. Key is correct (no extra spaces/newlines)
2. Key has not been revoked
3. Key has appropriate permissions

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Alert Processing                      │
├─────────────────────────────────────────────────────────┤
│  Falco Alert → Forwarder → IDS API → LLM Manager        │
│                                         │               │
│  ┌──────────────────────────────────────┴─────────────┐ │
│  │              LLM Engine Manager                     │ │
│  │  ┌────────────────────────────────────────────────┐│ │
│  │  │  Priority Chain: xai → anthropic → openai →    ││ │
│  │  │                  gemini → kimi                 ││ │
│  │  └────────────────────────────────────────────────┘│ │
│  │  ┌────────────────────────────────────────────────┐│ │
│  │  │  Circuit Breaker: Per-engine failure tracking  ││ │
│  │  │  - 5 failures → circuit OPEN (30s cooldown)    ││ │
│  │  │  - Success → circuit CLOSED                    ││ │
│  │  └────────────────────────────────────────────────┘│ │
│  └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

---

## Cost Optimization Tips

1. **Use Gemini** as primary (free tier: 1500 requests/day)
2. **Enable caching** - duplicate alerts reuse cached analysis
3. **Set appropriate timeout** - don't wait too long for slow APIs
4. **Monitor usage** in provider dashboards
