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
    KIMI_MODEL: str = os.getenv("KIMI_MODEL", "moonshot-v1-128k")
    
    # LLM Fallback Priority (comma-separated list of engines to try in order)
    LLM_PRIORITY: str = os.getenv("LLM_PRIORITY", "xai,anthropic,openai,gemini,kimi")
    
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
    def get_available_engines(cls) -> list:
        """Return list of available LLM engines based on configured API keys"""
        engines = []
        if cls.XAI_API_KEY:
            engines.append("xai")
        if cls.ANTHROPIC_API_KEY:
            engines.append("anthropic")
        if cls.OPENAI_API_KEY:
            engines.append("openai")
        if cls.GEMINI_API_KEY:
            engines.append("gemini")
        if cls.KIMI_API_KEY:
            engines.append("kimi")
        return engines
    
    @classmethod
    def get_engine_priority(cls) -> list:
        """Return ordered list of engines to try based on LLM_PRIORITY and available keys"""
        priority = [e.strip() for e in cls.LLM_PRIORITY.split(",")]
        available = cls.get_available_engines()
        # Return only engines that are both in priority list and have keys
        return [e for e in priority if e in available]

# Validate on import
Config.validate()
