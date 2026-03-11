"""
Configuration Management for Smart City IDS
Loads settings from environment variables
"""
import logging
import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

def _normalize_automation_mode(mode: str) -> str:
    """Normalize legacy mode names to SOAR mode vocabulary."""
    normalized = (mode or "").strip().lower()
    mode_map = {
        "live": "autonomous",
        "autopilot": "autonomous",
        "active": "assisted",
        "approval-required": "assisted",
        "dry-run": "manual",
    }
    return mode_map.get(normalized, normalized or "assisted")

class Config:
    """Application configuration"""
    
    # API Keys - Multi-LLM Support for Scalability
    XAI_API_KEY: str = os.getenv("XAI_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    KIMI_API_KEY: str = os.getenv("KIMI_API_KEY", "")
    
    # LLM Model Settings
    XAI_MODEL: str = os.getenv("XAI_MODEL", "grok-4-latest")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")
    ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    KIMI_MODEL: str = os.getenv("KIMI_MODEL", "moonshot-v1-128k")
    
    # LLM provider failover chain (cloud providers only)
    LLM_PRIORITY: str = os.getenv(
        "LLM_PRIORITY",
        os.getenv("LLM_PROVIDER_CHAIN", "kimi,xai,anthropic,openai"),
    )
    
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.3"))
    LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "1000"))
    
    # Kubernetes
    K8S_NAMESPACE: str = os.getenv("K8S_NAMESPACE", "smart-city")
    KUBECONFIG: Optional[str] = os.getenv("KUBECONFIG", "/etc/rancher/k3s/k3s.yaml")
    
    # Monitoring
    FALCO_ENABLED: bool = os.getenv("FALCO_ENABLED", "true").lower() == "true"
    SURICATA_ENABLED: bool = os.getenv("SURICATA_ENABLED", "true").lower() == "true"
    PROMETHEUS_ENABLED: bool = os.getenv("PROMETHEUS_ENABLED", "true").lower() == "true"
    
    # Thresholds
    CRITICAL_SEVERITY_THRESHOLD: int = int(os.getenv("CRITICAL_SEVERITY_THRESHOLD", "8"))
    HIGH_SEVERITY_THRESHOLD: int = int(os.getenv("HIGH_SEVERITY_THRESHOLD", "6"))

    # LLM provider orchestration (cloud-only; no local fallback analyzer)
    LLM_PROVIDER_CHAIN: str = os.getenv("LLM_PROVIDER_CHAIN", "kimi,xai,anthropic,openai")
    MAX_RETRY_ATTEMPTS: int = int(os.getenv("MAX_RETRY_ATTEMPTS", "3"))
    BACKOFF_STRATEGY: str = os.getenv("BACKOFF_STRATEGY", "exponential")
    BACKOFF_BASE_SECONDS: float = float(os.getenv("BACKOFF_BASE_SECONDS", "1.0"))

    # Analyst chat abuse controls (per-user/session token bucket)
    ANALYST_CHAT_RATE_LIMIT_PER_MINUTE: int = int(os.getenv("ANALYST_CHAT_RATE_LIMIT_PER_MINUTE", "30"))
    ANALYST_CHAT_RATE_LIMIT_BURST: int = int(os.getenv("ANALYST_CHAT_RATE_LIMIT_BURST", "10"))

    # Kubernetes action path control
    K8S_USE_THREATRESPONSE_CRD: bool = os.getenv("K8S_USE_THREATRESPONSE_CRD", "true").lower() == "true"
    
    # SOAR-style automation controls
    # Modes: autonomous | assisted | manual | emergency
    AUTOMATION_MODE: str = _normalize_automation_mode(os.getenv("AUTOMATION_MODE", "assisted"))
    AUTONOMOUS_MIN_CONFIDENCE: float = float(os.getenv("AUTONOMOUS_MIN_CONFIDENCE", "0.90"))
    ASSISTED_MIN_CONFIDENCE: float = float(os.getenv("ASSISTED_MIN_CONFIDENCE", "0.70"))
    EMERGENCY_MIN_CONFIDENCE: float = float(os.getenv("EMERGENCY_MIN_CONFIDENCE", "0.85"))
    EMERGENCY_SEVERITY_THRESHOLD: int = int(os.getenv("EMERGENCY_SEVERITY_THRESHOLD", "10"))
    PROTECTED_SERVICES: list = os.getenv("PROTECTED_SERVICES", "healthcare-api,ids-api,postgres").split(",")
    ALERT_CACHE_TTL_SECONDS: int = int(os.getenv("ALERT_CACHE_TTL_SECONDS", "60"))
    ALERT_CACHE_MAX_SIZE: int = int(os.getenv("ALERT_CACHE_MAX_SIZE", "100"))
    
    # Security / Auth
    # Generate a random secret at startup if none is provided.
    # Production deployments MUST set SECRET_KEY or JWT_SECRET_KEY in the environment.
    SECRET_KEY: str = os.getenv(
        "SECRET_KEY",
        os.getenv("JWT_SECRET_KEY", ""),
    ) or __import__("secrets").token_urlsafe(32)

    # Internal ingest (Falco/Suricata forwarders → IDS API)
    # This must be set in-cluster; otherwise /api/alerts/internal is disabled.
    IDS_INTERNAL_ALERT_TOKEN: str = os.getenv(
        "IDS_INTERNAL_ALERT_TOKEN",
        os.getenv("INTERNAL_ALERT_TOKEN", ""),
    )
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://postgres:idspassword@postgres:5432/smartcity_ids")
    
    # Application
    APP_HOST: str = os.getenv("APP_HOST", "0.0.0.0")
    APP_PORT: int = int(os.getenv("APP_PORT", "8000"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    @classmethod
    def validate(cls) -> bool:
        """Validate configuration"""
        available_keys = [
            cls.XAI_API_KEY,
            cls.OPENAI_API_KEY,
            cls.ANTHROPIC_API_KEY,
            cls.GEMINI_API_KEY,
            cls.KIMI_API_KEY
        ]
        if not any(available_keys):
            logger.warning(
                "No cloud LLM API keys configured. "
                "Starting in degraded mode: auth/UI/API remain available, "
                "LLM analysis will fail until a provider key is configured."
            )
            return False
        return True
    
    @classmethod
    def is_valid_api_key(cls, key: str, provider: str) -> bool:
        """
        Check if an API key appears valid (format check, not API call).
        This helps identify placeholder or malformed keys early.
        """
        if not key or key == "placeholder" or len(key) < 10:
            return False
        
        # Provider-specific format checks
        if provider == "xai":
            # xAI keys typically start with 'xai-'
            return key.startswith("xai-") and len(key) > 20
        elif provider == "openai":
            # OpenAI keys start with 'sk-' (old) or 'sk-proj-' (new)
            return (key.startswith("sk-") or key.startswith("sk-proj-")) and len(key) > 30
        elif provider == "anthropic":
            # Anthropic keys start with 'sk-ant-'
            return key.startswith("sk-ant-") and len(key) > 30
        elif provider == "gemini":
            # Google API keys start with 'AIza'
            return key.startswith("AIza") and len(key) > 30
        elif provider == "kimi":
            # Kimi/Moonshot keys start with 'sk-'
            return key.startswith("sk-") and len(key) > 30
        
        return True  # Unknown provider, assume valid
    
    @classmethod
    def get_valid_engines(cls) -> dict:
        """
        Return dict of engines with validation status.
        Helps identify which keys are likely valid vs placeholders.
        """
        engines = {}
        
        if cls.XAI_API_KEY:
            valid = cls.is_valid_api_key(cls.XAI_API_KEY, "xai")
            engines["xai"] = {"configured": True, "valid_format": valid}
        
        if cls.OPENAI_API_KEY:
            valid = cls.is_valid_api_key(cls.OPENAI_API_KEY, "openai")
            engines["openai"] = {"configured": True, "valid_format": valid}
        
        if cls.ANTHROPIC_API_KEY:
            valid = cls.is_valid_api_key(cls.ANTHROPIC_API_KEY, "anthropic")
            engines["anthropic"] = {"configured": True, "valid_format": valid}
        
        if cls.GEMINI_API_KEY:
            valid = cls.is_valid_api_key(cls.GEMINI_API_KEY, "gemini")
            engines["gemini"] = {"configured": True, "valid_format": valid}
        
        if cls.KIMI_API_KEY:
            valid = cls.is_valid_api_key(cls.KIMI_API_KEY, "kimi")
            engines["kimi"] = {"configured": True, "valid_format": valid}
        
        return engines
    
    @classmethod
    def get_available_engines(cls) -> list:
        """Return list of available LLM engines based on configured AND valid API keys"""
        engines = []
        if cls.XAI_API_KEY and cls.is_valid_api_key(cls.XAI_API_KEY, "xai"):
            engines.append("xai")
        if cls.ANTHROPIC_API_KEY and cls.is_valid_api_key(cls.ANTHROPIC_API_KEY, "anthropic"):
            engines.append("anthropic")
        if cls.OPENAI_API_KEY and cls.is_valid_api_key(cls.OPENAI_API_KEY, "openai"):
            engines.append("openai")
        if cls.GEMINI_API_KEY and cls.is_valid_api_key(cls.GEMINI_API_KEY, "gemini"):
            engines.append("gemini")
        if cls.KIMI_API_KEY and cls.is_valid_api_key(cls.KIMI_API_KEY, "kimi"):
            engines.append("kimi")
        return engines
    
    @classmethod
    def get_engine_priority(cls) -> list:
        """Return ordered list of engines to try based on LLM_PRIORITY and available keys"""
        priority = [e.strip() for e in cls.LLM_PRIORITY.split(",")]
        available = cls.get_available_engines()
        # Return only engines that are both in priority list and have valid keys
        return [e for e in priority if e in available]

# Validate on import
Config.validate()
