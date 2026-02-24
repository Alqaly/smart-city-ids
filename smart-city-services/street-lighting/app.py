"""
Smart City Street Lighting Emulator
Protocol-accurate: DALI-2 (IEC 62386) + TALQ Smart City Protocol

Emulates a network of smart LED street lights with:
- DALI-2 digital dimming (IEC 62386 gear/device commands)
- TALQ v2.4 outdoor lighting management API
- Luminaire-level monitoring (power, lumen, temp)
- Astronomical clock + motion-adaptive dimming
- Fault detection: lamp failure, driver fault, communication loss

Luminaire specs based on real smart city LED fixtures:
- Philips Luma / Iridium / Signify
- 50W-150W LED, 4000K CCT, CRI>70
- 0-100% DALI dimming, integrated tilt sensor
"""

from flask import Flask, request, jsonify
import os
import time, random, math, threading
from datetime import datetime, timezone

app = Flask(__name__)

# ── Luminaire Fleet ──
NUM_LUMINAIRES = max(1, int(os.environ.get("DEVICE_COUNT", os.environ.get("NUM_LUMINAIRES", "120"))))
ZONES = ["main-road", "residential", "park", "highway", "pedestrian", "parking-lot"]
LUMINAIRE_MODELS = [
    {"model": "SL-LED-150W", "wattage": 150, "lumens": 21000, "cct": 4000, "cri": 72, "driver": "DALI-2 D4i"},
    {"model": "SL-LED-100W", "wattage": 100, "lumens": 14000, "cct": 4000, "cri": 75, "driver": "DALI-2 D4i"},
    {"model": "SL-LED-50W", "wattage": 50, "lumens": 7000, "cct": 3000, "cri": 80, "driver": "DALI-2 D4i"},
]

# ── DALI-2 Command Set (IEC 62386) ──
DALI_COMMANDS = {
    0x00: "OFF",
    0x05: "RECALL_MAX_LEVEL",
    0x06: "RECALL_MIN_LEVEL",
    0x20: "STEP_DOWN_AND_OFF",
    0x08: "STEP_UP_AND_ON",
    0xA3: "QUERY_ACTUAL_LEVEL",
    0xA0: "QUERY_STATUS",
    0xA5: "QUERY_LAMP_FAILURE",
    0xA6: "QUERY_LAMP_POWER_ON",
    0x90: "QUERY_ACTUAL_LEVEL",
    0xFE: "QUERY_GEAR_TYPE",
}

# ── TALQ Configuration ──
TALQ_VERSION = "2.4.0"
TALQ_GATEWAY_ID = "GW-LIGHT-001"

# ── Dimming Profiles (TALQ astronomical + adaptive) ──
DIMMING_PROFILES = {
    "main-road":    {"sunset_offset": 0, "full": 100, "late_night": 70, "deep_night": 50, "dawn": 80},
    "residential":  {"sunset_offset": -15, "full": 80, "late_night": 50, "deep_night": 30, "dawn": 60},
    "park":         {"sunset_offset": 0, "full": 70, "late_night": 40, "deep_night": 20, "dawn": 50},
    "highway":      {"sunset_offset": 0, "full": 100, "late_night": 100, "deep_night": 80, "dawn": 100},
    "pedestrian":   {"sunset_offset": 10, "full": 90, "late_night": 60, "deep_night": 30, "dawn": 70},
    "parking-lot":  {"sunset_offset": -10, "full": 100, "late_night": 60, "deep_night": 40, "dawn": 80},
}


# ── State ──
luminaires = {}
_start_time = time.time()
_lock = threading.Lock()
_energy_total_kwh = 0.0


def _init_fleet():
    global luminaires
    for i in range(NUM_LUMINAIRES):
        lid = f"LUM-{i+1:04d}"
        zone = ZONES[i % len(ZONES)]
        model = LUMINAIRE_MODELS[i % len(LUMINAIRE_MODELS)]
        luminaires[lid] = {
            "luminaire_id": lid,
            "model": model["model"],
            "wattage_max": model["wattage"],
            "lumens_max": model["lumens"],
            "cct_k": model["cct"],
            "cri": model["cri"],
            "driver": model["driver"],
            "zone": zone,
            "pole_id": f"POLE-{i+1:04d}",
            "gps": {
                "lat": 37.7749 + random.uniform(-0.01, 0.01),
                "lon": -122.4194 + random.uniform(-0.01, 0.01),
            },
            "dali_address": i % 64,  # DALI short address 0-63
            "dali_group": ZONES.index(zone),
            "dim_level": 0,  # 0-254 DALI arc power
            "dim_pct": 0,
            "actual_power_w": 0,
            "actual_lumens": 0,
            "driver_temp_c": 25.0,
            "led_temp_c": 25.0,
            "tilt_deg": 0.0,
            "operating_hours": random.randint(5000, 35000),
            "status": "off",
            "lamp_failure": False,
            "driver_fault": False,
            "comm_fault": False,
            "energy_kwh": random.uniform(50, 500),
            "last_motion": None,
            "firmware": "v2.1.4-DALI2",
        }


_init_fleet()


def _get_target_dim(zone):
    """Calculate target dimming based on time of day (astronomical clock)."""
    hour = datetime.now(timezone.utc).hour
    profile = DIMMING_PROFILES.get(zone, DIMMING_PROFILES["main-road"])

    # Simplified astronomical clock
    if 6 <= hour < 18:  # Daytime
        return 0  # Lights off
    elif 18 <= hour < 21:  # Evening full
        return profile["full"]
    elif 21 <= hour < 24:  # Late night
        return profile["late_night"]
    elif 0 <= hour < 4:  # Deep night
        return profile["deep_night"]
    else:  # Dawn (4-6)
        return profile["dawn"]


def _update_luminaires():
    """Update all luminaire states — DALI dimming + fault injection."""
    global _energy_total_kwh
    with _lock:
        for lid, lum in luminaires.items():
            target_pct = _get_target_dim(lum["zone"])

            # Motion boost: if motion detected, boost to full for that zone
            if lum["last_motion"] and (time.time() - lum["last_motion"]) < 120:
                target_pct = min(100, target_pct + 30)

            # Random motion events (simulate PIR sensor triggers)
            if random.random() < 0.03 and lum["zone"] in ("pedestrian", "park", "parking-lot"):
                lum["last_motion"] = time.time()

            # DALI arc power: 0-254
            lum["dim_level"] = int(target_pct * 254 / 100) if target_pct > 0 else 0
            lum["dim_pct"] = target_pct

            # Power and lumens based on dimming
            if target_pct > 0 and not lum["lamp_failure"]:
                lum["actual_power_w"] = round(lum["wattage_max"] * (target_pct / 100) ** 1.3, 1)  # Non-linear
                lum["actual_lumens"] = int(lum["lumens_max"] * target_pct / 100)
                lum["status"] = "on"
            else:
                lum["actual_power_w"] = 0
                lum["actual_lumens"] = 0
                lum["status"] = "off" if not lum["lamp_failure"] else "fault"

            # Thermal model
            ambient = 15 + 10 * math.sin((datetime.now(timezone.utc).hour - 6) * math.pi / 12)
            lum["driver_temp_c"] = round(ambient + lum["actual_power_w"] * 0.25 + random.gauss(0, 1), 1)
            lum["led_temp_c"] = round(ambient + lum["actual_power_w"] * 0.35 + random.gauss(0, 1.5), 1)

            # Tilt sensor (wind/vandalism)
            lum["tilt_deg"] = round(random.gauss(0, 0.5), 1)

            # Energy accumulation (5s interval → kWh)
            lum["energy_kwh"] += lum["actual_power_w"] * 5 / 3600000
            _energy_total_kwh += lum["actual_power_w"] * 5 / 3600000

            # Fault injection (low probability — for IDS testing)
            if random.random() < 0.001:
                lum["lamp_failure"] = True
                lum["status"] = "fault"
            if random.random() < 0.0005:
                lum["driver_fault"] = True
            if random.random() < 0.0003:
                lum["comm_fault"] = True

            # Auto-recovery from faults
            if lum["lamp_failure"] and random.random() < 0.01:
                lum["lamp_failure"] = False
            if lum["driver_fault"] and random.random() < 0.02:
                lum["driver_fault"] = False
            if lum["comm_fault"] and random.random() < 0.05:
                lum["comm_fault"] = False

            lum["operating_hours"] += 5 / 3600


def _run_loop():
    while True:
        _update_luminaires()
        time.sleep(5)


threading.Thread(target=_run_loop, daemon=True).start()
_update_luminaires()


# ── DALI-2 Protocol Endpoints ──
@app.route("/dali/command", methods=["POST"])
def dali_command():
    """Simulate DALI-2 forward frame (IEC 62386).
    
    Body: {"address": 0-63 or "broadcast", "command": 0x00-0xFF, "data": optional}
    """
    body = request.get_json(force=True) or {}
    addr = body.get("address", "broadcast")
    cmd = body.get("command", 0xA3)
    cmd_name = DALI_COMMANDS.get(cmd, f"UNKNOWN_{cmd:#04x}")

    targets = []
    if addr == "broadcast":
        targets = list(luminaires.values())
    else:
        targets = [l for l in luminaires.values() if l["dali_address"] == addr]

    if not targets:
        return jsonify({"error": "No gear at address", "dali_status": "NO_REPLY"}), 404

    responses = []
    for lum in targets:
        if cmd == 0xA3 or cmd == 0x90:  # QUERY_ACTUAL_LEVEL
            responses.append({"address": lum["dali_address"], "luminaire": lum["luminaire_id"], "reply": lum["dim_level"]})
        elif cmd == 0xA0:  # QUERY_STATUS
            status_byte = 0
            if lum["lamp_failure"]: status_byte |= 0x02
            if lum["driver_fault"]: status_byte |= 0x04
            if lum["dim_level"] > 0: status_byte |= 0x08
            responses.append({"address": lum["dali_address"], "luminaire": lum["luminaire_id"], "reply": status_byte})
        elif cmd == 0xA5:  # QUERY_LAMP_FAILURE
            responses.append({"address": lum["dali_address"], "luminaire": lum["luminaire_id"], "reply": 1 if lum["lamp_failure"] else 0})
        elif cmd == 0x00:  # OFF
            lum["dim_level"] = 0
            lum["dim_pct"] = 0
            responses.append({"address": lum["dali_address"], "luminaire": lum["luminaire_id"], "reply": "OK"})
        elif cmd == 0x05:  # RECALL_MAX
            lum["dim_level"] = 254
            lum["dim_pct"] = 100
            responses.append({"address": lum["dali_address"], "luminaire": lum["luminaire_id"], "reply": "OK"})
        else:
            responses.append({"address": lum["dali_address"], "luminaire": lum["luminaire_id"], "reply": f"CMD_{cmd_name}"})

    return jsonify({
        "protocol": "DALI-2",
        "iec_standard": "IEC 62386",
        "command": cmd_name,
        "command_code": f"{cmd:#04x}",
        "target_address": addr,
        "responses": responses,
    })


@app.route("/dali/gear", methods=["GET"])
def dali_gear():
    """List all DALI gear (luminaires) with status."""
    gear = []
    for lum in luminaires.values():
        gear.append({
            "short_address": lum["dali_address"],
            "luminaire_id": lum["luminaire_id"],
            "gear_type": "LED driver",
            "actual_level": lum["dim_level"],
            "dim_pct": lum["dim_pct"],
            "status": lum["status"],
            "lamp_failure": lum["lamp_failure"],
            "driver_fault": lum["driver_fault"],
        })
    return jsonify({"protocol": "DALI-2", "gear_count": len(gear), "gear": gear[:64]})  # DALI max 64


# ── TALQ Protocol Endpoints ──
@app.route("/talq/gateway", methods=["GET"])
def talq_gateway():
    """TALQ v2.4 gateway information."""
    return jsonify({
        "talq_version": TALQ_VERSION,
        "gateway_id": TALQ_GATEWAY_ID,
        "gateway_type": "Smart Street Lighting Controller",
        "manufacturer": "SmartCity Systems",
        "model": "SLC-4000",
        "firmware": "v4.2.1-TALQ",
        "luminaires_managed": NUM_LUMINAIRES,
        "communication": {
            "uplink": "4G LTE-M Cat-M1",
            "downlink": "DALI-2 bus (IEC 62386)",
            "mesh": "6LoWPAN / Thread",
        },
        "features": [
            "astronomical_clock",
            "adaptive_dimming",
            "motion_detection",
            "energy_metering",
            "fault_detection",
            "tilt_monitoring",
        ],
    })


@app.route("/talq/outdoor-light-points", methods=["GET"])
def talq_light_points():
    """TALQ v2.4 OutdoorLightPoint resource (paginated)."""
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))
    zone_filter = request.args.get("zone")

    filtered = list(luminaires.values())
    if zone_filter:
        filtered = [l for l in filtered if l["zone"] == zone_filter]

    start = (page - 1) * per_page
    items = filtered[start:start + per_page]

    return jsonify({
        "talq_version": TALQ_VERSION,
        "resource_type": "OutdoorLightPoint",
        "total": len(filtered),
        "page": page,
        "per_page": per_page,
        "items": [{
            "id": lum["luminaire_id"],
            "pole_id": lum["pole_id"],
            "gps": lum["gps"],
            "zone": lum["zone"],
            "model": lum["model"],
            "dim_level_pct": lum["dim_pct"],
            "actual_power_w": lum["actual_power_w"],
            "actual_lumens": lum["actual_lumens"],
            "driver_temp_c": lum["driver_temp_c"],
            "led_temp_c": lum["led_temp_c"],
            "tilt_deg": lum["tilt_deg"],
            "operating_hours": int(lum["operating_hours"]),
            "energy_kwh": round(lum["energy_kwh"], 2),
            "status": lum["status"],
            "lamp_failure": lum["lamp_failure"],
            "driver_fault": lum["driver_fault"],
            "comm_fault": lum["comm_fault"],
        } for lum in items],
    })


# ── REST Management API ──
@app.route("/health")
def health():
    return jsonify({
        "status": "healthy",
        "service": "smart-street-lighting-emulator",
        "protocol": "DALI-2 (IEC 62386) + TALQ v2.4",
        "uptime": int(time.time() - _start_time),
        "luminaires": NUM_LUMINAIRES,
        "firmware": "v4.2.1-TALQ",
    })


@app.route("/api/stats")
def api_stats():
    """Dashboard summary statistics."""
    on_count = sum(1 for l in luminaires.values() if l["status"] == "on")
    fault_count = sum(1 for l in luminaires.values() if l["lamp_failure"] or l["driver_fault"])
    total_power = sum(l["actual_power_w"] for l in luminaires.values())
    total_lumens = sum(l["actual_lumens"] for l in luminaires.values())
    avg_dim = sum(l["dim_pct"] for l in luminaires.values()) / len(luminaires) if luminaires else 0

    zone_stats = {}
    for zone in ZONES:
        zone_lums = [l for l in luminaires.values() if l["zone"] == zone]
        zone_stats[zone] = {
            "count": len(zone_lums),
            "on": sum(1 for l in zone_lums if l["status"] == "on"),
            "avg_dim_pct": round(sum(l["dim_pct"] for l in zone_lums) / len(zone_lums), 1) if zone_lums else 0,
            "power_w": round(sum(l["actual_power_w"] for l in zone_lums), 1),
        }

    return jsonify({
        "service": "smart-street-lighting-emulator",
        "protocol": "DALI-2 + TALQ v2.4",
        "luminaires_total": NUM_LUMINAIRES,
        "luminaires_on": on_count,
        "luminaires_fault": fault_count,
        "total_power_w": round(total_power, 1),
        "total_lumens": total_lumens,
        "avg_dim_pct": round(avg_dim, 1),
        "energy_total_kwh": round(_energy_total_kwh, 2),
        "zones": zone_stats,
        "uptime_seconds": int(time.time() - _start_time),
    })


@app.route("/api/telemetry")
def api_telemetry():
    """Real-time telemetry snapshot."""
    zone_summary = {}
    for zone in ZONES:
        lums = [l for l in luminaires.values() if l["zone"] == zone]
        zone_summary[zone] = {
            "count": len(lums),
            "on": sum(1 for l in lums if l["status"] == "on"),
            "faults": sum(1 for l in lums if l["lamp_failure"] or l["driver_fault"]),
            "avg_dim_pct": round(sum(l["dim_pct"] for l in lums) / len(lums), 1) if lums else 0,
            "total_power_w": round(sum(l["actual_power_w"] for l in lums), 1),
        }

    return jsonify({
        "luminaires_total": NUM_LUMINAIRES,
        "zones": zone_summary,
        "total_power_w": round(sum(l["actual_power_w"] for l in luminaires.values()), 1),
        "energy_total_kwh": round(_energy_total_kwh, 2),
        "faults": sum(1 for l in luminaires.values() if l["lamp_failure"] or l["driver_fault"]),
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
