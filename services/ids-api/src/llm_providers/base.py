"""
Base Provider - Abstract interface for LLM providers

All providers must implement this interface.
The system auto-discovers providers via the registry.
"""

import os
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


@dataclass
class ProviderConfig:
    """
    Generic provider configuration.
    
    Each provider reads its own config from environment variables:
        <PROVIDER_NAME>_API_KEY     - Required API key
        <PROVIDER_NAME>_MODEL       - Model to use (provider sets default)
        <PROVIDER_NAME>_BASE_URL    - API base URL (provider sets default)
    
    Shared settings (apply to all providers):
        LLM_TEMPERATURE   - 0.0-1.0 (default: 0.3)
        LLM_MAX_TOKENS    - Max response tokens (default: 1000)
        LLM_TIMEOUT       - API timeout seconds (default: 30)
    """
    temperature: float = field(default_factory=lambda: float(os.getenv("LLM_TEMPERATURE", "0.3")))
    max_tokens: int = field(default_factory=lambda: int(os.getenv("LLM_MAX_TOKENS", "1000")))
    timeout: float = field(default_factory=lambda: float(os.getenv("LLM_TIMEOUT", "30")))
    priority: List[str] = field(default_factory=lambda: [
        p.strip().lower()
        for p in os.getenv("LLM_PRIORITY", "xai,anthropic,openai,gemini,kimi,custom").split(",")
        if p.strip()
    ])


class BaseProvider(ABC):
    """
    Abstract base class for LLM providers.
    
    To create a new provider:
    
        from llm_providers import BaseProvider, ProviderRegistry
        
        @ProviderRegistry.register("myprovider")
        class MyProvider(BaseProvider):
            NAME = "myprovider"
            ENV_KEY = "MYPROVIDER_API_KEY"
            DEFAULT_MODEL = "my-model-v1"
            DEFAULT_BASE_URL = "https://api.myprovider.com/v1"
            
            async def _call_api(self, system_prompt: str, user_prompt: str) -> str:
                # Implement API call
                ...
    
    The provider will automatically:
    - Be discovered if MYPROVIDER_API_KEY is set
    - Be available via get_available_providers()
    - Work with the unified LLM Manager
    """
    
    # Provider identity (subclasses MUST override)
    NAME: str = "base"
    ENV_KEY: str = "BASE_API_KEY"
    DEFAULT_MODEL: str = "default"
    DEFAULT_BASE_URL: str = "https://api.example.com"
    
    def __init__(self, config: Optional[ProviderConfig] = None):
        """
        Initialize provider with configuration.
        
        Args:
            config: Optional shared config. If None, loads from environment.
        """
        self.config = config or ProviderConfig()
        
        # Load provider-specific settings from environment
        self.api_key = os.getenv(self.ENV_KEY, "")
        self.model = os.getenv(f"{self.NAME.upper()}_MODEL", self.DEFAULT_MODEL)
        self.base_url = os.getenv(f"{self.NAME.upper()}_BASE_URL", self.DEFAULT_BASE_URL)
        
        if not self.api_key:
            raise ValueError(f"API key not set: {self.ENV_KEY}")
    
    @classmethod
    def is_available(cls) -> bool:
        """Check if this provider has a valid API key configured."""
        api_key = os.getenv(cls.ENV_KEY, "")
        return bool(api_key and len(api_key) > 10)
    
    @classmethod
    def get_info(cls) -> Dict[str, Any]:
        """Get provider info for status endpoints."""
        return {
            "name": cls.NAME,
            "available": cls.is_available(),
            "env_key": cls.ENV_KEY,
            "default_model": cls.DEFAULT_MODEL,
        }
    
    @abstractmethod
    async def _call_api(self, system_prompt: str, user_prompt: str) -> str:
        """
        Call the LLM API and return raw response text.
        
        Args:
            system_prompt: System instructions for the LLM
            user_prompt: User's request (the alert to analyze)
            
        Returns:
            Raw text response from the LLM
            
        Raises:
            Exception on API error (include status code in message)
        """
        pass
    
    async def analyze(self, alert: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze a security alert.
        
        This method handles:
        - Building the prompt from alert data
        - Calling the API via _call_api()
        - Parsing the JSON response
        - Error handling
        
        Args:
            alert: Security alert dict with keys: output, priority, rule, time, output_fields
            
        Returns:
            {
                "status": "success" | "error",
                "analysis": {...},      # if success
                "error": "...",         # if error
                "provider": NAME,
                "model": MODEL,
                "latency_ms": int
            }
        """
        import time
        import json
        
        start = time.perf_counter()
        
        try:
            # Build prompts
            system_prompt = self._get_system_prompt()
            user_prompt = self._build_user_prompt(alert)
            
            # Call API
            response_text = await self._call_api(system_prompt, user_prompt)
            
            # Parse response
            analysis = self._parse_response(response_text)
            
            latency_ms = int((time.perf_counter() - start) * 1000)
            logger.info(f"{self.NAME}: severity={analysis.get('severity')}, latency={latency_ms}ms")
            
            return {
                "status": "success",
                "analysis": analysis,
                "provider": self.NAME,
                "model": self.model,
                "latency_ms": latency_ms
            }
            
        except Exception as e:
            latency_ms = int((time.perf_counter() - start) * 1000)
            logger.error(f"{self.NAME} error: {e}")
            return {
                "status": "error",
                "error": str(e),
                "provider": self.NAME,
                "model": self.model,
                "latency_ms": latency_ms
            }
    
    def _get_system_prompt(self) -> str:
        """Get the system prompt for security analysis."""
        return """You are a cybersecurity expert analyzing threats in a Smart City infrastructure running on Kubernetes.

Your role:
1. Analyze security alerts from Falco (runtime) and Suricata (network)
2. Explain threats in plain English for operators
3. Assess severity on a 1-10 scale (10 = critical)
4. Recommend specific, actionable mitigation steps
5. Suggest automated Kubernetes responses when appropriate

Be concise, accurate, and security-focused. Always respond with valid JSON only."""

    def _build_user_prompt(self, alert: Dict[str, Any]) -> str:
        """Build analysis prompt from alert data."""
        fields = alert.get('output_fields', {})
        
        return f"""Analyze this security alert from Smart City infrastructure.

**Alert Output:** {alert.get('output', 'N/A')}
**Priority:** {alert.get('priority', 'N/A')}
**Rule:** {alert.get('rule', 'N/A')}
**Timestamp:** {alert.get('time', 'N/A')}
**Container:** {fields.get('container.name', 'Unknown')}
**Process:** {fields.get('proc.cmdline', 'Unknown')}
**Source IP:** {fields.get('fd.sip', fields.get('src.ip', 'N/A'))}

Provide analysis for human operator review. Respond with JSON ONLY:
{{
  "summary": "1-2 sentence explanation of what happened",
  "severity": <1-10 integer>,
  "threat_type": "DDoS|Privilege Escalation|Data Exfiltration|Malware|Policy Violation|Reconnaissance|Unknown",
  "confidence": <0.0-1.0 float>,
  "recommendations": ["Action 1", "Action 2", "Action 3"],
  "automated_actions": ["isolate_pod", "scale_up", "block_ip", "alert_team"]
}}"""

    def _parse_response(self, content: str) -> Dict[str, Any]:
        """Parse JSON from LLM response."""
        import json
        
        if not content:
            return self._fallback_response("No response content")
        
        # Try direct parse
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        
        # Try extracting from ```json block
        if "```json" in content:
            try:
                json_block = content.split("```json")[1].split("```")[0].strip()
                return json.loads(json_block)
            except (json.JSONDecodeError, IndexError):
                pass
        
        # Try extracting from ``` block
        if "```" in content:
            try:
                code_block = content.split("```")[1].split("```")[0].strip()
                return json.loads(code_block)
            except (json.JSONDecodeError, IndexError):
                pass
        
        return self._fallback_response(f"Could not parse response: {content[:100]}...")
    
    def _fallback_response(self, reason: str) -> Dict[str, Any]:
        """Generate fallback response when parsing fails."""
        return {
            "summary": f"Analysis incomplete: {reason}",
            "severity": 5,
            "threat_type": "Unknown",
            "confidence": 0.0,
            "recommendations": ["Manual review required"],
            "automated_actions": [],
            "parse_error": True
        }
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(model={self.model})>"
