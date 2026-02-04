"""
Moonshot Kimi K1 Integration for Threat Analysis
High-performance reasoning model from Moonshot AI
"""
import json
import logging
from typing import Dict, Any
import httpx
from config import Config

logger = logging.getLogger(__name__)

class KimiAnalyzer:
    """Moonshot Kimi K1 threat analyzer"""
    
    def __init__(self):
        self.api_key = Config.KIMI_API_KEY
        self.model = Config.KIMI_MODEL
        # Kimi uses OpenAI-compatible API
        self.base_url = "https://api.moonshot.cn/v1/chat/completions"
        
        self.system_prompt = """You are a cybersecurity expert analyzing threats in a Smart City infrastructure running on Kubernetes.

Your role:
1. Analyze security alerts from Falco (host-based) and Suricata (network-based)
2. Explain threats in plain English for non-experts
3. Assess severity on a 1-10 scale (10 = critical)
4. Recommend specific, actionable mitigation steps
5. Suggest automated Kubernetes responses when appropriate

Be concise, accurate, and security-focused. Always respond with valid JSON only."""

    async def analyze_alert(self, alert: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze security alert using Moonshot Kimi K1
        
        Args:
            alert: Parsed security alert
            
        Returns:
            Analysis with severity, threat type, and recommendations
        """
        try:
            user_prompt = self._build_prompt(alert)
            
            async with httpx.AsyncClient(timeout=60.0) as client:  # Kimi can be slower
                response = await client.post(
                    self.base_url,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.api_key}"
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": self.system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        "temperature": Config.LLM_TEMPERATURE,
                        "max_tokens": Config.LLM_MAX_TOKENS
                    }
                )
                
                if response.status_code != 200:
                    error_detail = response.text
                    logger.error(f"Kimi API error {response.status_code}: {error_detail}")
                    return {"status": "error", "error": f"Kimi API error: {response.status_code}"}
                
                result = response.json()
            
            # Extract content (OpenAI-compatible format)
            content = result["choices"][0]["message"]["content"]
            analysis = self._parse_json_response(content)
            
            logger.info(f"Kimi K1 analysis complete: severity={analysis.get('severity')}")
            return {"status": "success", "analysis": analysis}
            
        except httpx.TimeoutException:
            logger.error("Kimi API timeout")
            return {"status": "error", "error": "Kimi API timeout"}
        except Exception as e:
            logger.error(f"Kimi analysis error: {e}")
            return {"status": "error", "error": str(e)}
    
    def _parse_json_response(self, content: str) -> Dict[str, Any]:
        """Parse JSON from LLM response"""
        try:
            return json.loads(content)
        except:
            pass
        
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        try:
            return json.loads(content)
        except:
            return {
                "summary": content[:300] if len(content) > 300 else content,
                "severity": 7,
                "threat_type": "Unknown",
                "confidence": 0.65,
                "key_indicators": ["Alert triggered", "Requires investigation"],
                "mitigating_factors": ["Analysis uncertain due to parsing error"],
                "business_impact": "Potential security incident requiring investigation",
                "reasoning": "Fallback analysis due to LLM response parsing error.",
                "recommendations": ["Investigate immediately", "Review system logs"],
                "automated_actions": []
            }
    
    def _build_prompt(self, alert: Dict[str, Any]) -> str:
        """Build analysis prompt from alert"""
        if 'output' in alert:
            return f"""Analyze this security alert from Smart City infrastructure.

**Alert Output:** {alert.get('output', 'N/A')}
**Priority:** {alert.get('priority', 'N/A')}
**Rule:** {alert.get('rule', 'N/A')}
**Timestamp:** {alert.get('time', 'N/A')}
**Container:** {alert.get('output_fields', {}).get('container.name', 'Unknown')}
**Process:** {alert.get('output_fields', {}).get('proc.cmdline', 'Unknown')}

Provide TRANSPARENT analysis:
1. Assess threat type and severity (1-10)
2. Provide confidence score (0.0-1.0)
3. List key indicators
4. Note mitigating factors
5. Recommend specific actions

Respond with JSON only:
{{
  "summary": "1-2 sentence explanation",
  "severity": <1-10>,
  "threat_type": "DDoS|Privilege Escalation|Data Exfiltration|Malware|Policy Violation|Reconnaissance|Unknown",
  "confidence": <0.0-1.0>,
  "key_indicators": ["..."],
  "mitigating_factors": ["..."],
  "business_impact": "...",
  "reasoning": "...",
  "recommendations": ["..."],
  "automated_actions": ["isolate_pod", "scale_up", "block_ip", "cordon_node", "alert_team"]
}}"""
        else:
            return f"""Analyze this security alert:
{json.dumps(alert, indent=2)}

Respond with JSON only containing: summary, severity (1-10), threat_type, confidence, key_indicators, mitigating_factors, business_impact, reasoning, recommendations, automated_actions."""
