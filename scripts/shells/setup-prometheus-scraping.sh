#!/bin/bash

echo "🎯 Setting up Prometheus scraping..."

# Create ServiceMonitor for smart-city namespace
cat > servicemonitor-smartcity.yaml << 'YAML'
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: smart-city-services
  namespace: monitoring
  labels:
    app: smart-city-monitor
spec:
  selector:
    matchLabels:
      prometheus-scrape: "true"
  namespaceSelector:
    matchNames:
    - smart-city
  endpoints:
  - port: metrics
    interval: 30s
    path: /metrics
YAML

kubectl apply -f servicemonitor-smartcity.yaml

# Add metrics endpoints to your services
echo "Adding metrics labels to existing services..."

# Label services for Prometheus discovery
kubectl label services -n smart-city --all prometheus-scrape=true --overwrite
kubectl label pods -n smart-city --all prometheus-scrape=true --overwrite

echo "✅ Prometheus scraping configured"

