#!/usr/bin/env python3
"""
Smart Parking Sensor Emulator — MQTT / CoAP / SenML
====================================================
Faithfully emulates a real IoT parking sensor deployment:

  • Magnetometer + ultrasonic sensor fusion (Bosch PLS / Nedap SENSIT style)
  • MQTT v3.1.1 topic hierarchy  (smartcity/parking/{zone}/{slot}/+)
  • SenML (RFC 8428) payloads for sensor readings
  • CoAP-style resource discovery  (/.well-known/core, RFC 6690)
  • LWM2M object model  (Object 3302 Presence, 3300 Generic Sensor)

Protocol chain:
  Magnetometer/Ultrasonic → MCU (STM32L4) → LoRa/MQTT Gateway → Broker → REST API

Intentionally VULNERABLE for Smart City IDS demo:
  - No TLS on MQTT topics (plaintext payloads)
  - Payment endpoint logs PII (credit card tokens)
  - No sensor data authentication (spoofable)
  - Firmware update endpoint open without auth
"""

from flask import Flask, Response, jsonify, request
import time
import os
import random
import math
import threading
import logging
import json
import hashlib
import uuid
from datetime import datetime, timezone, timedelta
from collections import defaultdict

try:
    import paho.mqtt.client as mqtt
except Exception:  # pragma: no cover - optional dependency in some local runs
    mqtt = None

# ─── App ────────────────────────────────────────────────────────────────────────

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("parking-sensor")

GATEWAY_ID = os.environ.get("GATEWAY_ID", "GW-PARK-001")
FIRMWARE_VERSION = "v2.3.1-230815"
DEPLOYMENT_ZONE = os.environ.get("ZONE", "downtown")
MQTT_BROKER = os.environ.get("MQTT_BROKER", "mqtt-broker")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_ENABLED = os.environ.get("MQTT_ENABLED", "1").lower() not in {"0", "false", "no"}
MQTT_PUBLISH_INTERVAL = max(1, int(os.environ.get("MQTT_PUBLISH_INTERVAL", "5")))

# ═════════════════════════════════════════════════════════════════════════════════
# Sensor Hardware Emulation
# ═════════════════════════════════════════════════════════════════════════════════

class ParkingSensor:
    """Emulates a single ground-mount parking sensor (magnetometer + ultrasonic).

    Real sensors: Bosch PLS 400, Nedap SENSIT, Nwave, Libelium Smart Parking
    Protocol: LoRaWAN Class A or MQTT via gateway
    """

    STATES = ("vacant", "occupied", "reserved", "fault", "calibrating")

    def __init__(self, slot_id: str, zone: str, lot: str,
                 lat: float, lon: float, sensor_type: str = "magnetometer"):
        self.slot_id = slot_id
        self.zone = zone
        self.lot = lot
        self.lat = lat
        self.lon = lon
        self.sensor_type = sensor_type  # magnetometer | ultrasonic | dual
        # Hardware state
        self.state = "vacant"
        self.boot_time = time.time()
        self.last_state_change = time.time()
        self.battery_pct = round(random.uniform(60, 100), 1)
        self.battery_voltage = round(3.0 + self.battery_pct / 100.0 * 0.6, 3)
        self.rssi_dbm = random.randint(-120, -40)
        self.snr_db = round(random.uniform(5.0, 15.0), 1)
        self.fw_version = FIRMWARE_VERSION
        # Magnetometer (3-axis, µT)
        self.mag_x = random.gauss(25.0, 2.0)  # Earth's field ~25-65µT
        self.mag_y = random.gauss(5.0, 1.0)
        self.mag_z = random.gauss(42.0, 2.0)
        self.mag_baseline_x = self.mag_x
        self.mag_baseline_y = self.mag_y
        self.mag_baseline_z = self.mag_z
        self.mag_threshold_ut = 15.0  # µT deviation threshold
        # Ultrasonic (cm)
        self.us_distance_cm = random.uniform(180, 250)  # No car = far
        self.us_threshold_cm = 100.0
        # Telemetry
        self.temperature_c = round(random.uniform(15, 35), 1)
        self.humidity_pct = round(random.uniform(30, 70), 1)
        self.tx_count = 0
        self.uptime_seconds = 0
        # Detection
        self.detection_confidence = 0.0
        self.vehicle_duration_s = 0
        self.events = []  # Rolling event log
        self.events_max = 1000

    @property
    def mqtt_topic_base(self):
        return f"smartcity/parking/{self.zone}/{self.lot}/{self.slot_id}"

    def tick(self):
        """Called every second — mirrors real sensor MCU wake/sleep cycle."""
        self.uptime_seconds = time.time() - self.boot_time
        # Battery drain (~0.1% per hour for LoRa sensor)
        self.battery_pct = max(0, self.battery_pct - random.uniform(0, 0.003))
        self.battery_voltage = round(3.0 + self.battery_pct / 100.0 * 0.6, 3)
        # Environment
        self.temperature_c += random.gauss(0, 0.02)
        self.humidity_pct = max(10, min(95, self.humidity_pct + random.gauss(0, 0.1)))
        # Signal quality
        self.rssi_dbm = max(-130, min(-20, self.rssi_dbm + random.randint(-2, 2)))
        self.snr_db = max(0, min(20, self.snr_db + random.gauss(0, 0.2)))
        # Sensor readings
        if self.state == "occupied":
            # Vehicle present: magnetometer disturbed, ultrasonic close
            self.mag_x = self.mag_baseline_x + random.gauss(35, 5)
            self.mag_y = self.mag_baseline_y + random.gauss(20, 3)
            self.mag_z = self.mag_baseline_z + random.gauss(45, 8)
            self.us_distance_cm = random.gauss(55, 10)
            self.vehicle_duration_s += 1
            self.detection_confidence = min(1.0, 0.85 + random.uniform(0, 0.15))
        else:
            # No vehicle: baseline field + noise
            self.mag_x = self.mag_baseline_x + random.gauss(0, 0.5)
            self.mag_y = self.mag_baseline_y + random.gauss(0, 0.3)
            self.mag_z = self.mag_baseline_z + random.gauss(0, 0.6)
            self.us_distance_cm = random.gauss(210, 15)
            self.vehicle_duration_s = 0
            self.detection_confidence = max(0, random.gauss(0.05, 0.03))
        # Fault injection (0.1% chance per tick = ~3.6 faults/hour)
        if random.random() < 0.001 and self.state != "fault":
            self.state = "fault"
            self._log_event("sensor_fault", "Magnetometer ADC overflow")
        # State transitions based on sensor fusion
        mag_deviation = math.sqrt(
            (self.mag_x - self.mag_baseline_x) ** 2 +
            (self.mag_y - self.mag_baseline_y) ** 2 +
            (self.mag_z - self.mag_baseline_z) ** 2
        )
        us_close = self.us_distance_cm < self.us_threshold_cm
        mag_triggered = mag_deviation > self.mag_threshold_ut
        # Time-based state transitions (emulate real traffic patterns)
        hour = datetime.now().hour
        # Rush hours: 7-9, 16-18 → higher occupancy
        occupy_prob = {7: 0.03, 8: 0.05, 9: 0.04, 10: 0.02,
                       12: 0.03, 16: 0.04, 17: 0.05, 18: 0.03}
        vacate_prob = {10: 0.03, 11: 0.04, 14: 0.02, 19: 0.05, 20: 0.04}
        if self.state == "vacant" and random.random() < occupy_prob.get(hour, 0.01):
            self.state = "occupied"
            self.last_state_change = time.time()
            self.tx_count += 1
            self._log_event("vehicle_arrive", f"Mag: {mag_deviation:.1f}µT US: {self.us_distance_cm:.0f}cm")
        elif self.state == "occupied" and random.random() < vacate_prob.get(hour, 0.008):
            duration = time.time() - self.last_state_change
            self.state = "vacant"
            self.last_state_change = time.time()
            self.vehicle_duration_s = 0
            self.tx_count += 1
            self._log_event("vehicle_depart", f"Duration: {duration:.0f}s")

    def _log_event(self, event_type, detail):
        self.events.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "slot_id": self.slot_id,
            "event": event_type,
            "detail": detail,
            "battery_pct": round(self.battery_pct, 1),
        })
        if len(self.events) > self.events_max:
            self.events.pop(0)

    def to_senml(self):
        """RFC 8428 SenML Pack — real IoT data format."""
        bn = f"urn:dev:mac:{hashlib.md5(self.slot_id.encode()).hexdigest()[:12]}/"
        t = time.time()
        pack = [
            {"bn": bn, "bt": t, "n": "occupancy", "vb": self.state == "occupied"},
            {"n": "mag_x", "v": round(self.mag_x, 2), "u": "uT"},
            {"n": "mag_y", "v": round(self.mag_y, 2), "u": "uT"},
            {"n": "mag_z", "v": round(self.mag_z, 2), "u": "uT"},
            {"n": "mag_deviation", "v": round(math.sqrt(
                (self.mag_x - self.mag_baseline_x) ** 2 +
                (self.mag_y - self.mag_baseline_y) ** 2 +
                (self.mag_z - self.mag_baseline_z) ** 2
            ), 2), "u": "uT"},
            {"n": "us_distance", "v": round(self.us_distance_cm, 1), "u": "cm"},
            {"n": "confidence", "v": round(self.detection_confidence, 3)},
            {"n": "battery", "v": round(self.battery_pct, 1), "u": "%"},
            {"n": "battery_v", "v": round(self.battery_voltage, 3), "u": "V"},
            {"n": "temperature", "v": round(self.temperature_c, 1), "u": "Cel"},
            {"n": "humidity", "v": round(self.humidity_pct, 1), "u": "%RH"},
            {"n": "rssi", "v": self.rssi_dbm, "u": "dBm"},
            {"n": "snr", "v": round(self.snr_db, 1), "u": "dB"},
        ]
        return pack

    def to_lwm2m(self):
        """LWM2M Object 3302 (Presence Sensor) + 3300 (Generic Sensor)."""
        return {
            "ep": self.slot_id,
            "objects": {
                "/3302/0": {  # Presence Sensor
                    "5500": self.state == "occupied",           # Digital Input State
                    "5501": self.tx_count,                      # Digital Input Counter
                    "5750": f"Parking Slot {self.slot_id}",     # Application Type
                    "5751": self.sensor_type,                   # Sensor Type
                },
                "/3300/0": {  # Generic Sensor (magnetometer)
                    "5700": round(math.sqrt(
                        self.mag_x**2 + self.mag_y**2 + self.mag_z**2
                    ), 2),                                      # Sensor Value
                    "5701": "uT",                               # Sensor Units
                    "5601": 0.0,                                # Min Measured
                    "5602": 120.0,                              # Max Measured
                },
                "/3300/1": {  # Generic Sensor (ultrasonic)
                    "5700": round(self.us_distance_cm, 1),
                    "5701": "cm",
                    "5601": 3.0,
                    "5602": 400.0,
                },
                "/3316/0": {  # Voltage
                    "5700": round(self.battery_voltage, 3),
                    "5701": "V",
                },
                "/3303/0": {  # Temperature
                    "5700": round(self.temperature_c, 1),
                    "5701": "Cel",
                },
            },
        }

    def mqtt_messages(self):
        """Generate MQTT messages this sensor would publish."""
        base = self.mqtt_topic_base
        t = datetime.now(timezone.utc).isoformat()
        messages = [
            {
                "topic": f"{base}/status",
                "qos": 1,
                "retain": True,
                "payload": json.dumps({
                    "state": self.state,
                    "confidence": round(self.detection_confidence, 3),
                    "since": datetime.fromtimestamp(
                        self.last_state_change, tz=timezone.utc
                    ).isoformat(),
                    "duration_s": self.vehicle_duration_s if self.state == "occupied" else 0,
                    "ts": t,
                }),
            },
            {
                "topic": f"{base}/telemetry",
                "qos": 0,
                "retain": False,
                "payload": json.dumps({
                    "mag": {"x": round(self.mag_x, 2), "y": round(self.mag_y, 2), "z": round(self.mag_z, 2)},
                    "us_cm": round(self.us_distance_cm, 1),
                    "temp_c": round(self.temperature_c, 1),
                    "hum_pct": round(self.humidity_pct, 1),
                    "bat_pct": round(self.battery_pct, 1),
                    "bat_v": round(self.battery_voltage, 3),
                    "rssi": self.rssi_dbm,
                    "snr": round(self.snr_db, 1),
                    "tx_count": self.tx_count,
                    "ts": t,
                }),
            },
            {
                "topic": f"{base}/senml",
                "qos": 0,
                "retain": False,
                "payload": json.dumps(self.to_senml()),
            },
        ]
        return messages


# ═════════════════════════════════════════════════════════════════════════════════
# Parking Zones — sensor deployment topology
# ═════════════════════════════════════════════════════════════════════════════════

ZONES = {
    "downtown": {
        "LOT_A": {"name": "City Center Garage", "capacity": 100, "lat": 37.7749, "lon": -122.4194},
        "LOT_B": {"name": "Mall District Surface", "capacity": 200, "lat": 37.7751, "lon": -122.4180},
    },
    "airport": {
        "LOT_C": {"name": "Airport Terminal P1", "capacity": 150, "lat": 37.6213, "lon": -122.3790},
    },
}

# Logical fleet scaling (sensors per pod) for larger IoT emulation without extra pods.
_slot_scale = max(1, int(os.environ.get("DEVICE_COUNT_MULTIPLIER", os.environ.get("PARKING_SLOT_MULTIPLIER", "1"))))
if _slot_scale != 1:
    for _zone_name, _lots in ZONES.items():
        for _lot_id, _lot_info in _lots.items():
            _lot_info["capacity"] = int(_lot_info["capacity"]) * _slot_scale

sensors = {}  # slot_id → ParkingSensor
gateway_runtime = {
    "mqtt_enabled": bool(MQTT_ENABLED and mqtt),
    "mqtt_connected": False,
    "mqtt_last_publish": None,
    "mqtt_publish_count": 0,
    "mqtt_control_count": 0,
    "mqtt_last_control": None,
    "mqtt_last_error": None,
}

def _init_sensors():
    """Create sensor objects for every slot in every lot."""
    for zone, lots in ZONES.items():
        for lot_id, lot_info in lots.items():
            for i in range(lot_info["capacity"]):
                slot_id = f"{lot_id}-{i:03d}"
                s = ParkingSensor(
                    slot_id=slot_id,
                    zone=zone,
                    lot=lot_id,
                    lat=lot_info["lat"] + random.gauss(0, 0.0001),
                    lon=lot_info["lon"] + random.gauss(0, 0.0001),
                    sensor_type=random.choice(["magnetometer", "dual"]),
                )
                # Initialize ~50% occupied
                if random.random() < 0.5:
                    s.state = "occupied"
                    s.last_state_change = time.time() - random.randint(60, 7200)
                sensors[slot_id] = s

_init_sensors()


def _sensor_ticker():
    """Background thread — tick every sensor once per second."""
    while True:
        for s in sensors.values():
            s.tick()
        time.sleep(1.0)

threading.Thread(target=_sensor_ticker, daemon=True).start()


def _apply_control_message(topic: str, payload: dict):
    """Apply MQTT control semantics to one sensor, lot, zone, or the whole fleet."""
    action = str(payload.get("action", payload.get("command", ""))).strip().lower()
    desired_state = str(payload.get("state", payload.get("value", ""))).strip().lower()
    topic_parts = topic.split("/")
    targets = []

    if len(topic_parts) >= 5 and topic_parts[:2] == ["smartcity", "parking"]:
        if topic == "smartcity/parking/control/all":
            targets = list(sensors.values())
        elif len(topic_parts) == 4 and topic_parts[3] == "command":
            zone = topic_parts[2]
            targets = [s for s in sensors.values() if s.zone == zone]
        elif len(topic_parts) == 5 and topic_parts[4] == "command":
            zone, lot = topic_parts[2], topic_parts[3]
            targets = [s for s in sensors.values() if s.zone == zone and s.lot == lot]
        elif len(topic_parts) == 6 and topic_parts[5] == "command":
            zone, lot, slot = topic_parts[2], topic_parts[3], topic_parts[4]
            target = sensors.get(slot)
            if target and target.zone == zone and target.lot == lot:
                targets = [target]

    if not targets:
        return 0

    now = time.time()
    changed = 0
    for sensor in targets:
        if action in {"reserve", "occupied", "occupy"} or desired_state == "occupied":
            sensor.state = "occupied"
            sensor.last_state_change = now
            sensor.vehicle_duration_s = int(payload.get("duration_s", sensor.vehicle_duration_s or 0))
            sensor._log_event("mqtt_control_occupy", f"topic={topic}")
            changed += 1
        elif action in {"vacate", "release"} or desired_state == "vacant":
            sensor.state = "vacant"
            sensor.last_state_change = now
            sensor.vehicle_duration_s = 0
            sensor._log_event("mqtt_control_vacate", f"topic={topic}")
            changed += 1
        elif action in {"fault", "disable"} or desired_state == "fault":
            sensor.state = "fault"
            sensor.last_state_change = now
            sensor._log_event("mqtt_control_fault", f"topic={topic}")
            changed += 1
        elif action in {"restore", "clear_fault"}:
            sensor.state = "vacant"
            sensor.last_state_change = now
            sensor._log_event("mqtt_control_restore", f"topic={topic}")
            changed += 1
        elif action in {"calibrate", "reserved"} or desired_state == "reserved":
            sensor.state = "reserved"
            sensor.last_state_change = now
            sensor._log_event("mqtt_control_reserved", f"topic={topic}")
            changed += 1
    if changed:
        logger.warning("MQTT control applied: topic=%s action=%s changed=%s", topic, action or desired_state, changed)
    return changed


def _mqtt_gateway_loop():
    """Publish real MQTT telemetry and process control topics like a gateway."""
    if not gateway_runtime["mqtt_enabled"]:
        gateway_runtime["mqtt_last_error"] = "paho-mqtt unavailable or MQTT disabled"
        return

    pod_identity = os.environ.get("HOSTNAME", "pod")
    client_id = f"{GATEWAY_ID.lower()}-{pod_identity}-{os.getpid()}"
    client = mqtt.Client(client_id=client_id, clean_session=True, protocol=mqtt.MQTTv311)

    def on_connect(client, userdata, flags, rc):
        gateway_runtime["mqtt_connected"] = rc == 0
        if rc == 0:
            client.subscribe("smartcity/parking/control/all", qos=1)
            client.subscribe("smartcity/parking/+/command", qos=1)
            client.subscribe("smartcity/parking/+/+/command", qos=1)
            client.subscribe("smartcity/parking/+/+/+/command", qos=1)
            logger.info("MQTT gateway connected to %s:%s", MQTT_BROKER, MQTT_PORT)
        else:
            gateway_runtime["mqtt_last_error"] = f"connect_rc={rc}"

    def on_disconnect(client, userdata, rc):
        gateway_runtime["mqtt_connected"] = False
        if rc:
            gateway_runtime["mqtt_last_error"] = f"disconnect_rc={rc}"

    def on_message(client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8") or "{}")
        except Exception:
            payload = {}
        changed = _apply_control_message(msg.topic, payload)
        gateway_runtime["mqtt_control_count"] += changed
        gateway_runtime["mqtt_last_control"] = {
            "topic": msg.topic,
            "changed": changed,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    while True:
        try:
            if not gateway_runtime["mqtt_connected"]:
                client.connect(MQTT_BROKER, MQTT_PORT, keepalive=30)
                client.loop_start()
                time.sleep(1.0)

            published = 0
            sample = list(sensors.values())
            random.shuffle(sample)
            # Publish a bounded but real gateway sample each cycle.
            for sensor in sample[: min(80, len(sample))]:
                for msg in sensor.mqtt_messages():
                    result = client.publish(msg["topic"], payload=msg["payload"], qos=msg["qos"], retain=msg["retain"])
                    if result.rc == mqtt.MQTT_ERR_SUCCESS:
                        published += 1
            gateway_runtime["mqtt_publish_count"] += published
            gateway_runtime["mqtt_last_publish"] = datetime.now(timezone.utc).isoformat()
            time.sleep(MQTT_PUBLISH_INTERVAL)
        except Exception as exc:
            gateway_runtime["mqtt_last_error"] = str(exc)
            gateway_runtime["mqtt_connected"] = False
            try:
                client.loop_stop()
            except Exception:
                pass
            time.sleep(5.0)


threading.Thread(target=_mqtt_gateway_loop, daemon=True).start()


# ═════════════════════════════════════════════════════════════════════════════════
# CoAP Resource Discovery  (RFC 6690)
# ═════════════════════════════════════════════════════════════════════════════════

@app.route("/.well-known/core", methods=["GET"])
def coap_resource_discovery():
    """CoAP-style resource discovery (RFC 6690 Link-Format).

    Real IoT gateways expose this so LWM2M servers can discover resources.
    """
    links = [
        '</api/lots>;rt="parking.lots";ct=50',
        '</api/sensors>;rt="parking.sensors";ct=50',
        '</api/mqtt/topics>;rt="mqtt.topics";ct=50',
        '</api/senml>;rt="senml";ct=110',
        '</api/lwm2m>;rt="oma.lwm2m";ct=11543',
        '</api/events>;rt="parking.events";ct=50',
        '</api/gateway>;rt="gateway.info";ct=50',
    ]
    body = ",\n".join(links)
    return Response(body, content_type="application/link-format")


# ═════════════════════════════════════════════════════════════════════════════════
# MQTT Topic Tree  (/api/mqtt/*)
# ═════════════════════════════════════════════════════════════════════════════════

@app.route("/api/mqtt/topics", methods=["GET"])
def mqtt_topics():
    """Browse MQTT topic tree — VULNERABLE: no auth, sensor data exposed!"""
    zone_filter = request.args.get("zone")
    lot_filter = request.args.get("lot")
    topics = {}
    for s in sensors.values():
        if zone_filter and s.zone != zone_filter:
            continue
        if lot_filter and s.lot != lot_filter:
            continue
        for msg in s.mqtt_messages():
            topics[msg["topic"]] = {
                "qos": msg["qos"],
                "retain": msg["retain"],
                "payload_size": len(msg["payload"]),
                "last_update": datetime.now(timezone.utc).isoformat(),
            }
    return jsonify({
        "broker": f"mqtt://{MQTT_BROKER}:1883",
        "protocol": "MQTT v3.1.1",
        "tls": False,
        "topic_count": len(topics),
        "gateway_runtime": gateway_runtime,
        "topics": dict(list(topics.items())[:100]),
    })


@app.route("/api/mqtt/subscribe/<path:topic>", methods=["GET"])
def mqtt_subscribe(topic):
    """Retrieve latest payload for a specific MQTT topic."""
    for s in sensors.values():
        for msg in s.mqtt_messages():
            if msg["topic"] == topic:
                return Response(msg["payload"], content_type="application/json")
    return jsonify({"error": "Topic not found"}), 404


# ═════════════════════════════════════════════════════════════════════════════════
# SenML Endpoints  (RFC 8428)
# ═════════════════════════════════════════════════════════════════════════════════

@app.route("/api/senml", methods=["GET"])
def senml_feed():
    """SenML Pack for all sensors — real IoT data format (RFC 8428)."""
    lot_filter = request.args.get("lot")
    limit = min(int(request.args.get("limit", 20)), 100)
    pack = []
    count = 0
    for s in sensors.values():
        if lot_filter and s.lot != lot_filter:
            continue
        pack.extend(s.to_senml())
        count += 1
        if count >= limit:
            break
    return Response(
        json.dumps(pack),
        content_type="application/senml+json",
    )


@app.route("/api/senml/<slot_id>", methods=["GET"])
def senml_slot(slot_id):
    """SenML Pack for a single sensor."""
    s = sensors.get(slot_id)
    if not s:
        return jsonify({"error": "Sensor not found"}), 404
    return Response(
        json.dumps(s.to_senml()),
        content_type="application/senml+json",
    )


# ═════════════════════════════════════════════════════════════════════════════════
# LWM2M Endpoints  (OMA LightweightM2M)
# ═════════════════════════════════════════════════════════════════════════════════

@app.route("/api/lwm2m", methods=["GET"])
def lwm2m_registry():
    """LWM2M client registration — VULNERABLE: no DTLS!"""
    lot_filter = request.args.get("lot")
    limit = min(int(request.args.get("limit", 20)), 100)
    clients = []
    count = 0
    for s in sensors.values():
        if lot_filter and s.lot != lot_filter:
            continue
        clients.append(s.to_lwm2m())
        count += 1
        if count >= limit:
            break
    return jsonify({
        "server": "coap://parking-lwm2m.smart-city:5683",
        "security": "NoSec",
        "registered_clients": len(sensors),
        "returned": len(clients),
        "clients": clients,
    })


@app.route("/api/lwm2m/<slot_id>", methods=["GET"])
def lwm2m_client(slot_id):
    """LWM2M client object tree for a single sensor."""
    s = sensors.get(slot_id)
    if not s:
        return jsonify({"error": "Endpoint not found"}), 404
    return jsonify(s.to_lwm2m())


# ═════════════════════════════════════════════════════════════════════════════════
# Parking Management REST  (backward-compatible)
# ═════════════════════════════════════════════════════════════════════════════════

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy",
        "service": "parking-sensor-emulator",
        "protocol": "MQTT/CoAP/SenML",
        "firmware": FIRMWARE_VERSION,
        "gateway": GATEWAY_ID,
        "sensors_total": len(sensors),
        "uptime": round(time.time() - list(sensors.values())[0].boot_time if sensors else 0),
    }), 200


@app.route("/api/lots", methods=["GET"])
def get_lots():
    """Parking lot summary — aggregated from real sensor data."""
    result = {}
    for zone, lots in ZONES.items():
        for lot_id, lot_info in lots.items():
            lot_sensors = [s for s in sensors.values() if s.lot == lot_id]
            occupied = sum(1 for s in lot_sensors if s.state == "occupied")
            faulted = sum(1 for s in lot_sensors if s.state == "fault")
            avg_battery = round(
                sum(s.battery_pct for s in lot_sensors) / max(1, len(lot_sensors)), 1
            )
            result[lot_id] = {
                "name": lot_info["name"],
                "zone": zone,
                "location": {"lat": lot_info["lat"], "lon": lot_info["lon"]},
                "capacity": lot_info["capacity"],
                "occupied": occupied,
                "vacant": lot_info["capacity"] - occupied - faulted,
                "faulted_sensors": faulted,
                "occupancy_pct": round(occupied / max(1, lot_info["capacity"]) * 100, 1),
                "avg_battery_pct": avg_battery,
                "sensor_type": "magnetometer+ultrasonic",
            }
    return jsonify({
        "parking_lots": result,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "protocol": "MQTT/SenML",
    }), 200


@app.route("/api/sensors", methods=["GET"])
def get_sensors():
    """List individual sensor states — VULNERABLE: no auth on raw sensor data!"""
    lot_filter = request.args.get("lot")
    state_filter = request.args.get("state")
    limit = min(int(request.args.get("limit", 50)), 200)
    result = []
    for s in sensors.values():
        if lot_filter and s.lot != lot_filter:
            continue
        if state_filter and s.state != state_filter:
            continue
        result.append({
            "slot_id": s.slot_id,
            "zone": s.zone,
            "lot": s.lot,
            "state": s.state,
            "confidence": round(s.detection_confidence, 3),
            "duration_s": s.vehicle_duration_s if s.state == "occupied" else 0,
            "battery_pct": round(s.battery_pct, 1),
            "rssi_dbm": s.rssi_dbm,
            "temperature_c": round(s.temperature_c, 1),
            "sensor_type": s.sensor_type,
            "mqtt_topic": s.mqtt_topic_base,
            "location": {"lat": round(s.lat, 6), "lon": round(s.lon, 6)},
        })
        if len(result) >= limit:
            break
    return jsonify({
        "sensors": result,
        "total": len(sensors),
        "returned": len(result),
    })


@app.route("/api/lot/<lot_id>/reserve", methods=["POST"])
def reserve_spot(lot_id):
    """Reserve a parking spot — finds first vacant sensor in lot."""
    for s in sensors.values():
        if s.lot == lot_id and s.state == "vacant":
            s.state = "reserved"
            s.last_state_change = time.time()
            s._log_event("reservation", "Spot reserved via API")
            lot_sensors = [x for x in sensors.values() if x.lot == lot_id]
            vacant = sum(1 for x in lot_sensors if x.state == "vacant")
            return jsonify({
                "message": "Spot reserved",
                "slot_id": s.slot_id,
                "lot_id": lot_id,
                "mqtt_topic": f"{s.mqtt_topic_base}/status",
                "spots_remaining": vacant,
            }), 200
    return jsonify({"error": "No vacant spots available"}), 400


@app.route("/api/events", methods=["GET"])
def get_events():
    """Sensor event stream — arrive/depart/fault events."""
    lot_filter = request.args.get("lot")
    limit = min(int(request.args.get("limit", 100)), 500)
    all_events = []
    for s in sensors.values():
        if lot_filter and s.lot != lot_filter:
            continue
        all_events.extend(s.events)
    all_events.sort(key=lambda e: e["timestamp"], reverse=True)
    return jsonify({
        "events": all_events[:limit],
        "total": len(all_events),
    })


@app.route("/api/payment", methods=["POST"])
def process_payment():
    """Payment endpoint — VULNERABLE: logs PII / card tokens!"""
    payment_data = request.json or {}
    logger.warning(f"PAYMENT DATA LOGGED (PII EXPOSURE): {json.dumps(payment_data)}")
    txn_id = f"TXN-{uuid.uuid4().hex[:8].upper()}"
    return jsonify({
        "status": "success",
        "transaction_id": txn_id,
        "amount": payment_data.get("amount"),
        "lot_id": payment_data.get("lot_id"),
        "slot_id": payment_data.get("slot_id"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "WARNING": "PAYMENT_DATA_LOGGED_INSECURELY",
    }), 200


@app.route("/api/gateway", methods=["GET"])
def gateway_info():
    """IoT gateway diagnostic info — VULNERABLE: firmware/config exposure!"""
    return jsonify({
        "gateway_id": GATEWAY_ID,
        "firmware": FIRMWARE_VERSION,
        "protocol": "MQTT v3.1.1 (no TLS)",
        "broker": f"mqtt://{MQTT_BROKER}:1883",
        "sensors_registered": len(sensors),
        "sensors_online": sum(1 for s in sensors.values() if s.state != "fault"),
        "uplink": "LoRaWAN EU868 SF7BW125",
        "lora_eui": "00-11-22-33-44-55-66-77",
        "lora_app_key": os.environ.get("LORA_APP_KEY", "TEST_LORAWAN_APP_KEY_CHANGE_ME"),
        "mqtt_runtime": gateway_runtime,
    })


@app.route("/api/firmware/update", methods=["POST"])
def firmware_update():
    """VULNERABILITY: Unauthenticated OTA firmware update endpoint!"""
    logger.warning(f"FIRMWARE UPDATE attempt from {request.remote_addr}")
    data = request.json or {}
    return jsonify({
        "status": "accepted",
        "current_version": FIRMWARE_VERSION,
        "target_version": data.get("version", "unknown"),
        "WARNING": "OTA_UPDATE_NO_AUTH_NO_SIGNATURE_CHECK",
    }), 202


@app.route("/api/stats", methods=["GET"])
def get_stats():
    total_cap = sum(lot["capacity"] for lots in ZONES.values() for lot in lots.values())
    total_occ = sum(1 for s in sensors.values() if s.state == "occupied")
    return jsonify({
        "service": "parking-sensor-emulator",
        "protocol": "MQTT/CoAP/SenML/LWM2M",
        "gateway": GATEWAY_ID,
        "total_capacity": total_cap,
        "total_occupied": total_occ,
        "occupancy_rate": round(total_occ / max(1, total_cap) * 100, 2),
        "sensors_total": len(sensors),
        "sensors_faulted": sum(1 for s in sensors.values() if s.state == "fault"),
        "avg_battery_pct": round(
            sum(s.battery_pct for s in sensors.values()) / max(1, len(sensors)), 1
        ),
        "mqtt_connected": gateway_runtime["mqtt_connected"],
        "mqtt_publish_count": gateway_runtime["mqtt_publish_count"],
        "mqtt_control_count": gateway_runtime["mqtt_control_count"],
        "mqtt_last_publish": gateway_runtime["mqtt_last_publish"],
    }), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5002))
    logger.info(f"Starting Parking Sensor Emulator ({GATEWAY_ID}) on port {port}")
    logger.info(f"  Sensors: {len(sensors)} across {sum(len(l) for l in ZONES.values())} lots")
    logger.info(f"  MQTT Topics: smartcity/parking/{DEPLOYMENT_ZONE}/+/+/status")
    logger.info(f"  SenML Feed:  http://0.0.0.0:{port}/api/senml")
    logger.info(f"  CoAP Disc:   http://0.0.0.0:{port}/.well-known/core")
    logger.info(f"  LWM2M Reg:   http://0.0.0.0:{port}/api/lwm2m")
    logger.info(f"  MQTT uplink:  mqtt://{MQTT_BROKER}:{MQTT_PORT}")
    logger.info("  WARNING: No TLS, no auth — intentionally vulnerable for IDS research evaluation")
    app.run(host="0.0.0.0", port=port, debug=False)
