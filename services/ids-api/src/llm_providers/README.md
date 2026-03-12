# LLM Providers - Generic Plugin System

This package provides a **generic, extensible LLM provider system** that works with any provider.

## Quick Start

```bash
# Set any API key - that's it
export OPENAI_API_KEY="sk-..."
# or
export ANTHROPIC_API_KEY="sk-ant-..."
# or any supported provider
```

The system **auto-discovers** which providers are available based on environment variables.

## Usage

```python
from llm_providers.manager import LLMManager

manager = LLMManager()  # Auto-discovers available providers
print(manager.get_available_providers())  # ['openai', 'anthropic', ...]

# Analyze an alert
result = await manager.analyze(alert_dict)

# Runtime status (provider order + health stats)
status = manager.get_status()
```

## Supported Providers

| Provider | API Key Env Var | Default Model |
|----------|-----------------|---------------|
| OpenAI | `OPENAI_API_KEY` | gpt-4o |
| Anthropic | `ANTHROPIC_API_KEY` | claude-sonnet-4-20250514 |
| Google Gemini | `GEMINI_API_KEY` | gemini-2.5-flash-lite |
| xAI (Grok) | `XAI_API_KEY` | grok-4-latest |
| Moonshot (Kimi) | `KIMI_API_KEY` | moonshot-v1-128k |
| Custom | `CUSTOM_API_KEY` | (configurable) |

### Custom Model/URL

For any provider, you can override:

```bash
export OPENAI_MODEL="gpt-4o"
export OPENAI_BASE_URL="https://api.custom-endpoint.com/v1"
```

### Failover Priority

Control provider order globally:

```bash
export LLM_PRIORITY="xai,anthropic,openai,gemini,kimi,custom"
```

`LLMManager` sorts available providers using this list and then fails over in that order.

## Adding a New Provider

1. Create a class in `providers.py`:

```python
@ProviderRegistry.register("myprovider")
class MyProvider(BaseProvider):
    NAME = "myprovider"
    ENV_KEY = "MYPROVIDER_API_KEY"
    DEFAULT_MODEL = "my-model-v1"
    DEFAULT_BASE_URL = "https://api.myprovider.com/v1"
    
    async def _call_api(self, prompt: str) -> str:
        # Make API call, return raw response text
        ...
```

That's it. The system will **auto-discover** your provider when the API key is set.

### OpenAI-Compatible APIs

If your provider uses OpenAI-compatible format:

```python
@ProviderRegistry.register("myprovider")
class MyProvider(BaseProvider):
    NAME = "myprovider"
    ENV_KEY = "MYPROVIDER_API_KEY"
    DEFAULT_MODEL = "my-model"
    DEFAULT_BASE_URL = "https://api.myprovider.com/v1"
    
    async def _call_api(self, prompt: str) -> str:
        # Use the same pattern as OpenAIProvider
        return await self._openai_compatible_call(prompt)
```

## Architecture

```
llm_providers/
├── __init__.py      # Package exports
├── base.py          # BaseProvider abstract class
├── registry.py      # ProviderRegistry with auto-discovery
├── providers.py     # Concrete provider implementations
├── manager.py       # LLMManager for unified access
└── README.md        # This file
```

### Design Principles

1. **No hardcoded provider lists** - Everything is discovered dynamically
2. **Plugin pattern** - Use `@ProviderRegistry.register()` decorator
3. **Environment-driven** - Set API key = provider is available
4. **Unified interface** - All providers implement `BaseProvider.analyze()`
5. **Failover built-in** - Manager tries providers in order until one works
