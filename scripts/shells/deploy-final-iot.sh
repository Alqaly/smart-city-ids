#!/bin/bash

echo "🚀 FINAL IOT DEPLOYMENT WITH WORKING MQTT"

# MQTT broker is already running - verify
echo "✅ MQTT Broker Status:"
kubectl get pods -n smart-city -l app=mqtt-broker

# Create the IoT deployment that uses the working broker
cat > /tmp/iot-final-deployment.yaml << 'EOD'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: iot-devices-real
  namespace: smart-city
spec:
  replicas: 15
  selector:
    matchLabels:
      app: iot-device-real
  template:
    metadata:
      labels:
        app: iot-device-real
        prometheus-scrape: "true"
    spec:
      containers:
      - name: iot-sensor
        image: python:3.11-slim
        command: ["/bin/sh"]
        args:
        - -c
        - |
          pip install paho-mqtt flask requests prometheus-client &&
          cd /app &&
          cat > mqtt_simple.py << 'EOF'
import paho.mqtt.client as mqtt
import flask
import threading
import time
import json
import random
import os
from prometheus_client import Counter, Gauge, generate_latest, REGISTRY

app = flask.Flask(__name__)
messages_sent = Counter('iot_messages_sent', 'Messages sent')
device_status = Gauge('iot_device_status', 'Device status')
temperature_gauge = Gauge('iot_temperature', 'Temperature')
battery_gauge = Gauge('iot_battery', 'Battery level')

class SimpleIoTDevice:
    def __init__(self):
        self.device_id = os.getenv('HOSTNAME', 'unknown')
        self.connected = False
        self.temperature = random.uniform(20.0, 30.0)
        self.battery = random.uniform(0.3, 1.0)
        
    def connect_mqtt(self):
        client = mqtt.Client(self.device_id)
        broker = os.getenv('MQTT_BROKER', 'mqtt-broker')
        
        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                print(f"✅ {self.device_id} connected to MQTT")
                self.connected = True
                device_status.set(1)
            else:
                print(f"❌ Connection failed: {rc}")
                self.connected = False
                device_status.set(0)
                
        def on_disconnect(client, userdata, rc):
            print(f"⚠️ {self.device_id} disconnected")
            self.connected = False
            device_status.set(0)
            
        client.on_connect = on_connect
        client.on_disconnect = on_disconnect
        
        try:
            client.connect(broker, 1883, 60)
            client.loop_start()
            return client
        except Exception as e:
            print(f"❌ Connection error: {e}")
            return None

    def send_telemetry(self, client):
        while True:
            if self.connected:
                # Update sensor values
                self.temperature += random.uniform(-0.5, 0.5)
                self.temperature = max(15.0, min(35.0, self.temperature))
                self.battery -= 0.001
                
                # Update metrics
                temperature_gauge.set(self.temperature)
                battery_gauge.set(self.battery)
                
                # Create telemetry data
                telemetry = {
                    "device_id": self.device_id,
                    "timestamp": time.time(),
                    "temperature": round(self.temperature, 2),
                    "battery_level": round(self.battery, 3),
                    "location": {
                        "lat": round(random.uniform(40.7, 40.8), 4),
                        "lon": round(random.uniform(-74.0, -73.9), 4)
                    }
                }
                
                # Send with random packet loss simulation
                if random.random() > 0.1:  # 90% success rate
                    client.publish("iot/telemetry", json.dumps(telemetry))
                    messages_sent.inc()
                    print(f"📤 {self.device_id} sent telemetry")
                
                # Random failure simulation
                if random.random() < 0.02:  # 2% chance of failure
                    print(f"🔴 {self.device_id} simulating failure")
                    device_status.set(0)
                    time.sleep(random.randint(10, 30))
                    device_status.set(1)
                    print(f"🟢 {self.device_id} recovered")
            
            time.sleep(random.uniform(5, 10))  # 5-10 second intervals

@app.route('/')
def home():
    return {"status": "IoT Device Running", "mqtt_connected": device._connected}

@app.route('/status')
def status():
    return {
        "device_id": device.device_id,
        "connected": device.connected,
        "temperature": round(device.temperature, 2),
        "battery_level": round(device.battery, 3),
        "messages_sent": int(messages_sent._value.get())
    }

@app.route('/metrics')
def metrics():
    return generate_latest(REGISTRY), 200, {'Content-Type': 'text/plain'}

@app.route('/publish', methods=['POST'])
def publish_custom():
    if device.connected:
        import flask
        data = flask.request.json
        data['device_id'] = device.device_id
        data['timestamp'] = time.time()
        device._client.publish("iot/custom", json.dumps(data))
        return {"status": "published", "topic": "iot/custom"}
    return {"status": "not connected"}, 400

# Global device instance
device = SimpleIoTDevice()

def start_background_tasks():
    client = device.connect_mqtt()
    if client:
        device._client = client
        threading.Thread(target=lambda: device.send_telemetry(client), daemon=True).start()

if __name__ == '__main__':
    start_background_tasks()
    print(f"🚀 Starting IoT Device: {device.device_id}")
    app.run(host='0.0.0.0', port=5000, debug=False)
