"""
Built-in LLM Providers

This file contains implementations for common LLM providers.
Each provider auto-registers with the ProviderRegistry.

To add a new provider:
1. Create a class extending BaseProvider
2. Set NAME, ENV_KEY, DEFAULT_MODEL, DEFAULT_BASE_URL
3. Implement _call_api()
4. Add @ProviderRegistry.register("name") decorator

That's it - the provider will be auto-discovered.
"""

import httpx
import logging

from .base import BaseProvider, ProviderConfig
from .registry import ProviderRegistry

logger = logging.getLogger(__name__)


# =============================================================================
# OpenAI-compatible providers (most common API format)
# =============================================================================

@ProviderRegistry.register("openai")
class OpenAIProvider(BaseProvider):
    """OpenAI GPT models"""
    NAME = "openai"
    ENV_KEY = "OPENAI_API_KEY"
    DEFAULT_MODEL = "gpt-4-turbo-preview"
    DEFAULT_BASE_URL = "https://api.openai.com/v1"
    
    async def _call_api(self, system_prompt: str, user_prompt: str) -> str:
        async with httpx.AsyncClient(timeout=self.config.timeout) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}"
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": self.config.temperature,
                    "max_tokens": self.config.max_tokens,
                    "response_format": {"type": "json_object"}
                }
            )
            if response.status_code != 200:
                raise Exception(f"API error {response.status_code}: {response.text[:200]}")
            return response.json()["choices"][0]["message"]["content"]


@ProviderRegistry.register("xai")
class XAIProvider(BaseProvider):
    """xAI Grok models"""
    NAME = "xai"
    ENV_KEY = "XAI_API_KEY"
    DEFAULT_MODEL = "grok-4-latest"
    DEFAULT_BASE_URL = "https://api.x.ai/v1"
    
    async def _call_api(self, system_prompt: str, user_prompt: str) -> str:
        async with httpx.AsyncClient(timeout=self.config.timeout) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}"
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": self.config.temperature,
                    "max_tokens": self.config.max_tokens
                }
            )
            if response.status_code != 200:
                raise Exception(f"API error {response.status_code}: {response.text[:200]}")
            return response.json()["choices"][0]["message"]["content"]


@ProviderRegistry.register("kimi")
class KimiProvider(BaseProvider):
    """Moonshot Kimi models (OpenAI-compatible)"""
    NAME = "kimi"
    ENV_KEY = "KIMI_API_KEY"
    DEFAULT_MODEL = "moonshot-v1-8k"
    DEFAULT_BASE_URL = "https://api.moonshot.ai/v1"
    
    async def _call_api(self, system_prompt: str, user_prompt: str) -> str:
        async with httpx.AsyncClient(timeout=60.0) as client:  # Kimi can be slower
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}"
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": self.config.temperature,
                    "max_tokens": self.config.max_tokens
                }
            )
            if response.status_code != 200:
                raise Exception(f"API error {response.status_code}: {response.text[:200]}")
            return response.json()["choices"][0]["message"]["content"]


# =============================================================================
# Anthropic (different API format)
# =============================================================================

@ProviderRegistry.register("anthropic")
class AnthropicProvider(BaseProvider):
    """Anthropic Claude models"""
    NAME = "anthropic"
    ENV_KEY = "ANTHROPIC_API_KEY"
    DEFAULT_MODEL = "claude-3-5-sonnet-20241022"
    DEFAULT_BASE_URL = "https://api.anthropic.com/v1"
    
    async def _call_api(self, system_prompt: str, user_prompt: str) -> str:
        async with httpx.AsyncClient(timeout=self.config.timeout) as client:
            response = await client.post(
                f"{self.base_url}/messages",
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01"
                },
                json={
                    "model": self.model,
                    "max_tokens": self.config.max_tokens,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_prompt}]
                }
            )
            if response.status_code != 200:
                raise Exception(f"API error {response.status_code}: {response.text[:200]}")
            return response.json()["content"][0]["text"]


# =============================================================================
# Google Gemini (different API format)
# =============================================================================

@ProviderRegistry.register("gemini")
class GeminiProvider(BaseProvider):
    """Google Gemini models"""
    NAME = "gemini"
    ENV_KEY = "GEMINI_API_KEY"
    DEFAULT_MODEL = "gemini-2.0-flash"
    DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
    
    async def _call_api(self, system_prompt: str, user_prompt: str) -> str:
        url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"
        async with httpx.AsyncClient(timeout=self.config.timeout) as client:
            response = await client.post(
                url,
                headers={"Content-Type": "application/json"},
                json={
                    "system_instruction": {"parts": [{"text": system_prompt}]},
                    "contents": [{"parts": [{"text": user_prompt}]}],
                    "generationConfig": {
                        "temperature": self.config.temperature,
                        "maxOutputTokens": self.config.max_tokens,
                        "responseMimeType": "application/json"
                    }
                }
            )
            if response.status_code != 200:
                raise Exception(f"API error {response.status_code}: {response.text[:200]}")
            return response.json()["candidates"][0]["content"]["parts"][0]["text"]


# =============================================================================
# Generic OpenAI-compatible provider (for custom endpoints)
# =============================================================================

@ProviderRegistry.register("custom")
class CustomOpenAIProvider(BaseProvider):
    """
    Generic OpenAI-compatible provider for custom endpoints.
    
    Set these environment variables:
        CUSTOM_API_KEY    - API key
        CUSTOM_MODEL      - Model name
        CUSTOM_BASE_URL   - API endpoint (e.g., http://localhost:8080/v1)
    """
    NAME = "custom"
    ENV_KEY = "CUSTOM_API_KEY"
    DEFAULT_MODEL = "default"
    DEFAULT_BASE_URL = "http://localhost:8080/v1"
    
    async def _call_api(self, system_prompt: str, user_prompt: str) -> str:
        async with httpx.AsyncClient(timeout=self.config.timeout) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}"
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": self.config.temperature,
                    "max_tokens": self.config.max_tokens
                }
            )
            if response.status_code != 200:
                raise Exception(f"API error {response.status_code}: {response.text[:200]}")
            return response.json()["choices"][0]["message"]["content"]
