# IoT Device Integration SDK

> How to add **any** IoT device — hardware or software — to the Smart City IDS.

---

## 1. Architecture Overview

```
┌────────────────────┐     ┌──────────────┐     ┌──────────────────────────────┐
│  Your IoT Device   │────►│  REST / MQTT  │────►│  Smart City IDS API          │
│  (HW or Emulator)  │     │  Ingestion    │     │  /api/iot/sensor             │
└────────────────────┘     └──────────────┘     │  /api/alerts/internal        │
                                                 └──────┬───────────────────────┘
                                                        │
                                          ┌─────────────▼──────────────┐
                                          │  IDS Pipeline              │
                                          │  Dedup → LLM → Gov → K8s  │
                                          └────────────────────────────┘
```

There are **two integration paths**:

| Path | Endpoint | Purpose | When to Use |
|------|----------|---------|-------------|
| **Telemetry** | `POST /api/iot/sensor` | Send device data + anomaly events | Normal sensor data; alerts generated on threshold |
| **Alert (Cluster-Internal)** | `POST /api/alerts/internal` | Forwarder-only ingest to IDS pipeline | Falco/Suricata forwarders running *inside* the cluster |

Important:
- For a conference/public demo where **anyone can connect their own device**, the supported path is **Telemetry** (`/api/iot/sensor`).
- `/api/alerts/internal` requires the shared secret header `X-IDS-Internal-Token` and is intended for **in-cluster** forwarders (Falco/Suricata), not arbitrary external devices.

### Base URL (how to reach the IDS API)

The IDS API is exposed via Kubernetes NodePort by default:

- NodePort base URL: `http://<NODE_IP>:30800`

Optionally, scripts may also start a local port-forward:

- Port-forward base URL: `http://localhost:8000`

---

## 2. API Contract

### 2.1 Telemetry Path — `/api/iot/sensor`

```json
{
  "device_id": "building-temp-sensor-01",
  "device_type": "temperature_sensor",
  "event_type": "anomaly",
  "value": {
    "temperature_c": 85.2,
    "threshold_c": 60.0,
    "location": "server-room-b2"
  },
  "timestamp": "2026-02-13T14:30:00Z"
}
```

**Required fields:**

| Field | Type | Description |
|-------|------|-------------|
| `device_id` | string | Unique identifier (e.g., `rpi5-motion-sensor`, `water-meter-zone3`) |
| `device_type` | string | Category (e.g., `motion_sensor`, `temperature_sensor`, `water_meter`) |
| `event_type` | string | What happened: `telemetry`, `anomaly`, `heartbeat`, `rapid_motion` |
| `value` | object | Freeform payload — sensor readings, thresholds, counts |
| `timestamp` | string | ISO 8601 timestamp |

**Response** (200 OK):
```json
{
  "status": "received",
  "device_id": "building-temp-sensor-01",
  "alert_id": "a1b2c3",
  "message": "IoT event processed"
}
```

### 2.2 Alert Path — `/api/alerts/internal`

Use this when your device has already determined something is wrong:

```json
{
  "output": "Water pressure anomaly detected at zone 3 — 150 PSI (normal: 40-80)",
  "priority": "Warning",
  "rule": "Water Pressure Anomaly",
  "time": "2026-02-13T14:30:00Z",
  "output_fields": {
    "container.name": "water-system",
    "device.id": "water-meter-zone3",
    "alert.signature": "Pressure Anomaly",
    "threat.type": "Sensor Tampering"
  }
}
```

This enters the **full IDS pipeline**: Dedup → LLM Analysis → Governance → K8s Automation.

**Auth requirement:** You must include `X-IDS-Internal-Token` and the token must match the IDS API’s `IDS_INTERNAL_ALERT_TOKEN` setting.

---

## 3. Python Client Template

Copy and adapt this template for **any** IoT device:

```python
#!/usr/bin/env python3
"""
Smart City IDS — IoT Device Client Template
============================================
Copy this file and adapt for your specific sensor/device.
"""

import argparse
import requests
import time
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


class SmartCityDevice:
    """Base class for any IoT device connecting to Smart City IDS."""

    def __init__(self, ids_url, device_id, device_type,
                 threshold=5, window_sec=60, heartbeat_sec=60):
        self.ids_url = ids_url.rstrip('/')
        self.device_id = device_id
        self.device_type = device_type
        self.threshold = threshold
        self.window_sec = window_sec
        self.heartbeat_sec = heartbeat_sec
        self.event_times = []
        self.total_alerts = 0
        self.last_heartbeat = 0

    # ── Override these in your subclass ──────────────────────────
    def read_sensor(self):
        """Return a dict of current sensor readings.
        Override this method for your hardware/protocol."""
        raise NotImplementedError

    def is_anomaly(self, reading):
        """Return True if this reading should trigger an alert.
        Override this method with your detection logic."""
        return False
    # ─────────────────────────────────────────────────────────────

    def send_telemetry(self, reading, event_type="telemetry"):
        """Send a telemetry event to the IDS API."""
        payload = {
            "device_id": self.device_id,
            "device_type": self.device_type,
            "event_type": event_type,
            "value": reading,
            "timestamp": datetime.now().isoformat(),
        }
        try:
            r = requests.post(
                f"{self.ids_url}/api/iot/sensor",
                json=payload, timeout=10
            )
            if r.status_code == 200:
                logger.info(f"Telemetry sent: {event_type}")
                return r.json()
        except requests.exceptions.ConnectionError:
            logger.error(f"Cannot connect to {self.ids_url}")
        except Exception as e:
            logger.error(f"Send error: {e}")
        return None

    def send_alert(self, reading, rule_name="Device Anomaly"):
        """Send a security alert directly into the IDS pipeline."""
        self.total_alerts += 1
        payload = {
            "output": f"{rule_name}: {self.device_id} reported anomalous reading",
            "priority": "Warning",
            "rule": rule_name,
            "time": datetime.now().isoformat(),
            "output_fields": {
                "container.name": self.device_type,
                "device.id": self.device_id,
                "alert.signature": rule_name,
                "threat.type": "Sensor Anomaly"
            }
        }
        try:
            r = requests.post(
                f"{self.ids_url}/api/alerts/internal",
                json=payload, timeout=10
            )
            if r.status_code == 200:
                data = r.json()
                logger.warning(
                    f"ALERT #{self.total_alerts} sent! "
                    f"Severity: {data.get('severity', '?')}/10"
                )
                return data
        except Exception as e:
            logger.error(f"Alert error: {e}")
        return None

    def send_heartbeat(self):
        """Send periodic heartbeat to confirm device is alive."""
        self.send_telemetry(
            {"status": "alive", "uptime_alerts": self.total_alerts},
            event_type="heartbeat"
        )
        self.last_heartbeat = time.time()

    def run(self, interval_sec=1.0):
        """Main loop: read sensor → check anomaly → send data."""
        logger.info(f"Starting {self.device_type} [{self.device_id}]")
        logger.info(f"IDS API: {self.ids_url}")
        logger.info(f"Anomaly threshold: {self.threshold} events in {self.window_sec}s")

        while True:
            try:
                reading = self.read_sensor()

                if self.is_anomaly(reading):
                    now = time.time()
                    self.event_times.append(now)
                    self.event_times = [
                        t for t in self.event_times
                        if now - t < self.window_sec
                    ]
                    if len(self.event_times) >= self.threshold:
                        self.send_alert(reading)
                        self.event_times = []
                    else:
                        self.send_telemetry(reading, "anomaly")
                else:
                    self.send_telemetry(reading)

                # Periodic heartbeat
                if time.time() - self.last_heartbeat > self.heartbeat_sec:
                    self.send_heartbeat()

            except Exception as e:
                logger.error(f"Loop error: {e}")

            time.sleep(interval_sec)


# ─── EXAMPLE: Temperature Sensor ────────────────────────────────
class TemperatureSensor(SmartCityDevice):
    """Example: a temperature sensor that alerts on overheating."""

    def __init__(self, ids_url, max_temp=60.0, **kwargs):
        super().__init__(
            ids_url=ids_url,
            device_id="temp-sensor-01",
            device_type="temperature_sensor",
            **kwargs
        )
        self.max_temp = max_temp

    def read_sensor(self):
        # Replace with real hardware read (e.g., DS18B20 via w1-gpio)
        import random
        return {
            "temperature_c": round(20 + random.random() * 50, 1),
            "humidity_pct": round(30 + random.random() * 40, 1),
        }

    def is_anomaly(self, reading):
        return reading["temperature_c"] > self.max_temp


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Smart City IDS — IoT Device Client"
    )
    parser.add_argument(
        "--ids-url", required=True,
        help="IDS API URL (e.g., http://192.168.1.100:30800)"
    )
    parser.add_argument("--interval", type=float, default=5.0)
    args = parser.parse_args()

    sensor = TemperatureSensor(ids_url=args.ids_url)
    sensor.run(interval_sec=args.interval)
```

---

## 4. Kubernetes Deployment Template

To run your device as an emulator inside the K8s cluster:

```yaml
# my-device-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-iot-device
  namespace: smart-city
  labels:
    app: my-iot-device
    tier: iot-emulator
spec:
  replicas: 2
  selector:
    matchLabels:
      app: my-iot-device
  template:
    metadata:
      labels:
        app: my-iot-device
        tier: iot-emulator
    spec:
      containers:
      - name: my-iot-device
        image: python:3.11-slim
        command: ["python", "/app/app.py"]
        ports:
        - containerPort: 5000
        env:
        - name: IDS_API_URL
          value: "http://ids-api-service:8000"
        volumeMounts:
        - name: app-code
          mountPath: /app
        resources:
          requests:
            memory: "64Mi"
            cpu: "50m"
          limits:
            memory: "128Mi"
            cpu: "200m"
      volumes:
      - name: app-code
        configMap:
          name: my-iot-device-code
---
apiVersion: v1
kind: Service
metadata:
  name: my-iot-device-service
  namespace: smart-city
spec:
  selector:
    app: my-iot-device
  ports:
  - port: 80
    targetPort: 5000
```

### Deploy steps:

```bash
# 1. Create ConfigMap from your app code
kubectl create configmap my-iot-device-code \
  --from-file=app.py=smart-city-services/my-device/app.py \
  --from-file=requirements.txt=smart-city-services/my-device/requirements.txt \
  -n smart-city --dry-run=client -o yaml | kubectl apply -f -

# 2. Apply deployment
kubectl apply -f my-device-deployment.yaml

# 3. Verify
kubectl get pods -n smart-city -l app=my-iot-device
```

---

## 5. Flask Emulator Template (In-Cluster)

For software-emulated devices running inside K8s (like our 5 existing emulators):

```python
#!/usr/bin/env python3
"""Flask-based IoT device emulator template for K8s deployment."""

from flask import Flask, jsonify, request
import threading, time, random, math
from datetime import datetime

app = Flask(__name__)

# ── Device Configuration ─────────────────────────────────────
DEVICE_TYPE = "my_sensor"
PROTOCOL = "Your Protocol Name"
NUM_DEVICES = 10
TELEMETRY_INTERVAL = 5  # seconds

# ── State ─────────────────────────────────────────────────────
devices = {}
_start_time = time.time()

def init_devices():
    """Initialize simulated device fleet."""
    for i in range(NUM_DEVICES):
        devices[f"device-{i:03d}"] = {
            "id": f"device-{i:03d}",
            "status": "online",
            "last_reading": None,
            "readings_count": 0,
        }

def generate_reading(device_id):
    """Generate a simulated sensor reading. Replace with your logic."""
    t = time.time() - _start_time
    return {
        "value": round(20 + 5 * math.sin(t / 300) + random.gauss(0, 0.5), 2),
        "unit": "celsius",
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

# ── Background telemetry loop ────────────────────────────────
def telemetry_loop():
    while True:
        for did, dev in devices.items():
            dev["last_reading"] = generate_reading(did)
            dev["readings_count"] += 1
        time.sleep(TELEMETRY_INTERVAL)

# ── API Endpoints ─────────────────────────────────────────────
@app.route("/health")
def health():
    return jsonify({"status": "healthy", "device_type": DEVICE_TYPE,
                    "uptime": round(time.time() - _start_time)})

@app.route("/api/telemetry")
def telemetry():
    return jsonify({
        "device_type": DEVICE_TYPE,
        "protocol": PROTOCOL,
        "device_count": len(devices),
        "devices": devices,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    })

@app.route("/api/stats")
def stats():
    total = sum(d["readings_count"] for d in devices.values())
    online = sum(1 for d in devices.values() if d["status"] == "online")
    return jsonify({
        "total_readings": total,
        "online_devices": online,
        "total_devices": len(devices),
        "uptime": round(time.time() - _start_time),
    })

# ── Startup ───────────────────────────────────────────────────
init_devices()
threading.Thread(target=telemetry_loop, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
```

---

## 6. Register Your Device with the IDS Dashboard

After deploying, tell the IDS API about your new device by adding it to the telemetry proxy in `services/ids-api/src/main.py`:

```python
# In _IOT_SERVICES dict, add:
"my-device": {
    "url": "http://my-iot-device-service.smart-city.svc.cluster.local",
    "endpoints": {"telemetry": "/api/telemetry", "stats": "/api/stats"},
},

# In _IOT_POD_PREFIXES dict, add:
"my-iot-device": "my_sensor",
```

Then update the dashboard HTML in `services/ids-api/static/index.html` to add a service card.

---

## 7. Integration Checklist

| Step | Action | Verify |
|------|--------|--------|
| 1 | Write device code (template above) | `python app.py` runs locally |
| 2 | Create K8s ConfigMap + Deployment | `kubectl get pods -l app=my-device` |
| 3 | Expose K8s Service | `kubectl get svc my-device-service` |
| 4 | Add to `_IOT_SERVICES` in main.py | `curl /api/iot/telemetry` includes device |
| 5 | Add dashboard card in index.html | Card appears in IoT tab |
| 6 | Test alert flow | Inject alert → see in Live Alerts |
| 7 | Scale replicas | `kubectl scale deploy my-device --replicas=3` |

---

## 8. Hardware Device Integration (Raspberry Pi Example)

For physical hardware devices (not K8s emulators), see [raspberry-pi/SETUP.md](../raspberry-pi/SETUP.md).

**Network path for physical devices:**
```
Physical Device (WiFi/Ethernet)
  └─► Network Gateway / Port Proxy
       └─► K3s NodePort 30800
            └─► IDS API /api/iot/sensor
```

Physical devices use the **Telemetry Path** (`/api/iot/sensor`) and do not need K8s manifests.

---

## 9. Existing Emulators Reference

| Service | Protocol Stack | Port | Pods |
|---------|---------------|------|------|
| Traffic Camera | ONVIF Profile S / SOAP 1.2 / RTSP / ANPR | 5000 | 3 |
| Parking System | MQTT 3.1.1 / CoAP / SenML / LWM2M | 5000 | 3 |
| Healthcare API | HL7 FHIR R4 / LOINC / IEEE 11073 | 5000 | 3 |
| Env Sensor | Modbus TCP / OPC UA | 5000 | 2 |
| Street Lighting | DALI-2 (IEC 62386) / TALQ v2.4 | 5000 | 2 |

Each emulator exposes:
- `/health` — liveness probe
- `/api/telemetry` — current readings
- `/api/stats` — aggregate statistics
- Protocol-specific endpoints (e.g., `/modbus/read`, `/fhir/Patient`)

---

## 10. Scaling for Organizations

To scale this system for production use:

1. **Horizontal Pod Autoscaler**: Add HPA manifests for each IoT emulator
2. **Namespace isolation**: Deploy per-org device fleets in separate namespaces
3. **RBAC**: Scope API keys per device type / organization
4. **Helm Chart**: Package the full stack into a Helm chart for one-command deployment
5. **Device Registry**: Use the `/api/iot/devices` endpoint for fleet management

```bash
# Example: Scale any emulator
kubectl scale deployment traffic-camera -n smart-city --replicas=10
kubectl scale deployment parking-system -n smart-city --replicas=10

# Monitor fleet
curl http://localhost:30800/api/iot/devices | jq '.total_devices'
```
