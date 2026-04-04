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

There are **three integration paths**:

| Path | Endpoint | When to Use |
|------|----------|-------------|
| **Telemetry** | `POST /api/iot/sensor` | External devices sending sensor data; alerts generated when thresholds are exceeded |
| **Registry + Heartbeat** | `POST /api/iot/devices/register` + `POST /api/iot/devices/heartbeat` | Fleet onboarding, 100+ logical devices, physical hardware (Raspberry Pi) |
| **Alert (Cluster-Internal)** | `POST /api/alerts/internal` | Falco/Suricata forwarders running *inside* the K3s cluster |

**Which path should I use?**

- **Physical hardware** (Raspberry Pi, Arduino): use **Telemetry** path.  Optionally register via **Registry + Heartbeat** first for fleet visibility.
- **Software emulators** running inside K8s: use **Telemetry** for normal data, **Alert** for direct IDS pipeline injection.
- **Forwarders** (Falco/Suricata): use **Alert** path with `X-IDS-Internal-Token` header.

### Base URL

| Access Method | URL |
|---------------|-----|
| K8s NodePort (default) | `http://<NODE_IP>:30800` |
| Port-forward (dev) | `http://localhost:8000` |

---

## 2. API Contract

### 2.1 Device Registry — `/api/iot/devices/register`

Register a logical device so it appears in the dashboard independently of pod count:

```json
POST /api/iot/devices/register

{
  "device_id": "rpi5-motion-sensor-01",
  "device_type": "motion_sensor",
  "schema_version": "1.0",
  "metadata": {
    "location": "building-entrance-b2",
    "vendor": "Raspberry Pi Foundation",
    "firmware": "v1.0.0"
  },
  "capability_profile": {
    "protocols": ["rest"],
    "sensors": ["pir_motion"],
    "expected_ranges": {
      "motion_events_per_min": {"min": 0, "max": 30}
    }
  }
}
```

**Heartbeat** — send periodically (every 60 s) to confirm the device is alive:

```json
POST /api/iot/devices/heartbeat

{
  "device_id": "rpi5-motion-sensor-01",
  "status": "online",
  "timestamp": "2026-03-15T14:00:00Z",
  "metadata": {
    "ip": "192.168.1.44",
    "battery_pct": 92
  }
}
```

Dashboard states: `registered` → `online` (recent heartbeat) → `stale` (no heartbeat for >5 min).

### 2.2 Telemetry — `/api/iot/sensor`

Send sensor readings.  Anomalous events enter the IDS alert pipeline automatically.

```json
POST /api/iot/sensor

{
  "device_id": "rpi5-motion-sensor-01",
  "device_type": "motion_sensor",
  "event_type": "anomaly",
  "value": {
    "motion_events": 15,
    "threshold": 5,
    "window_seconds": 60,
    "location": "building-entrance-b2"
  },
  "timestamp": "2026-03-15T14:30:00Z"
}
```

**Required fields:**

| Field | Type | Description |
|-------|------|-------------|
| `device_id` | string | Unique identifier (e.g., `rpi5-motion-sensor-01`) |
| `device_type` | string | Category (e.g., `motion_sensor`, `temperature_sensor`) |
| `event_type` | string | One of: `telemetry`, `anomaly`, `heartbeat` |
| `value` | object | Freeform payload — sensor readings, thresholds |
| `timestamp` | string | ISO 8601 |

**Response** (200 OK):
```json
{
  "status": "received",
  "device_id": "rpi5-motion-sensor-01",
  "alert_id": "a1b2c3",
  "message": "IoT event processed"
}
```

### 2.3 Alert (Cluster-Internal) — `/api/alerts/internal`

For forwarders and devices that have already classified a threat:

```json
POST /api/alerts/internal
X-IDS-Internal-Token: <IDS_INTERNAL_ALERT_TOKEN>

{
  "output": "Rapid motion detected at entrance B2 — 15 events in 60s (threshold: 5)",
  "priority": "Warning",
  "rule": "Rapid Motion Alert",
  "time": "2026-03-15T14:30:00Z",
  "output_fields": {
    "container.name": "motion-sensor",
    "device.id": "rpi5-motion-sensor-01",
    "alert.signature": "Rapid Motion",
    "threat.type": "Physical Intrusion"
  }
}
```

This enters the **full IDS pipeline**: Dedup → LLM Analysis → Governance → K8s Automation.

> **Auth:** The `X-IDS-Internal-Token` header must match the `IDS_INTERNAL_ALERT_TOKEN` environment variable on the IDS API.

---

## 3. Python Client Template

Copy and adapt this for any IoT device.  The same base class is used by the Raspberry Pi integration (`raspberry-pi/device_template.py`).

```python
#!/usr/bin/env python3
"""Smart City IDS — IoT Device Client Template."""

import argparse
import requests
import time
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
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

    # ── Override in your subclass ────────────────────────────────
    def read_sensor(self):
        """Return a dict of current sensor readings."""
        raise NotImplementedError

    def is_anomaly(self, reading):
        """Return True if this reading should trigger an alert."""
        return False
    # ─────────────────────────────────────────────────────────────

    def register_device(self):
        """Register this device with the IDS dashboard."""
        payload = {
            "device_id": self.device_id,
            "device_type": self.device_type,
            "schema_version": "1.0",
            "metadata": {},
            "capability_profile": {
                "protocols": ["rest"],
                "sensors": [self.device_type],
            },
        }
        try:
            r = requests.post(f"{self.ids_url}/api/iot/devices/register",
                              json=payload, timeout=10)
            if r.status_code == 200:
                logger.info("Device registered with IDS")
                return r.json()
        except Exception as e:
            logger.error(f"Register error: {e}")
        return None

    def send_telemetry(self, reading, event_type="telemetry"):
        """Send sensor data to POST /api/iot/sensor."""
        payload = {
            "device_id": self.device_id,
            "device_type": self.device_type,
            "event_type": event_type,
            "value": reading,
            "timestamp": datetime.now().isoformat(),
        }
        try:
            r = requests.post(f"{self.ids_url}/api/iot/sensor",
                              json=payload, timeout=10)
            if r.status_code == 200:
                logger.info(f"Telemetry sent: {event_type}")
                return r.json()
        except requests.exceptions.ConnectionError:
            logger.error(f"Cannot connect to {self.ids_url}")
        except Exception as e:
            logger.error(f"Send error: {e}")
        return None

    def send_alert(self, reading, rule_name="Device Anomaly"):
        """Send a security alert to POST /api/alerts/internal."""
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
                "threat.type": "Sensor Anomaly",
            },
        }
        try:
            r = requests.post(f"{self.ids_url}/api/alerts/internal",
                              json=payload, timeout=10)
            if r.status_code == 200:
                data = r.json()
                logger.warning(f"ALERT #{self.total_alerts} sent! "
                               f"Severity: {data.get('severity', '?')}/10")
                return data
        except Exception as e:
            logger.error(f"Alert error: {e}")
        return None

    def send_heartbeat(self):
        """Send heartbeat to confirm device is alive."""
        try:
            requests.post(f"{self.ids_url}/api/iot/devices/heartbeat",
                          json={"device_id": self.device_id, "status": "online",
                                "metadata": {"uptime_alerts": self.total_alerts}},
                          timeout=5)
        except Exception:
            pass
        self.send_telemetry({"status": "alive", "uptime_alerts": self.total_alerts},
                            event_type="heartbeat")
        self.last_heartbeat = time.time()

    def run(self, interval_sec=1.0):
        """Main loop: read sensor → check anomaly → send to IDS."""
        logger.info(f"Starting {self.device_type} [{self.device_id}]")
        logger.info(f"IDS API: {self.ids_url}")

        while True:
            try:
                reading = self.read_sensor()

                if self.is_anomaly(reading):
                    now = time.time()
                    self.event_times = [t for t in self.event_times
                                        if now - t < self.window_sec]
                    self.event_times.append(now)
                    if len(self.event_times) >= self.threshold:
                        self.send_alert(reading)
                        self.event_times = []
                    else:
                        self.send_telemetry(reading, "anomaly")
                else:
                    self.send_telemetry(reading)

                if time.time() - self.last_heartbeat > self.heartbeat_sec:
                    self.send_heartbeat()
            except Exception as e:
                logger.error(f"Loop error: {e}")

            time.sleep(interval_sec)


# ─── Example: Temperature Sensor ────────────────────────────────
class TemperatureSensor(SmartCityDevice):
    def __init__(self, ids_url, max_temp=60.0, **kwargs):
        super().__init__(ids_url=ids_url, device_id="temp-sensor-01",
                         device_type="temperature_sensor", **kwargs)
        self.max_temp = max_temp

    def read_sensor(self):
        import random
        return {"temperature_c": round(20 + random.random() * 50, 1),
                "humidity_pct": round(30 + random.random() * 40, 1)}

    def is_anomaly(self, reading):
        return reading["temperature_c"] > self.max_temp


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Smart City IDS — IoT Device Client")
    parser.add_argument("--ids-url", required=True, help="e.g. http://10.200.0.1:30800")
    parser.add_argument("--interval", type=float, default=5.0)
    args = parser.parse_args()

    sensor = TemperatureSensor(ids_url=args.ids_url)
    sensor.register_device()
    sensor.run(interval_sec=args.interval)
```

---

## 4. Hardware Integration — Raspberry Pi

Physical devices connect over WiFi/Ethernet to the K3s NodePort.  No Kubernetes manifests needed.

```
Raspberry Pi 5 (WiFi/Ethernet)
  └─► Network Gateway / Port Proxy
       └─► K3s NodePort 30800
            └─► IDS API /api/iot/sensor
```

### Ready-to-use files

| File | Purpose |
|------|---------|
| `raspberry-pi/motion_sensor.py` | PIR motion sensor using `gpiozero.MotionSensor` — counts events in a sliding window, sends alerts when threshold is exceeded |
| `raspberry-pi/device_template.py` | Generic `SmartCityDevice` base class — subclass for any sensor type |
| `raspberry-pi/SETUP.md` | Full wiring guide (AM312/HC-SR501 PIR), GPIO pin map, network setup, systemd service, port-forwarding through Windows/VM |

### Quick start (on Raspberry Pi)

```bash
# Install dependencies
pip install requests gpiozero RPi.GPIO

# Run with real PIR sensor on GPIO 17
python motion_sensor.py --ids-url http://<NODE_IP>:30800 --gpio-pin 17

# Or run the generic template with simulated data (no hardware needed)
python device_template.py --ids-url http://<NODE_IP>:30800
```

The motion sensor sends events to `POST /api/iot/sensor` with `event_type: "rapid_motion"`.  When the event count exceeds the threshold (default: 5 events in 60 s), an alert is sent to the IDS pipeline.

See [raspberry-pi/SETUP.md](../raspberry-pi/SETUP.md) for the full wiring diagram and network configuration.

---

## 5. Kubernetes Deployment (Software Emulators)

For emulated devices running inside the K3s cluster:

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
        - name: DEVICE_COUNT
          value: "50"
        volumeMounts:
        - name: app-code
          mountPath: /app
        resources:
          requests: { memory: "64Mi", cpu: "50m" }
          limits: { memory: "128Mi", cpu: "200m" }
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

### Deploy

```bash
kubectl create configmap my-iot-device-code \
  --from-file=app.py=smart-city-services/my-device/app.py \
  -n smart-city --dry-run=client -o yaml | kubectl apply -f -

kubectl apply -f my-device-deployment.yaml
kubectl get pods -n smart-city -l app=my-iot-device
```

---

## 6. Register with the Dashboard

After deploying a new emulator, register it in **`services/ids-api/src/api/iot.py`**:

```python
# In _IOT_SERVICES dict, add:
"my-device": {
    "label": "My Device",
    "protocol": "Your Protocol",
    "url": "http://my-iot-device-service.smart-city.svc.cluster.local",
    "endpoints": {
        "health": "/health",
        "telemetry": "/api/telemetry",
        "stats": "/api/stats",
    },
},

# In _IOT_POD_PREFIXES list, add:
("my-iot-device", "My Device Type"),
```

Then add a service card in `services/ids-api/static/index.html` (IoT Mesh tab).

---

## 7. Existing Emulators

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

## 8. Integration Checklist

| # | Action | Verify |
|---|--------|--------|
| 1 | Write device code (Section 3 template or `raspberry-pi/device_template.py`) | `python app.py --ids-url http://...` runs |
| 2 | Register device | `curl /api/iot/devices` shows your device |
| 3 | Send telemetry | `curl /api/iot/sensor` with test payload returns 200 |
| 4 | For K8s emulators: deploy pod + service | `kubectl get pods -l app=my-device` |
| 5 | Add to `_IOT_SERVICES` in `api/iot.py` | `curl /api/iot/telemetry` includes device |
| 6 | Add dashboard card in `index.html` | Card appears in IoT Mesh tab |
| 7 | Test alert flow | Inject anomaly → see in Alerts tab with LLM analysis |

---

## 9. Scaling

```bash
# Scale logical devices per pod (no extra pods needed)
kubectl set env deployment/street-lighting -n smart-city DEVICE_COUNT=300
kubectl set env deployment/env-sensor -n smart-city ENV_SENSOR_STATION_COUNT=20

# Scale pods horizontally
kubectl scale deployment traffic-camera -n smart-city --replicas=10

# Check fleet counts (hybrid logical + pod-backed)
curl http://localhost:30800/api/iot/devices | jq '{total, logical_total, pod_backed_total}'
```

For production:
1. Use Registry + Heartbeat for defensible fleet counts
2. Add HPA manifests for auto-scaling
3. Scope API tokens per device type / organization
4. Package the full stack into a Helm chart for one-command deployment
