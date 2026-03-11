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
| Anthropic  | claude-sonnet-4        | ANTHROPIC_API_KEY  | https://console.anthropic.com/          |
| OpenAI     | gpt-4o                 | OPENAI_API_KEY     | https://platform.openai.com/api-keys    |
| Google     | gemini-2.5-flash       | GEMINI_API_KEY     | https://aistudio.google.com/apikey      |
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
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Tuple
from enum import Enum
import hashlib
import httpx
from enum import Enum

# Local imports for enhanced validation and retry
try:
    from llm_response_schema import validate_llm_response, create_fallback_response, response_metrics
    from llm_retry import retry_with_backoff, is_retryable_error, RateLimiter
    SCHEMA_VALIDATION_ENABLED = True
except ImportError:
    SCHEMA_VALIDATION_ENABLED = False

# Backward-compatible circuit breaker API used by legacy tests/importers.
class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Single-engine circuit breaker compatibility shim.

    New runtime code uses the multi-engine breaker in infrastructure middleware.
    This class preserves the legacy interface expected by older tests/modules.
    """

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = int(failure_threshold)
        self.recovery_timeout = int(recovery_timeout)
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.state = CircuitState.CLOSED

    def can_execute(self) -> bool:
        if self.state == CircuitState.OPEN:
            if (time.time() - self.last_failure_time) >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                return True
            return False
        return True

    def record_success(self):
        self.failure_count = 0
        self.state = CircuitState.CLOSED

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
    
logger = logging.getLogger(__name__)


# =============================================================================
# VERSION INFO
# =============================================================================

__version__ = "2.0.0"
__author__ = "Smart City IDS Team"


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
    anthropic_model: str = "claude-sonnet-4-20250514"
    openai_model: str = "gpt-4o"
    gemini_model: str = "gemini-2.5-flash"
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
            anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4o"),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
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

SYSTEM_PROMPT = """You are a senior cybersecurity analyst specializing in Smart City / ICS infrastructure security.
You work at a Security Operations Center (SOC) analyzing real-time alerts from an AI-driven Intrusion Detection System.

ENVIRONMENT:
- Smart City IoT platform on Kubernetes (K3s) with 5 IoT protocol emulators:
  • Traffic Camera (ONVIF Profile S / RTSP / ANPR) — controls traffic signals, ANPR license plate capture
  • Parking System (MQTT / CoAP / SenML magnetometer sensors) — manages 500+ parking spots
  • Healthcare API (HL7 FHIR R4 / IEEE 11073 medical devices) — patient vitals, medical records
  • Environmental Sensor (Modbus TCP / OPC UA — AQI monitoring stations) — air quality, emissions
  • Street Lighting (DALI-2 / TALQ v2.4 gateway control) — 10,000+ luminaires, smart dimming
- Monitoring: Falco (runtime syscall detection), Suricata (network IDS/IPS)
- MITRE ATT&CK for ICS framework applies to this environment
- Services are intentionally vulnerable for security research/demonstration

YOUR ANALYSIS APPROACH:
1. EVIDENCE: Identify the specific log lines, process names, file paths, and network indicators that prove this alert is real
2. REASONING: Walk through your analysis step-by-step — what happened, why it matters, what the attacker's goal likely is
3. CONFIDENCE: Rate your confidence (0.0-1.0) based on evidence quality — be honest when evidence is ambiguous
4. IMPACT: Assess real-world impact on Smart City operations (traffic safety, patient health, environmental monitoring)
5. ACTIONS: Recommend specific, executable Kubernetes remediation steps

SEVERITY GUIDELINES:
- 9-10: Life-safety impact (healthcare compromise, traffic signal manipulation, emergency system disruption)
- 7-8: Critical infrastructure disruption (full service outage, mass data exfiltration, cluster compromise)
- 5-6: Operational degradation (reconnaissance, policy violations, single-service impact)
- 3-4: Low-risk events (information gathering, benign anomalies, failed attack attempts)
- 1-2: Informational (normal operations triggering sensitive rules, expected maintenance)

AUTOMATED ACTIONS (only suggest when evidence strongly supports):
- isolate_pod: Apply deny-all NetworkPolicy — USE FOR severity >= 8 with clear malicious intent
- scale_up: Increase replicas to absorb load — USE FOR DDoS/availability threats severity >= 6
- block_ip: Block source IP via NetworkPolicy — USE when source IP is clearly malicious
- cordon_node: Prevent scheduling on compromised node — USE FOR container escape / node compromise
- restart_pod: Rolling restart — USE FOR configuration tampering or persistent malware
- alert_team: Notify SOC team — USE FOR any severity >= 7

CRITICAL RULES:
- NEVER assign severity 9-10 without strong evidence of life-safety or critical infrastructure impact
- ALWAYS provide at least 3 key indicators from the actual alert data
- ALWAYS note mitigating factors that could make this a false positive
- Respond with valid JSON ONLY — no markdown, no commentary outside the JSON"""


def build_analysis_prompt(alert: Dict[str, Any]) -> str:
    """
    Build standardized analysis prompt from alert data.
    Enhanced with evidence extraction requirements.
    
    Args:
        alert: Security alert dict with keys: output, priority, rule, time, output_fields
        
    Returns:
        Formatted prompt string for LLM
    """
    fields = alert.get('output_fields', {})
    
    # Extract all available evidence fields
    container = fields.get('container.name', 'Unknown')
    proc_cmdline = fields.get('proc.cmdline', 'Unknown')
    proc_name = fields.get('proc.name', 'N/A')
    user = fields.get('user.name', 'N/A')
    fd_name = fields.get('fd.name', 'N/A')
    src_ip = fields.get('fd.sip', fields.get('src.ip', 'N/A'))
    dst_ip = fields.get('fd.lip', fields.get('dst.ip', 'N/A'))
    dst_port = fields.get('fd.lport', fields.get('dst.port', 'N/A'))
    
    return f"""Analyze this security alert from Smart City infrastructure.

═══ ALERT DATA ═══
Rule:        {alert.get('rule', 'N/A')}
Priority:    {alert.get('priority', 'N/A')}
Timestamp:   {alert.get('time', 'N/A')}
Output:      {alert.get('output', 'N/A')}

═══ EVIDENCE FIELDS ═══
Container:   {container}
Process:     {proc_cmdline}
Process Name:{proc_name}
User:        {user}
File/FD:     {fd_name}
Source IP:    {src_ip}
Dest IP:     {dst_ip}
Dest Port:   {dst_port}

═══ REQUIRED RESPONSE FORMAT (JSON only) ═══
{{
  "summary": "Clear 1-2 sentence explanation of what happened and why it matters",
  "severity": <1-10 integer>,
  "threat_type": "<DDoS|Privilege Escalation|Data Exfiltration|Malware|Policy Violation|Reconnaissance|Credential Access|Lateral Movement|Command and Control|Container Escape|Unknown>",
  "confidence": <0.0-1.0 float — how confident you are based on evidence quality>,
  "key_indicators": ["Evidence item 1 from alert data", "Evidence item 2", "Evidence item 3"],
  "mitigating_factors": ["Reason this could be false positive 1", "Reason 2"],
  "business_impact": "Specific impact on Smart City operations (which service, what data, what safety implications)",
  "reasoning": "Step-by-step analysis: (1) What triggered this alert, (2) What the attacker likely intended, (3) How confident you are and why, (4) What the blast radius could be",
  "mitre_technique": "TXXXX — Technique Name (from MITRE ATT&CK for ICS where applicable)",
  "recommendations": ["Specific action 1 with target", "Action 2", "Action 3"],
  "automated_actions": ["isolate_pod|scale_up|block_ip|cordon_node|restart_pod|alert_team"]
}}"""


def parse_llm_response(content: str) -> Dict[str, Any]:
    """
    Parse JSON from LLM response with multiple fallback strategies.
    
    Args:
        content: Raw LLM response text
        
    Returns:
        Parsed analysis dict (always returns valid structure)
    """
    if content is None:
        return create_fallback_response("", "No content received") if SCHEMA_VALIDATION_ENABLED else {
            "summary": "No response content",
            "severity": 5,
            "threat_type": "Unknown"
        }
    
    # Strategy 1: Direct JSON parse
    try:
        parsed = json.loads(content)
        if SCHEMA_VALIDATION_ENABLED:
            validated = validate_llm_response(parsed)
            response_metrics.record_valid()
            return validated.model_dump()
        return parsed
    except json.JSONDecodeError:
        pass
    
    # Strategy 2: Extract from ```json block
    if "```json" in content:
        try:
            json_block = content.split("```json")[1].split("```")[0].strip()
            parsed = json.loads(json_block)
            if SCHEMA_VALIDATION_ENABLED:
                validated = validate_llm_response(parsed)
                response_metrics.record_valid()
                return validated.model_dump()
            return parsed
        except (json.JSONDecodeError, IndexError):
            pass
    
    # Strategy 3: Extract from ``` block
    if "```" in content:
        try:
            code_block = content.split("```")[1].split("```")[0].strip()
            parsed = json.loads(code_block)
            if SCHEMA_VALIDATION_ENABLED:
                validated = validate_llm_response(parsed)
                response_metrics.record_valid()
                return validated.model_dump()
            return parsed
        except (json.JSONDecodeError, IndexError):
            pass
    
    # Strategy 4: Fallback (parsing failed)
    logger.warning(f"Could not parse LLM JSON response: {content[:100]}...")
    
    if SCHEMA_VALIDATION_ENABLED:
        response_metrics.record_fallback()
        return create_fallback_response(content, "JSON parsing failed")
    
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
        
        # Provider cooldown: skip providers returning non-retryable errors (429/401/403/quota)
        self.cooldown_seconds = int(os.getenv("LLM_PROVIDER_COOLDOWN_SECONDS", "900"))
        self.provider_cooldown_until: Dict[str, float] = {}
        
        # Runtime stats for status reporting
        self.runtime_stats: Dict[str, Dict] = {}
        
        # Initialize available engines
        for name in self.config.get_available_engines():
            engine = create_engine(name, self.config)
            if engine:
                self.engines[name] = engine
                self.provider_cooldown_until[name] = 0.0
                self.runtime_stats[name] = {
                    "attempts": 0, "successes": 0, "failures": 0,
                    "last_latency_ms": None, "last_error": None,
                }
        
        if len(self.engines) == 0:
            logger.warning(
                "No LLM API keys configured. Set at least one of:\n"
                "  - XAI_API_KEY\n"
                "  - ANTHROPIC_API_KEY\n"
                "  - OPENAI_API_KEY\n"
                "  - GEMINI_API_KEY\n"
                "  - KIMI_API_KEY"
            )
        
        logger.info(f"LLM Manager initialized: engines={list(self.engines.keys())}, priority={self.config.get_priority_order()}, cooldown={self.cooldown_seconds}s")
    
    def get_available_engines(self) -> List[str]:
        """Return list of initialized engine names"""
        return list(self.engines.keys())

    def get_priority_order(self) -> List[str]:
        """Return current effective priority order limited to configured engines."""
        return self.config.get_priority_order()

    def set_priority_order(self, providers: List[str]) -> List[str]:
        """Update runtime provider priority order.

        Accepts a list of provider names, removes duplicates while preserving
        order, and keeps only known provider identifiers.
        """
        known = set(ENGINE_CLASSES.keys())
        cleaned: List[str] = []
        seen = set()

        for name in providers or []:
            provider_name = (name or "").strip().lower()
            if provider_name and provider_name in known and provider_name not in seen:
                cleaned.append(provider_name)
                seen.add(provider_name)

        # Keep existing providers that were omitted so failover remains complete.
        for name in self.config.priority:
            provider_name = (name or "").strip().lower()
            if provider_name in known and provider_name not in seen:
                cleaned.append(provider_name)
                seen.add(provider_name)

        if cleaned:
            self.config.priority = cleaned

        return self.get_priority_order()

    # ---- Provider cooldown (prevents retrying quota-exhausted / bad-auth providers) ----

    def _is_provider_in_cooldown(self, engine_name: str) -> bool:
        return self.provider_cooldown_until.get(engine_name, 0) > time.time()

    def _activate_provider_cooldown(self, engine_name: str, reason: str):
        until = time.time() + self.cooldown_seconds
        self.provider_cooldown_until[engine_name] = until
        logger.warning(
            f"{engine_name} entered cooldown for {self.cooldown_seconds}s — non-retryable error: {reason}"
        )

    @staticmethod
    def _should_cooldown_provider(error_message: str) -> bool:
        msg = (error_message or "").lower()
        cooldown_indicators = (
            "insufficient_quota", "quota",
            "resource has been exhausted", "used all available credits",
            "monthly spending limit", "exhausted",
            "invalid api key", "incorrect api key",
            "authentication", "unauthorized",
            "api error 401", "api error 403", "api error 429",
        )
        return any(indicator in msg for indicator in cooldown_indicators)

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
        failed_engines: List[str] = []
        
        for engine_name in order:
            engine = self.engines.get(engine_name)
            if not engine:
                continue

            # Skip providers in cooldown (quota exhausted / bad auth)
            if self._is_provider_in_cooldown(engine_name):
                remaining = max(0, int(self.provider_cooldown_until.get(engine_name, 0) - time.time()))
                logger.info(f"{engine_name} in cooldown ({remaining}s remaining), skipping")
                failed_engines.append(engine_name)
                last_error = f"{engine_name} in cooldown ({remaining}s remaining)"
                continue

            self.runtime_stats.setdefault(engine_name, {"attempts": 0, "successes": 0, "failures": 0, "last_latency_ms": None, "last_error": None})
            self.runtime_stats[engine_name]["attempts"] += 1
            
            result = await engine.analyze(alert)
            
            if result.get("status") == "success":
                self.runtime_stats[engine_name]["successes"] += 1
                self.runtime_stats[engine_name]["last_latency_ms"] = result.get("latency_ms")
                self.runtime_stats[engine_name]["last_error"] = None
                result.setdefault("failed_engines", failed_engines)
                result.setdefault("attempted_engines", failed_engines + [engine_name])
                return result
            
            last_error = result.get("error", "Unknown error")
            failed_engines.append(engine_name)
            self.runtime_stats[engine_name]["failures"] += 1
            self.runtime_stats[engine_name]["last_error"] = last_error

            # Activate cooldown for non-retryable errors
            if self._should_cooldown_provider(last_error):
                self._activate_provider_cooldown(engine_name, last_error)

            logger.warning(f"{engine_name} failed: {last_error}")
        
        return {
            "status": "error",
            "error": f"All engines failed. Last error: {last_error}",
            "engine": "none",
            "failed_engines": failed_engines,
            "attempted_engines": failed_engines,
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
