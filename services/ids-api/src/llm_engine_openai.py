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
        
        self.system_prompt = """You are a senior cybersecurity analyst specializing in Smart City / ICS infrastructure security.

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
