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

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field

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


class IoTDeviceRegisterRequest(BaseModel):
    """Lightweight logical device registry record for external/edge onboarding."""
    device_id: str = Field(..., min_length=1, max_length=128)
    device_type: str = Field(..., min_length=1, max_length=64)
    schema_version: str = Field(default="1.0")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    capability_profile: Dict[str, Any] = Field(default_factory=dict)


class IoTDeviceHeartbeatRequest(BaseModel):
    """Heartbeat from a logical device; updates last_seen and optional status."""
    device_id: str = Field(..., min_length=1, max_length=128)
    status: str = Field(default="online")
    timestamp: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

# Avoid blocking the FastAPI event loop on slow/unreachable Kubernetes API calls.
# The dashboard polls IoT endpoints frequently; if the in-cluster API is down,
# synchronous kubernetes-client calls can stall *all* HTTP handling and trip
# liveness/readiness probes.
_IOT_PODS_CACHE_TTL_SECONDS = 5
_iot_pods_cache: dict = {"ts": 0.0, "value": None}
_iot_pods_cache_lock = asyncio.Lock()

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


@router.post("/api/iot/devices/register")
async def register_iot_device_endpoint(data: IoTDeviceRegisterRequest):
    """Register a logical IoT device independent of Kubernetes pod count.

    This endpoint supports a research-grade fleet model where many logical
    devices may be emulated by a single pod. It stores minimal registry data
    in the existing DB-backed IoT device table and updates the in-memory
    active device map used by the dashboard.
    """
    db, iot_devices, iot_events, _ = _deps()
    now = datetime.now().isoformat()
    md = {
        **(data.metadata or {}),
        "schema_version": data.schema_version,
        "capability_profile": data.capability_profile or {},
    }
    created = db.register_iot_device(data.device_id, data.device_type, md)
    current = iot_devices.get(data.device_id, {})
    iot_devices[data.device_id] = {
        "device_id": data.device_id,
        "device_type": data.device_type,
        "first_seen": current.get("first_seen", now),
        "last_seen": now,
        "event_count": int(current.get("event_count", 0)),
        "status": "online",
        "schema_version": data.schema_version,
        "capability_profile": data.capability_profile or {},
        "metadata": md,
    }
    # Track a registry event for auditability.
    evt = {
        "device_id": data.device_id,
        "device_type": data.device_type,
        "event_type": "register",
        "value": {"created": bool(created), "schema_version": data.schema_version},
        "timestamp": now,
        "metadata": md,
    }
    try:
        evt["id"] = db.add_iot_event(evt)
        iot_events.append(evt)
    except Exception:
        pass
    try:
        PROM_IOT_DEVICES_ACTIVE.set(max(len(iot_devices), db.get_iot_device_count()))
    except Exception:
        PROM_IOT_DEVICES_ACTIVE.set(len(iot_devices))
    return {
        "status": "registered",
        "device_id": data.device_id,
        "created": bool(created),
        "logical_device_count": len(iot_devices),
    }


@router.post("/api/iot/devices/heartbeat")
async def iot_device_heartbeat_endpoint(data: IoTDeviceHeartbeatRequest):
    """Update logical device liveness without sending full telemetry payloads."""
    db, iot_devices, iot_events, _ = _deps()
    now = data.timestamp or datetime.now().isoformat()
    existing = iot_devices.get(data.device_id)
    if not existing:
        # Auto-register unknown devices as generic edge devices so heartbeats are useful.
        db.register_iot_device(data.device_id, "unknown", data.metadata or {})
        iot_devices[data.device_id] = {
            "device_id": data.device_id,
            "device_type": "unknown",
            "first_seen": now,
            "last_seen": now,
            "event_count": 0,
            "status": data.status,
            "metadata": data.metadata or {},
        }
    else:
        existing["last_seen"] = now
        existing["status"] = data.status
        if data.metadata:
            merged = dict(existing.get("metadata") or {})
            merged.update(data.metadata)
            existing["metadata"] = merged

    try:
        PROM_IOT_DEVICE_HEARTBEATS.labels(
            device_id=data.device_id,
            device_type=iot_devices[data.device_id].get("device_type", "unknown"),
        ).inc()
    except Exception:
        pass

    try:
        evt = {
            "device_id": data.device_id,
            "device_type": iot_devices[data.device_id].get("device_type", "unknown"),
            "event_type": "heartbeat",
            "value": {"status": data.status},
            "timestamp": now,
            "metadata": data.metadata or {},
        }
        evt["id"] = db.add_iot_event(evt)
        iot_events.append(evt)
    except Exception:
        pass

    return {
        "status": "heartbeat_received",
        "device_id": data.device_id,
        "last_seen": now,
    }


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
    logical_total = len(iot_devices)
    pod_backed_total = sum(1 for d in devices if str(d.get("device", "")).startswith(tuple(p for p, _ in _IOT_POD_PREFIXES)))
    return {
        "devices": devices,
        "total": len(devices),
        "active_rate": active_rate,
        "logical_total": logical_total,
        "pod_backed_total": pod_backed_total,
        "counting_mode": "hybrid_registry_plus_pods",
    }


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

    # Fast path: short TTL cache to avoid hammering the K8s API when the UI polls.
    now = time.time()
    cached = _iot_pods_cache.get("value")
    if cached is not None and (now - float(_iot_pods_cache.get("ts", 0.0))) < _IOT_PODS_CACHE_TTL_SECONDS:
        return cached

    if k8s_automation:
        async with _iot_pods_cache_lock:
            # Re-check cache after acquiring the lock.
            now = time.time()
            cached = _iot_pods_cache.get("value")
            if cached is not None and (now - float(_iot_pods_cache.get("ts", 0.0))) < _IOT_PODS_CACHE_TTL_SECONDS:
                return cached

            def _list_iot_pods_sync():
                return k8s_automation.core_v1.list_namespaced_pod(
                    namespace="smart-city",
                    timeout_seconds=5,
                    _request_timeout=(1, 2),
                )

            try:
                # Run the synchronous Kubernetes client call off the event loop.
                pod_list = await asyncio.wait_for(asyncio.to_thread(_list_iot_pods_sync), timeout=2.5)
                for p in getattr(pod_list, "items", []) or []:
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
                        "name": name,
                        "type": device_type,
                        "status": phase,
                        "ready": ready,
                        "ip": pod_ip,
                        "node": node,
                        "restarts": restarts,
                        "namespace": "smart-city",
                    })
            except asyncio.TimeoutError:
                logger.warning("Could not list IoT pods: Kubernetes API timeout")
            except Exception as e:
                logger.warning(f"Could not list IoT pods: {e}")

    # Count pods by device type for the summary.
    type_counts = {}
    for pod in pods:
        t = pod["type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    result = {
        "total": len(pods),
        "pods": pods,
        "types": type_counts,
        "running": sum(1 for p in pods if p["status"] == "Running"),
    }

    # Cache even empty results briefly to avoid tight retry loops when K8s is down.
    _iot_pods_cache["ts"] = time.time()
    _iot_pods_cache["value"] = result
    return result


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


@router.get("/api/iot/discover")
async def discover_iot_workloads():
    """Discover IoT workloads dynamically from cluster pods and emit SOC-friendly summary."""
    pods_info = await get_iot_pods()
    discovered = []
    for pod in pods_info.get("pods", []):
        restarts = int(pod.get("restarts") or 0)
        status = pod.get("status", "Unknown")
        risk_flags = []
        if status != "Running":
            risk_flags.append("pod_not_running")
        if restarts >= 3:
            risk_flags.append("high_restart_rate")
        discovered.append(
            {
                "device_id": pod.get("name"),
                "device_type": pod.get("type"),
                "namespace": pod.get("namespace", "smart-city"),
                "node": pod.get("node"),
                "pod_ip": pod.get("ip"),
                "status": status,
                "restarts": restarts,
                "risk_flags": risk_flags,
            }
        )

    return {
        "total": len(discovered),
        "running": sum(1 for d in discovered if d.get("status") == "Running"),
        "discovered_at": datetime.now().isoformat(),
        "devices": discovered,
    }


@router.get("/api/iot/vulnerabilities")
async def iot_vulnerability_assessment():
    """Comprehensive vulnerability/risk assessment for discovered IoT workloads.
    
    Performs multi-layer security analysis:
    1. Infrastructure health (pod status, restarts)
    2. Network exposure (service types, ports)
    3. Protocol security (known insecure protocols)
    4. CVE-based risk scoring (protocol-based)
    5. Device posture (missing security features)
    6. Compliance mapping (OWASP IoT Top 10)
    """
    data = await discover_iot_workloads()
    findings = []
    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    
    # Risk aggregation for summary
    risk_summary = {
        "infrastructure_issues": 0,
        "security_exposures": 0,
        "protocol_vulnerabilities": 0,
        "compliance_gaps": 0,
    }
    
    # Known vulnerable protocols and their CVE mappings
    PROTOCOL_RISKS = {
        "Modbus TCP": {
            "severity": "high",
            "cwe": "CWE-319",
            "description": "Modbus TCP lacks built-in encryption or authentication",
            "mitigation": "Use Modbus TLS or VPN tunneling",
            "cve_refs": ["CVE-2019-6800", "CVE-2021-22681"],
        },
        "OPC UA": {
            "severity": "medium",
            "cwe": "CWE-306",
            "description": "OPC UA security mode may be disabled or misconfigured",
            "mitigation": "Enable Sign&Encrypt security mode",
            "cve_refs": ["CVE-2018-12085"],
        },
        "MQTT": {
            "severity": "medium", 
            "cwe": "CWE-287",
            "description": "MQTT may lack authentication on broker connections",
            "mitigation": "Enable TLS and client certificate authentication",
            "cve_refs": ["CVE-2018-17614", "CVE-2020-13849"],
        },
        "CoAP": {
            "severity": "medium",
            "cwe": "CWE-319",
            "description": "CoAP may transmit data unencrypted",
            "mitigation": "Use CoAPs (DTLS) for all communications",
            "cve_refs": ["CVE-2019-9750"],
        },
        "DALI-2": {
            "severity": "low",
            "cwe": "CWE-287",
            "description": "DALI-2 has limited security controls",
            "mitigation": "Implement gateway-level access control",
            "cve_refs": [],
        },
        "ONVIF Profile S": {
            "severity": "high",
            "cwe": "CWE-287",
            "description": "IP cameras often use default credentials or unencrypted streams",
            "mitigation": "Change default passwords, enable RTSP over TLS",
            "cve_refs": ["CVE-2018-19937", "CVE-2021-33044"],
        },
    }
    
    # Get telemetry data for security analysis
    telemetry = {}
    try:
        telemetry = await iot_telemetry()
    except Exception as e:
        logger.warning(f"Could not fetch telemetry for vulnerability assessment: {e}")

    for device in data.get("devices", []):
        device_id = device.get("device_id")
        device_type = device.get("device_type", "unknown")
        risk_flags = device.get("risk_flags", [])
        
        # Find matching service in telemetry
        service_id = None
        for svc_id, svc in _IOT_SERVICES.items():
            if svc["label"] in device_type or device_id.startswith(svc_id.replace("-service", "")):
                service_id = svc_id
                break
        
        service_protocol = ""
        if service_id and service_id in _IOT_SERVICES:
            service_protocol = _IOT_SERVICES[service_id].get("protocol", "")

        # 1. Infrastructure Health Checks
        if "pod_not_running" in risk_flags:
            findings.append({
                "device_id": device_id,
                "category": "infrastructure",
                "severity": "high",
                "title": "IoT workload unavailable",
                "description": "Pod is not in Running state; service may be impaired.",
                "recommendation": "Inspect pod events/logs and recover workload.",
                "owasp_iot": "I1: Weak, Guessable, or Hardcoded Passwords",
            })
            severity_counts["high"] += 1
            risk_summary["infrastructure_issues"] += 1

        if "high_restart_rate" in risk_flags:
            findings.append({
                "device_id": device_id,
                "category": "infrastructure",
                "severity": "medium",
                "title": "Frequent container restarts",
                "description": "Repeated restarts can indicate crash loops, resource exhaustion, or attacks (OOM exploitation).",
                "recommendation": "Review deployment health probes, resource limits, and container logs.",
                "owasp_iot": "I9: Insecure Update Mechanism",
            })
            severity_counts["medium"] += 1
            risk_summary["infrastructure_issues"] += 1

        # 2. Protocol Security Analysis
        if service_protocol:
            for protocol, risk in PROTOCOL_RISKS.items():
                if protocol in service_protocol:
                    findings.append({
                        "device_id": device_id,
                        "category": "protocol",
                        "severity": risk["severity"],
                        "title": f"{protocol} security considerations",
                        "description": f"{risk['description']} (CWE: {risk['cwe']})",
                        "recommendation": risk["mitigation"],
                        "cve_references": risk["cve_refs"],
                        "cwe": risk["cwe"],
                        "owasp_iot": "I2: Insecure Network Services",
                    })
                    severity_counts[risk["severity"]] += 1
                    risk_summary["protocol_vulnerabilities"] += 1

        # 3. Device-Specific Security Checks
        device_security_checks = {
            "ONVIF Camera": [
                ("high", "Default credentials risk", 
                 "IP cameras frequently ship with default passwords that are not changed",
                 "Enforce password policy and audit camera configurations", "I1"),
                ("medium", "Unencrypted video stream",
                 "RTSP streams may be unencrypted, allowing eavesdropping",
                 "Enable SRTP or VPN tunneling for video streams", "I5"),
            ],
            "FHIR R4 Gateway": [
                ("high", "PHI exposure risk",
                 "Healthcare data requires HIPAA-compliant encryption and access controls",
                 "Verify TLS 1.3, audit logging, and access controls", "I5"),
            ],
            "MQTT/CoAP Sensor": [
                ("medium", "Broker authentication",
                 "MQTT sensors may connect without client certificates",
                 "Enable mutual TLS authentication for all broker connections", "I3"),
                ("medium", "Topic enumeration",
                 "Without proper ACLs, topics can be enumerated by attackers",
                 "Implement strict topic ACLs and monitor for unauthorized subscriptions", "I2"),
            ],
            "Modbus/OPC UA Env": [
                ("high", "Critical infrastructure exposure",
                 "Industrial protocols may bridge IT/OT networks",
                 "Implement network segmentation and ICS-specific IDS", "I4"),
                ("high", "No encryption in transit",
                 "Modbus TCP is plaintext and can be manipulated",
                 "Deploy Modbus TLS or application-layer encryption", "I5"),
            ],
            "DALI-2 Luminaire": [
                ("low", "Limited audit logging",
                 "DALI-2 devices may not log security events",
                 "Implement gateway-level logging for all control commands", "I8"),
            ],
        }
        
        for check_device_type, checks in device_security_checks.items():
            if check_device_type in device_type:
                for severity, title, description, recommendation, owasp_id in checks:
                    findings.append({
                        "device_id": device_id,
                        "category": "security_posture",
                        "severity": severity,
                        "title": title,
                        "description": description,
                        "recommendation": recommendation,
                        "owasp_iot": f"I{owasp_id}: {get_owasp_description(owasp_id)}",
                    })
                    severity_counts[severity] += 1
                    risk_summary["security_exposures"] += 1

        # 4. Telemetry-based Dynamic Risk Assessment
        if service_id and service_id in telemetry:
            svc_data = telemetry[service_id]
            if not svc_data.get("online", False):
                findings.append({
                    "device_id": device_id,
                    "category": "availability",
                    "severity": "high",
                    "title": "Service not responding to health checks",
                    "description": "Device is not responding to telemetry queries, indicating potential compromise or failure.",
                    "recommendation": "Investigate network connectivity and service health immediately.",
                    "owasp_iot": "I9: Insecure Update Mechanism",
                })
                severity_counts["high"] += 1
                risk_summary["infrastructure_issues"] += 1

        # 5. Compliance/Configuration Checks
        if not risk_flags and device.get("status") == "Running":
            # Device is healthy but still check for compliance gaps
            severity_counts["low"] += 1

    # Calculate overall risk score
    total_weight = (
        severity_counts["critical"] * 10 +
        severity_counts["high"] * 5 +
        severity_counts["medium"] * 2 +
        severity_counts["low"] * 0.5
    )
    max_possible = len(data.get("devices", [])) * 10
    risk_score = min(100, int((total_weight / max(max_possible, 1)) * 100))
    
    # Risk level determination
    if risk_score >= 70:
        risk_level = "critical"
    elif risk_score >= 40:
        risk_level = "high"
    elif risk_score >= 20:
        risk_level = "medium"
    else:
        risk_level = "low"

    return {
        "assessed_at": datetime.now().isoformat(),
        "total_devices": data.get("total", 0),
        "running_devices": data.get("running", 0),
        "risk_score": risk_score,
        "risk_level": risk_level,
        "severity_counts": severity_counts,
        "risk_summary": risk_summary,
        "findings": findings,
        "recommendations_priority": generate_priority_recommendations(findings),
        "compliance_frameworks": {
            "owasp_iot_top_10": True,
            "nist_cybersecurity_framework": "Partial",
            "iso_27001": "Not Assessed",
        },
    }


def get_owasp_description(id_num: str) -> str:
    """Get OWASP IoT Top 10 description"""
    descriptions = {
        "1": "Weak, Guessable, or Hardcoded Passwords",
        "2": "Insecure Network Services",
        "3": "Insecure Ecosystem Interfaces",
        "4": "Lack of Secure Update Mechanism",
        "5": "Use of Insecure or Outdated Components",
        "6": "Insufficient Privacy Protection",
        "7": "Insecure Data Transfer and Storage",
        "8": "Lack of Device Management",
        "9": "Insecure Default Settings",
        "10": "Lack of Physical Hardening",
    }
    return descriptions.get(id_num, "Unknown")


def generate_priority_recommendations(findings: List[Dict]) -> List[Dict]:
    """Generate prioritized remediation recommendations"""
    if not findings:
        return [{"priority": 1, "action": "Continue monitoring - no critical issues detected"}]
    
    # Group by severity and category
    critical_infrastructure = [f for f in findings if f["severity"] == "critical" and f.get("category") == "infrastructure"]
    critical_security = [f for f in findings if f["severity"] == "critical" and f.get("category") != "infrastructure"]
    high_findings = [f for f in findings if f["severity"] == "high"]
    protocol_issues = [f for f in findings if f.get("category") == "protocol"]
    
    recommendations = []
    priority = 1
    
    if critical_infrastructure:
        recommendations.append({
            "priority": priority,
            "action": "IMMEDIATE: Restore critical infrastructure services",
            "affected_devices": list(set(f["device_id"] for f in critical_infrastructure)),
            "count": len(critical_infrastructure),
        })
        priority += 1
    
    if critical_security:
        recommendations.append({
            "priority": priority,
            "action": "URGENT: Address critical security exposures",
            "affected_devices": list(set(f["device_id"] for f in critical_security)),
            "count": len(critical_security),
        })
        priority += 1
    
    if protocol_issues:
        high_protocol = [p for p in protocol_issues if p["severity"] in ("high", "critical")]
        if high_protocol:
            recommendations.append({
                "priority": priority,
                "action": "HIGH: Implement protocol encryption and authentication",
                "protocols": list(set(p["title"].split(" ")[0] for p in high_protocol)),
                "count": len(high_protocol),
            })
            priority += 1
    
    if high_findings:
        recommendations.append({
            "priority": priority,
            "action": "Address high-severity findings",
            "count": len(high_findings),
        })
        priority += 1
    
    return recommendations
