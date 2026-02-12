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
curl -s http://localhost:8000/health | jq '.components.llm_providers'
# Expected: provider connectivity + circuit breaker state
```

Or inspect detailed manager status:

```bash
curl -s http://localhost:8000/api/llm/status | jq
# Includes:
# - provider_count
# - providers (in failover order)
# - priority_order (from LLM_PRIORITY)
# - per-provider runtime stats (attempts/successes/failures/last_error)
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

---

## How the Unified LLM Manager Works

The system uses a **unified approach** that works identically whether you have 1 engine or 10.
No special cases. No "single engine mode". Just one code path.

### Architecture

```
┌────────────────────────────────────────────────────────┐
│                  LLMEngineManager                      │
├────────────────────────────────────────────────────────┤
│  Alert → Manager → Try first available engine          │
│                       │                                │
│                   Success?                             │
│                    /     \                             │
│                  Yes      No                           │
│                   │        │                           │
│               Return    Try next engine (if any)       │
│                            │                           │
│                        (repeat)                        │
└────────────────────────────────────────────────────────┘

Works the same for:
- 1 engine (just try it)
- 2 engines (try first, failover to second)
- N engines (try in priority order)
```

### Example Configurations

**1 Engine:**
```bash
export KIMI_API_KEY="sk-..."
# Just works. No special mode needed.
```

**3 Engines:**
```bash
export XAI_API_KEY="xai-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export GEMINI_API_KEY="AIza..."
export LLM_PRIORITY="xai,anthropic,gemini"
# Tries xai first, then anthropic, then gemini
```

### Startup Logs

```
🔧 LLM Manager: 1 provider(s) available
   ✅ kimi (moonshot-v1-128k)
✅ IDS API ready with 1 LLM provider(s)
```

Or with multiple:

```
🔧 LLM Manager: 3 provider(s) available
   ✅ xai (grok-4-latest)
   ✅ anthropic (claude-3-5-sonnet-20241022)
   ✅ gemini (gemini-2.0-flash)
✅ IDS API ready with 3 LLM provider(s)
```

---

## Check Current LLM Status

Use the `/api/llm/status` endpoint:

```bash
curl http://localhost:8000/api/llm/status | jq
```

**Response:**
```json
{
  "provider_count": 1,
  "providers": ["kimi"],
  "priority_order": ["kimi"],
  "details": {
    "kimi": {
      "model": "moonshot-v1-128k",
      "attempts": 12,
      "successes": 12,
      "failures": 0,
      "last_latency_ms": 420,
      "last_error": null,
      "last_success_at": 1739280000
    }
  }
}
```

---

## How LLM Providers Work Internally

### 1. Provider Initialization (`main.py`)

```python
from llm_providers.manager import LLMManager
llm_manager = LLMManager()  # auto-discovers providers by API key presence
```

### 2. Alert Analysis Flow

```python
# Single entry point - works for 1 or N providers
result = await llm_manager.analyze(alert_dict)

# Result includes which provider succeeded
provider_used = result.get("provider")
analysis = result.get("analysis")
```

---

## Adding a New LLM Provider

1. **Create engine class** in `llm_manager.py`:

```python
import httpx
from config import Config

class NewProviderEngine:
    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or Config.NEWPROVIDER_API_KEY
        self.model = model or Config.NEWPROVIDER_MODEL
        self.base_url = "https://api.newprovider.com/v1"
    
    def analyze(self, alert: dict) -> dict:
        # Implement API call
        ...
```

2. **Add config** in `config.py`:

```python
NEWPROVIDER_API_KEY = os.getenv("NEWPROVIDER_API_KEY")
NEWPROVIDER_MODEL = os.getenv("NEWPROVIDER_MODEL", "default-model")
```

3. **Register engine** in `main.py`:

```python
from llm_engine_newprovider import NewProviderEngine

if Config.NEWPROVIDER_API_KEY:
    llm_engines['newprovider'] = NewProviderEngine()
```

4. **Update priority** in config:

```python
LLM_PRIORITY = ['xai', 'anthropic', 'openai', 'gemini', 'kimi', 'newprovider']
```

---

## Common Patterns

### Use Specific Engine

```python
# Force use of specific engine (bypasses failover)
engine = llm_engines.get('gemini')
if engine:
    result = engine.analyze(alert)
```

### Check Engine Health

```bash
# API endpoint
curl http://localhost:8000/api/llm/status | jq '.circuit_breaker_summary'

# Or check circuit breaker directly
curl http://localhost:8000/api/circuit-breaker/status | jq
```

### Reset Failing Engine

```bash
# Reset specific engine's circuit breaker
curl -X POST http://localhost:8000/api/circuit-breaker/reset/gemini
```

---

## Performance Tuning

| Setting | Default | Description |
|---------|---------|-------------|
| `LLM_TIMEOUT` | 30s | Max wait for API response |
| `LLM_TEMPERATURE` | 0.3 | Lower = more consistent analysis |
| `LLM_MAX_TOKENS` | 1000 | Max response length |
| `CIRCUIT_FAILURE_THRESHOLD` | 5 | Failures before opening circuit |
| `CIRCUIT_RECOVERY_TIMEOUT` | 30s | Wait before retry after failure |
