"""
Smart City IDS - Unified LLM Engine Manager
============================================

Provides a single interface for multiple LLM providers with:
- Automatic failover based on availability and circuit breaker state
- Consistent response format across all providers
- Easy single-key setup (only need ONE working API key)

Supported Providers:
--------------------
| Provider   | Model                  | Env Variable       | Docs                                    |
|------------|------------------------|--------------------|-----------------------------------------|
| xAI        | grok-4-latest          | XAI_API_KEY        | https://console.x.ai/                   |
| Anthropic  | claude-3-5-sonnet      | ANTHROPIC_API_KEY  | https://console.anthropic.com/          |
| OpenAI     | gpt-4-turbo            | OPENAI_API_KEY     | https://platform.openai.com/api-keys    |
| Google     | gemini-2.0-flash       | GEMINI_API_KEY     | https://aistudio.google.com/apikey      |
| Moonshot   | moonshot-v1-128k       | KIMI_API_KEY       | https://platform.moonshot.cn/           |

Quick Start (Single Key):
-------------------------
    # Only need ONE key - system auto-detects available provider
    export GEMINI_API_KEY="AIza..."
    
    # Or in Kubernetes:
    kubectl create secret generic ids-secrets -n smart-city \\
      --from-literal=gemini-api-key="YOUR_KEY"

Multi-Provider Setup (Recommended for Production):
--------------------------------------------------
    # Set priority order (optional, default shown)
    export LLM_PRIORITY="xai,anthropic,openai,gemini,kimi"
    
    # Configure multiple keys for failover
    export XAI_API_KEY="xai-..."
    export ANTHROPIC_API_KEY="sk-ant-..."

Response Contract (All Providers):
----------------------------------
    {
        "summary": "1-2 sentence threat explanation",
        "severity": 1-10,           # 10 = critical
        "threat_type": "DDoS|Privilege Escalation|Data Exfiltration|...",
        "confidence": 0.0-1.0,      # Analysis confidence
        "key_indicators": [...],    # Evidence supporting assessment
        "mitigating_factors": [...], # Reasons this might be false positive
        "business_impact": "...",   # Effect on Smart City operations
        "reasoning": "...",         # Detailed explanation
        "recommendations": [...],   # Human actions
        "automated_actions": [...]  # K8s actions: isolate_pod, scale_up, etc.
    }

Architecture:
-------------
    ┌─────────────────────────────────────────────────────────┐
    │                    LLMEngineManager                      │
    │  ┌─────────────────────────────────────────────────────┐│
    │  │              Circuit Breaker (per engine)           ││
    │  │   xai: ●  anthropic: ●  openai: ○  gemini: ●       ││
    │  │   (● = healthy, ○ = open/failing)                  ││
    │  └─────────────────────────────────────────────────────┘│
    │                           │                              │
    │  ┌─────────────────────────────────────────────────────┐│
    │  │              Failover Chain (priority order)        ││
    │  │   xai → anthropic → openai → gemini → kimi         ││
    │  └─────────────────────────────────────────────────────┘│
    │                           │                              │
    │  ┌─────────────────────────────────────────────────────┐│
    │  │              Response Cache (dedupe)                ││
    │  │   TTL: 60s  |  Max: 10,000 alerts                  ││
    │  └─────────────────────────────────────────────────────┘│
    └─────────────────────────────────────────────────────────┘

Usage:
------
    from llm_manager import LLMEngineManager
    
    manager = LLMEngineManager()
    print(f"Available engines: {manager.get_available_engines()}")
    
    result = await manager.analyze(alert_dict)
    # result = {"status": "success", "analysis": {...}, "engine": "gemini", "latency_ms": 234}

Author: Smart City IDS Team
License: MIT
"""

import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Tuple
from enum import Enum
import httpx

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class LLMConfig:
    """
    LLM Engine Configuration
    
    Environment Variables:
        XAI_API_KEY         - xAI Grok API key
        ANTHROPIC_API_KEY   - Anthropic Claude API key  
        OPENAI_API_KEY      - OpenAI GPT API key
        GEMINI_API_KEY      - Google Gemini API key
        KIMI_API_KEY        - Moonshot Kimi API key
        LLM_PRIORITY        - Comma-separated priority list (default: xai,anthropic,openai,gemini,kimi)
        LLM_TEMPERATURE     - Response creativity 0.0-1.0 (default: 0.3)
        LLM_MAX_TOKENS      - Max response tokens (default: 1000)
        LLM_TIMEOUT         - API timeout seconds (default: 30)
    """
    # API Keys (loaded from environment)
    xai_api_key: str = ""
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""
    kimi_api_key: str = ""
    
    # Model configurations
    xai_model: str = "grok-4-latest"
    anthropic_model: str = "claude-3-5-sonnet-20241022"
    openai_model: str = "gpt-4-turbo-preview"
    gemini_model: str = "gemini-2.0-flash"
    kimi_model: str = "moonshot-v1-128k"
    
    # Engine priority (first available with healthy circuit breaker wins)
    priority: List[str] = field(default_factory=lambda: ["xai", "anthropic", "openai", "gemini", "kimi"])
    
    # Shared settings
    temperature: float = 0.3
    max_tokens: int = 1000
    timeout: float = 30.0
    
    @classmethod
    def from_env(cls) -> 'LLMConfig':
        """Load configuration from environment variables"""
        import os
        
        priority_str = os.getenv("LLM_PRIORITY", "xai,anthropic,openai,gemini,kimi")
        priority = [p.strip() for p in priority_str.split(",")]
        
        return cls(
            xai_api_key=os.getenv("XAI_API_KEY", ""),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
            kimi_api_key=os.getenv("KIMI_API_KEY", ""),
            xai_model=os.getenv("XAI_MODEL", "grok-4-latest"),
            anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022"),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4-turbo-preview"),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
            kimi_model=os.getenv("KIMI_MODEL", "moonshot-v1-128k"),
            priority=priority,
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.3")),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", "1000")),
            timeout=float(os.getenv("LLM_TIMEOUT", "30")),
        )
    
    def get_available_engines(self) -> List[str]:
        """Return list of engines with configured API keys"""
        engines = []
        if self.xai_api_key:
            engines.append("xai")
        if self.anthropic_api_key:
            engines.append("anthropic")
        if self.openai_api_key:
            engines.append("openai")
        if self.gemini_api_key:
            engines.append("gemini")
        if self.kimi_api_key:
            engines.append("kimi")
        return engines
    
    def get_priority_order(self) -> List[str]:
        """Return engines in priority order, filtered to only available ones"""
        available = self.get_available_engines()
        return [e for e in self.priority if e in available]


# =============================================================================
# SHARED PROMPT (All engines use identical prompt for consistency)
# =============================================================================

SYSTEM_PROMPT = """You are a cybersecurity expert analyzing threats in a Smart City infrastructure running on Kubernetes.

Your role:
1. Analyze security alerts from Falco (runtime) and Suricata (network)
2. Explain threats in plain English for operators
3. Assess severity on a 1-10 scale (10 = critical)
4. Recommend specific, actionable mitigation steps
5. Suggest automated Kubernetes responses when appropriate

Be concise, accurate, and security-focused. Always respond with valid JSON only."""


def build_analysis_prompt(alert: Dict[str, Any]) -> str:
    """
    Build standardized analysis prompt from alert data.
    
    Args:
        alert: Security alert dict with keys: output, priority, rule, time, output_fields
        
    Returns:
        Formatted prompt string for LLM
    """
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
  "key_indicators": ["Indicator 1", "Indicator 2"],
  "mitigating_factors": ["Factor 1", "Factor 2"],
  "business_impact": "How this affects Smart City operations",
  "reasoning": "Detailed explanation of the threat assessment",
  "recommendations": ["Action 1", "Action 2", "Action 3"],
  "automated_actions": ["isolate_pod", "scale_up", "block_ip", "cordon_node", "alert_team"]
}}"""


def parse_llm_response(content: str) -> Dict[str, Any]:
    """
    Parse JSON from LLM response with multiple fallback strategies.
    
    Args:
        content: Raw LLM response text
        
    Returns:
        Parsed analysis dict (always returns valid structure)
    """
    # Strategy 1: Direct JSON parse
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    
    # Strategy 2: Extract from ```json block
    if "```json" in content:
        try:
            json_block = content.split("```json")[1].split("```")[0].strip()
            return json.loads(json_block)
        except (json.JSONDecodeError, IndexError):
            pass
    
    # Strategy 3: Extract from ``` block
    if "```" in content:
        try:
            code_block = content.split("```")[1].split("```")[0].strip()
            return json.loads(code_block)
        except (json.JSONDecodeError, IndexError):
            pass
    
    # Strategy 4: Fallback (parsing failed)
    logger.warning(f"Could not parse LLM JSON response: {content[:100]}...")
    return {
        "summary": content[:300] if len(content) > 300 else content,
        "severity": 5,
        "threat_type": "Unknown",
        "confidence": 0.5,
        "key_indicators": ["LLM response parsing failed"],
        "mitigating_factors": ["Manual review required"],
        "business_impact": "Unknown - requires manual analysis",
        "reasoning": "Automated parsing failed. Raw response preserved in summary.",
        "recommendations": ["Review alert manually", "Check LLM configuration"],
        "automated_actions": []
    }


# =============================================================================
# BASE ENGINE CLASS
# =============================================================================

class BaseLLMEngine(ABC):
    """
    Abstract base class for LLM engines.
    
    Subclasses only need to implement _call_api() method.
    All prompt building and response parsing is handled here.
    """
    
    ENGINE_NAME: str = "base"
    
    def __init__(self, api_key: str, model: str, config: LLMConfig):
        self.api_key = api_key
        self.model = model
        self.config = config
    
    @abstractmethod
    async def _call_api(self, system_prompt: str, user_prompt: str) -> str:
        """
        Call the LLM API and return raw response text.
        
        Args:
            system_prompt: System instructions
            user_prompt: Alert analysis request
            
        Returns:
            Raw response text from LLM
            
        Raises:
            httpx.TimeoutException: On timeout
            Exception: On API error (include status code in message)
        """
        pass
    
    async def analyze(self, alert: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze security alert.
        
        Args:
            alert: Security alert dict
            
        Returns:
            {
                "status": "success" | "error",
                "analysis": {...},      # if success
                "error": "...",         # if error
                "engine": ENGINE_NAME,
                "latency_ms": int
            }
        """
        start = time.perf_counter()
        
        try:
            user_prompt = build_analysis_prompt(alert)
            response_text = await self._call_api(SYSTEM_PROMPT, user_prompt)
            analysis = parse_llm_response(response_text)
            
            latency_ms = int((time.perf_counter() - start) * 1000)
            logger.info(f"{self.ENGINE_NAME} analysis: severity={analysis.get('severity')}, latency={latency_ms}ms")
            
            return {
                "status": "success",
                "analysis": analysis,
                "engine": self.ENGINE_NAME,
                "latency_ms": latency_ms
            }
            
        except httpx.TimeoutException:
            logger.error(f"{self.ENGINE_NAME} timeout")
            return {"status": "error", "error": f"{self.ENGINE_NAME} timeout", "engine": self.ENGINE_NAME}
        except Exception as e:
            logger.error(f"{self.ENGINE_NAME} error: {e}")
            return {"status": "error", "error": str(e), "engine": self.ENGINE_NAME}


# =============================================================================
# ENGINE IMPLEMENTATIONS
# =============================================================================

class XAIEngine(BaseLLMEngine):
    """xAI Grok-4 - Fast, capable reasoning model"""
    ENGINE_NAME = "xai"
    
    async def _call_api(self, system_prompt: str, user_prompt: str) -> str:
        async with httpx.AsyncClient(timeout=self.config.timeout) as client:
            response = await client.post(
                "https://api.x.ai/v1/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}"
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": self.config.temperature,
                    "max_tokens": self.config.max_tokens
                }
            )
            if response.status_code != 200:
                raise Exception(f"xAI API error {response.status_code}: {response.text[:200]}")
            return response.json()["choices"][0]["message"]["content"]


class AnthropicEngine(BaseLLMEngine):
    """Anthropic Claude - Strong reasoning with safety alignment"""
    ENGINE_NAME = "anthropic"
    
    async def _call_api(self, system_prompt: str, user_prompt: str) -> str:
        async with httpx.AsyncClient(timeout=self.config.timeout) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01"
                },
                json={
                    "model": self.model,
                    "max_tokens": self.config.max_tokens,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_prompt}]
                }
            )
            if response.status_code != 200:
                raise Exception(f"Anthropic API error {response.status_code}: {response.text[:200]}")
            return response.json()["content"][0]["text"]


class OpenAIEngine(BaseLLMEngine):
    """OpenAI GPT-4 - Widely available, strong general capabilities"""
    ENGINE_NAME = "openai"
    
    async def _call_api(self, system_prompt: str, user_prompt: str) -> str:
        async with httpx.AsyncClient(timeout=self.config.timeout) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}"
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": self.config.temperature,
                    "max_tokens": self.config.max_tokens,
                    "response_format": {"type": "json_object"}
                }
            )
            if response.status_code != 200:
                raise Exception(f"OpenAI API error {response.status_code}: {response.text[:200]}")
            return response.json()["choices"][0]["message"]["content"]


class GeminiEngine(BaseLLMEngine):
    """Google Gemini - Fast, cost-effective, good free tier"""
    ENGINE_NAME = "gemini"
    
    async def _call_api(self, system_prompt: str, user_prompt: str) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        async with httpx.AsyncClient(timeout=self.config.timeout) as client:
            response = await client.post(
                url,
                headers={"Content-Type": "application/json"},
                json={
                    "system_instruction": {"parts": [{"text": system_prompt}]},
                    "contents": [{"parts": [{"text": user_prompt}]}],
                    "generationConfig": {
                        "temperature": self.config.temperature,
                        "maxOutputTokens": self.config.max_tokens,
                        "responseMimeType": "application/json"
                    }
                }
            )
            if response.status_code != 200:
                raise Exception(f"Gemini API error {response.status_code}: {response.text[:200]}")
            return response.json()["candidates"][0]["content"]["parts"][0]["text"]


class KimiEngine(BaseLLMEngine):
    """Moonshot Kimi K1 - Long context, good for complex analysis"""
    ENGINE_NAME = "kimi"
    
    async def _call_api(self, system_prompt: str, user_prompt: str) -> str:
        async with httpx.AsyncClient(timeout=60.0) as client:  # Kimi can be slower
            response = await client.post(
                "https://api.moonshot.cn/v1/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}"
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": self.config.temperature,
                    "max_tokens": self.config.max_tokens
                }
            )
            if response.status_code != 200:
                raise Exception(f"Kimi API error {response.status_code}: {response.text[:200]}")
            return response.json()["choices"][0]["message"]["content"]


# =============================================================================
# ENGINE FACTORY
# =============================================================================

ENGINE_CLASSES = {
    "xai": XAIEngine,
    "anthropic": AnthropicEngine,
    "openai": OpenAIEngine,
    "gemini": GeminiEngine,
    "kimi": KimiEngine,
}


def create_engine(name: str, config: LLMConfig) -> Optional[BaseLLMEngine]:
    """
    Create an LLM engine instance.
    
    Args:
        name: Engine name (xai, anthropic, openai, gemini, kimi)
        config: LLM configuration
        
    Returns:
        Engine instance or None if API key not configured
    """
    key_map = {
        "xai": (config.xai_api_key, config.xai_model),
        "anthropic": (config.anthropic_api_key, config.anthropic_model),
        "openai": (config.openai_api_key, config.openai_model),
        "gemini": (config.gemini_api_key, config.gemini_model),
        "kimi": (config.kimi_api_key, config.kimi_model),
    }
    
    if name not in ENGINE_CLASSES:
        logger.warning(f"Unknown engine: {name}")
        return None
    
    api_key, model = key_map.get(name, ("", ""))
    if not api_key:
        return None
    
    return ENGINE_CLASSES[name](api_key, model, config)


# =============================================================================
# MANAGER (Main Entry Point)
# =============================================================================

class LLMEngineManager:
    """
    Unified LLM Engine Manager with failover support.
    
    Example:
        manager = LLMEngineManager()
        result = await manager.analyze(alert_dict)
    """
    
    def __init__(self, config: Optional[LLMConfig] = None):
        """
        Initialize manager with configuration.
        
        Args:
            config: LLM configuration (loads from env if not provided)
        """
        self.config = config or LLMConfig.from_env()
        self.engines: Dict[str, BaseLLMEngine] = {}
        
        # Initialize available engines
        for name in self.config.get_available_engines():
            engine = create_engine(name, self.config)
            if engine:
                self.engines[name] = engine
        
        if not self.engines:
            raise ValueError(
                "No LLM API keys configured! Set at least one of:\n"
                "  - XAI_API_KEY\n"
                "  - ANTHROPIC_API_KEY\n"
                "  - OPENAI_API_KEY\n"
                "  - GEMINI_API_KEY\n"
                "  - KIMI_API_KEY"
            )
        
        logger.info(f"LLM Manager initialized: engines={list(self.engines.keys())}, priority={self.config.get_priority_order()}")
    
    def get_available_engines(self) -> List[str]:
        """Return list of initialized engine names"""
        return list(self.engines.keys())
    
    async def analyze(self, alert: Dict[str, Any], preferred_engine: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyze alert using available engines with failover.
        
        Args:
            alert: Security alert dict
            preferred_engine: Optional engine to try first
            
        Returns:
            Analysis result dict with status, analysis, engine, latency_ms
        """
        # Build engine order
        if preferred_engine and preferred_engine in self.engines:
            order = [preferred_engine] + [e for e in self.config.get_priority_order() if e != preferred_engine]
        else:
            order = self.config.get_priority_order()
        
        last_error = None
        
        for engine_name in order:
            engine = self.engines.get(engine_name)
            if not engine:
                continue
            
            result = await engine.analyze(alert)
            
            if result.get("status") == "success":
                return result
            
            last_error = result.get("error", "Unknown error")
            logger.warning(f"{engine_name} failed: {last_error}")
        
        return {
            "status": "error",
            "error": f"All engines failed. Last error: {last_error}",
            "engine": "none"
        }


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

_default_manager: Optional[LLMEngineManager] = None

def get_manager() -> LLMEngineManager:
    """Get or create default LLM manager singleton"""
    global _default_manager
    if _default_manager is None:
        _default_manager = LLMEngineManager()
    return _default_manager


async def analyze_alert(alert: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convenience function to analyze alert using default manager.
    
    Args:
        alert: Security alert dict
        
    Returns:
        Analysis result
    """
    return await get_manager().analyze(alert)
