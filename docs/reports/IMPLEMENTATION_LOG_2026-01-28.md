# Implementation Log - January 28, 2026

## Smart City IDS - Capstone II Project
### Session Focus: Production Hardening, Dual IDS Integration, Grafana Dashboard, Raspberry Pi Preparation, and Persistent Storage

---

## Executive Summary

This session completed critical production-readiness features for the Smart City IDS:
1. **Grafana IEEE Dashboard** - Created unified dashboard for IEEE paper with all metrics
2. **Suricata Network IDS Integration** - Added network-level intrusion detection alongside Falco runtime security
3. **IoT Services Deployment** - Deployed and fixed smart city services (traffic-camera, healthcare-api, parking-system)
4. **IoT Metrics Fixes** - Corrected Prometheus metric label mismatches
5. **PostgreSQL Persistence** - Implemented database storage for alerts and IoT data (survives restarts)
6. **Raspberry Pi IoT Integration** - Prepared `/api/iot/sensor` endpoint for motion sensor data

---

## 1. Grafana Dashboard Configuration

### Problem
- Multiple dashboards existed causing confusion (3 separate dashboards)
- No unified view for IEEE paper presentation
- IoT metrics panels were empty

### Solution
Created a unified IEEE dashboard combining all metrics into one comprehensive view.

### Files Created

#### `infrastructure/monitoring/grafana-dashboard-ieee.json`
**Purpose:** Unified dashboard for IEEE paper presentation

**Dashboard Sections:**
1. **System Overview** - Total alerts, uptime, active devices, API health
2. **LLM Engine Performance** - Analysis latency, success rate, token usage, circuit breaker status
3. **Security Analysis** - Alerts by source (Falco/Suricata), severity distribution, threat types
4. **Kubernetes Automation** - Pod isolations, service scaling, blocked actions
5. **IoT Telemetry** - Active devices, heartbeats, events by type, security events

**Key Panels:**
| Panel | Metric | Description |
|-------|--------|-------------|
| Total Alerts | `smartcity_ids_alerts_received_total` | Cumulative alert count |
| Active IoT Devices | `smartcity_ids_iot_devices_active` | Currently registered devices |
| LLM Analysis Time | `smartcity_ids_llm_analysis_seconds` | Histogram of analysis latency |
| Circuit Breaker | `smartcity_ids_circuit_breaker_state` | LLM engine health (0=closed, 1=open) |
| Alerts by Source | `sum by (source) (smartcity_ids_alerts_received_total)` | Falco vs Suricata breakdown |
| IoT Heartbeats | `smartcity_ids_iot_heartbeats_total` | Device health monitoring |

### Dashboard Access
- **URL:** `http://localhost:30300/d/smartcity-ids-ieee/`
- **Credentials:** admin / admin

### Dashboard Cleanup
Deleted duplicate dashboards to avoid confusion:
- Removed: `grafana-dashboard-ops.json`
- Removed: `grafana-dashboard-prod.json`
- Kept: `grafana-dashboard-ieee.json` (unified)

---

## 2. Raspberry Pi Motion Sensor Integration

### Preparation
The IDS API is ready to receive data from Raspberry Pi motion sensors via the `/api/iot/sensor` endpoint.

### API Endpoint for Raspberry Pi

#### `POST /api/iot/sensor`
**Purpose:** Receive sensor data from Raspberry Pi IoT devices

**Request Format:**
```json
{
    "device_id": "motion-sensor-rpi-01",
    "device_type": "motion_sensor",
    "event_type": "motion_detected",
    "value": {
        "confidence": 0.95,
        "zone": "entrance",
        "duration_ms": 1500
    },
    "timestamp": "2026-01-28T19:30:00Z",
    "metadata": {
        "location": "Building A - Main Entrance",
        "firmware_version": "1.2.3"
    }
}
```

**Event Types Supported:**
| Event Type | Description | Security Alert? |
|------------|-------------|-----------------|
| `heartbeat` | Device health check | No |
| `motion_detected` | Normal motion detected | No |
| `anomaly` | Unusual activity | ✅ Yes |
| `intrusion` | Unauthorized entry | ✅ Yes (Critical) |
| `tampering` | Device tampered with | ✅ Yes |
| `rapid_motion` | High-frequency motion | ✅ Yes |

**Response Format:**
```json
{
    "status": "received",
    "event_id": 42,
    "device_registered": true
}
```

**Security Event Response (when event_type is anomaly/intrusion):**
```json
{
    "status": "security_event_processed",
    "event_id": 42,
    "alert_id": 15,
    "analysis": {
        "severity": 8,
        "threat_type": "Unauthorized Access",
        "summary": "Intrusion detected by motion sensor",
        "recommendations": ["Dispatch security", "Review camera footage"]
    }
}
```

### Raspberry Pi Client Code

#### `raspberry-pi/motion_sensor.py` (Reference)
```python
#!/usr/bin/env python3
"""
Raspberry Pi Motion Sensor Client for Smart City IDS
Sends motion events to the IDS API
"""

import requests
import time
from datetime import datetime
import RPi.GPIO as GPIO

# Configuration
IDS_API_URL = "http://<K3S_NODE_IP>:30800/api/iot/sensor"
DEVICE_ID = "motion-sensor-rpi-01"
DEVICE_TYPE = "motion_sensor"
PIR_PIN = 17  # GPIO pin for PIR sensor

# Setup GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(PIR_PIN, GPIO.IN)

def send_event(event_type, value=None):
    """Send event to IDS API"""
    payload = {
        "device_id": DEVICE_ID,
        "device_type": DEVICE_TYPE,
        "event_type": event_type,
        "value": value or {},
        "timestamp": datetime.now().isoformat(),
        "metadata": {
            "location": "Building A - Main Entrance",
            "firmware_version": "1.0.0"
        }
    }
    try:
        response = requests.post(IDS_API_URL, json=payload, timeout=5)
        print(f"Event sent: {event_type} -> {response.status_code}")
        return response.json()
    except Exception as e:
        print(f"Error sending event: {e}")
        return None

def main():
    print(f"Starting motion sensor: {DEVICE_ID}")
    
    # Send initial heartbeat
    send_event("heartbeat")
    
    last_heartbeat = time.time()
    motion_count = 0
    
    while True:
        # Check for motion
        if GPIO.input(PIR_PIN):
            motion_count += 1
            print(f"Motion detected! Count: {motion_count}")
            
            # Detect rapid motion (potential intrusion)
            if motion_count > 10:
                send_event("rapid_motion", {"count": motion_count})
                motion_count = 0
            else:
                send_event("motion_detected", {"confidence": 0.9})
            
            time.sleep(2)  # Debounce
        
        # Send heartbeat every 60 seconds
        if time.time() - last_heartbeat > 60:
            send_event("heartbeat")
            last_heartbeat = time.time()
            motion_count = 0
        
        time.sleep(0.1)

if __name__ == "__main__":
    try:
        main()
    finally:
        GPIO.cleanup()
```

### Testing Without Raspberry Pi
You can simulate motion sensor events:

```bash
# Simulate heartbeat
curl -X POST http://localhost:30800/api/iot/sensor \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "motion-sensor-rpi-01",
    "device_type": "motion_sensor",
    "event_type": "heartbeat",
    "value": {}
  }'

# Simulate motion detection
curl -X POST http://localhost:30800/api/iot/sensor \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "motion-sensor-rpi-01",
    "device_type": "motion_sensor",
    "event_type": "motion_detected",
    "value": {"confidence": 0.95, "zone": "entrance"}
  }'

# Simulate intrusion (triggers security alert + LLM analysis)
curl -X POST http://localhost:30800/api/iot/sensor \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "motion-sensor-rpi-01",
    "device_type": "motion_sensor",
    "event_type": "intrusion",
    "value": {"confidence": 0.99, "zone": "restricted_area"}
  }'
```

### Metrics Generated by Motion Sensor

| Metric | Labels | Description |
|--------|--------|-------------|
| `smartcity_ids_iot_devices_active` | - | Total registered IoT devices |
| `smartcity_ids_iot_events_total` | `device_id`, `event_type` | Events per device/type |
| `smartcity_ids_iot_heartbeats_total` | `device_id`, `device_type` | Heartbeats per device |
| `smartcity_ids_iot_security_events_total` | `device_id`, `event_type` | Security events (anomaly, intrusion) |

### Grafana Panels for Motion Sensor

The IEEE dashboard includes these IoT panels:
1. **Active IoT Devices** - Gauge showing registered devices
2. **IoT Events by Type** - Time series of event types
3. **IoT Heartbeats** - Table showing device health
4. **IoT Security Events** - Alerts from motion sensors

---

## 3. Suricata Network IDS Integration

### Problem
- Only Falco (runtime security) was deployed
- No network-level intrusion detection
- Grafana dashboard showed no Suricata alerts

### Solution
Deployed Suricata and created a forwarder to translate Suricata alerts to IDS API format.

### Files Modified/Created

#### `k8s-manifests/suricata-forwarder-deployment.yaml`
**Change:** Fixed Pydantic v2 compatibility issue

```python
# BEFORE (Pydantic v1 syntax - BROKEN)
class IDSAlert(BaseModel):
    output: str = Field(..., regex=r".+")

# AFTER (Pydantic v2 syntax - FIXED)
class IDSAlert(BaseModel):
    output: str = Field(..., pattern=r".+")
```

**Change:** Fixed security context preventing apt-get

```yaml
# BEFORE (blocked apt-get)
securityContext:
  runAsNonRoot: true
  runAsUser: 1000

# AFTER (allows package installation)
securityContext:
  allowPrivilegeEscalation: false
```

### Deployment Commands
```bash
kubectl apply -f k8s-manifests/suricata-working.yaml
kubectl apply -f k8s-manifests/suricata-forwarder-deployment.yaml
```

### Verification
```bash
# Suricata generating alerts
kubectl exec -n suricata-system deployment/suricata -- tail -5 /var/log/suricata/eve.json

# Suricata alerts in Prometheus
curl -s "http://localhost:31701/api/v1/query?query=smartcity_ids_alerts_received_total" | jq '.data.result[] | select(.metric.source=="suricata")'
```

---

## 4. IoT Services Deployment

### Problem
- Smart city IoT services (traffic-camera, healthcare-api, parking-system) were not deployed
- ConfigMaps were missing
- Security context prevented pip install (read-only filesystem)

### Solution
Created ConfigMaps and fixed deployment security context.

### Files Modified

#### `k8s-manifests/services-no-build.yaml`
**Change:** Removed restrictive security context from all three services

```yaml
# BEFORE (for traffic-camera, healthcare-api, parking-system)
securityContext:
  runAsNonRoot: true
  runAsUser: 1000
  runAsGroup: 1000
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true  # <-- Blocked pip install
  capabilities:
    drop:
      - ALL

# AFTER
securityContext:
  allowPrivilegeEscalation: false
  capabilities:
    drop:
      - ALL
```

**Change:** Added `--no-cache-dir` to pip install
```yaml
args:
  - "pip install --no-cache-dir flask==3.0.0 && python /app/app.py"
```

### Deployment Commands
```bash
# Create ConfigMaps for each service
kubectl create configmap traffic-camera-code -n smart-city --from-file=smart-city-services/traffic-camera/
kubectl create configmap healthcare-api-code -n smart-city --from-file=smart-city-services/healthcare-api/
kubectl create configmap parking-system-code -n smart-city --from-file=smart-city-services/parking-system/

# Apply deployment
kubectl apply -f k8s-manifests/services-no-build.yaml
kubectl rollout restart deployment traffic-camera healthcare-api parking-system -n smart-city
```

### Result
| Service | Status | Replicas | Health Endpoint |
|---------|--------|----------|-----------------|
| traffic-camera | ✅ Running | 2 | `/health` |
| healthcare-api | ✅ Running | 2 | `/health` |
| parking-system | ✅ Running | 2 | `/health` |

---

## 5. IoT Metrics Label Fix

### Problem
Prometheus metrics had label mismatches causing `ValueError: Incorrect label names`:
- `PROM_IOT_DEVICE_HEARTBEATS` defined with `[device_id]` but called with `device_id, device_type`
- `PROM_IOT_SECURITY_EVENTS` defined with `[device_type, event_type]` but called with `device_id, event_type`

### Solution

#### `services/ids-api/src/main.py`
**Change:** Fixed metric label definitions

```python
# BEFORE
PROM_IOT_SECURITY_EVENTS = Counter(
    "smartcity_ids_iot_security_events_total",
    "Security events from IoT devices.",
    ["device_type", "event_type"],  # WRONG
)
PROM_IOT_DEVICE_HEARTBEATS = Counter(
    "smartcity_ids_iot_heartbeats_total",
    "Heartbeat signals received from IoT devices.",
    ["device_id"],  # WRONG - missing device_type
)

# AFTER
PROM_IOT_SECURITY_EVENTS = Counter(
    "smartcity_ids_iot_security_events_total",
    "Security events from IoT devices.",
    ["device_id", "event_type"],  # FIXED
)
PROM_IOT_DEVICE_HEARTBEATS = Counter(
    "smartcity_ids_iot_heartbeats_total",
    "Heartbeat signals received from IoT devices.",
    ["device_id", "device_type"],  # FIXED
)
```

### IoT Device Registration
```bash
# Register IoT devices with the IDS API
curl -s -X POST http://localhost:30800/api/iot/sensor \
  -H "Content-Type: application/json" \
  -d '{"device_id":"traffic-cam-01","device_type":"camera","event_type":"heartbeat","value":{}}'
```

### Result
- 13 IoT devices registered
- Heartbeats tracked per device
- Security events properly labeled

---

## 6. PostgreSQL Persistence Implementation

### Problem
- Alerts stored in memory (`alerts_db: List[Dict] = []`)
- All data lost when IDS API pod restarts
- Grafana showed 0 alerts after every restart

### Solution
Implemented PostgreSQL database storage with fallback to in-memory if database unavailable.

### Files Created

#### `services/ids-api/src/database.py` (NEW FILE - 350+ lines)

```python
"""Database module for persistent alert storage.

Uses PostgreSQL for storing alerts, IoT events, and metrics.
Falls back to in-memory storage if database is unavailable.
"""

import os
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import json

# Database configuration
DB_HOST = os.environ.get("DB_HOST", "postgres")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "smartcity_ids")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "postgres")

class Database:
    """PostgreSQL database handler with fallback to memory."""
    
    def __init__(self):
        self.conn = None
        self.use_memory = not PSYCOPG2_AVAILABLE
        self._memory_alerts: List[Dict[str, Any]] = []
        self._memory_iot_events: List[Dict[str, Any]] = []
        self._memory_iot_devices: Dict[str, Dict[str, Any]] = {}
        
        if PSYCOPG2_AVAILABLE:
            self._connect()
    
    def _init_tables(self):
        """Create tables if they don't exist."""
        # Creates: alerts, iot_devices, iot_events tables
        # With proper indexes for performance
```

**Key Features:**
- Automatic table creation on startup
- Fallback to in-memory if PostgreSQL unavailable
- Connection auto-recovery
- Indexed queries for performance

**Database Schema:**
```sql
CREATE TABLE alerts (
    id SERIAL PRIMARY KEY,
    source VARCHAR(50) NOT NULL,
    rule VARCHAR(255),
    priority VARCHAR(50),
    severity INTEGER,
    summary TEXT,
    threat_type VARCHAR(100),
    recommendations JSONB,
    automated_actions JSONB,
    raw_alert JSONB,
    analysis JSONB,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE iot_devices (
    device_id VARCHAR(64) PRIMARY KEY,
    device_type VARCHAR(50),
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    event_count INTEGER DEFAULT 0,
    metadata JSONB
);

CREATE TABLE iot_events (
    id SERIAL PRIMARY KEY,
    device_id VARCHAR(64) REFERENCES iot_devices(device_id),
    device_type VARCHAR(50),
    event_type VARCHAR(50),
    value JSONB,
    timestamp TIMESTAMP,
    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB
);
```

### Files Modified

#### `services/ids-api/src/main.py`

**Change 1:** Import database module
```python
from config import Config
from llm_engine_xai import XAIAnalyzer
from llm_engine_openai import OpenAIAnalyzer
from k8s_automation import K8sAutomation
from database import db  # NEW
```

**Change 2:** Initialize metrics from database on startup
```python
# Initialize metrics from database on startup
def init_metrics_from_db():
    """Load existing counts from database."""
    global metrics
    try:
        stats = db.get_stats()
        metrics["total_alerts"] = stats.get("total_alerts", 0)
        metrics["alerts_by_source"] = stats.get("alerts_by_source", {"falco": 0, "suricata": 0})
        logger.info(f"📊 Loaded metrics from DB: {stats['total_alerts']} alerts, storage: {stats['storage_type']}")
    except Exception as e:
        logger.warning(f"Could not load metrics from DB: {e}")

init_metrics_from_db()
```

**Change 3:** Store alerts in database instead of memory
```python
# BEFORE
alert_record = {
    "id": len(alerts_db) + 1,
    "timestamp": alert.time,
    "source": source,
    "alert": alert.dict(),
    "analysis": analysis,
    "actions": actions_taken,
    "processed_at": datetime.now().isoformat()
}
alerts_db.append(alert_record)

# AFTER
alert_record = {
    "timestamp": alert.time,
    "source": source,
    "rule": alert.rule,
    "priority": alert.priority,
    "severity": severity,
    "summary": analysis.get("summary", ""),
    "threat_type": analysis.get("threat_type", ""),
    "recommendations": analysis.get("recommendations", []),
    "automated_actions": actions_taken,
    "raw_alert": alert.dict(),
    "analysis": analysis
}
alert_id = db.add_alert(alert_record)  # Stored in PostgreSQL
alert_record["id"] = alert_id
alerts_db.append(alert_record)  # Also cache in memory
```

**Change 4:** Update `/api/alerts` to read from database
```python
@app.get("/api/alerts")
async def get_alerts(limit: int = 10, source: Optional[str] = None):
    """Get alerts from database."""
    alerts = db.get_alerts(limit=limit, source=source)
    total = db.get_alert_count(source=source)
    return {
        "total": total,
        "showing": len(alerts),
        "storage": db.get_stats()["storage_type"],
        "alerts": alerts
    }
```

**Change 5:** Add database stats endpoint
```python
@app.get("/api/db/stats")
async def get_db_stats():
    """Get database statistics."""
    return db.get_stats()
```

**Change 6:** IoT devices stored in database
```python
# Register device in database
is_new_device = db.register_iot_device(data.device_id, data.device_type, data.metadata)

# Store event in database
event_id = db.add_iot_event(event_record)
```

#### `services/ids-api/src/requirements.txt`

**Change:** Added psycopg2-binary
```
fastapi==0.109.0
uvicorn==0.27.0
kubernetes==29.0.0
httpx
openai
prometheus-client
python-dotenv
psycopg2-binary  # NEW - PostgreSQL driver
```

### Database Setup Commands
```bash
# Create database
kubectl exec -n smart-city deployment/postgres -- psql -U postgres -c "CREATE DATABASE smartcity_ids;"

# Redeploy IDS API
kubectl delete configmap ids-app-code -n smart-city
kubectl create configmap ids-app-code -n smart-city --from-file=services/ids-api/src/
kubectl rollout restart deployment ids-api -n smart-city
```

### Verification

**Check storage type in logs:**
```
2026-01-28 19:19:24,806 - main - INFO - 💾 Storage: postgresql - 0 alerts, 0 IoT devices
```

**Check database stats:**
```bash
curl -s http://localhost:30800/api/db/stats
# Output: {"storage_type":"postgresql","total_alerts":5,"alerts_by_source":{"falco":5,"suricata":0},"iot_devices":2,"iot_events":2}
```

**Verify data in PostgreSQL:**
```bash
kubectl exec -n smart-city deployment/postgres -- psql -U postgres -d smartcity_ids -c "SELECT id, source, rule, severity FROM alerts ORDER BY id DESC LIMIT 10;"

# Output:
#  id | source |        rule        | severity 
# ----+--------+--------------------+----------
#   5 | falco  | Test-2             |        8
#   4 | falco  | Test-1             |        8
#   3 | falco  | Test-Rule-2        |        8
#   2 | falco  | Test-Rule-1        |        8
#   1 | falco  | Unexpected-Process |        8
```

**Test persistence across restarts:**
```bash
# Before restart
curl -s http://localhost:30800/api/db/stats
# {"total_alerts":5, "iot_devices":2}

# Restart IDS API
kubectl rollout restart deployment ids-api -n smart-city

# After restart - DATA PERSISTS!
curl -s http://localhost:30800/api/db/stats
# {"total_alerts":5, "iot_devices":2}
```

---

## 7. Summary of All Changes

### New Files Created
| File | Purpose |
|------|---------|
| `services/ids-api/src/database.py` | PostgreSQL persistence layer |

### Files Modified
| File | Changes |
|------|---------|
| `services/ids-api/src/main.py` | Database integration, IoT metric fixes, startup initialization |
| `services/ids-api/src/requirements.txt` | Added psycopg2-binary |
| `k8s-manifests/services-no-build.yaml` | Fixed security context for IoT services |
| `k8s-manifests/suricata-forwarder-deployment.yaml` | Fixed Pydantic v2 and security context |

### New Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/db/stats` | GET | Database statistics (storage type, counts) |

### Deployment Status
| Component | Namespace | Status | Notes |
|-----------|-----------|--------|-------|
| IDS API | smart-city | ✅ Running | PostgreSQL storage |
| PostgreSQL | smart-city | ✅ Running | `smartcity_ids` database |
| Falco | falco-system | ✅ Running | Runtime security |
| Suricata | suricata-system | ✅ Running | Network IDS |
| Suricata Forwarder | monitoring | ✅ Running | Alert translation |
| Traffic Camera | smart-city | ✅ Running | 2 replicas |
| Healthcare API | smart-city | ✅ Running | 2 replicas |
| Parking System | smart-city | ✅ Running | 2 replicas |
| IoT Devices | smart-city | ✅ Running | MQTT simulator |
| MQTT Broker | smart-city | ✅ Running | Message broker |
| Prometheus | monitoring | ✅ Running | Port 31701 |
| Grafana | monitoring | ✅ Running | Port 30300 |

### Metrics Status
| Metric Category | Count | Status |
|-----------------|-------|--------|
| Core Alert Metrics | 8 | ✅ Active |
| LLM Engine Metrics | 10 | ✅ Active |
| Production Controls | 10 | ✅ Active |
| IoT Metrics | 5 | ✅ Fixed |
| K8s Automation | 5 | ✅ Active |
| **Total** | **38+** | ✅ Scraped |

---

## 8. Key Learnings / Challenges

### Challenge 1: Pydantic v2 Breaking Change
- **Issue:** `regex=` parameter removed in Pydantic v2
- **Solution:** Use `pattern=` instead
- **Lesson:** Check library version compatibility when using base images

### Challenge 2: Security Context vs. Runtime Needs
- **Issue:** `readOnlyRootFilesystem: true` blocked pip install
- **Solution:** Removed restriction for services that need runtime package installation
- **Lesson:** Balance security with operational requirements

### Challenge 3: Prometheus Label Consistency
- **Issue:** Metric definition labels must match `.labels()` calls exactly
- **Solution:** Audit all Counter/Gauge definitions against usage
- **Lesson:** Use constants for label names to prevent mismatches

### Challenge 4: In-Memory Storage Loss
- **Issue:** All alerts lost on pod restart
- **Solution:** PostgreSQL persistence with graceful fallback
- **Lesson:** Production systems need persistent storage from day one

---

## 9. Raspberry Pi IoT Integration (January 29, 2026)

### Network Architecture

The Raspberry Pi connects to the IDS API through a Windows port proxy:

```
┌─────────────────────┐      ┌─────────────────────┐      ┌─────────────────────┐
│   Raspberry Pi      │      │   Windows Host      │      │   Ubuntu VM (NAT)   │
│   172.20.10.2       │ ───► │   172.20.10.3:30800 │ ───► │   192.168.153.129   │
│   (WiFi Hotspot)    │      │   (Port Proxy)      │      │   K3s + IDS API     │
└─────────────────────┘      └─────────────────────┘      └─────────────────────┘
```

### Why NAT + Port Proxy (not Bridged)?

| Approach | Pros | Cons |
|----------|------|------|
| **NAT + Port Proxy** ✅ | VM IP stable, works across WiFi changes | Need to find host IP on new network |
| **Bridged Mode** ❌ | Direct connection | VM IP changes with WiFi, unstable |

### Windows Port Proxy Setup

**PowerShell (Run as Administrator):**

```powershell
# Add port proxy rule (persists across reboots)
netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=30800 connectaddress=192.168.153.129 connectport=30800

# Add firewall rule
netsh advfirewall firewall add rule name="IDS API Forward 30800" dir=in action=allow protocol=TCP localport=30800

# Verify
netsh interface portproxy show all
```

**Output:**
```
Listen on ipv4:             Connect to ipv4:
Address         Port        Address         Port
--------------- ----------  --------------- ----------
0.0.0.0         30800       192.168.153.129 30800
```

### Raspberry Pi Motion Sensor Script

**File:** `~/motion_sensor.py`

```python
#!/usr/bin/env python3
"""Raspberry Pi Motion Sensor for Smart City IDS"""
import requests
import time
import argparse
from datetime import datetime

try:
    from gpiozero import MotionSensor
    GPIO_AVAILABLE = True
except:
    GPIO_AVAILABLE = False

def send_motion_event(ids_url, sensor_id="pi-motion-001"):
    payload = {
        "device_id": sensor_id,
        "device_type": "motion_sensor",
        "event_type": "motion_detected",
        "data": {"triggered": True, "timestamp": datetime.now().isoformat()},
        "location": "building-entrance"
    }
    try:
        r = requests.post(f"{ids_url}/api/iot/sensor", json=payload, timeout=5)
        print(f"[{datetime.now()}] Motion sent! Status: {r.status_code}")
        return r.status_code == 200
    except Exception as e:
        print(f"[{datetime.now()}] Error: {e}")
        return False

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids-url", required=True, help="IDS API URL")
    parser.add_argument("--pin", type=int, default=17, help="GPIO pin")
    parser.add_argument("--simulate", action="store_true", help="Simulate motion")
    args = parser.parse_args()

    print(f"Motion Sensor -> {args.ids_url}")
    
    if args.simulate:
        print("SIMULATION MODE - sending test events every 10s")
        while True:
            send_motion_event(args.ids_url)
            time.sleep(10)
    elif GPIO_AVAILABLE:
        pir = MotionSensor(args.pin)
        print(f"Waiting for motion on GPIO {args.pin}...")
        while True:
            pir.wait_for_motion()
            send_motion_event(args.ids_url)
            pir.wait_for_no_motion()
    else:
        print("No GPIO - use --simulate")

if __name__ == "__main__":
    main()
```

### Installation on Raspberry Pi

```bash
# Install dependencies
sudo apt update && sudo apt install -y python3-pip python3-gpiozero
pip3 install requests --break-system-packages

# Test connectivity to IDS API
curl http://172.20.10.3:30800/health

# Run in simulation mode (no sensor required)
python3 ~/motion_sensor.py --ids-url http://172.20.10.3:30800 --simulate

# Run with real PIR sensor on GPIO 17
python3 ~/motion_sensor.py --ids-url http://172.20.10.3:30800 --gpio-pin 17
```

### Script Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--ids-url` | Required | IDS API URL (e.g., http://172.20.10.3:30800) |
| `--gpio-pin` | 17 | GPIO pin number for PIR sensor |
| `--device-id` | auto | Unique device ID (default: rpi5-motion-hostname) |
| `--simulate` | false | Run without real sensor |
| `--heartbeat` | 60 | Heartbeat interval in seconds |

### PIR Sensor Wiring (AM312 Mini)

**Note:** AM312 uses **3.3V** (not 5V like HC-SR501). No LED indicator.

```
AM312 Mini          Raspberry Pi 5
──────────          ──────────────
VCC (Left)   ────►  Pin 1  (3.3V)   ← NOT 5V!
OUT (Middle) ────►  Pin 11 (GPIO 17)
GND (Right)  ────►  Pin 6  (Ground)
```

**Pin Counting (from corner near SD card):**
```
   Pin 1 ●  ● Pin 2      ← VCC to Pin 1 (3.3V)
   Pin 3 ●  ● Pin 4  
   Pin 5 ●  ● Pin 6      ← GND to Pin 6
   Pin 7 ●  ● Pin 8
   Pin 9 ●  ● Pin 10
  Pin 11 ●  ● Pin 12     ← OUT to Pin 11 (GPIO17)
```

**Troubleshooting:**
- AM312 has NO LED - this is normal
- Uses 3.3V not 5V (will not work on 5V)
- Warm-up time: ~30 seconds after power-on

### When Changing WiFi Networks

1. **On Windows:** Run `ipconfig` to find new WiFi IP (e.g., `192.168.1.100`)
2. **On Pi:** Update the IDS URL:
   ```bash
   python3 ~/motion_sensor.py --ids-url http://<NEW_WINDOWS_IP>:30800 --simulate
   ```

The port proxy rule persists—only the Windows IP changes.

### Verification

```bash
# From Pi - verify connectivity
curl http://172.20.10.3:30800/health

# Expected response:
# {"status":"healthy","components":{"xai_grok4":"connected","openai":"connected","kubernetes":"connected","falco":"enabled"},"uptime_seconds":4570,"total_alerts_processed":79}

# From VM - check IoT registrations
curl -s http://localhost:30800/api/db/stats | jq .
```

---

## 10. Next Steps

1. **Grafana Dashboard Update** - Add database health panel
2. **Backup Strategy** - PostgreSQL backup/restore procedures
3. **IoT Auto-Heartbeat** - Services should auto-register with IDS API
4. **Suricata Rules** - Add custom Suricata rules for smart city traffic
5. **IEEE Paper** - Document architecture with persistence layer
6. **Real PIR Testing** - Wire and test physical motion sensor

---

## Appendix: Quick Reference Commands

```bash
# Check database stats
curl -s http://localhost:30800/api/db/stats | jq .

# View alerts in PostgreSQL
kubectl exec -n smart-city deployment/postgres -- psql -U postgres -d smartcity_ids -c "SELECT * FROM alerts ORDER BY id DESC LIMIT 5;"

# View IoT devices in PostgreSQL  
kubectl exec -n smart-city deployment/postgres -- psql -U postgres -d smartcity_ids -c "SELECT * FROM iot_devices;"

# Register an IoT device
curl -s -X POST http://localhost:30800/api/iot/sensor \
  -H "Content-Type: application/json" \
  -d '{"device_id":"device-01","device_type":"sensor","event_type":"heartbeat","value":{}}'

# Send a test alert
curl -s -X POST http://localhost:30800/api/alerts \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer test-token-123" \
  -d '{"output":"Test alert","priority":"Warning","rule":"Test","time":"2026-01-28T00:00:00Z","output_fields":{"container.name":"test"}}'

# Redeploy IDS API after code changes
kubectl delete configmap ids-app-code -n smart-city && \
kubectl create configmap ids-app-code -n smart-city --from-file=services/ids-api/src/ && \
kubectl rollout restart deployment ids-api -n smart-city
```

---

*Document generated: January 28, 2026*
*Author: Smart City IDS Development Team*
*Project: Capstone II - LLM-Driven Intrusion Detection System*
