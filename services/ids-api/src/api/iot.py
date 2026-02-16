"""IoT sensor endpoints and telemetry proxy.

This module provides the API layer for all Internet-of-Things device
interactions in the Smart City IDS.  It serves two distinct purposes:

1. **Telemetry aggregation** — ``GET /api/iot/telemetry`` fans out HTTP
   requests to every registered smart-city microservice (traffic cameras,
   parking systems, healthcare devices, environmental sensors, street
   lighting) and merges the responses into a single JSON payload for the
   operator dashboard.

2. **Sensor data ingestion** — ``POST /api/iot/sensor`` receives telemetry
   from edge devices (e.g. Raspberry Pi motion sensors).  Security-relevant
   events (anomaly, intrusion, tampering) are automatically forwarded to the
   alert processing pipeline (``api.alerts.process_alert_internal``).

Protocol diversity (mirrors real smart-city heterogeneity):
    ┌───────────────────┬──────────────────────────────┐
    │ Service           │ Protocol                     │
    ├───────────────────┼──────────────────────────────┤
    │ Traffic Camera    │ ONVIF Profile S              │
    │ Parking System    │ MQTT / CoAP / SenML          │
    │ Healthcare API    │ HL7 FHIR R4                  │
    │ Env Sensor        │ Modbus TCP + OPC UA          │
    │ Street Lighting   │ DALI-2 + TALQ v2.4          │
    └───────────────────┴──────────────────────────────┘

Endpoints:
    GET  /api/iot/telemetry  – aggregate live telemetry from all services
    POST /api/iot/sensor     – receive data from edge IoT devices
    GET  /api/iot/devices    – list known IoT devices (DB + K8s pods)
    GET  /api/iot/pods       – list running IoT pods from Kubernetes
    GET  /api/iot/events     – query recent IoT events
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter

from infrastructure.metrics import (
    PROM_IOT_DEVICES_ACTIVE,      # Gauge: number of active IoT devices
    PROM_IOT_DEVICE_HEARTBEATS,   # Counter: heartbeat signals per device
    PROM_IOT_EVENTS_TOTAL,        # Counter: total IoT events by device + type
    PROM_IOT_SECURITY_EVENTS,     # Counter: security-relevant IoT events
)
from models.alert import Alert
from models.iot import IoTSensorData

logger = logging.getLogger(__name__)
router = APIRouter(tags=["iot"])

# ══════════════════════════════════════════════════════════════════════════════
# IOT SERVICE REGISTRY
# ══════════════════════════════════════════════════════════════════════════════
# Each entry maps a service identifier to its cluster-internal URL and the
# REST endpoints it exposes.  The telemetry proxy iterates over this dict
# and fans out HTTP GET requests to each endpoint.

_IOT_SERVICES = {
    "traffic-camera": {
        "label": "Traffic Camera",
        "protocol": "ONVIF Profile S",                # IP camera standard
        "url": "http://traffic-camera-service.smart-city.svc.cluster.local",
        "endpoints": {
            "health": "/health",
            "telemetry": "/api/telemetry",
            "anpr": "/api/anpr/statistics",            # automatic number-plate recognition
            "cameras": "/api/cameras",
            "stats": "/api/stats",
        },
    },
    "parking-system": {
        "label": "Parking System",
        "protocol": "MQTT/CoAP/SenML",                # lightweight IoT protocols
        "url": "http://parking-system-service.smart-city.svc.cluster.local",
        "endpoints": {
            "health": "/health",
            "lots": "/api/lots",
            "gateway": "/api/gateway",
            "stats": "/api/stats",
        },
    },
    "healthcare-api": {
        "label": "Healthcare API",
        "protocol": "HL7 FHIR R4",                    # healthcare interoperability standard
        "url": "http://healthcare-api-service.smart-city.svc.cluster.local",
        "endpoints": {
            "health": "/health",
            "telemetry": "/api/devices/telemetry",
            "alarms": "/api/devices/alarms",
            "stats": "/api/stats",
        },
    },
    "env-sensor": {
        "label": "Environmental Sensor",
        "protocol": "Modbus TCP + OPC UA",             # industrial IoT protocols
        "url": "http://env-sensor-service.smart-city.svc.cluster.local",
        "endpoints": {
            "health": "/health",
            "stats": "/api/stats",
            "aqi": "/api/aqi",                         # air quality index
            "telemetry": "/api/telemetry",
        },
    },
    "street-lighting": {
        "label": "Street Lighting",
        "protocol": "DALI-2 + TALQ v2.4",             # smart-lighting standards
        "url": "http://street-lighting-service.smart-city.svc.cluster.local",
        "endpoints": {
            "health": "/health",
            "stats": "/api/stats",
            "telemetry": "/api/telemetry",
        },
    },
}

# ══════════════════════════════════════════════════════════════════════════════
# IOT POD LABEL PREFIXES
# ══════════════════════════════════════════════════════════════════════════════
# Used by ``GET /api/iot/pods`` to match Kubernetes pod names to their
# human-readable device-type labels.  A pod whose name starts with any
# prefix in this list is considered an IoT workload.

_IOT_POD_PREFIXES = [
    ("traffic-camera", "ONVIF Camera"),
    ("healthcare-api", "FHIR R4 Gateway"),
    ("parking-system", "MQTT/CoAP Sensor"),
    ("env-sensor", "Modbus/OPC UA Env"),
    ("street-lighting", "DALI-2 Luminaire"),
    ("iot-devices-enhanced", "MQTT Emulator"),
    ("iot-device-high", "MQTT High-Freq"),
    ("iot-device-medium", "MQTT Med-Freq"),
    ("iot-device-burst", "MQTT Burst"),
    ("mqtt-broker", "Message Broker"),
]


# ── Dependency helpers ───────────────────────────────────────────────────────

def _deps():
    """Retrieve shared state: database, IoT device registry, events, K8s client."""
    from api._state import db, iot_devices, iot_events, k8s_automation
    return db, iot_devices, iot_events, k8s_automation


async def _fetch_json(url: str, timeout: float = 3.0):
    """Fetch JSON from a cluster-internal HTTP endpoint.

    Returns the parsed JSON dict on success, or ``None`` on any error
    (timeout, connection refused, non-200 status).  Used by the telemetry
    proxy to gracefully handle services that are down.
    """
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        pass
    return None


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/api/iot/telemetry")
async def iot_telemetry():
    """Aggregate live telemetry from all IoT emulators for the dashboard.

    For each registered service in ``_IOT_SERVICES``, issues HTTP GET
    requests to every endpoint (health, telemetry, stats, …) and merges
    the responses.  Services that are offline are marked ``"online": false``.

    Returns:
        Dict keyed by service ID, each containing label, protocol, online
        status, and endpoint response data.
    """
    results = {}
    for svc_id, svc in _IOT_SERVICES.items():
        svc_data = {"label": svc["label"], "protocol": svc["protocol"], "online": False}
        # Fan out requests to every endpoint of this service.
        for ep_name, ep_path in svc["endpoints"].items():
            url = f"{svc['url']}{ep_path}"
            data = await _fetch_json(url)
            if data:
                svc_data["online"] = True  # At least one endpoint responded.
                svc_data[ep_name] = data
        results[svc_id] = svc_data
    return results


@router.post("/api/iot/sensor")
async def receive_iot_sensor_data(data: IoTSensorData):
    """Receive sensor data from Raspberry Pi / IoT edge devices.

    Processing flow:
        1. Register the device in the database (if new).
        2. Update the in-memory device registry with last-seen timestamp.
        3. Persist the event to the database.
        4. Increment Prometheus counters (events, heartbeats, security).
        5. **If the event is security-relevant** (anomaly, intrusion,
           tampering, unauthorized, rapid_motion), automatically construct
           an ``Alert`` object and forward it to the internal alert
           processing pipeline for LLM analysis.

    Args:
        data: Validated ``IoTSensorData`` Pydantic model.

    Returns:
        - ``{"status": "received", …}`` for normal telemetry.
        - ``{"status": "security_event_processed", …}`` for security events,
          including the LLM analysis result.
    """
    db, iot_devices, iot_events, _ = _deps()
    now = datetime.now().isoformat()

    # ── Step 1: Register device (idempotent) ─────────────────────────────
    is_new_device = db.register_iot_device(data.device_id, data.device_type, data.metadata)
    if data.device_id not in iot_devices or is_new_device:
        iot_devices[data.device_id] = {
            "device_id": data.device_id,
            "device_type": data.device_type,
            "first_seen": now,
            "last_seen": now,
            "event_count": 0,
        }
        PROM_IOT_DEVICES_ACTIVE.set(db.get_iot_device_count())

    # ── Step 2: Update last-seen and event count ─────────────────────────
    iot_devices[data.device_id]["last_seen"] = now
    iot_devices[data.device_id]["event_count"] += 1

    # ── Step 3: Persist event ────────────────────────────────────────────
    event_record = {
        "device_id": data.device_id,
        "device_type": data.device_type,
        "event_type": data.event_type,
        "value": data.value,
        "timestamp": data.timestamp or now,
        "metadata": data.metadata,
    }
    event_id = db.add_iot_event(event_record)
    event_record["id"] = event_id
    iot_events.append(event_record)

    # ── Step 4: Prometheus metrics ───────────────────────────────────────
    PROM_IOT_EVENTS_TOTAL.labels(device_id=data.device_id, event_type=data.event_type).inc()

    if data.event_type == "heartbeat":
        PROM_IOT_DEVICE_HEARTBEATS.labels(device_id=data.device_id, device_type=data.device_type).inc()

    # ── Step 5: Forward security events to the alert pipeline ────────────
    security_events = ["anomaly", "intrusion", "tampering", "unauthorized", "rapid_motion"]
    if data.event_type in security_events:
        PROM_IOT_SECURITY_EVENTS.labels(device_id=data.device_id, event_type=data.event_type).inc()
        logger.warning(f"🚨 Security event from IoT device: {data.event_type}")

        # Construct a standard Alert from the IoT event.
        alert = Alert(
            output=f"IoT Security Event: {data.event_type} detected by {data.device_id} ({data.device_type})",
            priority="Warning" if data.event_type != "intrusion" else "Critical",
            rule=f"IoT_{data.event_type}",
            time=data.timestamp or now,
            output_fields={
                "container.name": f"iot-{data.device_id}",
                "device.id": data.device_id,
                "device.type": data.device_type,
                "event.value": str(data.value) if data.value else "",
                "source": "raspberry_pi",
            },
        )

        # Forward to the cluster-internal alert endpoint (no auth required).
        from api.alerts import process_alert_internal

        alert_response = await process_alert_internal(alert)
        return {
            "status": "security_event_processed",
            "event_id": event_record["id"],
            "alert_id": alert_response.alert_id,
            "analysis": alert_response.analysis,
        }

    return {"status": "received", "event_id": event_record["id"], "device_registered": data.device_id in iot_devices}


@router.get("/api/iot/devices")
async def get_iot_devices_endpoint():
    """List IoT devices with live operational fields for the dashboard.

    Merges two data sources:
        1. **In-memory device registry** — populated by ``POST /api/iot/sensor``
           calls from edge devices.
        2. **Kubernetes pod list** — enriches records with real pod IPs,
           phase (Running / Pending / Failed), and restart counts.

    A device is considered ``connected`` if its last heartbeat was within
    the last 120 seconds.  The ``current_rate`` is a rough events-per-minute
    estimate based on event count and time since first seen.

    Returns:
        {"devices": [...], "total": int, "active_rate": float}
    """
    _, iot_devices, _, k8s_automation = _deps()
    devices: List[Dict[str, Any]] = []
    now = datetime.now()

    # ── Build device list from in-memory registry ────────────────────────
    for device_id, record in iot_devices.items():
        last_seen_raw = record.get("last_seen")
        last_seen = None
        if isinstance(last_seen_raw, str):
            try:
                last_seen = datetime.fromisoformat(last_seen_raw.replace("Z", "+00:00")).replace(tzinfo=None)
            except Exception:
                last_seen = None
        if not last_seen:
            last_seen = now
        # A device is "connected" if seen in the last 120 seconds.
        age_s = max(0, (now - last_seen).total_seconds())
        connected = age_s <= 120
        event_count = int(record.get("event_count", 0))
        # Rough events-per-minute rate estimate.
        rate_per_min = round((event_count / max(1.0, age_s / 60.0)) if connected else 0.0, 2)
        devices.append({
            "device": device_id,
            "namespace": "smart-city",
            "device_type": record.get("device_type", "unknown"),
            "status": "healthy" if connected else "stale",
            "current_rate": rate_per_min,
            "ip": record.get("ip", "-"),
            "connected": connected,
            "device_id": device_id,
            "last_seen": record.get("last_seen"),
            "event_count": event_count,
        })

    # ── Enrich from Kubernetes pod data ──────────────────────────────────
    # If K8s is available, overlay real pod IPs and statuses.
    if k8s_automation:
        try:
            pods = await get_iot_pods()
            for p in pods.get("pods", []):
                pod_name = p.get("name")
                exists = next((d for d in devices if d["device"] == pod_name), None)
                if exists:
                    # Update existing device with live pod info.
                    exists["ip"] = p.get("ip", exists["ip"])
                    exists["status"] = "healthy" if p.get("status") == "Running" else p.get("status", "unknown").lower()
                    exists["connected"] = p.get("status") == "Running"
                else:
                    # Pod exists in K8s but hasn't sent sensor data yet.
                    devices.append({
                        "device": pod_name,
                        "namespace": p.get("namespace", "smart-city"),
                        "device_type": p.get("type", "pod"),
                        "status": "healthy" if p.get("status") == "Running" else p.get("status", "unknown").lower(),
                        "current_rate": 0.0,
                        "ip": p.get("ip", "-"),
                        "connected": p.get("status") == "Running",
                        "device_id": pod_name,
                        "last_seen": now.isoformat(),
                        "event_count": 0,
                    })
        except Exception as e:
            logger.warning(f"Could not enrich /api/iot/devices from pods: {e}")

    # Aggregate event rate across all devices.
    active_rate = round(sum(float(d.get("current_rate", 0.0) or 0.0) for d in devices), 2)
    return {"devices": devices, "total": len(devices), "active_rate": active_rate}


@router.get("/api/iot/pods")
async def get_iot_pods():
    """List running IoT pods from the Kubernetes cluster.

    Queries the K8s API for all pods in the ``smart-city`` namespace and
    filters to those whose names match any prefix in ``_IOT_POD_PREFIXES``.
    Returns pod name, type label, phase, readiness, IP, node, and restarts.

    Returns:
        {"total": int, "pods": [...], "types": {type: count}, "running": int}
    """
    _, _, _, k8s_automation = _deps()
    pods = []
    if k8s_automation:
        try:
            pod_list = k8s_automation.core_v1.list_namespaced_pod(
                namespace="smart-city", timeout_seconds=5
            )
            for p in pod_list.items:
                name = p.metadata.name
                # Match pod name against known IoT prefixes.
                device_type = None
                for prefix, dtype in _IOT_POD_PREFIXES:
                    if name.startswith(prefix):
                        device_type = dtype
                        break
                if not device_type:
                    continue  # Not an IoT pod — skip.
                phase = p.status.phase or "Unknown"
                pod_ip = p.status.pod_ip or "-"
                node = p.spec.node_name or "-"
                ready = False
                restarts = 0
                if p.status.container_statuses:
                    for cs in p.status.container_statuses:
                        ready = ready or cs.ready
                        restarts += cs.restart_count or 0
                pods.append({
                    "name": name, "type": device_type, "status": phase,
                    "ready": ready, "ip": pod_ip, "node": node,
                    "restarts": restarts, "namespace": "smart-city",
                })
        except Exception as e:
            logger.warning(f"Could not list IoT pods: {e}")

    # Count pods by device type for the summary.
    type_counts = {}
    for pod in pods:
        t = pod["type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    return {
        "total": len(pods),
        "pods": pods,
        "types": type_counts,
        "running": sum(1 for p in pods if p["status"] == "Running"),
    }


@router.get("/api/iot/events")
async def get_iot_events(limit: int = 50, device_id: Optional[str] = None):
    """Get recent IoT events, optionally filtered by device ID.

    Args:
        limit:     Maximum number of events to return (default 50).
        device_id: If provided, return only events from this device.

    Returns:
        {"total": int, "showing": int, "events": [...]}
    """
    _, _, iot_events, _ = _deps()
    filtered = iot_events
    if device_id:
        filtered = [e for e in iot_events if e["device_id"] == device_id]
    return {"total": len(filtered), "showing": min(limit, len(filtered)), "events": filtered[-limit:]}
