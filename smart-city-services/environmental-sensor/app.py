"""
Smart City Environmental Sensor Emulator
Protocol-accurate: Modbus TCP (IEC 61131) + OPC UA (IEC 62541)

Emulates a network of air quality, noise, and weather monitoring stations
deployed across urban zones. Uses real Modbus register maps and OPC UA
information models following environmental monitoring standards.

Sensors:
- PM2.5 / PM10 particulate matter (EN 12341)
- CO, NO2, O3, SO2 gas sensors (EN 14211/14212/14625)
- Noise level dBA (IEC 61672-1 Class 1)
- Temperature, humidity, pressure, wind (WMO standards)
- UV index, rainfall rate

Protocols:
- Modbus TCP holding registers (function code 0x03)
- OPC UA information model (node browsing, subscriptions)
- REST API for integration
"""

from flask import Flask, request, jsonify
import os
import time, random, math, struct, threading, json
from datetime import datetime, timezone

try:
    from opcua import Server
except Exception:  # pragma: no cover - optional local fallback
    Server = None

app = Flask(__name__)

# ── Station Configuration ──
STATIONS = {
    "ENV-STN-001": {
        "name": "Downtown Air Quality Station",
        "location": {"lat": 37.7749, "lon": -122.4194, "altitude_m": 15},
        "zone": "urban-core",
        "modbus_unit_id": 1,
    },
    "ENV-STN-002": {
        "name": "Industrial District Monitor",
        "location": {"lat": 37.7780, "lon": -122.4050, "altitude_m": 8},
        "zone": "industrial",
        "modbus_unit_id": 2,
    },
    "ENV-STN-003": {
        "name": "Residential Park Sensor",
        "location": {"lat": 37.7700, "lon": -122.4300, "altitude_m": 22},
        "zone": "residential",
        "modbus_unit_id": 3,
    },
    "ENV-STN-004": {
        "name": "Highway Corridor Station",
        "location": {"lat": 37.7820, "lon": -122.4100, "altitude_m": 5},
        "zone": "highway",
        "modbus_unit_id": 4,
    },
    "ENV-STN-005": {
        "name": "Harbor Waterfront Monitor",
        "location": {"lat": 37.7950, "lon": -122.3930, "altitude_m": 3},
        "zone": "waterfront",
        "modbus_unit_id": 5,
    },
}

# Allow per-pod logical fleet sizing for research/demo scaling experiments.
_env_station_count = int(os.environ.get("DEVICE_COUNT", os.environ.get("ENV_SENSOR_STATION_COUNT", str(len(STATIONS)))))
if _env_station_count > 0 and _env_station_count != len(STATIONS):
    _all_station_items = list(STATIONS.items())
    if _env_station_count < len(_all_station_items):
        STATIONS = dict(_all_station_items[:_env_station_count])
    else:
        # Expand by cloning templates with unique IDs / unit IDs.
        expanded = dict(_all_station_items)
        next_idx = len(_all_station_items) + 1
        while len(expanded) < _env_station_count:
            base_key, base_cfg = _all_station_items[(next_idx - 1) % len(_all_station_items)]
            sid = f"ENV-STN-{next_idx:03d}"
            cfg = json.loads(json.dumps(base_cfg))
            cfg["name"] = f"{cfg['name']} #{next_idx}"
            cfg["modbus_unit_id"] = next_idx
            expanded[sid] = cfg
            next_idx += 1
        STATIONS = expanded

# ── Modbus Register Map (IEC 61131 style) ──
# Register address → (name, unit, scale_factor, data_type)
MODBUS_REGISTER_MAP = {
    0:  ("pm25", "µg/m³", 10, "uint16"),       # PM2.5 particulate
    1:  ("pm10", "µg/m³", 10, "uint16"),       # PM10 particulate
    2:  ("co_ppm", "ppm", 100, "uint16"),      # Carbon monoxide
    3:  ("no2_ppb", "ppb", 10, "uint16"),      # Nitrogen dioxide
    4:  ("o3_ppb", "ppb", 10, "uint16"),       # Ozone
    5:  ("so2_ppb", "ppb", 10, "uint16"),      # Sulfur dioxide
    6:  ("noise_dba", "dBA", 10, "uint16"),    # Noise level
    7:  ("temperature_c", "°C", 100, "int16"), # Temperature
    8:  ("humidity_pct", "%", 100, "uint16"),   # Relative humidity
    9:  ("pressure_hpa", "hPa", 10, "uint16"), # Barometric pressure
    10: ("wind_speed_ms", "m/s", 100, "uint16"),  # Wind speed
    11: ("wind_dir_deg", "°", 1, "uint16"),    # Wind direction
    12: ("uv_index", "", 10, "uint16"),        # UV index
    13: ("rainfall_mm", "mm/h", 100, "uint16"),# Rainfall rate
    14: ("aqi_index", "", 1, "uint16"),        # Computed AQI
    15: ("station_status", "", 1, "uint16"),   # 0=OK,1=cal,2=fault
}

# ── AQI breakpoints (EPA standard) ──
AQI_BREAKPOINTS_PM25 = [
    (0, 12.0, 0, 50), (12.1, 35.4, 51, 100), (35.5, 55.4, 101, 150),
    (55.5, 150.4, 151, 200), (150.5, 250.4, 201, 300), (250.5, 500.4, 301, 500),
]

# ── OPC UA namespace ──
OPCUA_NAMESPACE = "urn:smartcity:env:monitor"
OPCUA_NODES = {}
OPCUA_ENDPOINT = os.environ.get("OPCUA_ENDPOINT", "opc.tcp://0.0.0.0:4840/env")
OPCUA_ENABLED = os.environ.get("OPCUA_ENABLED", "1").lower() not in {"0", "false", "no"}
opcua_runtime = {
    "enabled": bool(OPCUA_ENABLED and Server),
    "running": False,
    "endpoint": OPCUA_ENDPOINT,
    "last_error": None,
}

# ── Live sensor state ──
sensor_state = {}
station_overrides = {}
_start_time = time.time()
_lock = threading.Lock()


def _compute_aqi(pm25):
    """Compute EPA AQI from PM2.5 value."""
    for c_low, c_high, i_low, i_high in AQI_BREAKPOINTS_PM25:
        if c_low <= pm25 <= c_high:
            return round(((i_high - i_low) / (c_high - c_low)) * (pm25 - c_low) + i_low)
    return min(500, round(pm25 * 2))


def _zone_baseline(zone):
    """Return pollution baselines by zone type."""
    baselines = {
        "urban-core":   {"pm25": 18, "pm10": 35, "co": 0.8, "no2": 30, "o3": 25, "so2": 5, "noise": 68},
        "industrial":   {"pm25": 32, "pm10": 55, "co": 1.5, "no2": 45, "o3": 15, "so2": 18, "noise": 72},
        "residential":  {"pm25": 10, "pm10": 20, "co": 0.3, "no2": 12, "o3": 35, "so2": 2, "noise": 48},
        "highway":      {"pm25": 25, "pm10": 45, "co": 2.0, "no2": 55, "o3": 20, "so2": 8, "noise": 75},
        "waterfront":   {"pm25": 8,  "pm10": 15, "co": 0.2, "no2": 8,  "o3": 40, "so2": 3, "noise": 52},
    }
    return baselines.get(zone, baselines["urban-core"])


def _diurnal_factor():
    """Diurnal pollution pattern — peaks at rush hours."""
    hour = datetime.now(timezone.utc).hour
    # Rush hour peaks: 7-9 AM, 5-7 PM
    if 7 <= hour <= 9:
        return 1.3 + random.uniform(-0.1, 0.15)
    elif 17 <= hour <= 19:
        return 1.4 + random.uniform(-0.1, 0.2)
    elif 0 <= hour <= 5:
        return 0.6 + random.uniform(-0.05, 0.1)
    else:
        return 1.0 + random.uniform(-0.1, 0.1)


def _update_sensors():
    """Generate protocol-accurate sensor readings for all stations."""
    with _lock:
        for sid, cfg in STATIONS.items():
            zone = cfg["zone"]
            bl = _zone_baseline(zone)
            df = _diurnal_factor()

            pm25 = max(0, bl["pm25"] * df + random.gauss(0, 3))
            pm10 = max(0, bl["pm10"] * df + random.gauss(0, 5))
            co = max(0, bl["co"] * df + random.gauss(0, 0.1))
            no2 = max(0, bl["no2"] * df + random.gauss(0, 4))
            o3 = max(0, bl["o3"] * (2 - df) + random.gauss(0, 5))  # O3 inversely correlated
            so2 = max(0, bl["so2"] * df + random.gauss(0, 1))
            noise = max(30, bl["noise"] * df + random.gauss(0, 3))

            # Weather
            temp = 15 + 10 * math.sin((datetime.now(timezone.utc).hour - 6) * math.pi / 12) + random.gauss(0, 1.5)
            humidity = max(20, min(100, 60 + random.gauss(0, 10)))
            pressure = 1013.25 + random.gauss(0, 3)
            wind_speed = max(0, random.weibullvariate(3.5, 2.0))
            wind_dir = random.randint(0, 359)
            uv = max(0, min(11, 5 * math.sin(max(0, (datetime.now(timezone.utc).hour - 6) * math.pi / 12)) + random.gauss(0, 0.5)))
            rainfall = max(0, random.expovariate(5)) if random.random() < 0.15 else 0

            aqi = _compute_aqi(pm25)

            # Random sensor fault injection (for IDS testing)
            status = 0  # OK
            if random.random() < 0.02:
                status = 2  # fault
            elif random.random() < 0.05:
                status = 1  # calibrating

            # Build Modbus registers (scaled integers)
            registers = {
                0: int(pm25 * 10),
                1: int(pm10 * 10),
                2: int(co * 100),
                3: int(no2 * 10),
                4: int(o3 * 10),
                5: int(so2 * 10),
                6: int(noise * 10),
                7: int(temp * 100) & 0xFFFF,  # int16 as uint16
                8: int(humidity * 100),
                9: int(pressure * 10),
                10: int(wind_speed * 100),
                11: wind_dir,
                12: int(uv * 10),
                13: int(rainfall * 100),
                14: aqi,
                15: status,
            }

            override = station_overrides.get(sid, {})
            override_until = override.get("until", 0)
            if override and override_until and time.time() > override_until:
                station_overrides.pop(sid, None)
                override = {}

            readings = {
                "pm25": round(pm25, 1),
                "pm10": round(pm10, 1),
                "co_ppm": round(co, 2),
                "no2_ppb": round(no2, 1),
                "o3_ppb": round(o3, 1),
                "so2_ppb": round(so2, 1),
                "noise_dba": round(noise, 1),
                "temperature_c": round(temp, 1),
                "humidity_pct": round(humidity, 1),
                "pressure_hpa": round(pressure, 1),
                "wind_speed_ms": round(wind_speed, 1),
                "wind_dir_deg": wind_dir,
                "uv_index": round(uv, 1),
                "rainfall_mm_h": round(rainfall, 2),
            }
            if override.get("readings"):
                readings.update(override["readings"])
            effective_aqi = int(override.get("aqi", aqi))
            effective_status = override.get("status", ["operational", "calibrating", "fault"][status])
            registers[14] = effective_aqi
            registers[15] = {"operational": 0, "calibrating": 1, "fault": 2}.get(effective_status, status)

            sensor_state[sid] = {
                "station_id": sid,
                "name": cfg["name"],
                "zone": cfg["zone"],
                "location": cfg["location"],
                "modbus_unit_id": cfg["modbus_unit_id"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "readings": readings,
                "aqi": effective_aqi,
                "aqi_category": _aqi_category(effective_aqi),
                "status": effective_status,
                "modbus_registers": registers,
                "override_active": bool(override),
            }


def _aqi_category(aqi):
    if aqi <= 50: return "Good"
    if aqi <= 100: return "Moderate"
    if aqi <= 150: return "Unhealthy for Sensitive Groups"
    if aqi <= 200: return "Unhealthy"
    if aqi <= 300: return "Very Unhealthy"
    return "Hazardous"


def _sensor_loop():
    while True:
        _update_sensors()
        time.sleep(5)


threading.Thread(target=_sensor_loop, daemon=True).start()
_update_sensors()  # Initial reading


def _run_native_opcua_server():
    """Expose a real OPC UA endpoint for browse/read clients."""
    if not opcua_runtime["enabled"]:
        opcua_runtime["last_error"] = "python-opcua unavailable or OPC UA disabled"
        return

    try:
        server = Server()
        server.set_endpoint(OPCUA_ENDPOINT)
        server.set_server_name("Smart City Environmental Sensor OPC UA Server")
        idx = server.register_namespace(OPCUA_NAMESPACE)
        stations_obj = server.get_objects_node().add_object(idx, "EnvironmentalStations")

        node_map = {}
        for sid, cfg in STATIONS.items():
            station_obj = stations_obj.add_object(idx, sid)
            station_obj.add_variable(idx, "stationName", cfg["name"]).set_writable(False)
            for key in sensor_state.get(sid, {}).get("readings", {}).keys():
                node_map[(sid, key)] = station_obj.add_variable(idx, key, 0.0)
                node_map[(sid, key)].set_writable(False)
            node_map[(sid, "AQI")] = station_obj.add_variable(idx, "AQI", 0)
            node_map[(sid, "AQI")].set_writable(False)
            node_map[(sid, "status")] = station_obj.add_variable(idx, "status", "operational")
            node_map[(sid, "status")].set_writable(False)

        server.start()
        opcua_runtime["running"] = True
        while True:
            with _lock:
                snapshot = dict(sensor_state)
            for sid, state in snapshot.items():
                for key, value in state.get("readings", {}).items():
                    node = node_map.get((sid, key))
                    if node is not None:
                        node.set_value(value)
                if node_map.get((sid, "AQI")) is not None:
                    node_map[(sid, "AQI")].set_value(int(state.get("aqi", 0)))
                if node_map.get((sid, "status")) is not None:
                    node_map[(sid, "status")].set_value(str(state.get("status", "unknown")))
            time.sleep(2)
    except Exception as exc:
        opcua_runtime["running"] = False
        opcua_runtime["last_error"] = str(exc)


threading.Thread(target=_run_native_opcua_server, daemon=True).start()


# ── Modbus TCP Endpoint (simulated function codes) ──
@app.route("/modbus/read", methods=["GET", "POST"])
def modbus_read():
    """Simulate Modbus TCP function code 0x03 (Read Holding Registers).
    
    Query params: unit_id, start_register, count
    Returns raw register values as Modbus would.
    """
    unit_id = int(request.args.get("unit_id", 1))
    start = int(request.args.get("start_register", 0))
    count = int(request.args.get("count", 16))

    # Find station by unit_id
    station = None
    for sid, cfg in STATIONS.items():
        if cfg["modbus_unit_id"] == unit_id:
            station = sensor_state.get(sid)
            break

    if not station:
        return jsonify({"error": "Modbus exception: unit not found", "exception_code": 0x0B}), 404

    registers = station.get("modbus_registers", {})
    values = []
    for addr in range(start, min(start + count, 16)):
        val = registers.get(addr, 0)
        values.append(val)

    # Modbus TCP response frame (simplified)
    return jsonify({
        "transaction_id": random.randint(1, 65535),
        "protocol_id": 0,  # Modbus
        "unit_id": unit_id,
        "function_code": 3,
        "byte_count": count * 2,
        "registers": values,
        "register_map": {str(start + i): {
            "name": MODBUS_REGISTER_MAP.get(start + i, ("unknown",))[0],
            "unit": MODBUS_REGISTER_MAP.get(start + i, ("", ""))[1],
            "raw": values[i] if i < len(values) else 0,
            "scaled": values[i] / MODBUS_REGISTER_MAP.get(start + i, ("", "", 1))[2] if i < len(values) and start + i in MODBUS_REGISTER_MAP else 0,
        } for i in range(min(count, 16 - start))},
    })


@app.route("/modbus/write", methods=["POST"])
def modbus_write():
    """Apply a bounded station override through a Modbus-style write interface."""
    body = request.get_json(force=True) or {}
    unit_id = int(body.get("unit_id", 1))
    duration_s = max(10, min(int(body.get("duration_s", 300)), 3600))
    register_updates = body.get("registers", {})

    sid = None
    for station_id, cfg in STATIONS.items():
        if cfg["modbus_unit_id"] == unit_id:
            sid = station_id
            break
    if not sid:
        return jsonify({"error": "Modbus exception: unit not found", "exception_code": 0x0B}), 404

    readings_override = {}
    aqi_override = None
    status_override = None
    applied = {}
    for raw_addr, raw_value in register_updates.items():
        addr = int(raw_addr)
        value = int(raw_value)
        if addr not in MODBUS_REGISTER_MAP:
            continue
        name, _unit, scale, data_type = MODBUS_REGISTER_MAP[addr]
        applied[str(addr)] = value
        if addr == 14:
            aqi_override = value
        elif addr == 15:
            status_override = {0: "operational", 1: "calibrating", 2: "fault"}.get(value, "fault")
        else:
            if data_type == "int16" and value > 32767:
                value -= 65536
            readings_override[name] = round(value / scale, 2)

    station_overrides[sid] = {
        "readings": readings_override,
        "aqi": aqi_override,
        "status": status_override,
        "until": time.time() + duration_s,
        "source": "modbus_write",
    }
    _update_sensors()
    return jsonify({
        "protocol": "Modbus TCP",
        "unit_id": unit_id,
        "station_id": sid,
        "write_type": "holding_register_override",
        "duration_s": duration_s,
        "applied_registers": applied,
        "override_active": True,
    })


# ── OPC UA Endpoint (simulated browse/read) ──
@app.route("/opcua/browse", methods=["GET"])
def opcua_browse():
    """Simulate OPC UA Browse request — returns information model nodes."""
    nodes = []
    for sid, state in sensor_state.items():
        station_node = {
            "node_id": f"ns=2;s={sid}",
            "browse_name": f"2:{sid}",
            "display_name": state["name"],
            "node_class": "Object",
            "type_definition": "EnvironmentalStationType",
            "children": [],
        }
        for key, val in state["readings"].items():
            reg_info = None
            for addr, info in MODBUS_REGISTER_MAP.items():
                if info[0] == key or info[0].replace("_", "") == key.replace("_", ""):
                    reg_info = info
                    break
            station_node["children"].append({
                "node_id": f"ns=2;s={sid}.{key}",
                "browse_name": f"2:{key}",
                "display_name": key.replace("_", " ").title(),
                "node_class": "Variable",
                "data_type": "Double",
                "value": val,
                "engineering_unit": reg_info[1] if reg_info else "",
                "source_timestamp": state["timestamp"],
            })
        # AQI node
        station_node["children"].append({
            "node_id": f"ns=2;s={sid}.AQI",
            "browse_name": "2:AQI",
            "display_name": "Air Quality Index",
            "node_class": "Variable",
            "data_type": "UInt16",
            "value": state["aqi"],
            "engineering_unit": "",
            "source_timestamp": state["timestamp"],
        })
        nodes.append(station_node)

    return jsonify({
        "namespace": OPCUA_NAMESPACE,
        "server_uri": "opc.tcp://env-sensor.smart-city:4840",
        "nodes": nodes,
        "total_nodes": sum(1 + len(n["children"]) for n in nodes),
    })


@app.route("/opcua/read", methods=["GET", "POST"])
def opcua_read():
    """Simulate OPC UA Read request for specific node IDs."""
    node_id = request.args.get("node_id", "")
    # Parse ns=2;s=ENV-STN-001.pm25
    parts = node_id.replace("ns=2;s=", "").split(".")
    if len(parts) < 2:
        return jsonify({"error": "Bad_NodeIdInvalid", "status_code": "0x80340000"}), 400

    sid, var_name = parts[0], parts[1]
    state = sensor_state.get(sid)
    if not state:
        return jsonify({"error": "Bad_NodeIdUnknown", "status_code": "0x80340000"}), 404

    if var_name == "AQI":
        value = state["aqi"]
    elif var_name in state["readings"]:
        value = state["readings"][var_name]
    else:
        return jsonify({"error": "Bad_AttributeIdInvalid"}), 400

    return jsonify({
        "node_id": node_id,
        "value": {"type": "Double", "value": value},
        "status_code": "Good",
        "source_timestamp": state["timestamp"],
        "server_timestamp": datetime.now(timezone.utc).isoformat(),
    })


# ── REST API ──
@app.route("/health")
def health():
    return jsonify({
        "status": "healthy",
        "service": "environmental-sensor-emulator",
        "protocol": "Modbus TCP + OPC UA",
        "uptime": int(time.time() - _start_time),
        "stations": len(STATIONS),
        "firmware": "v3.1.0-ENV-2024",
        "opcua": opcua_runtime,
    })


@app.route("/api/stations")
def api_stations():
    """Return all station data with latest readings."""
    return jsonify({
        "stations": list(sensor_state.values()),
        "count": len(sensor_state),
    })


@app.route("/api/aqi")
def api_aqi():
    """Return AQI summary across all stations."""
    aqis = {sid: s["aqi"] for sid, s in sensor_state.items()}
    avg_aqi = sum(aqis.values()) / len(aqis) if aqis else 0
    worst = max(aqis.items(), key=lambda x: x[1]) if aqis else ("none", 0)
    best = min(aqis.items(), key=lambda x: x[1]) if aqis else ("none", 0)
    return jsonify({
        "city_aqi": round(avg_aqi),
        "category": _aqi_category(round(avg_aqi)),
        "stations": {sid: {"aqi": aqi, "category": _aqi_category(aqi)} for sid, aqi in aqis.items()},
        "worst_station": {"id": worst[0], "aqi": worst[1]},
        "best_station": {"id": best[0], "aqi": best[1]},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


@app.route("/api/stats")
def api_stats():
    """Summary statistics for the dashboard."""
    total_stations = len(STATIONS)
    online = sum(1 for s in sensor_state.values() if s["status"] == "operational")
    faulted = sum(1 for s in sensor_state.values() if s["status"] == "fault")
    avg_aqi = round(sum(s["aqi"] for s in sensor_state.values()) / len(sensor_state)) if sensor_state else 0

    return jsonify({
        "service": "environmental-sensor-emulator",
        "protocol": "Modbus TCP + OPC UA (IEC 62541)",
        "stations_total": total_stations,
        "stations_online": online,
        "stations_faulted": faulted,
        "sensors_per_station": len(MODBUS_REGISTER_MAP),
        "total_sensor_channels": total_stations * len(MODBUS_REGISTER_MAP),
        "avg_aqi": avg_aqi,
        "aqi_category": _aqi_category(avg_aqi),
        "uptime_seconds": int(time.time() - _start_time),
        "opcua_running": opcua_runtime["running"],
        "opcua_endpoint": opcua_runtime["endpoint"],
    })


@app.route("/api/telemetry")
def api_telemetry():
    """Real-time telemetry for all stations."""
    return jsonify({
        "stations": {sid: {
            "readings": s["readings"],
            "aqi": s["aqi"],
            "aqi_category": s["aqi_category"],
            "status": s["status"],
            "zone": s["zone"],
            "timestamp": s["timestamp"],
        } for sid, s in sensor_state.items()},
        "register_map": {str(k): {"name": v[0], "unit": v[1]} for k, v in MODBUS_REGISTER_MAP.items()},
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
