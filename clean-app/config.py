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
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    
    # LLM Settings
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4-turbo-preview")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "mixtral-8x7b-32768")
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
    
    # Application
    APP_HOST: str = os.getenv("APP_HOST", "0.0.0.0")
    APP_PORT: int = int(os.getenv("APP_PORT", "8000"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    @classmethod
    def validate(cls) -> bool:
        """Validate configuration"""
        if not cls.OPENAI_API_KEY and not cls.GROQ_API_KEY:
            raise ValueError("At least one LLM API key must be configured")
        return True

# Validate on import
Config.validate()
