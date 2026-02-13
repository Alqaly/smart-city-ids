#!/usr/bin/env python3
"""
Traffic Camera Emulator — ONVIF Profile S / MJPEG / ANPR
=========================================================
Faithfully emulates a real IP surveillance camera (Hikvision / Axis / Dahua-class)
using industry-standard protocols:

  • ONVIF Device / Media / PTZ / Events services  (SOAP 1.2 over HTTP)
  • MJPEG snapshot endpoint  (real JPEG frames — synthetic but valid format)
  • ANPR (Automatic Number Plate Recognition) data feed  (ISO 14816 schema)
  • WS-Discovery response for network camera auto-detection

Intentionally VULNERABLE for Smart City IDS demo:
  - No ONVIF WS-UsernameToken authentication (any client can call)
  - No TLS — all traffic in clear text
  - ANPR / plate data exposed without access control
  - Debug endpoint leaks firmware + credentials
"""

from flask import Flask, Response, request, jsonify
import time
import os
import random
import struct
import math
import threading
import logging
import uuid
import io
from datetime import datetime, timezone, timedelta
from xml.etree.ElementTree import Element, SubElement, tostring

# ─── App ────────────────────────────────────────────────────────────────────────

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("onvif-camera")

DEVICE_UUID = os.environ.get(
    "DEVICE_UUID",
    str(uuid.uuid5(uuid.NAMESPACE_DNS, "traffic-cam-001.smartcity.local")),
)
FIRMWARE_VERSION = "v6.5.82-230615"
SERIAL_NUMBER = os.environ.get("SERIAL_NUMBER", "SC-TCAM-2024-001")
DEVICE_MODEL = "SC-IPC-B628H-Z"
MANUFACTURER = "SmartCity Instruments"
LOCATION = os.environ.get("CAMERA_LOCATION", "Main St & 1st Ave")
DEVICE_IP = os.environ.get("POD_IP", "10.42.0.50")
ONVIF_PORT = int(os.environ.get("PORT", 5000))

# ─── ONVIF XML namespaces ───────────────────────────────────────────────────────

NS = {
    "soap": "http://www.w3.org/2003/05/soap-envelope",
    "tds":  "http://www.onvif.org/ver10/device/wsdl",
    "trt":  "http://www.onvif.org/ver10/media/wsdl",
    "tptz": "http://www.onvif.org/ver20/ptz/wsdl",
    "tev":  "http://www.onvif.org/ver10/events/wsdl",
    "tt":   "http://www.onvif.org/ver10/schema",
    "wsnt": "http://docs.oasis-open.org/wsn/b-2",
    "wsa":  "http://www.w3.org/2005/08/addressing",
    "wsd":  "http://schemas.xmlsoap.org/ws/2005/04/discovery",
    "d":    "http://schemas.xmlsoap.org/ws/2005/04/discovery",
    "dn":   "http://www.onvif.org/ver10/network/wsdl",
}


# ═════════════════════════════════════════════════════════════════════════════════
# Camera State Machine — emulates real hardware
# ═════════════════════════════════════════════════════════════════════════════════

class CameraState:
    """Real IP camera state emulation with firmware-level detail."""

    STATES = ("idle", "streaming", "recording", "alarm", "maintenance")

    def __init__(self):
        self.state = "idle"
        self.boot_time = time.time()
        # PTZ
        self.pan = 0.0             # -1.0 … +1.0
        self.tilt = 0.0
        self.zoom = 1.0            # 1x … 30x
        # Image settings
        self.ir_mode = "auto"      # auto | on | off
        self.wdr_enabled = True
        self.fps = 25
        self.resolution = (1920, 1080)
        self.bitrate_kbps = 4096
        self.codec = "H.264"
        # Detection
        self.motion_detected = False
        self.motion_region = None
        self.frame_counter = 0
        self.vehicles_counted = 0
        self.last_plate = None
        # Sensor telemetry (real cameras have internal sensors)
        self.temperature_c = 42.0  # CMOS sensor temp
        self.voltage_v = 12.05
        self.storage_used_pct = 23.4
        self.uptime_seconds = 0
        # ANPR rolling buffer
        self.plate_buffer = []
        self.plate_buffer_max = 10000
        # Day / night
        self.day_night = "day"

    def tick(self):
        """Called every second to advance state — mirrors real camera MCU loop."""
        self.uptime_seconds = time.time() - self.boot_time
        # Sensor drift
        self.temperature_c = max(30.0, min(75.0, self.temperature_c + random.gauss(0, 0.05)))
        self.voltage_v = max(11.5, min(12.6, self.voltage_v + random.gauss(0, 0.001)))
        self.storage_used_pct = min(100.0, self.storage_used_pct + random.uniform(0, 0.001))
        self.frame_counter += self.fps
        # Day/night determination
        hour = datetime.now().hour
        self.day_night = "night" if hour < 6 or hour >= 20 else "day"
        self.ir_mode = "on" if self.day_night == "night" else "auto"
        # Motion probability by time of day (rush-hour peaks)
        rush = {7: 0.6, 8: 0.8, 9: 0.5, 16: 0.5, 17: 0.8, 18: 0.6}
        motion_prob = rush.get(hour, 0.15)
        self.motion_detected = random.random() < motion_prob
        if self.motion_detected:
            self.vehicles_counted += random.randint(1, 4)
            self.motion_region = {
                "x": random.randint(100, 1600),
                "y": random.randint(100, 900),
                "w": random.randint(50, 300),
                "h": random.randint(50, 200),
            }
            # ANPR detects ~40 % of vehicles passing
            if random.random() < 0.4:
                plate = self._generate_plate()
                self.last_plate = plate
                self.plate_buffer.append(plate)
                if len(self.plate_buffer) > self.plate_buffer_max:
                    self.plate_buffer.pop(0)

    def _generate_plate(self):
        """Generate realistic ANPR detection record (ISO 14816 schema)."""
        prefixes = ["CA", "NY", "TX", "FL", "WA", "OR", "NV", "AZ"]
        chars = "ABCDEFGHJKLMNPRSTUVWXYZ"
        digits = "0123456789"
        plate_text = (
            f"{random.choice(prefixes)}-"
            f"{random.choice(chars)}{random.choice(chars)}"
            f"{random.choice(digits)}{random.choice(digits)}"
            f"{random.choice(chars)}{random.choice(digits)}"
        )
        return {
            "plate_number": plate_text,
            "confidence": round(random.uniform(0.75, 0.99), 3),
            "country": "US",
            "region": plate_text[:2],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "capture_ms": round(random.uniform(5.0, 45.0), 1),
            "vehicle_class": random.choice(["sedan", "suv", "truck", "van", "motorcycle"]),
            "vehicle_color": random.choice(["white", "black", "silver", "red", "blue", "gray"]),
            "speed_kmh": round(random.gauss(50, 15), 1),
            "lane": random.randint(1, 3),
            "direction": random.choice(["northbound", "southbound", "eastbound", "westbound"]),
            "camera_id": SERIAL_NUMBER,
            "image_ref": f"capture/{int(time.time()*1000)}.jpg",
        }


cam = CameraState()


def _camera_ticker():
    while True:
        cam.tick()
        time.sleep(1.0)


threading.Thread(target=_camera_ticker, daemon=True).start()


# ═════════════════════════════════════════════════════════════════════════════════
# SOAP / ONVIF helpers
# ═════════════════════════════════════════════════════════════════════════════════

def _soap_envelope(body_element):
    """Wrap body in SOAP 1.2 envelope — standard ONVIF wire format."""
    env = Element(f"{{{NS['soap']}}}Envelope")
    for prefix, uri in NS.items():
        env.set(f"xmlns:{prefix}", uri)
    SubElement(env, f"{{{NS['soap']}}}Header")
    body = SubElement(env, f"{{{NS['soap']}}}Body")
    body.append(body_element)
    xml_bytes = (
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        + tostring(env, encoding="unicode").encode()
    )
    return Response(xml_bytes, content_type="application/soap+xml; charset=utf-8")


def _utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_soap_action(data: bytes) -> str:
    """Extract SOAP action from request body."""
    text = data.decode("utf-8", errors="ignore")
    for action in [
        "GetDeviceInformation", "GetCapabilities", "GetSystemDateAndTime",
        "GetProfiles", "GetStreamUri", "GetVideoSources", "GetSnapshotUri",
        "GetNodes", "GetStatus", "GetConfigurations",
        "Subscribe", "PullMessages", "CreatePullPointSubscription",
        "GetServiceCapabilities", "GetScopes", "GetNetworkInterfaces",
    ]:
        if action in text:
            return action
    return "Unknown"


# ═════════════════════════════════════════════════════════════════════════════════
# ONVIF Device Service  (/onvif/device_service)
# ═════════════════════════════════════════════════════════════════════════════════

def _get_device_information():
    resp = Element(f"{{{NS['tds']}}}GetDeviceInformationResponse")
    SubElement(resp, f"{{{NS['tds']}}}Manufacturer").text = MANUFACTURER
    SubElement(resp, f"{{{NS['tds']}}}Model").text = DEVICE_MODEL
    SubElement(resp, f"{{{NS['tds']}}}FirmwareVersion").text = FIRMWARE_VERSION
    SubElement(resp, f"{{{NS['tds']}}}SerialNumber").text = SERIAL_NUMBER
    SubElement(resp, f"{{{NS['tds']}}}HardwareId").text = f"HW-{SERIAL_NUMBER}"
    return _soap_envelope(resp)


def _get_system_date_and_time():
    now = datetime.now(timezone.utc)
    resp = Element(f"{{{NS['tds']}}}GetSystemDateAndTimeResponse")
    sdt = SubElement(resp, f"{{{NS['tds']}}}SystemDateAndTime")
    SubElement(sdt, f"{{{NS['tt']}}}DateTimeType").text = "NTP"
    SubElement(sdt, f"{{{NS['tt']}}}DaylightSavings").text = "false"
    tz_elem = SubElement(sdt, f"{{{NS['tt']}}}TimeZone")
    SubElement(tz_elem, f"{{{NS['tt']}}}TZ").text = "UTC+0"
    utc = SubElement(sdt, f"{{{NS['tt']}}}UTCDateTime")
    t_elem = SubElement(utc, f"{{{NS['tt']}}}Time")
    SubElement(t_elem, f"{{{NS['tt']}}}Hour").text = str(now.hour)
    SubElement(t_elem, f"{{{NS['tt']}}}Minute").text = str(now.minute)
    SubElement(t_elem, f"{{{NS['tt']}}}Second").text = str(now.second)
    d_elem = SubElement(utc, f"{{{NS['tt']}}}Date")
    SubElement(d_elem, f"{{{NS['tt']}}}Year").text = str(now.year)
    SubElement(d_elem, f"{{{NS['tt']}}}Month").text = str(now.month)
    SubElement(d_elem, f"{{{NS['tt']}}}Day").text = str(now.day)
    return _soap_envelope(resp)


def _get_capabilities():
    resp = Element(f"{{{NS['tds']}}}GetCapabilitiesResponse")
    caps = SubElement(resp, f"{{{NS['tds']}}}Capabilities")
    for label, path in [
        ("Device",    "/onvif/device_service"),
        ("Media",     "/onvif/media_service"),
        ("PTZ",       "/onvif/ptz_service"),
        ("Events",    "/onvif/event_service"),
        ("Analytics", "/onvif/analytics_service"),
    ]:
        node = SubElement(caps, f"{{{NS['tt']}}}{label}")
        SubElement(node, f"{{{NS['tt']}}}XAddr").text = f"http://{DEVICE_IP}:{ONVIF_PORT}{path}"
    return _soap_envelope(resp)


def _get_scopes():
    resp = Element(f"{{{NS['tds']}}}GetScopesResponse")
    for s in [
        "onvif://www.onvif.org/type/video_encoder",
        "onvif://www.onvif.org/type/ptz",
        "onvif://www.onvif.org/Profile/Streaming",
        f"onvif://www.onvif.org/location/{LOCATION.replace(' ', '_')}",
        f"onvif://www.onvif.org/name/{DEVICE_MODEL}",
        f"onvif://www.onvif.org/hardware/{DEVICE_MODEL}",
    ]:
        scope = SubElement(resp, f"{{{NS['tds']}}}Scopes")
        SubElement(scope, f"{{{NS['tt']}}}ScopeDef").text = "Fixed"
        SubElement(scope, f"{{{NS['tt']}}}ScopeItem").text = s
    return _soap_envelope(resp)


def _get_network_interfaces():
    resp = Element(f"{{{NS['tds']}}}GetNetworkInterfacesResponse")
    iface = SubElement(resp, f"{{{NS['tds']}}}NetworkInterfaces")
    iface.set("token", "eth0")
    SubElement(iface, f"{{{NS['tt']}}}Enabled").text = "true"
    info = SubElement(iface, f"{{{NS['tt']}}}Info")
    SubElement(info, f"{{{NS['tt']}}}Name").text = "eth0"
    SubElement(info, f"{{{NS['tt']}}}HwAddress").text = "AA:BB:CC:DD:EE:01"
    SubElement(info, f"{{{NS['tt']}}}MTU").text = "1500"
    ipv4 = SubElement(iface, f"{{{NS['tt']}}}IPv4")
    SubElement(ipv4, f"{{{NS['tt']}}}Enabled").text = "true"
    manual = SubElement(ipv4, f"{{{NS['tt']}}}Manual")
    SubElement(manual, f"{{{NS['tt']}}}Address").text = DEVICE_IP
    SubElement(manual, f"{{{NS['tt']}}}PrefixLength").text = "24"
    return _soap_envelope(resp)


@app.route("/onvif/device_service", methods=["POST"])
def onvif_device_service():
    """ONVIF Device Service — SOAP endpoint. VULNERABLE: no WS-UsernameToken."""
    action = _parse_soap_action(request.data)
    logger.info(f"ONVIF Device: {action} from {request.remote_addr}")
    handlers = {
        "GetDeviceInformation": _get_device_information,
        "GetSystemDateAndTime": _get_system_date_and_time,
        "GetCapabilities":      _get_capabilities,
        "GetScopes":            _get_scopes,
        "GetNetworkInterfaces": _get_network_interfaces,
    }
    handler = handlers.get(action)
    if handler:
        return handler()
    return _soap_envelope(Element(f"{{{NS['tds']}}}UnknownActionResponse")), 500


# ═════════════════════════════════════════════════════════════════════════════════
# ONVIF Media Service  (/onvif/media_service)
# ═════════════════════════════════════════════════════════════════════════════════

def _get_profiles():
    resp = Element(f"{{{NS['trt']}}}GetProfilesResponse")
    for name, (w, h, fps, codec) in [
        ("MainStream",  (1920, 1080, 25, "H.264")),
        ("SubStream",   (640,  360,  15, "H.264")),
        ("ThirdStream", (320,  240,  10, "MJPEG")),
    ]:
        prof = SubElement(resp, f"{{{NS['trt']}}}Profiles")
        prof.set("token", name)
        prof.set("fixed", "true")
        SubElement(prof, f"{{{NS['tt']}}}Name").text = name
        # Video source configuration
        vsc = SubElement(prof, f"{{{NS['tt']}}}VideoSourceConfiguration")
        vsc.set("token", "VSC_1")
        SubElement(vsc, f"{{{NS['tt']}}}Name").text = "Primary Source"
        SubElement(vsc, f"{{{NS['tt']}}}SourceToken").text = "VS_1"
        bounds = SubElement(vsc, f"{{{NS['tt']}}}Bounds")
        bounds.set("x", "0"); bounds.set("y", "0")
        bounds.set("width", str(w)); bounds.set("height", str(h))
        # Video encoder configuration
        vec = SubElement(prof, f"{{{NS['tt']}}}VideoEncoderConfiguration")
        vec.set("token", f"VEC_{name}")
        SubElement(vec, f"{{{NS['tt']}}}Name").text = f"{codec} {w}x{h}"
        SubElement(vec, f"{{{NS['tt']}}}Encoding").text = codec
        res = SubElement(vec, f"{{{NS['tt']}}}Resolution")
        SubElement(res, f"{{{NS['tt']}}}Width").text = str(w)
        SubElement(res, f"{{{NS['tt']}}}Height").text = str(h)
        SubElement(vec, f"{{{NS['tt']}}}Quality").text = "6"
        rate = SubElement(vec, f"{{{NS['tt']}}}RateControl")
        SubElement(rate, f"{{{NS['tt']}}}FrameRateLimit").text = str(fps)
        SubElement(rate, f"{{{NS['tt']}}}BitrateLimit").text = str(cam.bitrate_kbps)
        # PTZ configuration
        ptz_cfg = SubElement(prof, f"{{{NS['tt']}}}PTZConfiguration")
        ptz_cfg.set("token", "PTZ_1")
        SubElement(ptz_cfg, f"{{{NS['tt']}}}Name").text = "PTZ Config"
        SubElement(ptz_cfg, f"{{{NS['tt']}}}NodeToken").text = "PTZ_Node_1"
    return _soap_envelope(resp)


def _get_stream_uri():
    resp = Element(f"{{{NS['trt']}}}GetStreamUriResponse")
    uri_el = SubElement(resp, f"{{{NS['trt']}}}MediaUri")
    SubElement(uri_el, f"{{{NS['tt']}}}Uri").text = (
        f"rtsp://{DEVICE_IP}:554/cam/realmonitor?channel=1&subtype=0"
    )
    SubElement(uri_el, f"{{{NS['tt']}}}InvalidAfterConnect").text = "false"
    SubElement(uri_el, f"{{{NS['tt']}}}InvalidAfterReboot").text = "false"
    SubElement(uri_el, f"{{{NS['tt']}}}Timeout").text = "PT60S"
    return _soap_envelope(resp)


def _get_snapshot_uri():
    resp = Element(f"{{{NS['trt']}}}GetSnapshotUriResponse")
    uri_el = SubElement(resp, f"{{{NS['trt']}}}MediaUri")
    SubElement(uri_el, f"{{{NS['tt']}}}Uri").text = (
        f"http://{DEVICE_IP}:{ONVIF_PORT}/snap.jpg"
    )
    SubElement(uri_el, f"{{{NS['tt']}}}InvalidAfterConnect").text = "false"
    SubElement(uri_el, f"{{{NS['tt']}}}InvalidAfterReboot").text = "false"
    SubElement(uri_el, f"{{{NS['tt']}}}Timeout").text = "PT60S"
    return _soap_envelope(resp)


def _get_video_sources():
    resp = Element(f"{{{NS['trt']}}}GetVideoSourcesResponse")
    vs = SubElement(resp, f"{{{NS['trt']}}}VideoSources")
    vs.set("token", "VS_1")
    SubElement(vs, f"{{{NS['tt']}}}Framerate").text = str(cam.fps)
    res = SubElement(vs, f"{{{NS['tt']}}}Resolution")
    SubElement(res, f"{{{NS['tt']}}}Width").text = str(cam.resolution[0])
    SubElement(res, f"{{{NS['tt']}}}Height").text = str(cam.resolution[1])
    return _soap_envelope(resp)


@app.route("/onvif/media_service", methods=["POST"])
def onvif_media_service():
    """ONVIF Media Service — profiles, stream URIs, snapshots."""
    action = _parse_soap_action(request.data)
    logger.info(f"ONVIF Media: {action} from {request.remote_addr}")
    handlers = {
        "GetProfiles":            _get_profiles,
        "GetStreamUri":           _get_stream_uri,
        "GetSnapshotUri":         _get_snapshot_uri,
        "GetVideoSources":        _get_video_sources,
        "GetServiceCapabilities": lambda: _soap_envelope(
            Element(f"{{{NS['trt']}}}GetServiceCapabilitiesResponse")
        ),
    }
    handler = handlers.get(action)
    if handler:
        return handler()
    return _soap_envelope(Element(f"{{{NS['trt']}}}UnknownActionResponse")), 500


# ═════════════════════════════════════════════════════════════════════════════════
# ONVIF PTZ Service  (/onvif/ptz_service)
# ═════════════════════════════════════════════════════════════════════════════════

@app.route("/onvif/ptz_service", methods=["POST"])
def onvif_ptz_service():
    """ONVIF PTZ Service — pan/tilt/zoom control."""
    action = _parse_soap_action(request.data)
    logger.info(f"ONVIF PTZ: {action} from {request.remote_addr}")

    if action == "GetNodes":
        resp = Element(f"{{{NS['tptz']}}}GetNodesResponse")
        node = SubElement(resp, f"{{{NS['tptz']}}}PTZNode")
        node.set("token", "PTZ_Node_1")
        SubElement(node, f"{{{NS['tt']}}}Name").text = "PTZ Motor"
        space = SubElement(node, f"{{{NS['tt']}}}SupportedPTZSpaces")
        pt = SubElement(space, f"{{{NS['tt']}}}AbsolutePanTiltPositionSpace")
        SubElement(pt, f"{{{NS['tt']}}}URI").text = (
            "http://www.onvif.org/ver10/tptz/PanTiltSpaces/PositionGenericSpace"
        )
        xr = SubElement(pt, f"{{{NS['tt']}}}XRange")
        SubElement(xr, f"{{{NS['tt']}}}Min").text = "-1.0"
        SubElement(xr, f"{{{NS['tt']}}}Max").text = "1.0"
        yr = SubElement(pt, f"{{{NS['tt']}}}YRange")
        SubElement(yr, f"{{{NS['tt']}}}Min").text = "-1.0"
        SubElement(yr, f"{{{NS['tt']}}}Max").text = "1.0"
        return _soap_envelope(resp)

    if action == "GetStatus":
        resp = Element(f"{{{NS['tptz']}}}GetStatusResponse")
        status = SubElement(resp, f"{{{NS['tptz']}}}PTZStatus")
        pos = SubElement(status, f"{{{NS['tt']}}}Position")
        pt = SubElement(pos, f"{{{NS['tt']}}}PanTilt")
        pt.set("x", f"{cam.pan:.4f}")
        pt.set("y", f"{cam.tilt:.4f}")
        zm = SubElement(pos, f"{{{NS['tt']}}}Zoom")
        zm.set("x", f"{cam.zoom:.4f}")
        SubElement(status, f"{{{NS['tt']}}}MoveStatus").text = "IDLE"
        SubElement(status, f"{{{NS['tt']}}}UtcTime").text = _utc_now()
        return _soap_envelope(resp)

    return _soap_envelope(Element(f"{{{NS['tptz']}}}UnknownActionResponse")), 500


# ═════════════════════════════════════════════════════════════════════════════════
# ONVIF Event Service  (/onvif/event_service)
# ═════════════════════════════════════════════════════════════════════════════════

@app.route("/onvif/event_service", methods=["POST"])
def onvif_event_service():
    """ONVIF Event Service — motion / tamper / analytics events."""
    action = _parse_soap_action(request.data)
    logger.info(f"ONVIF Event: {action} from {request.remote_addr}")

    if action in ("CreatePullPointSubscription", "Subscribe"):
        resp = Element(f"{{{NS['tev']}}}CreatePullPointSubscriptionResponse")
        ref = SubElement(resp, f"{{{NS['tev']}}}SubscriptionReference")
        addr = SubElement(ref, f"{{{NS['wsa']}}}Address")
        addr.text = (
            f"http://{DEVICE_IP}:{ONVIF_PORT}/onvif/event_service/sub/"
            f"{uuid.uuid4().hex[:8]}"
        )
        SubElement(resp, f"{{{NS['wsnt']}}}CurrentTime").text = _utc_now()
        SubElement(resp, f"{{{NS['wsnt']}}}TerminationTime").text = (
            datetime.now(timezone.utc) + timedelta(hours=1)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        return _soap_envelope(resp)

    if action == "PullMessages":
        resp = Element(f"{{{NS['tev']}}}PullMessagesResponse")
        SubElement(resp, f"{{{NS['tev']}}}CurrentTime").text = _utc_now()
        SubElement(resp, f"{{{NS['tev']}}}TerminationTime").text = (
            datetime.now(timezone.utc) + timedelta(hours=1)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        if cam.motion_detected:
            msg = SubElement(resp, f"{{{NS['wsnt']}}}NotificationMessage")
            topic = SubElement(msg, f"{{{NS['wsnt']}}}Topic")
            topic.set("Dialect", "http://www.onvif.org/ver10/tev/topicExpression/ConcreteSet")
            topic.text = "tns1:RuleEngine/CellMotionDetector/Motion"
            message = SubElement(msg, f"{{{NS['wsnt']}}}Message")
            message.set("UtcTime", _utc_now())
            data = SubElement(message, f"{{{NS['tt']}}}Data")
            si = SubElement(data, f"{{{NS['tt']}}}SimpleItem")
            si.set("Name", "IsMotion")
            si.set("Value", "true")
        return _soap_envelope(resp)

    return _soap_envelope(Element(f"{{{NS['tev']}}}UnknownActionResponse")), 500


# ═════════════════════════════════════════════════════════════════════════════════
# MJPEG snapshot — valid JPEG frames
# ═════════════════════════════════════════════════════════════════════════════════

def _generate_jpeg_frame():
    """Generate a minimal valid JPEG image with embedded metadata.

    Produces an 8x8 pixel JFIF JPEG with timestamp and vehicle-count
    data in a COM marker — exactly what forensic tools can parse.
    """
    w, h = 8, 8
    buf = io.BytesIO()
    # SOI
    buf.write(b"\xff\xd8")
    # APP0 JFIF
    app0 = b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    buf.write(b"\xff\xe0")
    buf.write(struct.pack(">H", len(app0) + 2))
    buf.write(app0)
    # COM marker with device metadata
    comment = (
        f"Camera:{SERIAL_NUMBER} Frame:{cam.frame_counter} "
        f"Time:{_utc_now()} Vehicles:{cam.vehicles_counted}"
    ).encode()
    buf.write(b"\xff\xfe")
    buf.write(struct.pack(">H", len(comment) + 2))
    buf.write(comment)
    # DQT
    dqt = bytes([0] + [1] * 64)
    buf.write(b"\xff\xdb")
    buf.write(struct.pack(">H", len(dqt) + 2))
    buf.write(dqt)
    # SOF0
    sof = struct.pack(">BHHB", 8, h, w, 1)
    sof += struct.pack("BBB", 1, 0x11, 0)
    buf.write(b"\xff\xc0")
    buf.write(struct.pack(">H", len(sof) + 2))
    buf.write(sof)
    # DHT
    dht = bytes([0x00]) + bytes([1] + [0] * 15) + bytes([0x00])
    buf.write(b"\xff\xc4")
    buf.write(struct.pack(">H", len(dht) + 2))
    buf.write(dht)
    # SOS
    sos = struct.pack("B", 1) + struct.pack("BB", 1, 0x00) + bytes([0, 0, 0])
    buf.write(b"\xff\xda")
    buf.write(struct.pack(">H", len(sos) + 2))
    buf.write(sos)
    buf.write(bytes([0x00]))
    # EOI
    buf.write(b"\xff\xd9")
    return buf.getvalue()


@app.route("/snap.jpg", methods=["GET"])
def snapshot():
    """ONVIF-compatible JPEG snapshot endpoint (real JPEG format)."""
    frame = _generate_jpeg_frame()
    return Response(
        frame,
        content_type="image/jpeg",
        headers={
            "X-Frame-Timestamp": _utc_now(),
            "X-Vehicle-Count": str(cam.vehicles_counted),
        },
    )


@app.route("/mjpeg", methods=["GET"])
def mjpeg_stream():
    """MJPEG live stream — real multipart/x-mixed-replace as used by IP cameras."""
    def generate():
        while True:
            frame = _generate_jpeg_frame()
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Content-Length: " + str(len(frame)).encode() + b"\r\n\r\n"
                + frame + b"\r\n"
            )
            time.sleep(1.0 / 5)
    return Response(generate(), content_type="multipart/x-mixed-replace; boundary=frame")


# ═════════════════════════════════════════════════════════════════════════════════
# ANPR Data Feed  (ISO 14816 schema)
# ═════════════════════════════════════════════════════════════════════════════════

@app.route("/api/anpr/detections", methods=["GET"])
def anpr_detections():
    """ANPR plate detection feed — VULNERABLE: no auth, PII exposed!"""
    limit = min(int(request.args.get("limit", 50)), 500)
    since_ts = request.args.get("since")
    records = cam.plate_buffer[-limit:]
    if since_ts:
        records = [r for r in records if r["timestamp"] >= since_ts]
    return jsonify({
        "camera_id": SERIAL_NUMBER,
        "location": LOCATION,
        "total_detections": len(cam.plate_buffer),
        "returned": len(records),
        "detections": records,
    })


@app.route("/api/anpr/statistics", methods=["GET"])
def anpr_statistics():
    """ANPR aggregate statistics."""
    plates = cam.plate_buffer
    if not plates:
        return jsonify({"total": 0})
    speeds = [p["speed_kmh"] for p in plates]
    by_class = {}
    for p in plates:
        by_class[p["vehicle_class"]] = by_class.get(p["vehicle_class"], 0) + 1
    return jsonify({
        "total_detections": len(plates),
        "avg_speed_kmh": round(sum(speeds) / len(speeds), 1),
        "max_speed_kmh": round(max(speeds), 1),
        "vehicle_classes": by_class,
        "avg_confidence": round(sum(p["confidence"] for p in plates) / len(plates), 3),
        "timespan_start": plates[0]["timestamp"],
        "timespan_end": plates[-1]["timestamp"],
    })


# ═════════════════════════════════════════════════════════════════════════════════
# Camera Telemetry  (Hikvision ISAPI / Dahua CGI style)
# ═════════════════════════════════════════════════════════════════════════════════

@app.route("/api/telemetry", methods=["GET"])
def telemetry():
    """Internal sensor telemetry (ISAPI/CGI-compatible)."""
    return jsonify({
        "device_id": SERIAL_NUMBER,
        "uptime_seconds": round(cam.uptime_seconds),
        "cmos_temperature_c": round(cam.temperature_c, 1),
        "input_voltage_v": round(cam.voltage_v, 2),
        "storage_used_pct": round(cam.storage_used_pct, 1),
        "state": cam.state,
        "day_night_mode": cam.day_night,
        "ir_status": cam.ir_mode,
        "wdr_enabled": cam.wdr_enabled,
        "current_fps": cam.fps,
        "resolution": f"{cam.resolution[0]}x{cam.resolution[1]}",
        "codec": cam.codec,
        "bitrate_kbps": cam.bitrate_kbps,
        "ptz": {
            "pan": round(cam.pan, 4),
            "tilt": round(cam.tilt, 4),
            "zoom": round(cam.zoom, 2),
        },
        "frame_counter": cam.frame_counter,
        "motion_active": cam.motion_detected,
        "vehicles_total": cam.vehicles_counted,
        "last_plate": cam.last_plate,
    })


# ═════════════════════════════════════════════════════════════════════════════════
# WS-Discovery  (camera auto-detection by NVR / VMS)
# ═════════════════════════════════════════════════════════════════════════════════

@app.route("/ws-discovery", methods=["GET"])
def ws_discovery():
    """WS-Discovery Probe response — how NVRs find cameras on the network."""
    resp = Element(f"{{{NS['soap']}}}Envelope")
    for prefix, uri in NS.items():
        resp.set(f"xmlns:{prefix}", uri)
    body = SubElement(resp, f"{{{NS['soap']}}}Body")
    probe_match = SubElement(body, f"{{{NS['d']}}}ProbeMatches")
    match = SubElement(probe_match, f"{{{NS['d']}}}ProbeMatch")
    addr = SubElement(match, f"{{{NS['wsa']}}}EndpointReference")
    SubElement(addr, f"{{{NS['wsa']}}}Address").text = f"urn:uuid:{DEVICE_UUID}"
    SubElement(match, f"{{{NS['d']}}}Types").text = "dn:NetworkVideoTransmitter tds:Device"
    SubElement(match, f"{{{NS['d']}}}Scopes").text = (
        f"onvif://www.onvif.org/name/{DEVICE_MODEL} "
        f"onvif://www.onvif.org/location/{LOCATION.replace(' ', '_')}"
    )
    SubElement(match, f"{{{NS['d']}}}XAddrs").text = (
        f"http://{DEVICE_IP}:{ONVIF_PORT}/onvif/device_service"
    )
    SubElement(match, f"{{{NS['d']}}}MetadataVersion").text = "1"
    xml_bytes = (
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        + tostring(resp, encoding="unicode").encode()
    )
    return Response(xml_bytes, content_type="application/soap+xml; charset=utf-8")


# ═════════════════════════════════════════════════════════════════════════════════
# Debug / Admin  (VULNERABILITY: firmware + creds exposure)
# ═════════════════════════════════════════════════════════════════════════════════

@app.route("/api/debug/config", methods=["GET"])
def debug_config():
    """VULNERABILITY: Exposes firmware config + hardcoded credentials."""
    logger.warning(f"DEBUG CONFIG accessed from {request.remote_addr} — credentials EXPOSED")
    return jsonify({
        "firmware": FIRMWARE_VERSION,
        "serial": SERIAL_NUMBER,
        "admin_user": "admin",
        "admin_password": "admin123",
        "rtsp_auth": "disabled",
        "onvif_auth": "disabled",
        "telnet_enabled": True,
        "ssh_enabled": False,
        "ntp_server": "pool.ntp.org",
        "dns": ["8.8.8.8", "8.8.4.4"],
        "gateway": "10.42.0.1",
        "manufacturer_backdoor_port": 9527,
    })


# ═════════════════════════════════════════════════════════════════════════════════
# Legacy REST endpoints (backward compatible with existing IDS integration)
# ═════════════════════════════════════════════════════════════════════════════════

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy",
        "service": "traffic-camera-onvif",
        "protocol": "ONVIF Profile S",
        "firmware": FIRMWARE_VERSION,
        "uptime": round(cam.uptime_seconds),
    }), 200


@app.route("/api/cameras", methods=["GET"])
def get_cameras():
    """Legacy camera list — now backed by real ONVIF device state."""
    return jsonify({
        "cameras": {
            SERIAL_NUMBER: {
                "location": LOCATION,
                "status": cam.state,
                "vehicles_detected": cam.vehicles_counted,
                "resolution": f"{cam.resolution[0]}x{cam.resolution[1]}",
                "day_night": cam.day_night,
                "motion_active": cam.motion_detected,
                "onvif_url": f"http://{DEVICE_IP}:{ONVIF_PORT}/onvif/device_service",
                "rtsp_url": f"rtsp://{DEVICE_IP}:554/cam/realmonitor?channel=1&subtype=0",
                "snapshot_url": f"http://{DEVICE_IP}:{ONVIF_PORT}/snap.jpg",
            }
        },
        "count": 1,
    }), 200


@app.route("/api/plates", methods=["GET"])
def get_plates():
    """ANPR data — VULNERABLE: PII without auth."""
    limit = min(int(request.args.get("limit", 50)), 500)
    return jsonify({
        "plates": cam.plate_buffer[-limit:],
        "total": len(cam.plate_buffer),
    }), 200


@app.route("/api/plates", methods=["POST"])
def add_plate():
    """Manual plate entry — VULNERABLE: no input validation."""
    data = request.get_json(silent=True) or {}
    plate = {
        "plate_number": data.get("plate", "UNKNOWN"),
        "confidence": 1.0,
        "country": "US",
        "region": "manual",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "capture_ms": 0,
        "vehicle_class": data.get("vehicle_class", "unknown"),
        "vehicle_color": data.get("color", "unknown"),
        "speed_kmh": data.get("speed", 0),
        "lane": 0,
        "direction": "unknown",
        "camera_id": SERIAL_NUMBER,
        "image_ref": None,
    }
    cam.plate_buffer.append(plate)
    return jsonify({"status": "logged", "plate": plate}), 201


@app.route("/api/analytics", methods=["GET"])
def get_analytics():
    """Traffic analytics endpoint."""
    return jsonify({
        "total_vehicles": cam.vehicles_counted,
        "active_cameras": 1,
        "plates_logged": len(cam.plate_buffer),
        "avg_speed_kmh": (
            round(sum(p["speed_kmh"] for p in cam.plate_buffer[-50:]) / max(1, len(cam.plate_buffer[-50:])), 1)
            if cam.plate_buffer else 0
        ),
    }), 200


@app.route("/api/stats", methods=["GET"])
def get_stats():
    return jsonify({
        "service": "traffic-camera-onvif",
        "protocol_version": "ONVIF 21.06",
        "device_model": DEVICE_MODEL,
        "firmware": FIRMWARE_VERSION,
        "vehicles_total": cam.vehicles_counted,
        "plates_detected": len(cam.plate_buffer),
        "uptime_seconds": round(cam.uptime_seconds),
        "frames_processed": cam.frame_counter,
    }), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"Starting ONVIF Camera Emulator ({DEVICE_MODEL}) on port {port}")
    logger.info(f"  Serial: {SERIAL_NUMBER} | Location: {LOCATION}")
    logger.info(f"  ONVIF Device:  http://0.0.0.0:{port}/onvif/device_service")
    logger.info(f"  MJPEG Stream:  http://0.0.0.0:{port}/mjpeg")
    logger.info(f"  Snapshot:      http://0.0.0.0:{port}/snap.jpg")
    logger.info(f"  ANPR Feed:     http://0.0.0.0:{port}/api/anpr/detections")
    logger.info(f"  WS-Discovery:  http://0.0.0.0:{port}/ws-discovery")
    logger.info(f"  WARNING: Auth DISABLED — intentionally vulnerable for IDS demo")
    app.run(host="0.0.0.0", port=port, debug=False)
