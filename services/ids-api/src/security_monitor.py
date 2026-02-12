"""
Security Monitor - Collects alerts from Falco and Suricata

DEPRECATED: This module is retained for reference only.
Alert collection is now handled directly in main.py through the /api/alerts
and /api/alerts/internal endpoints, with Prometheus counters for tracking.
The Falco forwarder (services/forwarders/falco/) and alert_rate_limiter.py
have replaced this module's functionality.

Remove in a future cleanup pass once all references are confirmed unused.
"""
import logging
from typing import Dict, Any, List
import asyncio

logger = logging.getLogger(__name__)

class SecurityMonitor:
    """Monitor security events from multiple sources"""
    
    def __init__(self):
        self.falco_alerts: List[Dict] = []
        self.suricata_alerts: List[Dict] = []
        logger.info("Security monitor initialized")
    
    def record_falco_alert(self, alert: Dict[str, Any]):
        """Record Falco alert"""
        self.falco_alerts.append(alert)
        logger.debug(f"Recorded Falco alert: {alert.get('rule')}")
    
    def record_suricata_alert(self, alert: Dict[str, Any]):
        """Record Suricata alert"""
        self.suricata_alerts.append(alert)
        logger.debug(f"Recorded Suricata alert: {alert.get('signature')}")
    
    def get_stats(self) -> Dict[str, int]:
        """Get monitoring statistics"""
        return {
            "falco_alerts": len(self.falco_alerts),
            "suricata_alerts": len(self.suricata_alerts),
            "total_alerts": len(self.falco_alerts) + len(self.suricata_alerts)
        }
