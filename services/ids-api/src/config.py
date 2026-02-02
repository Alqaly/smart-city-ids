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
    
    # API Keys
    XAI_API_KEY: str = os.getenv("XAI_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    
    # LLM Settings
    XAI_MODEL: str = os.getenv("XAI_MODEL", "grok-4-latest")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4-turbo-preview")
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
        if not cls.XAI_API_KEY and not cls.OPENAI_API_KEY:
            raise ValueError("At least one LLM API key must be configured (XAI_API_KEY or OPENAI_API_KEY)")
        return True

# Validate on import
Config.validate()
