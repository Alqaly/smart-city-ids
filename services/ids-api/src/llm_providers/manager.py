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

import asyncio
import logging
import time
import os
from typing import Dict, Any, List, Optional

from .base import BaseProvider, ProviderConfig
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
        
        # Try to load priority from database
        try:
            from api._state import db
            db_priority = db.get_system_config('llm_priority')
            if db_priority:
                self.config.priority = db_priority
                logger.info(f"Loaded LLM priority from database: {self.config.priority}")
        except Exception as e:
            logger.warning(f"Could not load LLM priority from database: {e}")
            
        discovered_providers = get_available_providers(self.config)
        self.providers = self._sort_providers_by_priority(discovered_providers)
        self.provider_states = {
            name: {
                "status": "operational",  # operational, cooldown, auth_failed
                "reason": "Ready (no requests yet)",
                "last_error": None,
                "last_error_ts": None,
                "cooldown_until": 0,
                "auth_failed_at": 0,
                "attempts": 0,
                "successes": 0,
                "failures": 0,
            }
            for name in self.providers
        }
        self.state_lock = asyncio.Lock()
        self.runtime_stats = {
            provider.NAME: {
                "attempts": 0,
                "successes": 0,
                "failures": 0,
                "last_latency_ms": None,
                "last_error": None,
                "last_success_at": None,
                "latencies": [],
            }
            for provider in self.providers
        }
        self.cooldown_seconds = int(os.getenv("LLM_PROVIDER_COOLDOWN_SECONDS", "900"))
        # Backward-compatible alias used by older error-handling branches.
        self.rate_limit_cooldown_seconds = self.cooldown_seconds
        # Auth failures (401/403) should not trigger long cooldowns.
        # Instead we temporarily disable the provider to stop tight retry loops.
        self.auth_disable_seconds = int(os.getenv("LLM_PROVIDER_AUTH_DISABLE_SECONDS", "300"))
        # 5xx/server errors get a short cooldown to avoid hammering an unstable API.
        self.server_error_cooldown_seconds = int(os.getenv("LLM_PROVIDER_SERVER_ERROR_COOLDOWN_SECONDS", "60"))
        self.provider_cooldown_until = {provider.NAME: 0.0 for provider in self.providers}
        # Persistent auth-failed state: do not retry until operator enables.
        self.provider_auth_failed = {provider.NAME: False for provider in self.providers}
        self.provider_auth_failed_reason = {provider.NAME: None for provider in self.providers}
        
        # Do not raise if zero providers are available.
        # Cloud-only requirement: if keys are missing/invalid, the system must
        # return a clear error (no silent local fallback).
        if not self.providers:
            logger.error(
                "No working LLM providers available. Check cloud API keys (e.g., KIMI_API_KEY, GEMINI_API_KEY)."
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

    def get_priority_order(self) -> List[str]:
        """Get effective priority order restricted to available providers."""
        available = set(self.get_available_providers())
        return [name for name in self.config.priority if name in available]

    def set_priority_order(self, providers: List[str]) -> List[str]:
        """Update runtime provider priority and re-sort provider chain."""
        known = set(ProviderRegistry.get_all_registered().keys())
        cleaned: List[str] = []
        seen = set()

        for name in providers or []:
            provider_name = (name or "").strip().lower()
            if provider_name and provider_name in known and provider_name not in seen:
                cleaned.append(provider_name)
                seen.add(provider_name)

        for name in self.config.priority:
            provider_name = (name or "").strip().lower()
            if provider_name in known and provider_name not in seen:
                cleaned.append(provider_name)
                seen.add(provider_name)

        if cleaned:
            self.config.priority = cleaned
            self.providers = self._sort_providers_by_priority(self.providers)
            
            # Save to database
            try:
                from api._state import db
                db.set_system_config('llm_priority', cleaned)
                logger.info(f"Saved new LLM priority to database: {cleaned}")
            except Exception as e:
                logger.warning(f"Could not save LLM priority to database: {e}")

        return self.get_priority_order()
    
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
        details = {}
        for p in self.providers:
            stats = self.runtime_stats.get(p.NAME, {})
            attempts = stats.get("attempts", 0)
            successes = stats.get("successes", 0)
            latencies = stats.get("latencies", [])
            
            success_rate = (successes / attempts) if attempts > 0 else 0.0
            p95_latency_ms = None
            if latencies:
                sorted_lats = sorted(latencies)
                idx = int(len(sorted_lats) * 0.95)
                if len(sorted_lats) >= 2:
                    p95_latency_ms = sorted_lats[idx]
                else:
                    p95_latency_ms = sorted_lats[0]
                    
            details[p.NAME] = {
                "model": p.model,
                "base_url": p.base_url,
                "cooldown_until": int(self.provider_cooldown_until.get(p.NAME, 0)),
                "cooldown_remaining_seconds": max(0, int(self.provider_cooldown_until.get(p.NAME, 0) - time.time())),
                "auth_failed": bool(self.provider_auth_failed.get(p.NAME, False)),
                "auth_failed_reason": self.provider_auth_failed_reason.get(p.NAME),
                "success_rate": success_rate,
                "p95_latency_ms": p95_latency_ms,
                **stats,
            }
            
        return {
            "provider_count": len(self.providers),
            "providers": [p.NAME for p in self.providers],
            "priority_order": self.config.priority,
            "details": details
        }

    def update_provider_state(self, provider_name: str, state: str, reason: str, cooldown_seconds: Optional[int] = None):
        """Thread-safe update of provider state."""
        if provider_name not in self.provider_states:
            return
        
        self.provider_states[provider_name]["status"] = state
        self.provider_states[provider_name]["reason"] = reason
        
        if state == "auth_failed":
            self.provider_auth_failed[provider_name] = True
            self.provider_auth_failed_reason[provider_name] = reason
            self.provider_states[provider_name]["auth_failed_at"] = time.time()
        elif state == "cooldown" and cooldown_seconds:
            self.provider_cooldown_until[provider_name] = time.time() + cooldown_seconds
            self.provider_states[provider_name]["cooldown_until"] = time.time() + cooldown_seconds
        elif state == "operational":
            self.provider_auth_failed[provider_name] = False
            self.provider_auth_failed_reason[provider_name] = None
            self.provider_cooldown_until[provider_name] = 0
            self.provider_states[provider_name]["cooldown_until"] = 0
            self.provider_states[provider_name]["auth_failed_at"] = 0

    def reset_all_provider_states(self):
        """Resets the status of all providers to operational."""
        reset_providers = []
        for key in self.provider_states:
            name = key if isinstance(key, str) else getattr(key, "NAME", str(key))
            self.update_provider_state(name, "operational", "Manually reset by operator")
            reset_providers.append(str(name))
        logger.info(f"Operator manually reset state for all providers: {', '.join(reset_providers)}")
        return {"reset_providers": reset_providers}

    def enable_provider(self, provider_name: str) -> Dict[str, Any]:
        """Clear auth_failed so the provider can be retried."""
        if provider_name not in self.provider_auth_failed:
            return {"status": "error", "error": "unknown_provider"}
        self.provider_auth_failed[provider_name] = False
        self.provider_auth_failed_reason[provider_name] = None
        self.runtime_stats[provider_name]["last_error"] = None
        return {"status": "success", "provider": provider_name, "enabled": True}

    def _extract_http_status(self, error_message: str) -> Optional[int]:
        msg = (error_message or "").lower()
        for code in (401, 403, 408, 429, 500, 501, 502, 503, 504):
            if f"api error {code}" in msg or f"http {code}" in msg:
                return code
        return None

    def _classify_error(self, error_message: str) -> str:
        """Classify provider errors so cooldown behavior matches severity.

        Required behavior:
        - 401/403: disable provider immediately (no long cooldown)
        - 429/quota: long cooldown
        - 5xx: short cooldown
        """
        msg = (error_message or "").lower()
        code = self._extract_http_status(msg)
        if code in (401, 403):
            return "auth"
        if code == 429 or "rate limit" in msg or "too many requests" in msg:
            return "rate_limit"
        if any(x in msg for x in ("insufficient_quota", "quota", "exhausted", "credits")):
            return "quota"
        if code and 500 <= code < 600:
            return "server"
        return "other"
    
    async def analyze(self, alert: Dict[str, Any], preferred_engine: Optional[str] = None) -> Dict[str, Any]:
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
        
        providers_order = self.providers
        if preferred_engine:
            preferred = [p for p in self.providers if p.NAME == preferred_engine]
            if preferred:
                providers_order = preferred + [p for p in self.providers if p.NAME != preferred_engine]

        for provider in providers_order:
            async with self.state_lock:
                in_cooldown = self.provider_cooldown_until.get(provider.NAME, 0) > time.time()
                auth_failed = self.provider_auth_failed.get(provider.NAME, False)

            if in_cooldown:
                remaining = max(0, int(self.provider_cooldown_until.get(provider.NAME, 0) - time.time()))
                last_error = f"{provider.NAME} in cooldown ({remaining}s remaining)"
                provider_errors.append({"provider": provider.NAME, "error": last_error})
                logger.info(last_error)
                continue

            if auth_failed:
                last_error = f"{provider.NAME} auth_failed (disabled)"
                provider_errors.append({"provider": provider.NAME, "error": last_error})
                logger.info(last_error)
                continue

            providers_tried.append(provider.NAME)
            async with self.state_lock:
                self.runtime_stats[provider.NAME]["attempts"] += 1
            
            try:
                result = await provider.analyze(alert)
                
                if result.get("status") == "success":
                    async with self.state_lock:
                        self.runtime_stats[provider.NAME]["successes"] += 1
                        latency = result.get("latency_ms")
                        self.runtime_stats[provider.NAME]["last_latency_ms"] = latency
                        if latency is not None:
                            self.runtime_stats[provider.NAME]["latencies"].append(latency)
                            if len(self.runtime_stats[provider.NAME]["latencies"]) > 100:
                                self.runtime_stats[provider.NAME]["latencies"] = self.runtime_stats[provider.NAME]["latencies"][-100:]
                        self.runtime_stats[provider.NAME]["last_error"] = None
                        self.runtime_stats[provider.NAME]["last_success_at"] = int(time.time())
                    result["providers_tried"] = providers_tried
                    result["failed_engines"] = [entry["provider"] for entry in provider_errors]
                    return result
                
                # Provider returned error, try next
                last_error = result.get("error", "Unknown error")
                provider_errors.append({"provider": provider.NAME, "error": last_error})
                kind = self._classify_error(last_error)
                if kind == "auth":
                    friendly = f"{provider.NAME} API key invalid or expired - check {provider.ENV_KEY} env var"
                    async with self.state_lock:
                        self.runtime_stats[provider.NAME]["failures"] += 1
                        self.runtime_stats[provider.NAME]["last_latency_ms"] = result.get("latency_ms")
                        self.runtime_stats[provider.NAME]["last_error"] = friendly
                        self.update_provider_state(provider.NAME, "auth_failed", friendly)
                elif kind in ("rate_limit", "quota"):
                    async with self.state_lock:
                        self.runtime_stats[provider.NAME]["failures"] += 1
                        self.runtime_stats[provider.NAME]["last_latency_ms"] = result.get("latency_ms")
                        self.runtime_stats[provider.NAME]["last_error"] = last_error
                        self.update_provider_state(provider.NAME, "cooldown", last_error, self.rate_limit_cooldown_seconds)
                elif kind == "server":
                    async with self.state_lock:
                        self.runtime_stats[provider.NAME]["failures"] += 1
                        self.runtime_stats[provider.NAME]["last_latency_ms"] = result.get("latency_ms")
                        self.runtime_stats[provider.NAME]["last_error"] = last_error
                        self.provider_cooldown_until[provider.NAME] = time.time() + self.server_error_cooldown_seconds
                    logger.warning(
                        f"{provider.NAME} short cooldown {self.server_error_cooldown_seconds}s due to server error: {last_error}"
                    )
                else:
                    async with self.state_lock:
                        self.runtime_stats[provider.NAME]["failures"] += 1
                        self.runtime_stats[provider.NAME]["last_latency_ms"] = result.get("latency_ms")
                        self.runtime_stats[provider.NAME]["last_error"] = last_error
                logger.warning(f"{provider.NAME} failed: {last_error}")
                
            except Exception as e:
                last_error = str(e)
                provider_errors.append({"provider": provider.NAME, "error": last_error})
                kind = self._classify_error(last_error)
                if kind == "auth":
                    friendly = f"{provider.NAME} API key invalid or expired - check {provider.ENV_KEY} env var"
                    async with self.state_lock:
                        self.runtime_stats[provider.NAME]["failures"] += 1
                        self.runtime_stats[provider.NAME]["last_error"] = friendly
                        self.update_provider_state(provider.NAME, "auth_failed", friendly)
                elif kind in ("rate_limit", "quota"):
                    async with self.state_lock:
                        self.runtime_stats[provider.NAME]["failures"] += 1
                        self.runtime_stats[provider.NAME]["last_error"] = last_error
                        self.update_provider_state(provider.NAME, "cooldown", last_error, self.rate_limit_cooldown_seconds)
                elif kind == "server":
                    async with self.state_lock:
                        self.runtime_stats[provider.NAME]["failures"] += 1
                        self.runtime_stats[provider.NAME]["last_error"] = last_error
                        self.provider_cooldown_until[provider.NAME] = time.time() + self.server_error_cooldown_seconds
                    logger.warning(
                        f"{provider.NAME} short cooldown {self.server_error_cooldown_seconds}s due to server error: {last_error}"
                    )
                else:
                    async with self.state_lock:
                        self.runtime_stats[provider.NAME]["failures"] += 1
                        self.runtime_stats[provider.NAME]["last_latency_ms"] = None
                        self.runtime_stats[provider.NAME]["last_error"] = last_error
                logger.warning(f"{provider.NAME} exception: {e}")
        
        # All providers failed
        latency_ms = int((time.perf_counter() - start) * 1000)
        return {
            "status": "error",
            "error": f"All providers failed. Last: {last_error}",
            "provider": providers_tried[-1] if providers_tried else "none",
            "providers_tried": providers_tried,
            "failed_engines": [entry["provider"] for entry in provider_errors],
            "provider_errors": provider_errors,
            "latency_ms": latency_ms
        }


    async def validate_providers_on_startup(self):
        """
        Perform a cheap, non-blocking probe of all configured providers at startup.
        This helps identify invalid keys or auth issues immediately without waiting
        for the first real analysis request.
        """
        logger.info("Performing startup validation of all configured LLM providers...")
        tasks = []
        configured_providers = self.get_available_providers()

        for provider_name in configured_providers:
            provider = next((p for p in self.providers if p.NAME == provider_name), None)
            if provider and hasattr(provider, "probe"):
                tasks.append(asyncio.create_task(self._probe_and_update_status(provider)))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        valid_count = 0
        for i, provider_name in enumerate(configured_providers):
            result = results[i]
            if isinstance(result, Exception):
                logger.error(f"Startup probe for '{provider_name}' failed with exception: {result}")
            elif result and result.get("status") == "success":
                valid_count += 1
                logger.info(f"  - ✅ {provider_name}: OK")
            else:
                logger.warning(f"  - ❌ {provider_name}: FAILED. Reason: {result.get('error', 'Unknown')}. Marking as auth_failed.")

        logger.info(f"Startup validation complete: {valid_count} / {len(configured_providers)} providers are operational.")

    async def _probe_and_update_status(self, provider):
        """Helper to run probe and update provider state on failure."""
        provider_name = provider.NAME
        try:
            # Use a lightweight probe, not a full analysis
            result = await asyncio.wait_for(provider.probe(), timeout=10.0)
            if result.get("status") != "success":
                # This is where we mark the provider as failed on startup
                self.update_provider_state(
                    provider_name,
                    state="auth_failed",
                    reason=f"Startup probe failed: {result.get('error', 'Probe returned non-success status')}",
                    cooldown_seconds=None # No cooldown for auth failures
                )
            return result
        except Exception as e:
            self.update_provider_state(
                provider_name,
                state="auth_failed",
                reason=f"Startup probe exception: {str(e)}",
                cooldown_seconds=None
            )
            return {"status": "error", "error": str(e)}


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
