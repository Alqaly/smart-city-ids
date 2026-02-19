"""
Smart City IDS - Enhanced LLM Engine Manager with Credit Checking
==================================================================

Extends the base LLM manager with:
- Credit checking before API calls
- Integration with security analyst prompts
- Tool/function calling support
- Cost-aware provider selection

This is a drop-in replacement for llm_manager.py with enhanced features.
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

# Import enhanced components
try:
    from llm_credit_checker import credit_checker, has_sufficient_credits
    from security_analyst_prompts import (
        SecurityAnalystPrompts, 
        AlertContext,
        BASE_SECURITY_ANALYST_PROMPT,
        SYSTEM_INTERACTION_PROMPT
    )
    from llm_tools import tool_registry, execute_tool_call
    CREDIT_CHECKING_AVAILABLE = True
except ImportError as e:
    CREDIT_CHECKING_AVAILABLE = False
    logging.warning(f"Credit checking not available: {e}")

# Local imports for enhanced validation and retry
try:
    from llm_response_schema import validate_llm_response, create_fallback_response, response_metrics
    from llm_retry import retry_with_backoff, is_retryable_error, RateLimiter
    SCHEMA_VALIDATION_ENABLED = True
except ImportError:
    SCHEMA_VALIDATION_ENABLED = False
    
logger = logging.getLogger(__name__)


# =============================================================================
# VERSION INFO
# =============================================================================

__version__ = "2.1.0-enhanced"
__author__ = "Smart City IDS Team"


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class LLMConfig:
    """
    Enhanced LLM Engine Configuration with credit awareness
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
    
    # Credit management
    min_credits_threshold: float = 0.5  # Minimum credits for a single call
    skip_low_credit_providers: bool = True
    
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
            min_credits_threshold=float(os.getenv("LLM_MIN_CREDITS_THRESHOLD", "0.5")),
            skip_low_credit_providers=os.getenv("LLM_SKIP_LOW_CREDIT", "true").lower() == "true",
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
# ENHANCED SYSTEM PROMPT WITH CREDIT AWARENESS
# =============================================================================

ENHANCED_SYSTEM_PROMPT = """You are a senior cybersecurity analyst specializing in Smart City / ICS infrastructure security.
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
- Respond with valid JSON ONLY — no markdown, no commentary outside the JSON
"""


def build_enhanced_prompt(alert: Dict[str, Any], context: Optional[AlertContext] = None) -> str:
    """
    Build enhanced analysis prompt with optional context.
    
    Args:
        alert: Security alert dict
        context: Optional system context for richer analysis
        
    Returns:
        Formatted prompt string
    """
    if context:
        # Use the full contextual prompt from security_analyst_prompts
        return SecurityAnalystPrompts.build_alert_analysis_prompt(context)
    
    # Fallback to basic prompt
    fields = alert.get('output_fields', {})
    
    return f"""Analyze this security alert from Smart City infrastructure.

═══ ALERT DATA ═══
Rule:        {alert.get('rule', 'N/A')}
Priority:    {alert.get('priority', 'N/A')}
Timestamp:   {alert.get('time', 'N/A')}
Output:      {alert.get('output', 'N/A')}

═══ EVIDENCE FIELDS ═══
Container:   {fields.get('container.name', 'Unknown')}
Process:     {fields.get('proc.cmdline', 'Unknown')}
User:        {fields.get('user.name', 'N/A')}
File/FD:     {fields.get('fd.name', 'N/A')}

═══ REQUIRED RESPONSE FORMAT (JSON only) ═══
{{
  "summary": "Clear explanation of what happened",
  "severity": <1-10 integer>,
  "threat_type": "<Threat category>",
  "confidence": <0.0-1.0>,
  "key_indicators": ["evidence1", "evidence2"],
  "mitigating_factors": ["factor1"],
  "business_impact": "Impact on Smart City operations",
  "reasoning": "Step-by-step analysis",
  "mitre_technique": "TXXXX — Technique Name",
  "recommendations": ["action1", "action2"],
  "automated_actions": ["isolate_pod|scale_up|block_ip"]
}}"""


def parse_llm_response(content: str) -> Dict[str, Any]:
    """
    Parse JSON from LLM response with multiple fallback strategies.
    """
    if content is None:
        return {
            "summary": "No response content",
            "severity": 5,
            "threat_type": "Unknown",
            "confidence": 0.5,
            "key_indicators": ["No response from LLM"],
            "mitigating_factors": ["Check LLM configuration"],
            "business_impact": "Unknown",
            "reasoning": "No response received from LLM provider",
            "recommendations": ["Check LLM credits", "Verify API keys"],
            "automated_actions": []
        }
    
    # Strategy 1: Direct JSON parse
    try:
        parsed = json.loads(content)
        if SCHEMA_VALIDATION_ENABLED:
            validated = validate_llm_response(parsed)
            return validated.model_dump()
        return parsed
    except json.JSONDecodeError:
        pass
    
    # Strategy 2: Extract from ```json block
    if "```json" in content:
        try:
            json_block = content.split("```json")[1].split("```")[0].strip()
            parsed = json.loads(json_block)
            return parsed
        except (json.JSONDecodeError, IndexError):
            pass
    
    # Strategy 3: Extract from ``` block
    if "```" in content:
        try:
            code_block = content.split("```")[1].split("```")[0].strip()
            parsed = json.loads(code_block)
            return parsed
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
    """Abstract base class for LLM engines"""
    
    ENGINE_NAME: str = "base"
    ESTIMATED_COST_PER_1K_TOKENS: float = 0.01  # Default estimate
    
    def __init__(self, api_key: str, model: str, config: LLMConfig):
        self.api_key = api_key
        self.model = model
        self.config = config
    
    @abstractmethod
    async def _call_api(self, system_prompt: str, user_prompt: str) -> str:
        """Call the LLM API and return raw response text"""
        pass
    
    async def analyze(self, alert: Dict[str, Any], context: Optional[AlertContext] = None) -> Dict[str, Any]:
        """
        Analyze security alert.
        
        Returns:
            {
                "status": "success" | "error",
                "analysis": {...},
                "error": "...",
                "engine": ENGINE_NAME,
                "latency_ms": int,
                "estimated_cost": float
            }
        """
        start = time.perf_counter()
        
        try:
            user_prompt = build_enhanced_prompt(alert, context)
            response_text = await self._call_api(ENHANCED_SYSTEM_PROMPT, user_prompt)
            analysis = parse_llm_response(response_text)
            
            latency_ms = int((time.perf_counter() - start) * 1000)
            
            # Estimate cost (rough approximation)
            estimated_tokens = len(user_prompt.split()) + len(response_text.split())
            estimated_cost = (estimated_tokens / 1000) * self.ESTIMATED_COST_PER_1K_TOKENS
            
            logger.info(f"{self.ENGINE_NAME} analysis: severity={analysis.get('severity')}, latency={latency_ms}ms")
            
            return {
                "status": "success",
                "analysis": analysis,
                "engine": self.ENGINE_NAME,
                "latency_ms": latency_ms,
                "estimated_cost_usd": round(estimated_cost, 6)
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
    """xAI Grok-4"""
    ENGINE_NAME = "xai"
    ESTIMATED_COST_PER_1K_TOKENS = 0.015
    
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
    """Anthropic Claude"""
    ENGINE_NAME = "anthropic"
    ESTIMATED_COST_PER_1K_TOKENS = 0.018
    
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
    """OpenAI GPT-4"""
    ENGINE_NAME = "openai"
    ESTIMATED_COST_PER_1K_TOKENS = 0.03
    
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
    """Google Gemini"""
    ENGINE_NAME = "gemini"
    ESTIMATED_COST_PER_1K_TOKENS = 0.005  # Free tier available
    
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
    """Moonshot Kimi"""
    ENGINE_NAME = "kimi"
    ESTIMATED_COST_PER_1K_TOKENS = 0.012
    
    async def _call_api(self, system_prompt: str, user_prompt: str) -> str:
        async with httpx.AsyncClient(timeout=60.0) as client:
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
    """Create an LLM engine instance"""
    key_map = {
        "xai": (config.xai_api_key, config.xai_model),
        "anthropic": (config.anthropic_api_key, config.anthropic_model),
        "openai": (config.openai_api_key, config.openai_model),
        "gemini": (config.gemini_api_key, config.gemini_model),
        "kimi": (config.kimi_api_key, config.kimi_model),
    }
    
    if name not in ENGINE_CLASSES:
        return None
    
    api_key, model = key_map.get(name, ("", ""))
    if not api_key:
        return None
    
    return ENGINE_CLASSES[name](api_key, model, config)


# =============================================================================
# ENHANCED MANAGER WITH CREDIT CHECKING
# =============================================================================

class EnhancedLLMManager:
    """
    Enhanced LLM Manager with:
    - Credit checking before API calls
    - Cost-aware provider selection
    - Tool calling support
    - Contextual analysis prompts
    """
    
    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig.from_env()
        self.engines: Dict[str, BaseLLMEngine] = {}
        
        # Provider cooldown
        self.cooldown_seconds = int(os.getenv("LLM_PROVIDER_COOLDOWN_SECONDS", "900"))
        self.provider_cooldown_until: Dict[str, float] = {}
        
        # Runtime stats
        self.runtime_stats: Dict[str, Dict] = {}
        
        # Initialize engines
        for name in self.config.get_available_engines():
            engine = create_engine(name, self.config)
            if engine:
                self.engines[name] = engine
                self.provider_cooldown_until[name] = 0.0
                self.runtime_stats[name] = {
                    "attempts": 0, "successes": 0, "failures": 0,
                    "last_latency_ms": None, "last_error": None,
                    "total_cost_usd": 0.0
                }
        
        logger.info(f"Enhanced LLM Manager: engines={list(self.engines.keys())}, credit_checking={CREDIT_CHECKING_AVAILABLE}")
    
    def get_available_engines(self) -> List[str]:
        """Return list of initialized engine names"""
        return list(self.engines.keys())
    
    async def _check_credits(self, engine_name: str) -> Tuple[bool, Optional[str]]:
        """
        Check if provider has sufficient credits.
        
        Returns:
            (has_credits, error_message)
        """
        if not CREDIT_CHECKING_AVAILABLE:
            return True, None
        
        try:
            has_credits = has_sufficient_credits(engine_name, self.config.min_credits_threshold)
            if not has_credits:
                return False, f"Insufficient credits for {engine_name}"
            return True, None
        except Exception as e:
            logger.warning(f"Credit check failed for {engine_name}: {e}")
            return True, None  # Allow on check failure
    
    def _is_provider_in_cooldown(self, engine_name: str) -> bool:
        return self.provider_cooldown_until.get(engine_name, 0) > time.time()
    
    def _activate_provider_cooldown(self, engine_name: str, reason: str):
        until = time.time() + self.cooldown_seconds
        self.provider_cooldown_until[engine_name] = until
        logger.warning(f"{engine_name} cooldown: {self.cooldown_seconds}s - {reason}")
    
    @staticmethod
    def _should_cooldown_provider(error_message: str) -> bool:
        msg = (error_message or "").lower()
        cooldown_indicators = (
            "insufficient_quota", "quota", "resource has been exhausted",
            "used all available credits", "monthly spending limit", "exhausted",
            "invalid api key", "authentication", "unauthorized",
            "api error 401", "api error 403", "api error 429",
        )
        return any(indicator in msg for indicator in cooldown_indicators)
    
    async def analyze(
        self, 
        alert: Dict[str, Any], 
        preferred_engine: Optional[str] = None,
        context: Optional[AlertContext] = None
    ) -> Dict[str, Any]:
        """
        Analyze alert with credit checking and failover.
        
        Args:
            alert: Security alert dict
            preferred_engine: Optional engine to try first
            context: Optional system context for richer analysis
            
        Returns:
            Analysis result with status, analysis, engine, cost info
        """
        # Build engine order
        if preferred_engine and preferred_engine in self.engines:
            order = [preferred_engine] + [e for e in self.config.get_priority_order() if e != preferred_engine]
        else:
            order = self.config.get_priority_order()
        
        last_error = None
        failed_engines: List[str] = []
        credit_issues: List[str] = []
        
        for engine_name in order:
            engine = self.engines.get(engine_name)
            if not engine:
                continue
            
            # Check cooldown
            if self._is_provider_in_cooldown(engine_name):
                logger.debug(f"Skipping {engine_name} - in cooldown")
                continue
            
            # Check credits
            if CREDIT_CHECKING_AVAILABLE and self.config.skip_low_credit_providers:
                has_credits, credit_error = await self._check_credits(engine_name)
                if not has_credits:
                    logger.warning(f"Skipping {engine_name} - {credit_error}")
                    credit_issues.append(f"{engine_name}: {credit_error}")
                    continue
            
            # Attempt analysis
            self.runtime_stats[engine_name]["attempts"] += 1
            
            try:
                result = await engine.analyze(alert, context)
                
                if result["status"] == "success":
                    self.runtime_stats[engine_name]["successes"] += 1
                    self.runtime_stats[engine_name]["last_latency_ms"] = result.get("latency_ms")
                    
                    # Track cost
                    if "estimated_cost_usd" in result:
                        self.runtime_stats[engine_name]["total_cost_usd"] += result["estimated_cost_usd"]
                    
                    # Add credit info to result
                    if credit_issues:
                        result["credit_warnings"] = credit_issues
                    
                    logger.info(f"Analysis successful with {engine_name}: severity={result['analysis'].get('severity')}")
                    return result
                else:
                    error = result.get("error", "Unknown error")
                    raise Exception(error)
                    
            except Exception as e:
                error_msg = str(e)
                logger.warning(f"{engine_name} failed: {error_msg}")
                failed_engines.append(f"{engine_name}: {error_msg}")
                self.runtime_stats[engine_name]["failures"] += 1
                self.runtime_stats[engine_name]["last_error"] = error_msg
                last_error = error_msg
                
                # Activate cooldown for non-retryable errors
                if self._should_cooldown_provider(error_msg):
                    self._activate_provider_cooldown(engine_name, error_msg)
        
        # All engines failed
        logger.error(f"All LLM engines failed. Errors: {failed_engines}")
        
        # Return rule-based fallback analysis
        return {
            "status": "fallback",
            "analysis": self._rule_based_fallback_analysis(alert),
            "engine": "rule_based_fallback",
            "error": f"All providers failed. Last error: {last_error}",
            "failed_engines": failed_engines,
            "credit_issues": credit_issues,
            "latency_ms": 0
        }
    
    def _rule_based_fallback_analysis(self, alert: Dict[str, Any]) -> Dict[str, Any]:
        """Rule-based analysis when all LLMs fail"""
        output = alert.get("output", "").lower()
        rule = alert.get("rule", "").lower()
        
        # Pattern matching rules
        patterns = [
            ("crypto, miner, xmrig, stratum", 7, "Malware"),
            ("sql injection, sqlmap, union select", 8, "Data Exfiltration"),
            ("/etc/shadow, /etc/passwd, sensitive file", 8, "Data Exfiltration"),
            ("container escape, nsenter, /proc/1", 9, "Privilege Escalation"),
            ("privilege escalation, setuid, sudo", 9, "Privilege Escalation"),
            ("shell, bash, /bin/sh spawned", 7, "Privilege Escalation"),
            ("ddos, flood, amplification", 8, "DDoS"),
            ("dns exfiltration, dns tunnel", 7, "Data Exfiltration"),
            ("lateral movement, service discovery", 8, "Reconnaissance"),
            ("outbound connection, unexpected", 7, "Policy Violation"),
            ("port scan, network scan", 6, "Reconnaissance"),
        ]
        
        for keywords, severity, threat_type in patterns:
            if any(k.strip() in output or k.strip() in rule for k in keywords.split(",")):
                return {
                    "summary": f"Detected potential {threat_type} based on rule: {rule}",
                    "severity": severity,
                    "threat_type": threat_type,
                    "confidence": 0.6,
                    "key_indicators": [f"Rule match: {rule}", f"Output: {output[:100]}"],
                    "mitigating_factors": ["Rule-based fallback analysis - LLM unavailable"],
                    "business_impact": "Unknown - manual review required",
                    "reasoning": "Rule-based pattern matching used due to LLM provider failures",
                    "recommendations": ["Review alert manually", "Check LLM provider status"],
                    "automated_actions": ["isolate_pod"] if severity >= 8 else []
                }
        
        return {
            "summary": f"Alert triggered: {rule}",
            "severity": 5,
            "threat_type": "Policy Violation",
            "confidence": 0.5,
            "key_indicators": [rule],
            "mitigating_factors": ["Rule-based fallback - limited analysis"],
            "business_impact": "Unknown",
            "reasoning": "Default rule-based analysis - no specific pattern matched",
            "recommendations": ["Manual review required"],
            "automated_actions": []
        }
    
    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive status including credit info"""
        status = {
            "provider_count": len(self.engines),
            "providers": list(self.engines.keys()),
            "credit_checking_available": CREDIT_CHECKING_AVAILABLE,
            "details": {}
        }
        
        for provider in self.engines:
            stats = self.runtime_stats.get(provider, {})
            cooldown_until = self.provider_cooldown_until.get(provider, 0)
            
            status["details"][provider] = {
                "configured": True,
                "model": self.engines[provider].model,
                "attempts": stats.get("attempts", 0),
                "successes": stats.get("successes", 0),
                "failures": stats.get("failures", 0),
                "total_cost_usd": round(stats.get("total_cost_usd", 0), 4),
                "last_latency_ms": stats.get("last_latency_ms"),
                "last_error": stats.get("last_error"),
                "cooldown_until": int(cooldown_until),
                "cooldown_remaining_seconds": max(0, int(cooldown_until - time.time())),
            }
        
        return status
    
    async def analyze_security_alert(self, alert_data: Dict[str, Any], system_prompt: str, force_provider: Optional[str] = None) -> Dict[str, Any]:
        """
        Specialized analysis for security alerts with conversational context.
        Used by the Analyst API.
        """
        # Select engine (default to first available)
        provider = force_provider or (list(self.engines.keys())[0] if self.engines else None)
        
        if not provider or provider not in self.engines:
            return {"status": "error", "error": f"No engine available (requested: {force_provider})"}
            
        engine = self.engines[provider]
        
        try:
            # Extract conversation history
            conversation = alert_data.get("conversation", [])
            last_msg = conversation[-1] if conversation else {"content": ""}
            user_content = last_msg.get('content', '')
            
            # Simple context appending for stateless engines
            context_str = json.dumps([m for m in conversation[:-1]], indent=2)
            full_system = f"{system_prompt}\n\nPREVIOUS CONTEXT:\n{context_str}"
            
            # Call API
            response_text = await engine._call_api(full_system, user_content)
            
            # Estimate cost
            input_tokens = len(full_system + user_content) / 4
            output_tokens = len(response_text) / 4
            cost = ((input_tokens + output_tokens) / 1000) * engine.ESTIMATED_COST_PER_1K_TOKENS
            
            return {
                "status": "success",
                "analysis": {"raw_analysis": response_text},
                "provider": provider,
                "credit_info": {"estimated_cost_usd": cost}
            }
        except Exception as e:
            logger.error(f"Chat analysis failed: {e}")
            return {"status": "error", "error": str(e)}

    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any], governance_mode: str = "assisted") -> Dict[str, Any]:
        """Execute a tool on behalf of the LLM"""
        return await execute_tool_call(tool_name, arguments, governance_mode)


# Maintain backward compatibility
LLMEngineManager = EnhancedLLMManager

__all__ = [
    "EnhancedLLMManager",
    "LLMEngineManager",
    "LLMConfig",
    "BaseLLMEngine",
    "XAIEngine",
    "AnthropicEngine",
    "OpenAIEngine",
    "GeminiEngine",
    "KimiEngine",
    "AlertContext",
]
