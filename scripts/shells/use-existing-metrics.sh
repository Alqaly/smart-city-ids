#!/bin/bash

echo "🔄 Using existing Kubernetes metrics..."

# Check what metrics are already available
kubectl port-forward -n monitoring svc/prometheus 9090:9090 > /dev/null 2>&1 &
PROM_PID=$!

sleep 3

echo "📈 Available Kubernetes metrics:"
curl -s "http://localhost:9090/api/v1/label/__name__/values" | jq -r '.data[]' | grep -E "^(kube_|container_|node_)" | head -20

echo -e "\n🎯 Creating dashboard with existing metrics..."

# Create a dashboard using available metrics
cat > existing-metrics-dashboard.json << 'DASHBOARD'
{
  "dashboard": {
    "title": "Smart City - Kubernetes Metrics",
    "tags": ["kubernetes", "smart-city", "demo"],
    "panels": [
      {
        "id": 1,
        "title": "🏗️ Smart City Pods",
        "type": "stat",
        "targets": [{
          "expr": "count(kube_pod_info{namespace='smart-city'})",
          "legendFormat": "Total Pods"
        }],
        "gridPos": {"h": 8, "w": 8, "x": 0, "y": 0}
      },
      {
        "id": 2,
        "title": "📦 Pods by Application",
        "type": "barchart",
        "targets": [{
          "expr": "count by (app) (kube_pod_info{namespace='smart-city'})",
          "legendFormat": "{{app}}"
        }],
        "gridPos": {"h": 10, "w": 16, "x": 8, "y": 0}
      },
      {
        "id": 3,
        "title": "💾 Memory Usage (MB)",
        "type": "gauge",
        "targets": [{
          "expr": "sum(container_memory_usage_bytes{namespace='smart-city'}) / 1024 / 1024",
          "legendFormat": "Memory"
        }],
        "gridPos": {"h": 8, "w": 8, "x": 0, "y": 8}
      },
      {
        "id": 4,
        "title": "⚡ CPU Usage",
        "type": "stat",
        "targets": [{
          "expr": "sum(rate(container_cpu_usage_seconds_total{namespace='smart-city'}[5m]))",
          "legendFormat": "CPU Cores"
        }],
        "gridPos": {"h": 8, "w": 8, "x": 8, "y": 8}
      }
    ],
    "time": {"from": "now-1h", "to": "now"}
  },
  "folderId": 0,
  "overwrite": true
}
DASHBOARD

# Import to Grafana
curl -X POST \
  -H "Content-Type: application/json" \
  -d @existing-metrics-dashboard.json \
  "http://192.168.18.63:30030/api/dashboards/db" -u "admin:admin123"

kill $PROM_PID 2>/dev/null

echo "✅ Dashboard created with existing Kubernetes metrics!"

