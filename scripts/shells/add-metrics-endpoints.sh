#!/bin/bash

echo "📊 Adding metrics to Smart City services..."

# Create a metrics sidecar for IoT devices
cat > iot-metrics-sidecar.yaml << 'YAML'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: iot-devices
  namespace: smart-city
spec:
  replicas: 5
  selector:
    matchLabels:
      app: iot-device
  template:
    metadata:
      labels:
        app: iot-device
        prometheus-scrape: "true"
    spec:
      containers:
      - name: iot-sensor
        image: python:3.11-slim
        command: ["python", "-m", "http.server", "8080"]
        ports:
        - containerPort: 8080
        env:
        - name: MOCK_DATA
          value: "true"
      - name: metrics-exporter
        image: nginx:alpine
        ports:
        - name: metrics
          containerPort: 9113
        command: ["/bin/sh", "-c"]
        args:
          - |
            echo '# Mock metrics for demo' > /tmp/metrics;
            while true; do
              echo '# HELP iot_messages_total Total messages processed' >> /tmp/metrics;
              echo '# TYPE iot_messages_total counter' >> /tmp/metrics;
              echo "iot_messages_total{device=\"sensor-1\"} $((RANDOM % 1000))" >> /tmp/metrics;
              echo '# HELP iot_latency_seconds Message processing latency' >> /tmp/metrics;
              echo '# TYPE iot_latency_seconds gauge' >> /tmp/metrics;
              echo "iot_latency_seconds{device=\"sensor-1\"} 0.$((RANDOM % 100))" >> /tmp/metrics;
              mv /tmp/metrics /usr/share/nginx/html/metrics;
              sleep 15;
            done
YAML

kubectl apply -f iot-metrics-sidecar.yaml

echo "✅ Metrics endpoints added to IoT devices"

