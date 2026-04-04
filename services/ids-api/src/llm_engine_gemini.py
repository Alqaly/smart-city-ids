"""
Google Gemini Integration for Threat Analysis
Fast multimodal model with strong reasoning capabilities
"""
import json
import logging
from typing import Dict, Any
import httpx
from config import Config

logger = logging.getLogger(__name__)

class GeminiAnalyzer:
    """Google Gemini threat analyzer"""
    
    def __init__(self):
        self.api_key = Config.GEMINI_API_KEY
        self.model = Config.GEMINI_MODEL
        self.base_url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        
        self.system_instruction = """You are a senior cybersecurity analyst specializing in Smart City / ICS infrastructure security.

ENVIRONMENT:
- Smart City IoT platform on Kubernetes (K3s) with 5 IoT protocol emulators:
  • Traffic Camera (ONVIF Profile S / RTSP / ANPR)
  • Parking System (MQTT / CoAP / SenML magnetometer sensors)
  • Healthcare API (HL7 FHIR R4 / IEEE 11073 medical devices)
  • Environmental Sensor (Modbus TCP / OPC UA — AQI stations)
  • Street Lighting (DALI-2 / TALQ v2.4 gateway control)
- Monitoring: Falco (runtime syscall detection), Suricata (network IDS/IPS)
- MITRE ATT&CK for ICS framework applies to this environment

YOUR ROLE:
1. Analyze security alerts from Falco (host-based) and Suricata (network-based)
2. Explain threats in clear, plain English suitable for non-expert stakeholders
3. Assess severity on a 1-10 scale (10 = critical, life-safety impact)
4. Map to MITRE ATT&CK for ICS techniques where applicable
5. Recommend specific, actionable mitigation steps
6. Suggest automated Kubernetes responses (isolate pod, scale up, etc.)

SEVERITY GUIDELINES:
- 9-10: Life-safety impact (healthcare data, traffic control compromise)
- 7-8: Critical infrastructure disruption (service outage, data exfiltration)
- 5-6: Operational degradation (reconnaissance, policy violations)
- 1-4: Low-risk events (info gathering, benign anomalies)

Be concise, accurate, and security-focused. Always respond with valid JSON only."""

    async def analyze_alert(self, alert: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze security alert using Google Gemini
        
        Args:
            alert: Parsed security alert
            
        Returns:
            Analysis with severity, threat type, and recommendations
        """
        try:
            user_prompt = self._build_prompt(alert)
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Gemini 2.5 "thinking" models consume maxOutputTokens for
                # internal reasoning.  Disable thinking for structured JSON
                # analysis and use a higher output budget.
                gemini_max = max(Config.LLM_MAX_TOKENS, 2048)
                gen_config: dict = {
                    "temperature": Config.LLM_TEMPERATURE,
                    "maxOutputTokens": gemini_max,
                    "responseMimeType": "application/json",
                }
                if "2.5" in self.model:
                    gen_config["thinkingConfig"] = {"thinkingBudget": 0}

                response = await client.post(
                    f"{self.base_url}?key={self.api_key}",
                    headers={"Content-Type": "application/json"},
                    json={
                        "system_instruction": {
                            "parts": [{"text": self.system_instruction}]
                        },
                        "contents": [{
                            "parts": [{"text": user_prompt}]
                        }],
                        "generationConfig": gen_config,
                    }
                )
                
                if response.status_code != 200:
                    error_detail = response.text
                    logger.error(f"Gemini API error {response.status_code}: {error_detail}")
                    return {"status": "error", "error": f"Gemini API error: {response.status_code}"}
                
                result = response.json()
            
            # Extract content from Gemini response
            content = result["candidates"][0]["content"]["parts"][0]["text"]
            analysis = self._parse_json_response(content)
            
            logger.info(f"Gemini analysis complete: severity={analysis.get('severity')}")
            return {"status": "success", "analysis": analysis}
            
        except httpx.TimeoutException:
            logger.error("Gemini API timeout")
            return {"status": "error", "error": "Gemini API timeout"}
        except Exception as e:
            logger.error(f"Gemini analysis error: {e}")
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
