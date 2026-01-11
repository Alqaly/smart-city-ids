"""
Groq Mixtral Integration - FIXED VERSION
Uses actual Groq API, not OpenAI!
"""
import json
import logging
from typing import Dict, Any
from groq import Groq
from config import Config

logger = logging.getLogger(__name__)

class GroqAnalyzer:
    """Groq Mixtral threat analyzer"""
    
    def __init__(self):
        # Use Groq client, not OpenAI!
        self.client = Groq(api_key=Config.GROQ_API_KEY)
        self.model = Config.GROQ_MODEL
        
        self.system_prompt = """You are a cybersecurity expert analyzing threats in a Smart City infrastructure.

Analyze security alerts and provide:
1. Plain English explanation
2. Severity score (1-10)
3. Threat classification
4. Business impact
5. Actionable recommendations

Always respond in JSON format."""

    async def analyze_alert(self, alert: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze security alert using Groq Mixtral
        """
        try:
            # Build prompt
            user_prompt = self._build_prompt(alert)
            
            # Call Groq API (synchronous)
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=Config.LLM_TEMPERATURE,
                max_tokens=Config.LLM_MAX_TOKENS
            )
            
            # Parse response
            content = response.choices[0].message.content
            
            # Try to extract JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            try:
                analysis = json.loads(content)
            except:
                # If JSON parsing fails, create structured response
                analysis = {
                    "summary": content[:200],
                    "severity": 7,
                    "threat_type": "Unknown",
                    "business_impact": "Potential security incident",
                    "recommendations": ["Investigate immediately", "Review logs"],
                    "automated_actions": ["isolate_pod"]
                }
            
            logger.info(f"Groq analysis complete: severity={analysis.get('severity')}")
            
            return {"status": "success", "analysis": analysis}
            
        except Exception as e:
            logger.error(f"Groq analysis error: {e}")
            return {"status": "error", "error": str(e)}
    
    def _build_prompt(self, alert: Dict[str, Any]) -> str:
        """Build analysis prompt"""
        return f"""Analyze this security alert from Smart City infrastructure:

Alert Details:
- Output: {alert.get('output', 'N/A')}
- Priority: {alert.get('priority', 'N/A')}
- Rule: {alert.get('rule', 'N/A')}
- Time: {alert.get('time', 'N/A')}
- Container: {alert.get('output_fields', {}).get('container.name', 'Unknown')}
- Process: {alert.get('output_fields', {}).get('proc.cmdline', 'Unknown')}

Respond ONLY with valid JSON in this exact format:
{{
  "summary": "Brief 1-2 sentence explanation",
  "severity": <integer 1-10>,
  "threat_type": "DDoS|Privilege Escalation|Data Exfiltration|Malware|etc",
  "business_impact": "How this affects operations",
  "recommendations": ["action1", "action2", "action3"],
  "automated_actions": ["isolate_pod", "scale_up", "block_ip", "cordon_node"]
}}"""
