"""
Operator Interface Service - PhD-Level Governance

Transforms raw security alerts + LLM analysis into operator-friendly format:
- Incident summaries (plain language, not technical)
- Evidence visualization (what Falco+Suricata actually detected)
- Reasoning transparency (why the LLM reached this conclusion)
- Action governance (what's approved, what needs operator sign-off, what's blocked)
- Confidence metrics (how certain is the analysis)

This makes the operator the Tier-2 authority with full visibility and control.
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from operator_models import (
    OperatorIncident, EvidenceItem, AnalysisReasoning, RecommendedAction,
    AutomationGovernance, ConfidenceLevel, IncidentDashboard, OperatorMetrics
)

logger = logging.getLogger(__name__)


class OperatorInterfaceService:
    """Transform security events into operator-readable format"""
    
    def __init__(self):
        self.incident_cache: Dict[int, OperatorIncident] = {}
        self.incidents_by_date: Dict[str, List[int]] = {}
    
    def build_incident_for_operator(
        self,
        alert_id: int,
        alert_data: Dict[str, Any],
        analysis: Dict[str, Any],
        llm_model_used: str,
        analysis_duration_ms: int,
        automation_mode: str,
        protected_services: List[str]
    ) -> OperatorIncident:
        """
        Transform raw alert + LLM analysis into operator-friendly incident summary
        
        Args:
            alert_id: Database alert ID
            alert_data: Raw alert from Falco/Suricata
            analysis: LLM analysis result
            llm_model_used: Which LLM engine analyzed this
            analysis_duration_ms: How long analysis took
            automation_mode: autopilot | assisted | manual
            protected_services: List of service names that can't be auto-isolated
        
        Returns:
            OperatorIncident with full context for operator dashboard
        """
        
        # Extract severity and confidence from analysis
        severity = analysis.get("severity", 5)
        confidence_score = analysis.get("confidence", 0.7)
        threat_type = analysis.get("threat_type", "Unknown")
        
        # Map confidence score to semantic level
        confidence_level = self._map_confidence_level(confidence_score)
        
        # Build evidence items from raw alert
        evidence_items = self._extract_evidence(alert_data)
        
        # Build reasoning explanation
        reasoning = self._build_reasoning(
            threat_type=threat_type,
            confidence_score=confidence_score,
            confidence_level=confidence_level,
            analysis=analysis,
            key_indicators=self._extract_key_indicators(alert_data, analysis)
        )
        
        # Extract container/service info for targeting
        container_name = alert_data.get("output_fields", {}).get("container.name", "unknown")
        service_name = container_name.split("-")[0] if container_name else "unknown"
        
        # Build recommended actions
        recommended_actions = self._build_recommended_actions(
            severity=severity,
            threat_type=threat_type,
            container_name=container_name,
            service_name=service_name
        )
        
        # Determine governance: what's auto vs needs approval
        automation_governance = self._determine_governance(
            severity=severity,
            automation_mode=automation_mode,
            actions=recommended_actions,
            protected_services=protected_services,
            container_name=container_name
        )
        
        # Build the complete incident
        incident = OperatorIncident(
            incident_id=alert_id,
            timestamp=self._parse_timestamp(alert_data.get("time")),
            incident_summary=self._generate_summary(threat_type, severity, alert_data),
            severity=severity,
            evidence=evidence_items,
            reasoning=reasoning,
            recommended_actions=recommended_actions,
            automation_governance=automation_governance,
            business_impact=analysis.get("business_impact", "Potential security incident requiring investigation"),
            llm_model_used=llm_model_used,
            analysis_duration_ms=analysis_duration_ms,
            analysis_timestamp=datetime.now()
        )
        
        # Cache for quick lookup
        self.incident_cache[alert_id] = incident
        today = datetime.now().date().isoformat()
        if today not in self.incidents_by_date:
            self.incidents_by_date[today] = []
        self.incidents_by_date[today].append(alert_id)
        
        return incident
    
    def _map_confidence_level(self, score: float) -> ConfidenceLevel:
        """Map 0.0-1.0 confidence score to semantic level"""
        if score < 0.4:
            return ConfidenceLevel.VERY_LOW
        elif score < 0.6:
            return ConfidenceLevel.LOW
        elif score < 0.75:
            return ConfidenceLevel.MEDIUM
        elif score < 0.9:
            return ConfidenceLevel.HIGH
        else:
            return ConfidenceLevel.VERY_HIGH
    
    def _extract_evidence(self, alert_data: Dict[str, Any]) -> List[EvidenceItem]:
        """Extract Falco/Suricata evidence from raw alert"""
        evidence = []
        
        rule = alert_data.get("rule", "Unknown")
        output = alert_data.get("output", "")
        timestamp = alert_data.get("time", "")
        container = alert_data.get("output_fields", {}).get("container.name")
        process = alert_data.get("output_fields", {}).get("proc.cmdline")
        
        # Determine source (Falco vs Suricata)
        source = "suricata" if "suricata" in rule.lower() else "falco"
        
        # Determine severity indicator category
        severity_indicator = self._classify_alert_type(rule, output)
        
        # Create evidence item with plain language excerpt
        excerpt = self._humanize_alert(rule, output, container, process)
        
        evidence.append(EvidenceItem(
            source=source,
            rule=rule,
            timestamp=timestamp,
            container=container,
            process=process,
            excerpt=excerpt,
            severity_indicator=severity_indicator
        ))
        
        return evidence
    
    def _classify_alert_type(self, rule: str, output: str) -> str:
        """Classify what type of detection this is"""
        rule_lower = rule.lower()
        output_lower = output.lower()
        
        if any(x in rule_lower for x in ["syscall", "execve", "open", "socket"]):
            return "syscall"
        elif any(x in rule_lower for x in ["http", "dns", "tcp", "udp", "port", "connection"]):
            return "network"
        elif any(x in rule_lower for x in ["behavior", "activity", "action"]):
            return "behavior"
        else:
            return "pattern"
    
    def _humanize_alert(self, rule: str, output: str, container: Optional[str] = None, process: Optional[str] = None) -> str:
        """Convert technical alert into plain English"""
        output_lower = output.lower() if output else ""
        
        # Extract the meaningful part of the output
        if "Falco" in rule or "falco" in rule.lower():
            # Falco alert - extract key details
            if "Unauthorized process" in rule:
                return f"Unusual process detected in {container or 'container'}: {process or 'unknown'}"
            elif "Privilege escalation" in rule:
                return f"Potential privilege escalation attempt in {container or 'container'}"
            elif "Reverse shell" in rule:
                return f"Possible reverse shell connection from {container or 'container'}"
            elif "Data exfiltration" in rule:
                return f"Potential data transfer from {container or 'container'}"
            else:
                return f"Suspicious activity: {rule[:100]}"
        elif "suricata" in rule.lower():
            # Suricata alert - network-based
            if "DDoS" in rule or "flood" in rule.lower():
                return f"Potential DDoS or flooding attack detected"
            elif "SQL" in rule or "sql" in output_lower:
                return f"Potential SQL injection attempt detected"
            elif "XSS" in rule or "xss" in output_lower:
                return f"Potential cross-site scripting (XSS) detected"
            else:
                return f"Network threat: {rule[:100]}"
        else:
            return output[:200] if output else rule
    
    def _extract_key_indicators(self, alert_data: Dict[str, Any], analysis: Dict[str, Any]) -> List[str]:
        """Extract top 3-5 signals that led to this assessment"""
        indicators = []
        
        rule = alert_data.get("rule", "")
        container = alert_data.get("output_fields", {}).get("container.name", "")
        process = alert_data.get("output_fields", {}).get("proc.cmdline", "")
        severity = analysis.get("severity", 5)
        
        # Add rule name as indicator
        if rule:
            indicators.append(f"Triggered rule: '{rule}'")
        
        # Add process indicator if unusual
        if process and len(process) > 50:
            indicators.append(f"Long/complex command line: {process[:60]}...")
        elif process:
            indicators.append(f"Process execution: {process}")
        
        # Add container context
        if container:
            indicators.append(f"Container: {container}")
        
        # Add severity context
        if severity >= 8:
            indicators.append("High severity score from threat analysis")
        
        # Add recommendations if available
        recommendations = analysis.get("recommendations", [])
        if recommendations:
            indicators.append(f"Analysis recommends: {recommendations[0]}")
        
        return indicators[:5]  # Top 5 indicators
    
    def _build_reasoning(
        self,
        threat_type: str,
        confidence_score: float,
        confidence_level: ConfidenceLevel,
        analysis: Dict[str, Any],
        key_indicators: List[str]
    ) -> AnalysisReasoning:
        """Build the LLM's reasoning chain"""
        
        reasoning_summary = (
            f"The analysis detected {threat_type.lower()} threat pattern "
            f"with {confidence_level.value} confidence ({confidence_score*100:.0f}%). "
            f"Multiple indicators support this assessment: {'; '.join(key_indicators[:3])}."
        )
        
        mitigating_factors = []
        if confidence_score < 0.75:
            mitigating_factors.append("Moderate confidence - could be legitimate activity")
        if confidence_score < 0.6:
            mitigating_factors.append("This may be a false positive - review carefully")
        
        return AnalysisReasoning(
            threat_type=threat_type,
            key_indicators=key_indicators,
            mitigating_factors=mitigating_factors if mitigating_factors else None,
            confidence_score=confidence_score,
            confidence_level=confidence_level,
            reasoning_summary=reasoning_summary
        )
    
    def _build_recommended_actions(
        self,
        severity: int,
        threat_type: str,
        container_name: str,
        service_name: str
    ) -> List[RecommendedAction]:
        """Build list of available actions operator can take"""
        actions = []
        
        # Action 1: Isolate pod (for severity >= 8)
        if severity >= 8:
            actions.append(RecommendedAction(
                action_type="isolate_pod",
                target=container_name,
                priority=1,  # Critical priority
                rationale="Immediately isolate the compromised container to prevent lateral movement",
                estimated_impact="Container will be unable to send/receive network traffic",
                reversible=True
            ))
        
        # Action 2: Scale up service (for severity >= 6)
        if severity >= 6:
            actions.append(RecommendedAction(
                action_type="scale_up",
                target=service_name,
                priority=2,  # High priority
                rationale="Increase replicas to distribute load and isolate compromised instance",
                estimated_impact=f"{service_name} will have more instances running",
                reversible=True
            ))
        
        # Action 3: Alert team (always available)
        actions.append(RecommendedAction(
            action_type="alert_team",
            target="security-team",
            priority=3 if severity < 6 else 2,
            rationale="Notify security team for manual investigation and response coordination",
            estimated_impact="Security team receives alert and begins investigation",
            reversible=False
        ))
        
        return actions
    
    def _determine_governance(
        self,
        severity: int,
        automation_mode: str,
        actions: List[RecommendedAction],
        protected_services: List[str],
        container_name: str
    ) -> AutomationGovernance:
        """Determine what happens automatically vs needs operator approval"""
        
        # Check if target is protected
        is_protected = any(
            protected.lower() in container_name.lower()
            for protected in protected_services
        )
        
        # Determine approval requirement based on mode + severity
        requires_approval = False
        approval_reason = None
        why_automated = None
        why_blocked = None
        
        if automation_mode == "manual":
            requires_approval = True
            approval_reason = "Operator has selected MANUAL mode - all actions require explicit approval"
        elif automation_mode == "assisted":
            if severity >= 8:
                requires_approval = True
                approval_reason = f"ASSISTED mode: Critical severity ({severity}/10) requires operator approval"
            else:
                why_automated = f"ASSISTED mode: Moderate severity ({severity}/10) allows automated response"
        elif automation_mode == "autopilot":
            why_automated = f"AUTOPILOT mode: All recommended actions execute automatically"
        
        # Check if action is blocked by protected service
        if is_protected:
            why_blocked = f"Target '{container_name}' is a protected service - automation blocked to prevent service disruption"
            requires_approval = True  # Always require approval for protected services
            approval_reason = why_blocked
        
        return AutomationGovernance(
            automation_mode=automation_mode,
            requires_approval=requires_approval,
            approval_reason=approval_reason,
            why_automated=why_automated,
            why_blocked=why_blocked,
            protected_service=is_protected
        )
    
    def _generate_summary(self, threat_type: str, severity: int, alert_data: Dict[str, Any]) -> str:
        """Generate plain English incident summary"""
        container = alert_data.get("output_fields", {}).get("container.name", "a system component")
        
        severity_labels = {
            (8, 10): "Critical",
            (6, 7): "High",
            (4, 5): "Medium",
            (1, 3): "Low"
        }
        
        severity_label = next(
            (label for (min_s, max_s), label in severity_labels.items() if min_s <= severity <= max_s),
            "Unknown"
        )
        
        return f"{severity_label} severity {threat_type.lower()} threat detected in {container}. Requires operator attention."
    
    def _parse_timestamp(self, timestamp_str: Optional[str]) -> datetime:
        """Parse ISO timestamp from alert"""
        if not timestamp_str:
            return datetime.now()
        try:
            return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        except:
            return datetime.now()
    
    def get_incident(self, incident_id: int) -> Optional[OperatorIncident]:
        """Get a cached incident by ID"""
        return self.incident_cache.get(incident_id)
    
    def get_dashboard(self, limit: int = 50) -> IncidentDashboard:
        """Get operator dashboard with recent incidents"""
        today = datetime.now().date().isoformat()
        today_incidents = self.incidents_by_date.get(today, [])
        
        # Get incidents, most recent first
        incidents_list = [
            self.incident_cache[iid]
            for iid in reversed(today_incidents[-limit:])
            if iid in self.incident_cache
        ]
        
        critical_count = sum(1 for i in incidents_list if i.severity >= 8)
        pending_count = sum(1 for i in incidents_list if i.automation_governance.requires_approval)
        
        return IncidentDashboard(
            total_incidents=len(today_incidents),
            critical_incidents=critical_count,
            pending_approval=pending_count,
            incidents=incidents_list[:limit]
        )
    
    def get_metrics(self) -> OperatorMetrics:
        """Get operator dashboard metrics"""
        incidents = list(self.incident_cache.values())
        
        if not incidents:
            return OperatorMetrics(
                avg_analysis_time_ms=0,
                avg_confidence_score=0.0,
                approval_rate=0.0,
                rejection_rate=0.0,
                override_rate=0.0,
                incident_volume_trend="stable"
            )
        
        avg_time = sum(i.analysis_duration_ms for i in incidents) // len(incidents)
        avg_confidence = sum(i.reasoning.confidence_score for i in incidents) / len(incidents)

        # Pull governance outcomes for real approval/rejection metrics.
        approved = 0
        rejected = 0
        auto_executed = 0
        try:
            from governance import governance
            history = governance.get_action_history(limit=1000)
            approved = sum(1 for h in history if h.get("status") == "approved")
            rejected = sum(1 for h in history if h.get("status") == "rejected")
            auto_executed = sum(1 for h in history if h.get("status") == "auto_executed")
        except Exception as e:
            logger.debug(f"Governance metrics unavailable: {e}")

        terminal_human_decisions = approved + rejected
        approval_rate = (approved / terminal_human_decisions) if terminal_human_decisions else 0.0
        rejection_rate = (rejected / terminal_human_decisions) if terminal_human_decisions else 0.0
        denominator = approved + rejected + auto_executed
        override_rate = (rejected / denominator) if denominator else 0.0

        now_ts = datetime.now().timestamp()
        current_window = sum(1 for i in incidents if (now_ts - i.timestamp.timestamp()) <= 86400)
        previous_window = sum(
            1 for i in incidents
            if 86400 < (now_ts - i.timestamp.timestamp()) <= 172800
        )
        if current_window > previous_window:
            trend = "increasing"
        elif current_window < previous_window:
            trend = "decreasing"
        else:
            trend = "stable"

        return OperatorMetrics(
            avg_analysis_time_ms=avg_time,
            avg_confidence_score=avg_confidence,
            approval_rate=approval_rate,
            rejection_rate=rejection_rate,
            override_rate=override_rate,
            incident_volume_trend=trend
        )

    def get_full_dashboard_data(self) -> Dict:
        """Get comprehensive dashboard data for operator UI."""
        dashboard = self.get_dashboard()
        metrics = self.get_metrics()
        
        # Build severity distribution
        severity_dist = {}
        for incident in self.incident_cache.values():
            sev = incident.severity
            severity_dist[sev] = severity_dist.get(sev, 0) + 1
        
        # Build threat type distribution
        threat_dist = {}
        for incident in self.incident_cache.values():
            threat = incident.reasoning.threat_type if incident.reasoning else "Unknown"
            threat_dist[threat] = threat_dist.get(threat, 0) + 1
        
        # Recent timeline
        recent_timeline = []
        for incident in list(self.incident_cache.values())[-20:]:
            recent_timeline.append({
                "id": incident.incident_id,
                "timestamp": incident.timestamp.isoformat(),
                "severity": incident.severity,
                "summary": incident.incident_summary[:100],
                "requires_approval": incident.automation_governance.requires_approval
            })
        
        return {
            "summary": {
                "total_incidents": dashboard.total_incidents,
                "critical_incidents": dashboard.critical_incidents,
                "pending_approval": dashboard.pending_approval,
                "avg_analysis_time_ms": metrics.avg_analysis_time_ms,
                "avg_confidence": round(metrics.avg_confidence_score, 2)
            },
            "severity_distribution": severity_dist,
            "threat_distribution": threat_dist,
            "recent_timeline": recent_timeline,
            "incidents": [
                {
                    "id": i.incident_id,
                    "timestamp": i.timestamp.isoformat(),
                    "severity": i.severity,
                    "summary": i.incident_summary,
                    "threat_type": i.reasoning.threat_type if i.reasoning else "Unknown",
                    "confidence": i.reasoning.confidence_score if i.reasoning else 0,
                    "requires_approval": i.automation_governance.requires_approval,
                    "llm_model": i.llm_model_used,
                    "business_impact": i.business_impact
                }
                for i in dashboard.incidents[:50]
            ]
        }

    def search_incidents(self, query: str = None, severity_min: int = None, 
                        severity_max: int = None, threat_type: str = None,
                        limit: int = 50) -> List[Dict]:
        """Search and filter incidents."""
        results = []
        
        for incident in self.incident_cache.values():
            # Apply filters
            if severity_min and incident.severity < severity_min:
                continue
            if severity_max and incident.severity > severity_max:
                continue
            if threat_type and incident.reasoning.threat_type != threat_type:
                continue
            if query:
                query_lower = query.lower()
                if query_lower not in incident.incident_summary.lower() and \
                   query_lower not in (incident.reasoning.threat_type or "").lower():
                    continue
            
            results.append({
                "id": incident.incident_id,
                "timestamp": incident.timestamp.isoformat(),
                "severity": incident.severity,
                "summary": incident.incident_summary,
                "threat_type": incident.reasoning.threat_type if incident.reasoning else "Unknown",
                "confidence": incident.reasoning.confidence_score if incident.reasoning else 0,
                "requires_approval": incident.automation_governance.requires_approval
            })
        
        # Sort by timestamp descending
        results.sort(key=lambda x: x["timestamp"], reverse=True)
        return results[:limit]


# Global instance
operator_interface = OperatorInterfaceService()
