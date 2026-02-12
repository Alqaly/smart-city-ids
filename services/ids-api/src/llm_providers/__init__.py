"""
LLM Providers - Plugin-based Architecture

This module provides a GENERIC, EXTENSIBLE way to add LLM providers.
No hardcoded provider names - just register any provider that implements BaseProvider.

Usage:
    from llm_providers import ProviderRegistry, get_available_providers
    
    # Get all providers with valid API keys
    providers = get_available_providers()
    
    # Use first available provider
    result = await providers[0].analyze(alert)

Adding a new provider:
    1. Create a class that extends BaseProvider
    2. Register it with @ProviderRegistry.register("name")
    3. Set the API key env var: <NAME>_API_KEY
    
    That's it. No other code changes needed.
"""

from .base import BaseProvider, ProviderConfig
from .registry import ProviderRegistry, get_available_providers, get_provider

__all__ = [
    "BaseProvider",
    "ProviderConfig", 
    "ProviderRegistry",
    "get_available_providers",
    "get_provider",
]
