"""
LLM Credit Checker — Smart City IDS
=====================================

Checks remaining credits/balance for all configured LLM providers.
Prevents API calls when credits are low or exhausted.
Provides real-time credit status for dashboard display.

Supported Providers:
- xAI (Grok)
- OpenAI
- Anthropic (Claude)
- Google (Gemini)
- Moonshot (Kimi)

Usage:
    from llm_credit_checker import CreditChecker, LLMHealthMonitor
    
    checker = CreditChecker()
    status = await checker.check_all_providers()
    # Returns: {"xai": {"credits": 100.50, "currency": "USD", "status": "ok"}, ...}
    
    # For health-aware routing decisions:
    health = LLMHealthMonitor()
    can_use = health.can_use_provider("xai")
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Any, List, Tuple
from datetime import datetime, timedelta
from enum import Enum
import httpx
import json
import os

# Import config to get API keys
try:
    from config import Config
except ImportError:
    # Fallback for standalone usage
    import os
    class Config:
        XAI_API_KEY = os.getenv("XAI_API_KEY", "")
        OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
        ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
        GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
        KIMI_API_KEY = os.getenv("KIMI_API_KEY", "")
        
        # Credit thresholds
        CREDIT_WARNING_THRESHOLD = float(os.getenv("CREDIT_WARNING_THRESHOLD", "10.0"))
        CREDIT_CRITICAL_THRESHOLD = float(os.getenv("CREDIT_CRITICAL_THRESHOLD", "2.0"))

logger = logging.getLogger(__name__)


class ProviderHealthStatus(Enum):
    """Health status for LLM providers"""
    HEALTHY = "healthy"           # Provider is fully operational
    DEGRADED = "degraded"         # Working but issues detected
    UNHEALTHY = "unhealthy"       # Not usable
    UNKNOWN = "unknown"           # Status not yet checked
    NOT_CONFIGURED = "not_configured"  # No API key


@dataclass
class CreditInfo:
    """Credit information for a single provider"""
    provider: str
    credits: Optional[float] = None
    currency: str = "USD"
    status: str = "unknown"  # ok, warning, critical, exhausted, error
    total_used: Optional[float] = None
    total_granted: Optional[float] = None
    expires_at: Optional[datetime] = None
    last_checked: Optional[datetime] = None
    error_message: Optional[str] = None
    raw_response: Optional[Dict] = field(default=None, repr=False)
    
    # New health monitoring fields
    api_reachable: bool = False
    rate_limit_remaining: Optional[int] = None
    rate_limit_reset: Optional[datetime] = None
    response_time_ms: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "credits": self.credits,
            "currency": self.currency,
            "status": self.status,
            "total_used": self.total_used,
            "total_granted": self.total_granted,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "last_checked": self.last_checked.isoformat() if self.last_checked else None,
            "error_message": self.error_message,
            "api_reachable": self.api_reachable,
            "rate_limit_remaining": self.rate_limit_remaining,
            "rate_limit_reset": self.rate_limit_reset.isoformat() if self.rate_limit_reset else None,
            "response_time_ms": self.response_time_ms,
        }
    
    @property
    def is_usable(self) -> bool:
        """Check if provider has credits and is reachable"""
        if not self.api_reachable:
            return False
        if self.status in ("exhausted", "error"):
            return False
        if self.credits is not None and self.credits <= 0:
            return False
        return True


@dataclass
class ProviderHealth:
    """Complete health status for a provider including credits and connectivity"""
    provider: str
    health_status: ProviderHealthStatus
    credit_info: Optional[CreditInfo] = None
    last_successful_call: Optional[datetime] = None
    consecutive_failures: int = 0
    average_response_time_ms: Optional[float] = None
    recommendation: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "health_status": self.health_status.value,
            "credit_info": self.credit_info.to_dict() if self.credit_info else None,
            "last_successful_call": self.last_successful_call.isoformat() if self.last_successful_call else None,
            "consecutive_failures": self.consecutive_failures,
            "average_response_time_ms": self.average_response_time_ms,
            "recommendation": self.recommendation,
        }


class CreditChecker:
    """
    Checks and monitors LLM provider credits/balances.
    
    Features:
    - Real-time balance checking for all providers
    - Configurable credit thresholds (warning/critical)
    - Automatic fallback when credits are low
    - Caching to avoid excessive API calls
    - Response time tracking
    """
    
    # Cache duration in seconds
    CACHE_TTL = 300  # 5 minutes

    # If a provider returns 401/invalid auth once, do not retry its balance check
    # for 5 minutes to prevent dashboard polling loops from hammering it.
    AUTH_FAIL_TTL = 300
    
    # Provider-specific endpoints and configurations
    PROVIDER_CONFIG = {
        "xai": {
            "base_url": "https://api.x.ai/v1",
            "balance_endpoint": "/billing/balance",
            "models_endpoint": "/models",  # For health check
            "headers": lambda key: {"Authorization": f"Bearer {key}"},
            "parser": "_parse_xai_response",
        },
        "openai": {
            "base_url": "https://api.openai.com/v1",
            "balance_endpoint": "/dashboard/billing/credit_grants",
            "models_endpoint": "/models",
            "headers": lambda key: {"Authorization": f"Bearer {key}"},
            "parser": "_parse_openai_response",
        },
        "anthropic": {
            "base_url": "https://api.anthropic.com/v1",
            "balance_endpoint": "/account/billing",
            "models_endpoint": "/models",
            "headers": lambda key: {
                "Authorization": f"Bearer {key}",
                "Anthropic-Version": "2023-06-01"
            },
            "parser": "_parse_anthropic_response",
        },
        "gemini": {
            "base_url": "https://generativelanguage.googleapis.com/v1beta",
            "balance_endpoint": "/billingInfo",
            "models_endpoint": "/models",
            "headers": lambda key: {},  # Key is in query param
            "parser": "_parse_gemini_response",
        },
        "kimi": {
            "base_url": "https://api.moonshot.ai/v1",
            "balance_endpoint": "/users/me/balance",
            "models_endpoint": "/models",
            "headers": lambda key: {"Authorization": f"Bearer {key}"},
            "parser": "_parse_kimi_response",
        },
    }
    
    def __init__(self):
        self._cache: Dict[str, CreditInfo] = {}
        self._cache_timestamp: Optional[datetime] = None
        self._lock = asyncio.Lock()
        self._auth_fail_until: Dict[str, float] = {}
        
        # Thresholds from config
        self.warning_threshold = getattr(Config, 'CREDIT_WARNING_THRESHOLD', 10.0)
        self.critical_threshold = getattr(Config, 'CREDIT_CRITICAL_THRESHOLD', 2.0)
        
        logger.info(f"CreditChecker initialized (warning: ${self.warning_threshold}, critical: ${self.critical_threshold})")
    
    async def check_all_providers(self, force_refresh: bool = False) -> Dict[str, CreditInfo]:
        """
        Check credits for all configured providers.
        
        Args:
            force_refresh: Ignore cache and fetch fresh data
            
        Returns:
            Dict mapping provider names to CreditInfo objects
        """
        async with self._lock:
            # Check cache
            if not force_refresh and self._cache and self._cache_timestamp:
                age = (datetime.now() - self._cache_timestamp).total_seconds()
                if age < self.CACHE_TTL:
                    logger.debug(f"Returning cached credit info (age: {age:.0f}s)")
                    return self._cache.copy()
            
            # Fetch fresh data for all providers
            tasks = []
            providers = []
            
            for provider in ["xai", "openai", "anthropic", "gemini", "kimi"]:
                api_key = self._get_api_key(provider)
                if api_key:
                    tasks.append(self._check_provider(provider, api_key))
                    providers.append(provider)
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Update cache
            self._cache = {}
            for provider, result in zip(providers, results):
                if isinstance(result, Exception):
                    self._cache[provider] = CreditInfo(
                        provider=provider,
                        status="error",
                        error_message=str(result),
                        last_checked=datetime.now()
                    )
                else:
                    self._cache[provider] = result
            
            self._cache_timestamp = datetime.now()
            return self._cache.copy()
    
    async def check_provider(self, provider: str, force_refresh: bool = False) -> CreditInfo:
        """Check credits for a specific provider"""
        if not force_refresh and self._cache and provider in self._cache:
            cached = self._cache[provider]
            if self._cache_timestamp and (datetime.now() - self._cache_timestamp).total_seconds() < self.CACHE_TTL:
                return cached
        api_key = self._get_api_key(provider)
        if not api_key:
            return CreditInfo(
                provider=provider,
                status="not_configured",
                error_message="No API key configured",
                last_checked=datetime.now()
            )
        
        return await self._check_provider(provider, api_key)
    
    async def _check_provider(self, provider: str, api_key: str) -> CreditInfo:
        """Internal method to check a specific provider with health validation"""
        config = self.PROVIDER_CONFIG.get(provider)
        if not config:
            return CreditInfo(
                provider=provider,
                status="error",
                error_message=f"Unknown provider: {provider}",
                last_checked=datetime.now()
            )
        
        # ── Auth-fail suppression ─────────────────────────────────────────
        until = self._auth_fail_until.get(provider, 0.0)
        if until and until > time.time():
            retry_in = max(0, int(until - time.time()))
            return CreditInfo(
                provider=provider,
                status="error",
                error_message=f"Auth previously failed — retrying in {retry_in}s",
                last_checked=datetime.now(),
            )

        # ── Key format validation (no network call) ───────────────────────
        try:
            if hasattr(Config, "is_valid_api_key") and not Config.is_valid_api_key(api_key, provider):
                self._auth_fail_until[provider] = time.time() + self.AUTH_FAIL_TTL
                msg = f"{provider} API key format invalid or expired - check {provider.upper()}_API_KEY env var"
                logger.error(msg)
                return CreditInfo(
                    provider=provider,
                    status="error",
                    error_message=msg,
                    last_checked=datetime.now(),
                )
        except Exception:
            pass

        start_time = time.time()
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                headers = config["headers"](api_key)
                url = f"{config['base_url']}{config['balance_endpoint']}"
                
                # Special handling for Gemini (key in query param)
                if provider == "gemini":
                    url = f"{url}?key={api_key}"
                
                logger.debug(f"Checking credits for {provider}: {url}")
                
                response = await client.get(url, headers=headers)
                response_time_ms = (time.time() - start_time) * 1000
                
                if response.status_code == 200:
                    data = response.json()
                    parser = getattr(self, config["parser"])
                    credit_info = parser(data)
                    credit_info.provider = provider
                    credit_info.last_checked = datetime.now()
                    credit_info.raw_response = data
                    credit_info.api_reachable = True
                    credit_info.response_time_ms = round(response_time_ms, 2)
                    
                    # Extract rate limit info if present
                    credit_info.rate_limit_remaining = self._extract_rate_limit_remaining(response)
                    credit_info.rate_limit_reset = self._extract_rate_limit_reset(response)
                    
                    # Determine status based on thresholds
                    if credit_info.credits is not None:
                        if credit_info.credits <= 0:
                            credit_info.status = "exhausted"
                        elif credit_info.credits < self.critical_threshold:
                            credit_info.status = "critical"
                        elif credit_info.credits < self.warning_threshold:
                            credit_info.status = "warning"
                        else:
                            credit_info.status = "ok"
                    
                    logger.info(f"{provider}: ${credit_info.credits} {credit_info.currency} ({credit_info.status})")
                    return credit_info

                elif response.status_code == 429:
                    # Rate limited. API is reachable but temporarily degraded.
                    info = CreditInfo(
                        provider=provider,
                        credits=None,
                        currency="USD",
                        status="warning",
                        error_message="Rate limited (HTTP 429) — retry later",
                        last_checked=datetime.now(),
                        api_reachable=True,
                        response_time_ms=round(response_time_ms, 2),
                    )
                    info.rate_limit_remaining = self._extract_rate_limit_remaining(response)
                    info.rate_limit_reset = self._extract_rate_limit_reset(response)
                    return info
                    
                elif response.status_code == 401:
                    self._auth_fail_until[provider] = time.time() + self.AUTH_FAIL_TTL
                    logger.error(f"{provider} API key invalid or expired - check {provider.upper()}_API_KEY env var")
                    return CreditInfo(
                        provider=provider,
                        status="error",
                        error_message="Invalid API key",
                        last_checked=datetime.now(),
                        api_reachable=True,
                        response_time_ms=round(response_time_ms, 2),
                    )
                elif response.status_code == 403:
                    self._auth_fail_until[provider] = time.time() + self.AUTH_FAIL_TTL
                    return CreditInfo(
                        provider=provider,
                        status="error",
                        error_message="API key lacks billing permissions",
                        last_checked=datetime.now(),
                        api_reachable=True,
                        response_time_ms=round(response_time_ms, 2),
                    )
                elif response.status_code == 404:
                    # Billing endpoint not available - this is NORMAL for most providers
                    # Try models endpoint as health check and return 'ok' if reachable
                    health_info = await self._health_check_only(provider, api_key, config)
                    if health_info.api_reachable:
                        # API is reachable but billing info not available - this is normal
                        health_info.status = "ok"
                        health_info.error_message = None  # Clear error since this is normal
                    return health_info
                else:
                    return CreditInfo(
                        provider=provider,
                        status="error",
                        error_message=f"HTTP {response.status_code}: {response.text[:200]}",
                        last_checked=datetime.now(),
                        api_reachable=True,
                        response_time_ms=round(response_time_ms, 2),
                    )
                    
        except httpx.TimeoutException:
            return CreditInfo(
                provider=provider,
                status="warning",
                error_message="Request timeout",
                last_checked=datetime.now(),
                api_reachable=False,
            )
        except Exception as e:
            logger.error(f"Error checking {provider} credits: {e}")
            return CreditInfo(
                provider=provider,
                status="error",
                error_message=str(e),
                last_checked=datetime.now(),
                api_reachable=False,
            )
    
    async def _health_check_only(self, provider: str, api_key: str, config: Dict) -> CreditInfo:
        """Perform a basic health check when billing endpoint is not available"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                headers = config["headers"](api_key)
                url = f"{config['base_url']}{config.get('models_endpoint', '/models')}"
                
                if provider == "gemini":
                    url = f"{url}?key={api_key}"
                
                start_time = time.time()
                response = await client.get(url, headers=headers)
                response_time_ms = (time.time() - start_time) * 1000
                
                if response.status_code == 200:
                    # API is reachable but billing info not available
                    return CreditInfo(
                        provider=provider,
                        credits=None,  # Unknown
                        currency="USD",
                        status="ok",
                        error_message="Billing API not available, but API is reachable",
                        last_checked=datetime.now(),
                        api_reachable=True,
                        response_time_ms=round(response_time_ms, 2),
                    )
                else:
                    return CreditInfo(
                        provider=provider,
                        status="error",
                        error_message=f"Health check failed: HTTP {response.status_code}",
                        last_checked=datetime.now(),
                        api_reachable=False,
                    )
        except Exception as e:
            return CreditInfo(
                provider=provider,
                status="error",
                error_message=f"Health check failed: {str(e)}",
                last_checked=datetime.now(),
                api_reachable=False,
            )
    
    def _extract_rate_limit_remaining(self, response: httpx.Response) -> Optional[int]:
        """Extract rate limit remaining from response headers"""
        # Prefer explicit request-based limit headers when present.
        header_candidates = [
            # OpenAI-style
            "x-ratelimit-remaining-requests",
            "x-ratelimit-remaining-request",
            "x-rate-limit-remaining-requests",
            # Generic
            "x-ratelimit-remaining",
            "x-rate-limit-remaining",
            "ratelimit-remaining",
            "rate-limit-remaining",
        ]
        for header in header_candidates:
            value = response.headers.get(header)
            if not value:
                continue
            try:
                return int(float(value))
            except ValueError:
                continue
        return None
    
    def _extract_rate_limit_reset(self, response: httpx.Response) -> Optional[datetime]:
        """Extract rate limit reset time from response headers"""
        header_candidates = [
            # OpenAI-style
            "x-ratelimit-reset-requests",
            "x-rate-limit-reset-requests",
            # Generic
            "x-ratelimit-reset",
            "x-rate-limit-reset",
            "ratelimit-reset",
            "rate-limit-reset",
        ]
        for header in header_candidates:
            value = response.headers.get(header)
            if not value:
                continue
            parsed = self._parse_rate_limit_reset_value(value)
            if parsed:
                return parsed
        return None

    def _parse_rate_limit_reset_value(self, value: str) -> Optional[datetime]:
        """Parse common rate-limit reset header formats.

        Providers return reset headers as:
        - unix epoch seconds: "1700000000"
        - ISO timestamps: "2026-02-21T12:34:56Z"
        - durations: "1s", "250ms" (meaning: now + duration)
        """
        raw = str(value).strip()
        if not raw:
            return None

        # Epoch seconds
        try:
            ts = int(raw)
            if ts > 10_000_000:  # avoid parsing small integers as epoch
                return datetime.fromtimestamp(ts)
        except (ValueError, OSError):
            pass

        # ISO
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            pass

        # Duration format (e.g. "1s", "250ms")
        try:
            unit = raw[-2:] if raw.endswith("ms") else raw[-1:]
            num = raw[:-2] if unit == "ms" else raw[:-1]
            seconds = None
            if unit == "ms":
                seconds = float(num) / 1000.0
            elif unit == "s":
                seconds = float(num)
            elif unit == "m":
                seconds = float(num) * 60.0
            if seconds is not None:
                return datetime.fromtimestamp(time.time() + max(0.0, seconds))
        except Exception:
            return None

        return None
    
    def _get_api_key(self, provider: str) -> Optional[str]:
        """Get API key for a provider from config"""
        key_map = {
            "xai": Config.XAI_API_KEY,
            "openai": Config.OPENAI_API_KEY,
            "anthropic": Config.ANTHROPIC_API_KEY,
            "gemini": Config.GEMINI_API_KEY,
            "kimi": Config.KIMI_API_KEY,
        }
        return key_map.get(provider)
    
    # Provider-specific response parsers
    
    def _parse_xai_response(self, data: Dict) -> CreditInfo:
        """Parse xAI billing response"""
        # xAI format: {"balance": 100.50, "currency": "USD"}
        return CreditInfo(
            provider="xai",
            credits=data.get("balance") or data.get("credits"),
            currency=data.get("currency", "USD"),
            total_used=data.get("total_used"),
            total_granted=data.get("total_granted"),
        )
    
    def _parse_openai_response(self, data: Dict) -> CreditInfo:
        """Parse OpenAI billing response"""
        # OpenAI format varies; try multiple known formats
        credits = None
        total_granted = None
        total_used = None
        
        # Format 1: {"total_available": 100.50, "total_used": 50.25}
        if "total_available" in data:
            credits = data.get("total_available")
            total_used = data.get("total_used")
            total_granted = data.get("total_granted")
        # Format 2: {"balance": 100.50}
        elif "balance" in data:
            credits = data.get("balance")
        # Format 3: {"data": [{"grant_amount": ..., "used_amount": ...}]}
        elif "data" in data and isinstance(data["data"], list):
            grants = data["data"]
            if grants:
                total_granted = sum(g.get("grant_amount", 0) for g in grants)
                total_used = sum(g.get("used_amount", 0) for g in grants)
                credits = total_granted - total_used
        
        return CreditInfo(
            provider="openai",
            credits=credits,
            currency="USD",
            total_used=total_used,
            total_granted=total_granted,
        )
    
    def _parse_anthropic_response(self, data: Dict) -> CreditInfo:
        """Parse Anthropic billing response"""
        # Anthropic may not expose detailed billing
        credits = data.get("balance") or data.get("credits") or data.get("available")
        return CreditInfo(
            provider="anthropic",
            credits=credits,
            currency=data.get("currency", "USD"),
        )
    
    def _parse_gemini_response(self, data: Dict) -> CreditInfo:
        """Parse Google Gemini billing response"""
        # Gemini billing info may be in different format
        credits = data.get("balance") or data.get("availableCredit")
        return CreditInfo(
            provider="gemini",
            credits=credits,
            currency="USD",
        )
    
    def _parse_kimi_response(self, data: Dict) -> CreditInfo:
        """Parse Moonshot Kimi billing response"""
        # Kimi format: {"balance": 100.50, "currency": "CNY"}
        return CreditInfo(
            provider="kimi",
            credits=data.get("balance"),
            currency=data.get("currency", "CNY"),
        )


class LLMHealthMonitor:
    """
    Monitors LLM provider health for intelligent routing decisions.
    
    Combines credit information with usage patterns to determine
    which providers are healthy and should be used.
    """
    
    def __init__(self, credit_checker: Optional[CreditChecker] = None):
        self.credit_checker = credit_checker or CreditChecker()
        self._health_history: Dict[str, List[ProviderHealth]] = {}
        self._max_history = 10
        self._call_stats: Dict[str, Dict] = {
            "xai": {"successes": 0, "failures": 0, "total_latency_ms": 0},
            "openai": {"successes": 0, "failures": 0, "total_latency_ms": 0},
            "anthropic": {"successes": 0, "failures": 0, "total_latency_ms": 0},
            "gemini": {"successes": 0, "failures": 0, "total_latency_ms": 0},
            "kimi": {"successes": 0, "failures": 0, "total_latency_ms": 0},
        }
    
    async def get_health_status(self, provider: Optional[str] = None) -> Dict[str, ProviderHealth]:
        """Get comprehensive health status for all or specific provider"""
        credit_info = await self.credit_checker.check_all_providers()
        
        result = {}
        providers = [provider] if provider else ["xai", "openai", "anthropic", "gemini", "kimi"]
        
        for p in providers:
            info = credit_info.get(p)
            if not info:
                # Check if API key exists
                api_key = self.credit_checker._get_api_key(p)
                if not api_key:
                    result[p] = ProviderHealth(
                        provider=p,
                        health_status=ProviderHealthStatus.NOT_CONFIGURED,
                        recommendation="Configure API key to use this provider"
                    )
                else:
                    result[p] = ProviderHealth(
                        provider=p,
                        health_status=ProviderHealthStatus.UNKNOWN,
                        recommendation="Health status unknown - check may have failed"
                    )
            else:
                health = self._assess_health(p, info)
                result[p] = health
                
                # Update history
                if p not in self._health_history:
                    self._health_history[p] = []
                self._health_history[p].append(health)
                if len(self._health_history[p]) > self._max_history:
                    self._health_history[p].pop(0)
        
        return result
    
    def _assess_health(self, provider: str, credit_info: CreditInfo) -> ProviderHealth:
        """Assess overall health based on credit info and usage stats"""
        stats = self._call_stats.get(provider, {"successes": 0, "failures": 0})
        total_calls = stats["successes"] + stats["failures"]
        failure_rate = stats["failures"] / total_calls if total_calls > 0 else 0
        
        # Determine health status
        if not credit_info.api_reachable:
            health_status = ProviderHealthStatus.UNHEALTHY
            recommendation = "API not reachable - check network or provider status"
        elif credit_info.status == "exhausted":
            health_status = ProviderHealthStatus.UNHEALTHY
            recommendation = "Credits exhausted - add funds or switch provider"
        elif credit_info.status == "error":
            # Differentiate auth/billing hard failures vs transient API issues.
            msg = (credit_info.error_message or "").lower()
            if "invalid api key" in msg or "billing permissions" in msg or "format invalid" in msg:
                health_status = ProviderHealthStatus.UNHEALTHY
                recommendation = f"Auth/billing error: {credit_info.error_message}"
            else:
                health_status = ProviderHealthStatus.DEGRADED
                recommendation = f"Transient API error: {credit_info.error_message}"
        elif credit_info.status == "critical":
            health_status = ProviderHealthStatus.DEGRADED
            recommendation = "Credits critically low - consider switching provider"
        elif failure_rate > 0.5:
            health_status = ProviderHealthStatus.DEGRADED
            recommendation = f"High failure rate ({failure_rate:.0%}) - consider fallback"
        elif credit_info.status == "warning":
            health_status = ProviderHealthStatus.DEGRADED
            recommendation = "Credits low - monitor usage closely"
        else:
            health_status = ProviderHealthStatus.HEALTHY
            if credit_info.credits is not None:
                recommendation = f"Healthy - ${credit_info.credits:.2f} credits available"
            else:
                recommendation = "Healthy - API reachable"
        
        return ProviderHealth(
            provider=provider,
            health_status=health_status,
            credit_info=credit_info,
            average_response_time_ms=credit_info.response_time_ms,
            recommendation=recommendation,
        )
    
    def can_use_provider(self, provider: str) -> Tuple[bool, str]:
        """Quick check if a provider can be used for new requests"""
        # Get cached credit info
        cached = self.credit_checker._cache.get(provider)
        if not cached:
            return False, "No health data available"
        
        if not cached.api_reachable:
            return False, cached.error_message or "API not reachable"
        
        if cached.status == "exhausted":
            return False, "Credits exhausted"
        
        if cached.status == "error":
            return False, cached.error_message or "Provider error"
        
        return True, "Provider healthy"
    
    def record_call(self, provider: str, success: bool, latency_ms: float):
        """Record a call result for health tracking"""
        if provider not in self._call_stats:
            self._call_stats[provider] = {"successes": 0, "failures": 0, "total_latency_ms": 0}
        
        stats = self._call_stats[provider]
        if success:
            stats["successes"] += 1
        else:
            stats["failures"] += 1
        stats["total_latency_ms"] += latency_ms
    
    async def choose_best_provider(self) -> Optional[str]:
        """Async: get the best available provider based on current health."""
        health_status = await self.get_health_status()
        
        # Filter healthy providers
        healthy = [
            (p, h) for p, h in health_status.items()
            if h.health_status == ProviderHealthStatus.HEALTHY
        ]
        
        if not healthy:
            # Try degraded providers
            healthy = [
                (p, h) for p, h in health_status.items()
                if h.health_status == ProviderHealthStatus.DEGRADED
            ]
        
        if not healthy:
            return None
        
        # Sort by credits (if available), then by response time
        def sort_key(item):
            h = item[1]
            credits = h.credit_info.credits if h.credit_info else 0
            latency = h.average_response_time_ms or 9999
            return (-(credits or 0), latency)
        
        healthy.sort(key=sort_key)
        return healthy[0][0]

    def get_best_provider_cached(self) -> Optional[str]:
        """Sync best-provider choice using cached CreditInfo only."""
        candidates: list[ProviderHealth] = []
        for p in ["xai", "openai", "anthropic", "gemini", "kimi"]:
            cached = self.credit_checker._cache.get(p)
            if not cached:
                continue
            h = self._assess_health(p, cached)
            if h.health_status in (ProviderHealthStatus.HEALTHY, ProviderHealthStatus.DEGRADED):
                candidates.append(h)

        if not candidates:
            return None

        def sort_key(h: ProviderHealth):
            credits = h.credit_info.credits if h.credit_info else 0
            latency = h.average_response_time_ms or 9999
            health_rank = 0 if h.health_status == ProviderHealthStatus.HEALTHY else 1
            return (health_rank, -(credits or 0), latency)

        candidates.sort(key=sort_key)
        return candidates[0].provider

    def get_best_provider(self) -> Optional[str]:
        """Backward-compatible sync helper.

        If called from within an event loop, falls back to cached credit data
        rather than calling asyncio.run().
        """
        try:
            asyncio.get_running_loop()
            return self.get_best_provider_cached()
        except RuntimeError:
            return asyncio.run(self.choose_best_provider())


# Singleton instances for global use
credit_checker = CreditChecker()
health_monitor = LLMHealthMonitor(credit_checker)


# Convenience functions
async def check_all_providers(force_refresh: bool = False) -> Dict[str, Dict]:
    """Check all providers and return simplified status dict"""
    results = await credit_checker.check_all_providers(force_refresh)
    return {p: info.to_dict() for p, info in results.items()}


async def get_provider_health(provider: Optional[str] = None) -> Dict[str, Dict]:
    """Get health status for providers"""
    results = await health_monitor.get_health_status(provider)
    return {p: h.to_dict() for p, h in results.items()}


def quick_provider_check(provider: str) -> Tuple[bool, str]:
    """Quick check if provider can be used (uses cached data)"""
    return health_monitor.can_use_provider(provider)


# Backward compatibility aliases
check_all_credits = check_all_providers


def has_sufficient_credits(provider: str, min_credits: float = 0.5) -> bool:
    """Check if a provider has sufficient credits (backward compatible)."""
    cached = credit_checker._cache.get(provider)
    if not cached:
        # Try to get from API key existence as fallback
        return bool(credit_checker._get_api_key(provider))
    
    if cached.status in ("exhausted", "error"):
        return False
    
    if cached.credits is not None:
        return cached.credits >= min_credits
    
    # If credits unknown but API reachable, assume sufficient
    return cached.api_reachable
