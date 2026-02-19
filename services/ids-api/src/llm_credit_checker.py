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
    from llm_credit_checker import CreditChecker
    
    checker = CreditChecker()
    status = await checker.check_all_providers()
    # Returns: {"xai": {"credits": 100.50, "currency": "USD", "status": "ok"}, ...}
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Any, List
from datetime import datetime, timedelta
import httpx
import json

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
        }


class CreditChecker:
    """
    Checks and monitors LLM provider credits/balances.
    
    Features:
    - Real-time balance checking for all providers
    - Configurable credit thresholds (warning/critical)
    - Automatic fallback when credits are low
    - Caching to avoid excessive API calls
    """
    
    # Cache duration in seconds
    CACHE_TTL = 300  # 5 minutes
    
    # Provider-specific endpoints and configurations
    PROVIDER_CONFIG = {
        "xai": {
            "base_url": "https://api.x.ai/v1",
            "balance_endpoint": "/billing/balance",
            "headers": lambda key: {"Authorization": f"Bearer {key}"},
            "parser": "_parse_xai_response",
        },
        "openai": {
            "base_url": "https://api.openai.com/v1",
            "balance_endpoint": "/dashboard/billing/credit_grants",
            "headers": lambda key: {"Authorization": f"Bearer {key}"},
            "parser": "_parse_openai_response",
        },
        "anthropic": {
            "base_url": "https://api.anthropic.com/v1",
            "balance_endpoint": "/account/billing",
            "headers": lambda key: {
                "Authorization": f"Bearer {key}",
                "Anthropic-Version": "2023-06-01"
            },
            "parser": "_parse_anthropic_response",
        },
        "gemini": {
            "base_url": "https://generativelanguage.googleapis.com/v1beta",
            "balance_endpoint": "/billingInfo",
            "headers": lambda key: {},  # Key is in query param
            "parser": "_parse_gemini_response",
        },
        "kimi": {
            "base_url": "https://api.moonshot.cn/v1",
            "balance_endpoint": "/users/me/balance",
            "headers": lambda key: {"Authorization": f"Bearer {key}"},
            "parser": "_parse_kimi_response",
        },
    }
    
    def __init__(self):
        self._cache: Dict[str, CreditInfo] = {}
        self._cache_timestamp: Optional[datetime] = None
        self._lock = asyncio.Lock()
        
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
            if self._cache_timestamp and (datetime.now() - self._cache_timestamp).total_seconds() < self._cache_ttl:
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
        """Internal method to check a specific provider"""
        config = self.PROVIDER_CONFIG.get(provider)
        if not config:
            return CreditInfo(
                provider=provider,
                status="error",
                error_message=f"Unknown provider: {provider}",
                last_checked=datetime.now()
            )
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                headers = config["headers"](api_key)
                url = f"{config['base_url']}{config['balance_endpoint']}"
                
                # Special handling for Gemini (key in query param)
                if provider == "gemini":
                    url = f"{url}?key={api_key}"
                
                logger.debug(f"Checking credits for {provider}: {url}")
                
                response = await client.get(url, headers=headers)
                
                if response.status_code == 200:
                    data = response.json()
                    parser = getattr(self, config["parser"])
                    credit_info = parser(data)
                    credit_info.provider = provider
                    credit_info.last_checked = datetime.now()
                    credit_info.raw_response = data
                    
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
                    
                elif response.status_code == 401:
                    return CreditInfo(
                        provider=provider,
                        status="error",
                        error_message="Invalid API key",
                        last_checked=datetime.now()
                    )
                elif response.status_code == 403:
                    return CreditInfo(
                        provider=provider,
                        status="error",
                        error_message="API key lacks billing permissions",
                        last_checked=datetime.now()
                    )
                else:
                    return CreditInfo(
                        provider=provider,
                        status="error",
                        error_message=f"HTTP {response.status_code}: {response.text[:200]}",
                        last_checked=datetime.now()
                    )
                    
        except httpx.TimeoutException:
            return CreditInfo(
                provider=provider,
                status="error",
                error_message="Request timeout",
                last_checked=datetime.now()
            )
        except Exception as e:
            logger.error(f"Error checking {provider} credits: {e}")
            return CreditInfo(
                provider=provider,
                status="error",
                error_message=str(e),
                last_checked=datetime.now()
            )
    
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
        # OpenAI format: {"total_available": 100.50, "total_used": 50.00, "total_granted": 150.00}
        grants = data.get("grants", {})
        if grants:
            return CreditInfo(
                provider="openai",
                credits=grants.get("total_available"),
                currency="USD",
                total_used=grants.get("total_used"),
                total_granted=grants.get("total_granted"),
            )
        # Alternative format
        return CreditInfo(
            provider="openai",
            credits=data.get("total_available") or data.get("balance"),
            currency="USD",
            total_used=data.get("total_used"),
            total_granted=data.get("total_granted"),
        )
    
    def _parse_anthropic_response(self, data: Dict) -> CreditInfo:
        """Parse Anthropic billing response"""
        # Anthropic may not expose direct credit balance
        # Return estimated based on usage limits
        return CreditInfo(
            provider="anthropic",
            credits=data.get("current_balance") or data.get("credits_remaining"),
            currency=data.get("currency", "USD"),
            total_used=data.get("total_spend"),
        )
    
    def _parse_gemini_response(self, data: Dict) -> CreditInfo:
        """Parse Google Gemini billing response"""
        # Gemini uses quota/free tier model
        billing_info = data.get("billingInfo", {})
        return CreditInfo(
            provider="gemini",
            credits=billing_info.get("creditBalance"),
            currency="USD",
            total_used=billing_info.get("totalSpend"),
            expires_at=datetime.fromisoformat(billing_info["expiresAt"].replace('Z', '+00:00')) if billing_info.get("expiresAt") else None,
        )
    
    def _parse_kimi_response(self, data: Dict) -> CreditInfo:
        """Parse Moonshot Kimi billing response"""
        # Kimi format: {"balance": 100.50, "currency": "CNY"}
        return CreditInfo(
            provider="kimi",
            credits=data.get("balance"),
            currency=data.get("currency", "CNY"),
            total_used=data.get("total_usage"),
        )
    
    def has_sufficient_credits(self, provider: str, min_credits: float = 0.5) -> bool:
        """
        Check if a provider has sufficient credits for an API call.
        
        Args:
            provider: Provider name
            min_credits: Minimum credits required (default 0.5 for one call)
            
        Returns:
            True if credits are sufficient, False otherwise
        """
        if provider not in self._cache:
            return True  # Allow if not cached (will be checked on actual call)
        
        info = self._cache[provider]
        if info.credits is None:
            return True  # Allow if unknown
        
        return info.credits >= min_credits and info.status not in ["exhausted", "critical"]
    
    def get_health_summary(self) -> Dict[str, Any]:
        """Get a health summary for all providers"""
        if not self._cache:
            return {"status": "unknown", "providers": {}}
        
        total = len(self._cache)
        ok = sum(1 for p in self._cache.values() if p.status == "ok")
        warning = sum(1 for p in self._cache.values() if p.status == "warning")
        critical = sum(1 for p in self._cache.values() if p.status in ["critical", "exhausted"])
        errors = sum(1 for p in self._cache.values() if p.status == "error")
        
        # Overall status
        if critical > 0:
            overall = "critical"
        elif warning > 0:
            overall = "warning"
        elif errors == total:
            overall = "error"
        else:
            overall = "ok"
        
        return {
            "status": overall,
            "total_providers": total,
            "healthy": ok,
            "warning": warning,
            "critical": critical,
            "errors": errors,
            "last_updated": self._cache_timestamp.isoformat() if self._cache_timestamp else None,
            "providers": {name: info.to_dict() for name, info in self._cache.items()}
        }


# Singleton instance
credit_checker = CreditChecker()


# Convenience functions for external use
async def check_all_credits(force_refresh: bool = False) -> Dict[str, CreditInfo]:
    """Check credits for all providers"""
    return await credit_checker.check_all_providers(force_refresh)


async def check_provider_credits(provider: str) -> CreditInfo:
    """Check credits for a specific provider"""
    return await credit_checker.check_provider(provider)


def get_credit_health() -> Dict[str, Any]:
    """Get credit health summary"""
    return credit_checker.get_health_summary()


def has_sufficient_credits(provider: str, min_credits: float = 0.5) -> bool:
    """Check if provider has sufficient credits"""
    return credit_checker.has_sufficient_credits(provider, min_credits)


if __name__ == "__main__":
    # Test the credit checker
    logging.basicConfig(level=logging.INFO)
    
    async def main():
        checker = CreditChecker()
        results = await checker.check_all_providers()
        
        print("\n" + "="*60)
        print("LLM CREDIT CHECK RESULTS")
        print("="*60)
        
        for provider, info in results.items():
            print(f"\n{provider.upper()}:")
            print(f"  Status: {info.status}")
            if info.credits is not None:
                print(f"  Credits: ${info.credits:.2f} {info.currency}")
            if info.total_used is not None:
                print(f"  Total Used: ${info.total_used:.2f}")
            if info.error_message:
                print(f"  Error: {info.error_message}")
        
        print("\n" + "="*60)
        print("HEALTH SUMMARY")
        print("="*60)
        summary = checker.get_health_summary()
        print(f"Overall: {summary['status']}")
        print(f"Healthy: {summary['healthy']}/{summary['total_providers']}")
        print(f"Warning: {summary['warning']}")
        print(f"Critical: {summary['critical']}")
        print(f"Errors: {summary['errors']}")
    
    asyncio.run(main())
