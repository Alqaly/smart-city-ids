"""
Configuration Management for Smart City IDS
Loads settings from environment variables
"""
import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

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
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4-turbo-preview")
    ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    KIMI_MODEL: str = os.getenv("KIMI_MODEL", "moonshot-v1-8k")
    
    # LLM Fallback Priority (comma-separated list of engines to try in order)
    LLM_PRIORITY: str = os.getenv("LLM_PRIORITY", "kimi,xai,anthropic,openai,gemini")
    
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
    
    # Safety Controls
    AUTOMATION_MODE: str = os.getenv("AUTOMATION_MODE", "live")  # "live" | "dry-run" | "approval-required"
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
            raise ValueError("At least one LLM API key must be configured (XAI_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY, or KIMI_API_KEY)")
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
