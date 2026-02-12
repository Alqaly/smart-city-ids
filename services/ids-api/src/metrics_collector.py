"""
Metrics Collection for Evaluation

DEPRECATED: This module is retained for reference only. 
Prometheus-based metrics (PROM_* counters/gauges) in main.py have replaced
this class for all production metric collection. See main.py lines ~45-100
for the active Prometheus metrics definitions.

Remove in a future cleanup pass once all references are confirmed unused.
"""
from datetime import datetime
from typing import List, Dict
import json

class MetricsCollector:
    def __init__(self):
        self.alerts_received = 0
        self.alerts_processed = 0
        self.false_positives = 0
        self.response_times = []
        self.actions_executed = []
        self.start_time = datetime.now()
    
    def record_alert(self, alert_data, analysis, response_time):
        """Record metrics for each alert"""
        self.alerts_received += 1
        
        if analysis.get("severity", 0) > 3:  # Only count significant alerts
            self.alerts_processed += 1
            self.response_times.append(response_time)
        
        self.actions_executed.extend(analysis.get("automated_actions", []))
    
    def get_metrics(self) -> Dict:
        """Get current metrics"""
        runtime = (datetime.now() - self.start_time).total_seconds()
        
        return {
            "alerts_received": self.alerts_received,
            "alerts_processed": self.alerts_processed,
            "alert_reduction_ratio": 1 - (self.alerts_processed / max(self.alerts_received, 1)),
            "avg_response_time": sum(self.response_times) / len(self.response_times) if self.response_times else 0,
            "actions_executed": len(self.actions_executed),
            "runtime_seconds": runtime,
            "alerts_per_minute": (self.alerts_received / runtime) * 60 if runtime > 0 else 0
        }
    
    def save_report(self, filename="metrics_report.json"):
        """Save metrics to file"""
        with open(filename, 'w') as f:
            json.dump(self.get_metrics(), f, indent=2)
