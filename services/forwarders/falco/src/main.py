"""
Falco Integration - Real Security Event Monitoring
"""
import asyncio
import json
import re
import logging
from kubernetes import client, config, watch
import os

logger = logging.getLogger(__name__)

# ============================================
# FALSE POSITIVE FILTERS
# Filter known benign alerts to reduce noise
# ============================================
FALSE_POSITIVE_FILTERS = [
    {
        "rule": "Read sensitive file untrusted",
        "container_patterns": ["postgres", "ars0n-framework.*db"],
        "proc_names": ["pg_isready", "psql", "postgres", "pg_dump", "pg_restore"],
        "file_patterns": ["/etc/shadow", "/etc/passwd", "/etc/group"]
    },
    {
        "rule": "Sensitive file opened for reading by non-trusted program",
        "container_patterns": ["postgres"],
        "proc_names": ["pg_isready", "psql", "postgres"],
        "file_patterns": ["/etc/shadow", "/etc/passwd"]
    },
    {
        "rule": "Clear Log Activities",
        "container_patterns": ["postgres"],
        "proc_names": ["postgres"]
    },
    {
        "rule": "Contact K8S API Server From Container",
        "container_patterns": ["forwarder", "falco.*", "metacollector", "ids-api.*"],
    },
    {
        "rule": "Unexpected K8s NodePort Connection",
        "container_patterns": ["forwarder", "falco.*"],
    },
]

# Track filtered alerts for metrics
FILTERED_COUNT = 0


def should_forward_alert(alert: dict) -> bool:
    """
    Check if alert should be forwarded or filtered as false positive.
    
    Args:
        alert: Falco alert dict
        
    Returns:
        True if alert should be forwarded, False if it's a false positive
    """
    global FILTERED_COUNT
    
    rule = alert.get("rule", "")
    output_fields = alert.get("output_fields", {})
    container = output_fields.get("container.name", "")
    proc_name = output_fields.get("proc.name", "")
    fd_name = output_fields.get("fd.name", "")
    
    for fp_filter in FALSE_POSITIVE_FILTERS:
        # Check rule match
        if fp_filter.get("rule") != rule:
            continue
            
        # Check container pattern (if specified)
        if "container_patterns" in fp_filter:
            container_match = any(
                re.match(pattern, container, re.IGNORECASE)
                for pattern in fp_filter["container_patterns"]
            )
            if not container_match:
                continue
        
        # Check process name (if specified)
        if "proc_names" in fp_filter:
            if proc_name not in fp_filter["proc_names"]:
                continue
        
        # Check file pattern (if specified)
        if "file_patterns" in fp_filter:
            file_match = any(
                pattern in fd_name
                for pattern in fp_filter["file_patterns"]
            )
            if not file_match:
                continue
        
        # All conditions matched - this is a false positive
        FILTERED_COUNT += 1
        logger.info(
            f"🔇 FILTERED FALSE POSITIVE: rule='{rule}' "
            f"container='{container}' proc='{proc_name}' file='{fd_name}' "
            f"(total_filtered={FILTERED_COUNT})"
        )
        return False
    
    return True


class FalcoMonitor:
    def __init__(self, ids_callback):
        """
        ids_callback: function to call when alert received
        """
        config.load_kube_config(os.getenv("KUBECONFIG", os.path.expanduser("~/.kube/config")))
        self.v1 = client.CoreV1Api()
        self.namespace = "falco-system"
        self.callback = ids_callback
    
    async def start_monitoring(self):
        """Stream Falco alerts in real-time"""
        print("🔍 Starting Falco monitoring...")
        
        # Get Falco pod name
        pods = self.v1.list_namespaced_pod(
            namespace=self.namespace,
            label_selector="app.kubernetes.io/name=falco"
        )
        
        if not pods.items:
            print("❌ No Falco pods found")
            return
        
        falco_pod = pods.items[0].metadata.name
        print(f"📡 Monitoring Falco pod: {falco_pod}")
        
        # Stream logs from the 'falco' container specifically
        w = watch.Watch()
        try:
            for line in w.stream(
                self.v1.read_namespaced_pod_log,
                name=falco_pod,
                namespace=self.namespace,
                container="falco",  # ← Specify the falco container
                follow=True,
                _preload_content=False
            ):
                try:
                    # Falco outputs JSON alerts
                    if line.strip().startswith('{'):
                        alert = json.loads(line)
                        
                        # Only process actual alerts (not startup messages)
                        if 'rule' in alert and 'output' in alert:
                            # Check if this is a false positive
                            if not should_forward_alert(alert):
                                continue  # Skip false positives
                            
                            # Convert to our format
                            formatted_alert = {
                                "type": alert.get("rule", "Unknown"),
                                "source": alert.get("output_fields", {}).get("container.name", "Unknown"),
                                "timestamp": alert.get("time"),
                                "details": {
                                    "priority": alert.get("priority"),
                                    "output": alert.get("output"),
                                    "fields": alert.get("output_fields", {})
                                },
                                "severity": self._map_priority(alert.get("priority"))
                            }
                            
                            print(f"🚨 REAL ALERT: {formatted_alert['type']}")
                            
                            # Send to IDS for LLM analysis
                            await self.callback(formatted_alert)
                            
                except json.JSONDecodeError:
                    # Skip non-JSON lines (startup messages, etc.)
                    continue
                except Exception as e:
                    print(f"Error parsing Falco alert: {e}")
                    
        except Exception as e:
            print(f"❌ Falco monitoring error: {e}")
    
    def _map_priority(self, priority):
        """Map Falco priority to 1-10 scale"""
        mapping = {
            "Emergency": 10,
            "Alert": 9,
            "Critical": 8,
            "Error": 6,
            "Warning": 4,
            "Notice": 2,
            "Informational": 1,
            "Debug": 1
        }
        return mapping.get(priority, 5)
