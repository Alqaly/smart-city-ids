"""
Provider Registry - Auto-discovery of LLM providers

This module provides automatic discovery of all available LLM providers.
Providers register themselves using the @ProviderRegistry.register decorator.

The system will automatically:
1. Find all registered providers
2. Check which have valid API keys
3. Make them available for use

No hardcoded provider lists. Add a new provider = it just works.
"""

import os
import logging
from typing import Dict, Type, List, Optional, Any

from .base import BaseProvider, ProviderConfig

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """
    Central registry for LLM providers.
    
    Usage:
        # Register a provider
        @ProviderRegistry.register("openai")
        class OpenAIProvider(BaseProvider):
            ...
        
        # Get all available providers
        providers = ProviderRegistry.get_available()
        
        # Get specific provider
        provider = ProviderRegistry.get("openai")
    """
    
    _providers: Dict[str, Type[BaseProvider]] = {}
    
    @classmethod
    def register(cls, name: str):
        """
        Decorator to register a provider class.
        
        Usage:
            @ProviderRegistry.register("myprovider")
            class MyProvider(BaseProvider):
                ...
        """
        def decorator(provider_class: Type[BaseProvider]):
            cls._providers[name] = provider_class
            logger.debug(f"Registered LLM provider: {name}")
            return provider_class
        return decorator
    
    @classmethod
    def get_all_registered(cls) -> Dict[str, Type[BaseProvider]]:
        """Get all registered provider classes (whether available or not)."""
        return dict(cls._providers)
    
    @classmethod
    def get_available(cls, config: Optional[ProviderConfig] = None) -> List[BaseProvider]:
        """
        Get instances of all providers that have valid API keys.
        
        Args:
            config: Optional shared config. If None, loads from environment.
            
        Returns:
            List of initialized provider instances
        """
        config = config or ProviderConfig()
        available = []
        
        for name, provider_class in cls._providers.items():
            if provider_class.is_available():
                try:
                    instance = provider_class(config)
                    available.append(instance)
                except Exception as e:
                    logger.warning(f"Failed to initialize {name}: {e}")
        
        return available
    
    @classmethod
    def get(cls, name: str, config: Optional[ProviderConfig] = None) -> Optional[BaseProvider]:
        """
        Get a specific provider by name.
        
        Args:
            name: Provider name
            config: Optional shared config
            
        Returns:
            Provider instance or None if not available
        """
        provider_class = cls._providers.get(name)
        if not provider_class:
            return None
        
        if not provider_class.is_available():
            return None
        
        config = config or ProviderConfig()
        return provider_class(config)
    
    @classmethod
    def get_status(cls) -> Dict[str, Any]:
        """
        Get status of all registered providers.
        
        Returns:
            {
                "registered": ["openai", "anthropic", ...],
                "available": ["openai"],  # Those with valid API keys
                "details": {
                    "openai": {"available": True, "env_key": "OPENAI_API_KEY", ...},
                    ...
                }
            }
        """
        registered = list(cls._providers.keys())
        available = []
        details = {}
        
        for name, provider_class in cls._providers.items():
            info = provider_class.get_info()
            details[name] = info
            if info["available"]:
                available.append(name)
        
        return {
            "registered": registered,
            "available": available,
            "count": len(available),
            "details": details
        }


# Convenience functions
def get_available_providers(config: Optional[ProviderConfig] = None) -> List[BaseProvider]:
    """Get all providers with valid API keys."""
    return ProviderRegistry.get_available(config)


def get_provider(name: str, config: Optional[ProviderConfig] = None) -> Optional[BaseProvider]:
    """Get a specific provider by name."""
    return ProviderRegistry.get(name, config)


def get_provider_status() -> Dict[str, Any]:
    """Get status of all providers."""
    return ProviderRegistry.get_status()
