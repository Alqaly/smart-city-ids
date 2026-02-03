"""
LLM Base Class - Shared Logic for All LLM Engines

Provides common functionality for xAI, OpenAI, and Groq LLM integrations:
- Prompt building
- JSON response parsing with fallbacks
- Error handling and logging
- Response validation
- Retry logic

This reduces code duplication from ~450 lines → ~150 lines per engine.
"""

import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple
from datetime import datetime
import httpx

logger = logging.getLogger(__name__)


class LLMAnalysisError(Exception):
    """Custom exception for LLM analysis failures"""
    def __init__(self, message: str, error_code: str = "unknown", retryable: bool = False):
        self.message = message
        self.error_code = error_code
        self.retryable = retryable
        super().__init__(message)


class LLMResponse(dict):
    """Validated LLM response with strict schema"""
    
    REQUIRED_FIELDS = {
        'severity': int,
        'threat_type': str,
        'summary': str,
        'recommendations': list,
        'automated_actions': list
    }
    
    @classmethod
    def validate(cls, data: Dict[str, Any]) -> 'LLMResponse':
        """Validate response against schema"""
        errors = []
        
        # Check required fields exist
        for field, expected_type in cls.REQUIRED_FIELDS.items():
            if field not in data:
                errors.append(f"Missing required field: {field}")
            elif not isinstance(data[field], expected_type):
                errors.append(f"{field}: expected {expected_type.__name__}, got {type(data[field]).__name__}")
        
        # Validate severity is 1-10
        if 'severity' in data:
            severity = data['severity']
            if not isinstance(severity, int) or severity < 1 or severity > 10:
                errors.append(f"severity must be integer 1-10, got {severity}")
        
        # Validate automated_actions are valid
        if 'automated_actions' in data:
            valid_actions = {'isolate_pod', 'scale_deployment', 'restart_pod', 'rollback_deployment', 'evict_pod'}
            for action in data.get('automated_actions', []):
                if action not in valid_actions:
                    errors.append(f"Unknown automated action: {action}")
        
        if errors:
            raise ValueError("Response validation failed: " + "; ".join(errors))
        
        return cls(data)


class BaseLLMAnalyzer(ABC):
    """Abstract base class for LLM engines"""
    
    # Override in subclasses
    ENGINE_NAME = "base"
    
    def __init__(self):
        self.api_key = None
        self.model = None
        self.base_url = None
        self.system_prompt = self._build_system_prompt()
        self.request_timeout = 30.0
        self.max_retries = 1  # Override in subclass if needed
        self.retry_delay = 1.0  # seconds
    
    def _build_system_prompt(self) -> str:
        """Build system prompt for LLM. Override in subclass for customization."""
        return """You are a cybersecurity expert analyzing threats in a Smart City 
infrastructure running on Kubernetes.

Your role:
1. Analyze security alerts from Falco (host-based) and Suricata (network-based)
2. Explain threats in plain English for non-experts
3. Assess severity on a 1-10 scale (10 = critical)
4. Recommend specific, actionable mitigation steps
5. Suggest automated Kubernetes responses when appropriate

Be concise, accurate, and security-focused. Always respond with valid JSON only."""
    
    def _build_user_prompt(self, alert: Dict[str, Any]) -> str:
        """Build user prompt from alert data. Override if needed."""
        rule = alert.get('rule', 'Unknown')
        output = alert.get('output', '')
        priority = alert.get('priority', 'Unknown')
        fields = alert.get('output_fields', {})
        
        # Extract key fields
        container = fields.get('container.name', 'Unknown')
        proc_cmdline = fields.get('proc.cmdline', 'N/A')
        src_ip = fields.get('src.ip', 'N/A')
        dst_port = fields.get('dst.port', 'N/A')
        
        return f"""Analyze this security alert from a Kubernetes cluster:

ALERT RULE: {rule}
PRIORITY: {priority}
CONTAINER: {container}
PROCESS: {proc_cmdline}
SOURCE IP: {src_ip}
DEST PORT: {dst_port}
OUTPUT: {output}

Respond with JSON containing:
{{
  "severity": <1-10>,
  "threat_type": "<category>",
  "summary": "<1-2 sentences>",
  "recommendations": ["<action1>", "<action2>"],
  "automated_actions": ["<k8s_action1>"]
}}"""
    
    async def analyze_alert(self, alert: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze security alert. Must be implemented by subclass.
        
        Args:
            alert: Parsed security alert
            
        Returns:
            {
                "status": "success" | "error",
                "analysis": {...},  # if status == success
                "error": "...",     # if status == error
                "llm_engine": self.ENGINE_NAME,
                "response_time_ms": int
            }
        """
        raise NotImplementedError("Subclass must implement analyze_alert()")
    
    @abstractmethod
    async def _call_api(self, system_prompt: str, user_prompt: str) -> str:
        """
        Call LLM API and return raw response text.
        Must be implemented by subclass.
        
        Args:
            system_prompt: System prompt for LLM
            user_prompt: User prompt with alert context
            
        Returns:
            Raw response text from LLM
        """
        pass
    
    def _parse_json_response(self, content: str) -> Dict[str, Any]:
        """
        Parse JSON from LLM response with multiple fallback strategies.
        
        Tries:
        1. Direct JSON parse
        2. Extract from ```json code block
        3. Extract from ```python code block
        4. Regex-based extraction
        5. Conservative fallback
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
        
        # Strategy 3: Extract from ```python block
        if "```python" in content:
            try:
                python_block = content.split("```python")[1].split("```")[0].strip()
                # Try to parse as JSON (Python dict literal might be JSON-compatible)
                return json.loads(python_block)
            except (json.JSONDecodeError, IndexError):
                pass
        
        # Strategy 4: Regex-based extraction (find JSON-like structure)
        try:
            match = re.search(r'\{[^{}]*"severity"[^{}]*\}', content, re.DOTALL)
            if match:
                json_str = match.group(0)
                # Try to find matching braces
                brace_count = 0
                for i, char in enumerate(json_str):
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            json_str = json_str[:i+1]
                            break
                return json.loads(json_str)
        except (json.JSONDecodeError, AttributeError):
            pass
        
        # Strategy 5: Fallback analysis (no JSON found)
        logger.warning(f"Could not parse LLM response as JSON. Content: {content[:100]}...")
        return {
            "severity": 5,
            "threat_type": "Unknown",
            "summary": "LLM response could not be parsed. Manual review required.",
            "recommendations": ["Review alert manually", "Check LLM response format"],
            "automated_actions": []
        }
    
    def _validate_response(self, response: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validate response against schema.
        
        Returns:
            (is_valid: bool, error_message: str)
        """
        try:
            LLMResponse.validate(response)
            return True, ""
        except ValueError as e:
            return False, str(e)
    
    async def _call_with_retry(self, system_prompt: str, user_prompt: str) -> str:
        """
        Call API with exponential backoff retry logic.
        
        Args:
            system_prompt: System prompt
            user_prompt: User prompt
            
        Returns:
            API response text
        """
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                return await self._call_api(system_prompt, user_prompt)
            except httpx.TimeoutException as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    wait_time = (2 ** attempt) * self.retry_delay
                    logger.warning(f"{self.ENGINE_NAME} timeout, retrying in {wait_time}s...")
                    import asyncio
                    await asyncio.sleep(wait_time)
            except Exception as e:
                last_error = e
                break
        
        raise LLMAnalysisError(
            f"{self.ENGINE_NAME} failed after {self.max_retries} attempts: {last_error}",
            error_code="api_error",
            retryable=isinstance(last_error, httpx.TimeoutException)
        )
    
    def _log_analysis_context(self, alert: Dict[str, Any], analysis: Dict[str, Any], 
                             response_time_ms: int, status: str):
        """Log analysis with rich context for debugging"""
        logger.info(
            f"{self.ENGINE_NAME} analysis completed",
            extra={
                "engine": self.ENGINE_NAME,
                "status": status,
                "severity": analysis.get('severity'),
                "threat_type": analysis.get('threat_type'),
                "rule": alert.get('rule'),
                "container": alert.get('output_fields', {}).get('container.name'),
                "response_time_ms": response_time_ms,
                "automated_actions": len(analysis.get('automated_actions', []))
            }
        )


# Example subclass implementation (xAI)
class XAIAnalyzer(BaseLLMAnalyzer):
    """xAI Grok-4 specific implementation"""
    
    ENGINE_NAME = "xai-grok-4"
    
    def __init__(self, api_key: str, model: str = "grok-4-latest"):
        super().__init__()
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.x.ai/v1/chat/completions"
        self.request_timeout = 30.0
        self.max_retries = 2
    
    async def _call_api(self, system_prompt: str, user_prompt: str) -> str:
        """Call xAI API"""
        async with httpx.AsyncClient(timeout=self.request_timeout) as client:
            response = await client.post(
                self.base_url,
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
                    "temperature": 0.3,
                    "max_tokens": 1000,
                    "stream": False
                }
            )
            
            if response.status_code != 200:
                raise LLMAnalysisError(
                    f"xAI API error {response.status_code}",
                    error_code=str(response.status_code),
                    retryable=response.status_code >= 500
                )
            
            result = response.json()
            return result["choices"][0]["message"]["content"]
    
    async def analyze_alert(self, alert: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze alert using xAI Grok-4"""
        start_time = datetime.now()
        
        try:
            system_prompt = self._build_system_prompt()
            user_prompt = self._build_user_prompt(alert)
            
            # Call API with retries
            content = await self._call_with_retry(system_prompt, user_prompt)
            
            # Parse response
            analysis = self._parse_json_response(content)
            
            # Validate
            is_valid, error_msg = self._validate_response(analysis)
            if not is_valid:
                logger.warning(f"xAI response validation failed: {error_msg}")
                analysis['severity'] = 5  # Downgrade to medium if validation fails
            
            response_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            self._log_analysis_context(alert, analysis, response_time_ms, "success")
            
            return {
                "status": "success",
                "analysis": analysis,
                "llm_engine": self.ENGINE_NAME,
                "response_time_ms": response_time_ms
            }
            
        except LLMAnalysisError as e:
            logger.error(f"xAI analysis error: {e.message}")
            return {
                "status": "error",
                "error": e.message,
                "error_code": e.error_code,
                "llm_engine": self.ENGINE_NAME
            }
        except Exception as e:
            logger.error(f"Unexpected error in xAI analysis: {e}")
            return {
                "status": "error",
                "error": str(e),
                "llm_engine": self.ENGINE_NAME
            }
