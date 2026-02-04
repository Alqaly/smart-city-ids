"""
OpenAI GPT-4 Integration for Threat Analysis
"""
import json
import logging
from typing import Dict, Any
from openai import AsyncOpenAI
from config import Config

logger = logging.getLogger(__name__)

class OpenAIAnalyzer:
    """OpenAI GPT-4 threat analyzer"""
    
    def __init__(self):
        self.client = AsyncOpenAI(api_key=Config.OPENAI_API_KEY)
        self.model = Config.OPENAI_MODEL
        
        self.system_prompt = """You are a cybersecurity expert analyzing threats in a Smart City infrastructure running on Kubernetes.

Your role:
1. Analyze security alerts from Falco (host-based) and Suricata (network-based)
2. Explain threats in plain English for non-experts
3. Assess severity on a 1-10 scale
4. Recommend specific, actionable mitigation steps
5. Suggest automated Kubernetes responses

Be concise, accurate, and security-focused. Always respond in JSON format."""

    async def analyze_alert(self, alert: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze security alert using OpenAI GPT-4
        
        Args:
            alert: Parsed security alert
            
        Returns:
            Analysis with severity, threat type, and recommendations
        """
        try:
            # Build prompt
            user_prompt = self._build_prompt(alert)
            
            # Call OpenAI API
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=Config.LLM_TEMPERATURE,
                max_tokens=Config.LLM_MAX_TOKENS,
                response_format={"type": "json_object"}
            )
            
            # Parse response
            analysis = json.loads(response.choices[0].message.content)
            
            logger.info(f"OpenAI analysis complete: severity={analysis.get('severity')}")
            
            return {"status": "success", "analysis": analysis}
            
        except Exception as e:
            logger.error(f"OpenAI analysis error: {e}")
            return {"status": "error", "error": str(e)}
    
    def _build_prompt(self, alert: Dict[str, Any]) -> str:
        """Build analysis prompt from alert - includes confidence and reasoning requirements"""
        
        if 'output' in alert:
            # Falco format
            return f"""Analyze this security alert from Smart City infrastructure.

**Alert Output:** {alert.get('output', 'N/A')}
**Priority:** {alert.get('priority', 'N/A')}
**Rule:** {alert.get('rule', 'N/A')}
**Timestamp:** {alert.get('time', 'N/A')}
**Container:** {alert.get('output_fields', {}).get('container.name', 'Unknown')}
**Process:** {alert.get('output_fields', {}).get('proc.cmdline', 'Unknown')}

Provide TRANSPARENT analysis for human operator review:
1. Assess threat type and severity (1-10)
2. Provide confidence score (0.0-1.0) based on evidence strength
3. List key indicators that support this assessment
4. Note any mitigating factors or reasons this might be false positive
5. Recommend specific actions with clear rationale

Respond with JSON ONLY in this exact format:
{{
  "summary": "1-2 sentence explanation of what happened",
  "severity": <1-10 integer>,
  "threat_type": "DDoS|Privilege Escalation|Data Exfiltration|Malware|Policy Violation|Reconnaissance|Unknown",
  "confidence": <0.0-1.0 float>,
  "key_indicators": ["Indicator 1", "Indicator 2", "Indicator 3"],
  "mitigating_factors": ["Factor 1", "Factor 2"],
  "business_impact": "How this affects Smart City operations",
  "reasoning": "Detailed explanation of the threat assessment",
  "recommendations": ["Action 1", "Action 2", "Action 3"],
  "automated_actions": ["isolate_pod", "scale_up", "block_ip", "cordon_node", "alert_team"]
}}"""
        else:
            # Normalized format
            return f"""Analyze this security alert from Smart City infrastructure:

**Alert Source:** {alert.get('source', 'unknown')}
**Alert Type:** {alert.get('alert_type', 'unknown')}
**Timestamp:** {alert.get('timestamp', 'N/A')}
**Severity:** {alert.get('severity', 'N/A')}

**Details:**
{json.dumps(alert.get('details', {}), indent=2)}

Provide TRANSPARENT analysis for human operator review. Respond with JSON ONLY:
{{
  "summary": "1-2 sentence explanation of what happened",
  "severity": <1-10 integer>,
  "threat_type": "DDoS|Privilege Escalation|Data Exfiltration|Malware|Policy Violation|Reconnaissance|Unknown",
  "confidence": <0.0-1.0 float>,
  "key_indicators": ["Indicator 1", "Indicator 2", "Indicator 3"],
  "mitigating_factors": ["Factor 1", "Factor 2"],
  "business_impact": "How this affects Smart City operations",
  "reasoning": "Detailed explanation of the threat assessment",
  "recommendations": ["Action 1", "Action 2", "Action 3"],
  "automated_actions": ["isolate_pod", "scale_up", "block_ip", "cordon_node", "alert_team"]
}}"""
