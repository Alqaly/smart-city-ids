"""
Prometheus Metrics for Smart City IDS
"""
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response
import time

# Metrics
alerts_total = Counter('ids_alerts_total', 'Total alerts received', ['source', 'severity'])
alerts_processed = Counter('ids_alerts_processed', 'Alerts processed by AI')
ai_analysis_duration = Histogram('ids_ai_analysis_duration_seconds', 'AI analysis time')
automated_actions = Counter('ids_automated_actions_total', 'Automated actions executed', ['action_type'])
alert_severity = Gauge('ids_alert_severity', 'Current alert severity', ['alert_id'])

# Response time tracking
response_time = Histogram('ids_response_time_seconds', 'Total response time from detection to action')

class PrometheusMetrics:
    """Prometheus metrics helper"""
    
    @staticmethod
    def record_alert(source: str, severity: str):
        """Record incoming alert"""
        alerts_total.labels(source=source, severity=severity).inc()
    
    @staticmethod
    def record_processing():
        """Record alert processing"""
        alerts_processed.inc()
    
    @staticmethod
    def record_ai_time(duration: float):
        """Record AI analysis duration"""
        ai_analysis_duration.observe(duration)
    
    @staticmethod
    def record_action(action: str):
        """Record automated action"""
        automated_actions.labels(action_type=action).inc()
    
    @staticmethod
    def record_response_time(duration: float):
        """Record total response time"""
        response_time.observe(duration)
    
    @staticmethod
    def get_metrics() -> Response:
        """Get Prometheus metrics"""
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
