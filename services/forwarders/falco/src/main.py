"""
Falco Integration - Real Security Event Monitoring
"""
import asyncio
import json
from kubernetes import client, config, watch
import os

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
