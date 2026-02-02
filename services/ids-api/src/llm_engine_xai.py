"""
xAI Grok-4 Integration for Threat Analysis
Primary LLM engine - Fastest and most capable
"""
import json
import logging
from typing import Dict, Any
import httpx
from config import Config

logger = logging.getLogger(__name__)

class XAIAnalyzer:
    """xAI Grok-4 threat analyzer - Primary engine"""
    
    def __init__(self):
        self.api_key = Config.XAI_API_KEY
        self.model = Config.XAI_MODEL
        self.base_url = "https://api.x.ai/v1/chat/completions"
        
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
        Analyze security alert using xAI Grok-4
        
        Args:
            alert: Parsed security alert
            
        Returns:
            Analysis with severity, threat type, and recommendations
        """
        try:
            # Build prompt
            user_prompt = self._build_prompt(alert)
            
            # Call xAI API using httpx (async)
            async with httpx.AsyncClient(timeout=30.0) as client:
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
                        "max_tokens": Config.LLM_MAX_TOKENS,
                        "stream": False
                    }
                )
                
                if response.status_code != 200:
                    error_detail = response.text
                    logger.error(f"xAI API error {response.status_code}: {error_detail}")
                    return {"status": "error", "error": f"xAI API error: {response.status_code}"}
                
                result = response.json()
            
            # Extract content
            content = result["choices"][0]["message"]["content"]
            
            # Parse JSON from response
            analysis = self._parse_json_response(content)
            
            logger.info(f"xAI Grok analysis complete: severity={analysis.get('severity')}")
            
            return {"status": "success", "analysis": analysis}
            
        except httpx.TimeoutException:
            logger.error("xAI API timeout")
            return {"status": "error", "error": "xAI API timeout"}
        except Exception as e:
            logger.error(f"xAI analysis error: {e}")
            return {"status": "error", "error": str(e)}
    
    def _parse_json_response(self, content: str) -> Dict[str, Any]:
        """Parse JSON from LLM response, handling various formats"""
        # Try direct JSON parse first
        try:
            return json.loads(content)
        except:
            pass
        
        # Try extracting from markdown code blocks
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        try:
            return json.loads(content)
        except:
            # Fallback structured response
            return {
                "summary": content[:300] if len(content) > 300 else content,
                "severity": 7,
                "threat_type": "Unknown",
                "business_impact": "Potential security incident requiring investigation",
                "recommendations": ["Investigate immediately", "Review system logs", "Check for indicators of compromise"],
                "automated_actions": ["isolate_pod"]
            }
    
    def _build_prompt(self, alert: Dict[str, Any]) -> str:
        """Build analysis prompt from alert"""
        
        # Handle both Falco and normalized alert formats
        if 'output' in alert:
            # Falco format
            return f"""Analyze this security alert from Smart City infrastructure:

**Alert Output:** {alert.get('output', 'N/A')}
**Priority:** {alert.get('priority', 'N/A')}
**Rule:** {alert.get('rule', 'N/A')}
**Timestamp:** {alert.get('time', 'N/A')}
**Container:** {alert.get('output_fields', {}).get('container.name', 'Unknown')}
**Process:** {alert.get('output_fields', {}).get('proc.cmdline', 'Unknown')}

Respond with JSON only in this exact format:
{{
  "summary": "1-2 sentence explanation of what happened",
  "severity": <1-10 integer>,
  "threat_type": "<DDoS|Privilege Escalation|Data Exfiltration|Malware|Policy Violation|Reconnaissance|Unknown>",
  "business_impact": "How this affects Smart City operations",
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

Respond with JSON only in this exact format:
{{
  "summary": "1-2 sentence explanation of what happened",
  "severity": <1-10 integer>,
  "threat_type": "<DDoS|Privilege Escalation|Data Exfiltration|Malware|Policy Violation|Reconnaissance|Unknown>",
  "business_impact": "How this affects Smart City operations",
  "recommendations": ["Action 1", "Action 2", "Action 3"],
  "automated_actions": ["isolate_pod", "scale_up", "block_ip", "cordon_node", "alert_team"]
}}"""
