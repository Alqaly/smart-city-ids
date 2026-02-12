"""
LLM Manager - Unified interface for LLM providers

This manager provides:
- Auto-discovery of available providers
- Failover between providers
- Caching to reduce API costs
- Consistent response format

Usage:
    from llm_providers.manager import LLMManager
    
    manager = LLMManager()
    print(f"Available: {manager.get_available_providers()}")
    
    result = await manager.analyze(alert)
"""

import logging
import time
import os
from typing import Dict, Any, List, Optional

from .base import ProviderConfig
from .registry import ProviderRegistry, get_available_providers
# Import providers to trigger registration
from . import providers  # noqa: F401

logger = logging.getLogger(__name__)


class LLMManager:
    """
    Unified LLM Manager with auto-discovery and failover.
    
    Works with any number of providers (1, 2, or N).
    No special cases - same code path for all configurations.
    """
    
    def __init__(self, config: Optional[ProviderConfig] = None):
        """
        Initialize manager by discovering available providers.
        
        Args:
            config: Optional shared config. If None, loads from environment.
        """
        self.config = config or ProviderConfig()
        discovered_providers = get_available_providers(self.config)
        self.providers = self._sort_providers_by_priority(discovered_providers)
        self.runtime_stats = {
            provider.NAME: {
                "attempts": 0,
                "successes": 0,
                "failures": 0,
                "last_latency_ms": None,
                "last_error": None,
                "last_success_at": None,
            }
            for provider in self.providers
        }
        self.cooldown_seconds = int(os.getenv("LLM_PROVIDER_COOLDOWN_SECONDS", "900"))
        self.provider_cooldown_until = {provider.NAME: 0.0 for provider in self.providers}
        
        if not self.providers:
            raise RuntimeError(
                "No LLM providers available. Set at least one API key:\n"
                + "\n".join(f"  - {name}: {cls.ENV_KEY}" 
                           for name, cls in ProviderRegistry.get_all_registered().items())
            )
        
        # Log available providers
        provider_names = [p.NAME for p in self.providers]
        logger.info(f"🔧 LLM Manager: {len(self.providers)} provider(s) available")
        for p in self.providers:
            logger.info(f"   ✅ {p.NAME} ({p.model})")

    def _sort_providers_by_priority(self, providers: List[Any]) -> List[Any]:
        """Sort available providers using LLM_PRIORITY with stable fallback."""
        priority_order = {name: idx for idx, name in enumerate(self.config.priority)}
        return sorted(
            providers,
            key=lambda provider: priority_order.get(provider.NAME, len(priority_order) + 1)
        )
    
    def get_available_providers(self) -> List[str]:
        """Get names of all available providers."""
        return [p.NAME for p in self.providers]
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get comprehensive status.
        
        Returns:
            {
                "provider_count": 2,
                "providers": ["openai", "anthropic"],
                "details": {...}
            }
        """
        return {
            "provider_count": len(self.providers),
            "providers": [p.NAME for p in self.providers],
            "priority_order": self.config.priority,
            "details": {
                p.NAME: {
                    "model": p.model,
                    "base_url": p.base_url,
                    "cooldown_until": int(self.provider_cooldown_until.get(p.NAME, 0)),
                    "cooldown_remaining_seconds": max(0, int(self.provider_cooldown_until.get(p.NAME, 0) - time.time())),
                    **self.runtime_stats.get(p.NAME, {}),
                }
                for p in self.providers
            }
        }

    def _is_provider_in_cooldown(self, provider_name: str) -> bool:
        cooldown_until = self.provider_cooldown_until.get(provider_name, 0)
        return cooldown_until > time.time()

    def _activate_provider_cooldown(self, provider_name: str, reason: str):
        cooldown_until = time.time() + self.cooldown_seconds
        self.provider_cooldown_until[provider_name] = cooldown_until
        logger.warning(
            f"{provider_name} entered cooldown for {self.cooldown_seconds}s due to non-retryable provider error: {reason}"
        )

    def _should_cooldown_provider(self, error_message: str) -> bool:
        msg = (error_message or "").lower()
        cooldown_indicators = (
            "insufficient_quota",
            "quota",
            "resource has been exhausted",
            "used all available credits",
            "monthly spending limit",
            "exhausted",
            "invalid api key",
            "incorrect api key",
            "authentication",
            "unauthorized",
            "api error 401",
            "api error 403",
            "api error 429",
        )
        return any(indicator in msg for indicator in cooldown_indicators)
    
    async def analyze(self, alert: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze an alert using available provider(s).
        
        Tries providers in order until one succeeds.
        
        Args:
            alert: Security alert dict
            
        Returns:
            {
                "status": "success" | "error",
                "analysis": {...},
                "provider": "openai",
                "model": "gpt-4",
                "latency_ms": 234,
                "providers_tried": ["xai", "openai"]
            }
        """
        start = time.perf_counter()
        providers_tried = []
        provider_errors = []
        last_error = None
        
        for provider in self.providers:
            if self._is_provider_in_cooldown(provider.NAME):
                remaining = max(0, int(self.provider_cooldown_until.get(provider.NAME, 0) - time.time()))
                last_error = f"{provider.NAME} in cooldown ({remaining}s remaining)"
                provider_errors.append({"provider": provider.NAME, "error": last_error})
                logger.info(last_error)
                continue

            providers_tried.append(provider.NAME)
            self.runtime_stats[provider.NAME]["attempts"] += 1
            
            try:
                result = await provider.analyze(alert)
                
                if result.get("status") == "success":
                    self.runtime_stats[provider.NAME]["successes"] += 1
                    self.runtime_stats[provider.NAME]["last_latency_ms"] = result.get("latency_ms")
                    self.runtime_stats[provider.NAME]["last_error"] = None
                    self.runtime_stats[provider.NAME]["last_success_at"] = int(time.time())
                    result["providers_tried"] = providers_tried
                    return result
                
                # Provider returned error, try next
                last_error = result.get("error", "Unknown error")
                provider_errors.append({"provider": provider.NAME, "error": last_error})
                self.runtime_stats[provider.NAME]["failures"] += 1
                self.runtime_stats[provider.NAME]["last_latency_ms"] = result.get("latency_ms")
                self.runtime_stats[provider.NAME]["last_error"] = last_error
                if self._should_cooldown_provider(last_error):
                    self._activate_provider_cooldown(provider.NAME, last_error)
                logger.warning(f"{provider.NAME} failed: {last_error}")
                
            except Exception as e:
                last_error = str(e)
                provider_errors.append({"provider": provider.NAME, "error": last_error})
                self.runtime_stats[provider.NAME]["failures"] += 1
                self.runtime_stats[provider.NAME]["last_error"] = last_error
                if self._should_cooldown_provider(last_error):
                    self._activate_provider_cooldown(provider.NAME, last_error)
                logger.warning(f"{provider.NAME} exception: {e}")
        
        # All providers failed
        latency_ms = int((time.perf_counter() - start) * 1000)
        return {
            "status": "error",
            "error": f"All providers failed. Last: {last_error}",
            "provider": providers_tried[-1] if providers_tried else "none",
            "providers_tried": providers_tried,
            "provider_errors": provider_errors,
            "latency_ms": latency_ms
        }


# Singleton instance
_manager: Optional[LLMManager] = None


def get_llm_manager() -> LLMManager:
    """Get or create the singleton LLM Manager."""
    global _manager
    if _manager is None:
        _manager = LLMManager()
    return _manager


def reset_llm_manager():
    """Reset the singleton (for testing)."""
    global _manager
    _manager = None
