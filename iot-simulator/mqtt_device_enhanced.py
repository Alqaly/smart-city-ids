#!/usr/bin/env python3
"""
Smart City IDS - Enhanced IoT Device Emulator
Implements realistic IoT traffic patterns for Capstone II validation.

Features:
- Poisson arrival process with time-of-day λ(t)
- Rush-hour burst multipliers (10x at 08:00, 17:00)
- Four device classes (high-freq, medium-freq, burst, smart_lights)
- Realistic sensor value ranges with anomaly injection
- Failure injection (disconnects, latency spikes, packet loss)
- Prometheus metrics for observability
- Statistical validation endpoints
"""

import os
import threading
import time
import random
import json
import math
import hashlib
from datetime import datetime
from collections import deque
from flask import Flask, request, jsonify, Response
import paho.mqtt.client as mqtt

app = Flask(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

POD_NAME = os.environ.get("POD_NAME", "iot-device-0")
MQTT_BROKER = os.environ.get("MQTT_BROKER", "mqtt-broker")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))
DEVICE_CLASS = os.environ.get("DEVICE_CLASS", "medium")  # high, medium, burst, smart_lights
DEVICE_NAMESPACE = os.environ.get("DEVICE_NAMESPACE", "traffic")  # traffic, energy, environment, lighting

# Poisson base rates (λ) per device class - messages per minute
DEVICE_CLASS_RATES = {
    "high": 60.0,        # 1 msg/sec - continuous sensors (temperature, pressure)
    "medium": 6.0,       # 1 msg/10sec - standard sensors (vehicle counters)
    "burst": 0.5,        # 1 msg/2min baseline, burst on events (collision detection)
    "smart_lights": 1.0, # 1 msg/min - low-freq event-driven (on/off state)
}

# Rush hour multipliers (hour: multiplier)
RUSH_HOUR_MULTIPLIERS = {
    6: 2.0,
    7: 3.0,
    8: 10.0,   # Morning rush peak
    9: 5.0,
    10: 2.0,
    15: 2.0,
    16: 3.0,
    17: 10.0,  # Evening rush peak
    18: 5.0,
    19: 2.0,
}

# Weekday patterns (0=Monday, 6=Sunday)
WEEKDAY_MULTIPLIERS = {
    0: 1.0, 1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0,  # Weekdays
    5: 0.3, 6: 0.2,  # Weekend reduction
}

# Failure injection parameters
FAILURE_DISCONNECT_PROB = float(os.environ.get("FAILURE_DISCONNECT_PROB", 0.01))  # 1% per interval
FAILURE_DISCONNECT_DURATION = float(os.environ.get("FAILURE_DISCONNECT_DURATION", 30))  # seconds
FAILURE_LATENCY_SPIKE_PROB = float(os.environ.get("FAILURE_LATENCY_SPIKE_PROB", 0.02))  # 2%
FAILURE_LATENCY_SPIKE_MAX = float(os.environ.get("FAILURE_LATENCY_SPIKE_MAX", 5.0))  # seconds
NETWORK_PACKET_LOSS = float(os.environ.get("NETWORK_PACKET_LOSS", 0.05))  # 5% message loss

# Anomaly injection
ANOMALY_RATE = float(os.environ.get("ANOMALY_RATE", 0.01))  # 1% of messages have anomalies
ANOMALY_SEVERITY = float(os.environ.get("ANOMALY_SEVERITY", 0.5))  # 0.0-1.0 severity scale

# Realistic sensor value ranges
SENSOR_RANGES = {
    "traffic": {
        "vehicle_count": {"min": 0, "max": 100, "anomaly_min": 150, "anomaly_max": 500},
        "avg_speed_kmh": {"min": 0, "max": 60, "anomaly_min": -10, "anomaly_max": 200},
        "congestion_level": {"min": 0.0, "max": 1.0},
    },
    "energy": {
        "voltage_v": {"min": 220, "max": 240, "anomaly_min": 180, "anomaly_max": 280},
        "current_a": {"min": 0, "max": 32, "anomaly_min": 40, "anomaly_max": 100},
        "power_w": {"min": 0, "max": 7500, "anomaly_min": 8000, "anomaly_max": 15000},
        "frequency_hz": {"min": 49.9, "max": 50.1, "anomaly_min": 45, "anomaly_max": 55},
    },
    "environment": {
        "temperature_c": {"min": -10, "max": 40, "anomaly_min": -30, "anomaly_max": 60},
        "humidity_pct": {"min": 20, "max": 95},
        "air_quality_index": {"min": 0, "max": 150, "anomaly_min": 200, "anomaly_max": 500},
        "co2_ppm": {"min": 350, "max": 1000, "anomaly_min": 2000, "anomaly_max": 5000},
    },
    "lighting": {
        "brightness_pct": {"min": 0, "max": 100},
        "color_temp_k": {"min": 2700, "max": 6500},
        "power_on": {"values": [True, False]},
    },
}

# =============================================================================
# METRICS TRACKING
# =============================================================================

class MetricsCollector:
    """Thread-safe metrics collector for Prometheus exposition."""
    
    def __init__(self):
        self.lock = threading.Lock()
        self.messages_sent = 0
        self.messages_received = 0
        self.messages_failed = 0
        self.messages_lost = 0  # Emulated packet loss
        self.disconnects_total = 0
        self.latency_spikes_total = 0
        self.anomalies_injected = 0
        self.current_rate = 0.0
        self.burst_factor = 1.0
        self.device_active = 1
        self.latencies = []
        self.hourly_counts = {}  # For statistical validation
        self.start_time = time.time()
        
    def inc_sent(self):
        with self.lock:
            self.messages_sent += 1
            # Track hourly for pattern validation
            hour = datetime.now().hour
            self.hourly_counts[hour] = self.hourly_counts.get(hour, 0) + 1
            
    def inc_received(self):
        with self.lock:
            self.messages_received += 1
            
    def inc_failed(self):
        with self.lock:
            self.messages_failed += 1

    def inc_lost(self):
        with self.lock:
            self.messages_lost += 1
            
    def inc_disconnect(self):
        with self.lock:
            self.disconnects_total += 1
            
    def inc_latency_spike(self):
        with self.lock:
            self.latency_spikes_total += 1

    def inc_anomaly(self):
        with self.lock:
            self.anomalies_injected += 1
            
    def set_rate(self, rate):
        with self.lock:
            self.current_rate = rate
            
    def set_burst_factor(self, factor):
        with self.lock:
            self.burst_factor = factor
            
    def set_active(self, active):
        with self.lock:
            self.device_active = 1 if active else 0
            
    def record_latency(self, latency):
        with self.lock:
            self.latencies.append(latency)
            if len(self.latencies) > 1000:
                self.latencies = self.latencies[-1000:]

    def get_stats(self):
        """Get statistical summary for validation."""
        with self.lock:
            uptime = time.time() - self.start_time
            total = self.messages_sent + self.messages_failed + self.messages_lost
            return {
                "uptime_seconds": uptime,
                "messages_sent": self.messages_sent,
                "messages_failed": self.messages_failed,
                "messages_lost": self.messages_lost,
                "anomalies_injected": self.anomalies_injected,
                "anomaly_rate": self.anomalies_injected / max(1, self.messages_sent),
                "loss_rate": self.messages_lost / max(1, total),
                "avg_rate_per_min": (self.messages_sent / max(1, uptime)) * 60,
                "hourly_distribution": dict(self.hourly_counts),
                "latency_p50": sorted(self.latencies)[len(self.latencies)//2] if self.latencies else 0,
                "latency_p95": sorted(self.latencies)[int(len(self.latencies)*0.95)] if len(self.latencies) > 20 else 0,
            }
                
    def get_prometheus_metrics(self):
        """Generate Prometheus exposition format."""
        with self.lock:
            lines = [
                "# HELP iot_messages_sent_total Total messages sent by this device",
                "# TYPE iot_messages_sent_total counter",
                f'iot_messages_sent_total{{device="{POD_NAME}",namespace="{DEVICE_NAMESPACE}",class="{DEVICE_CLASS}"}} {self.messages_sent}',
                "",
                "# HELP iot_messages_received_total Total messages received by this device",
                "# TYPE iot_messages_received_total counter",
                f'iot_messages_received_total{{device="{POD_NAME}",namespace="{DEVICE_NAMESPACE}",class="{DEVICE_CLASS}"}} {self.messages_received}',
                "",
                "# HELP iot_messages_failed_total Total messages that failed to send",
                "# TYPE iot_messages_failed_total counter",
                f'iot_messages_failed_total{{device="{POD_NAME}",namespace="{DEVICE_NAMESPACE}",class="{DEVICE_CLASS}"}} {self.messages_failed}',
                "",
                "# HELP iot_messages_lost_total Total messages lost to emulated packet loss",
                "# TYPE iot_messages_lost_total counter",
                f'iot_messages_lost_total{{device="{POD_NAME}",namespace="{DEVICE_NAMESPACE}",class="{DEVICE_CLASS}"}} {self.messages_lost}',
                "",
                "# HELP iot_anomalies_injected_total Total anomalous readings injected",
                "# TYPE iot_anomalies_injected_total counter",
                f'iot_anomalies_injected_total{{device="{POD_NAME}",namespace="{DEVICE_NAMESPACE}",class="{DEVICE_CLASS}"}} {self.anomalies_injected}',
                "",
                "# HELP iot_device_disconnects_total Total emulated disconnects",
                "# TYPE iot_device_disconnects_total counter",
                f'iot_device_disconnects_total{{device="{POD_NAME}"}} {self.disconnects_total}',
                "",
                "# HELP iot_latency_spikes_total Total latency spike events",
                "# TYPE iot_latency_spikes_total counter",
                f'iot_latency_spikes_total{{device="{POD_NAME}"}} {self.latency_spikes_total}',
                "",
                "# HELP iot_device_active Whether device is currently active",
                "# TYPE iot_device_active gauge",
                f'iot_device_active{{device="{POD_NAME}",namespace="{DEVICE_NAMESPACE}",class="{DEVICE_CLASS}"}} {self.device_active}',
                "",
                "# HELP iot_current_message_rate Current Poisson rate (messages/minute)",
                "# TYPE iot_current_message_rate gauge",
                f'iot_current_message_rate{{device="{POD_NAME}",class="{DEVICE_CLASS}"}} {self.current_rate:.2f}',
                "",
                "# HELP iot_burst_factor Current burst multiplier",
                "# TYPE iot_burst_factor gauge",
                f'iot_burst_factor{{device="{POD_NAME}"}} {self.burst_factor:.2f}',
                "",
            ]
            
            # Latency histogram buckets
            if self.latencies:
                buckets = [0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
                lines.append("# HELP iot_message_latency_seconds Message send latency")
                lines.append("# TYPE iot_message_latency_seconds histogram")
                
                count = len(self.latencies)
                total = sum(self.latencies)
                
                for bucket in buckets:
                    bucket_count = sum(1 for l in self.latencies if l <= bucket)
                    lines.append(f'iot_message_latency_seconds_bucket{{device="{POD_NAME}",le="{bucket}"}} {bucket_count}')
                lines.append(f'iot_message_latency_seconds_bucket{{device="{POD_NAME}",le="+Inf"}} {count}')
                lines.append(f'iot_message_latency_seconds_sum{{device="{POD_NAME}"}} {total:.4f}')
                lines.append(f'iot_message_latency_seconds_count{{device="{POD_NAME}"}} {count}')
                
            return "\n".join(lines) + "\n"

metrics = MetricsCollector()

# =============================================================================
# MQTT CLIENT
# =============================================================================

mqtt_client = mqtt.Client()
mqtt_connected = False
mqtt_paused = False

def on_connect(client, userdata, flags, rc):
    global mqtt_connected
    mqtt_connected = (rc == 0)
    if mqtt_connected:
        print(f"[MQTT] Connected to {MQTT_BROKER}:{MQTT_PORT}")
        client.subscribe(f"sensors/{DEVICE_NAMESPACE}/#")
    else:
        print(f"[MQTT] Connection failed with code {rc}")

def on_disconnect(client, userdata, rc):
    global mqtt_connected
    mqtt_connected = False
    print(f"[MQTT] Disconnected (rc={rc})")

def on_message(client, userdata, msg):
    metrics.inc_received()
    try:
        data = json.loads(msg.payload.decode())
        if "timestamp" in data:
            latency = time.time() - data["timestamp"]
            metrics.record_latency(latency)
    except:
        pass

mqtt_client.on_connect = on_connect
mqtt_client.on_disconnect = on_disconnect
mqtt_client.on_message = on_message

# =============================================================================
# POISSON ARRIVAL PROCESS
# =============================================================================

def get_current_lambda():
    """
    Calculate current Poisson rate λ(t) based on:
    - Device class base rate
    - Time-of-day (rush hour multipliers)
    - Day-of-week patterns
    
    Returns: messages per minute
    """
    now = datetime.now()
    hour = now.hour
    weekday = now.weekday()
    
    # Base rate from device class
    base_rate = DEVICE_CLASS_RATES.get(DEVICE_CLASS, 6.0)
    
    # Rush hour multiplier
    rush_multiplier = RUSH_HOUR_MULTIPLIERS.get(hour, 1.0)
    
    # Weekday multiplier
    weekday_multiplier = WEEKDAY_MULTIPLIERS.get(weekday, 1.0)
    
    # Final rate
    final_rate = base_rate * rush_multiplier * weekday_multiplier
    
    # Update metrics
    metrics.set_rate(final_rate)
    metrics.set_burst_factor(rush_multiplier)
    
    return final_rate

def poisson_interval(lambda_rate):
    """
    Generate inter-arrival time from Poisson process.
    λ is in messages/minute, returns seconds.
    """
    if lambda_rate <= 0:
        return 60.0  # Default 1 minute
    
    # Convert to messages/second
    lambda_per_sec = lambda_rate / 60.0
    
    # Exponential distribution for inter-arrival times
    interval = random.expovariate(lambda_per_sec)
    
    # Clamp to reasonable bounds
    return max(0.1, min(interval, 300))  # 0.1s to 5min

# =============================================================================
# FAILURE INJECTION
# =============================================================================

def maybe_inject_disconnect():
    """Randomly inject device disconnect."""
    global mqtt_paused
    
    if random.random() < FAILURE_DISCONNECT_PROB:
        metrics.inc_disconnect()
        metrics.set_active(False)
        mqtt_paused = True
        
        duration = random.uniform(5, FAILURE_DISCONNECT_DURATION)
        print(f"[FAILURE] Emulating disconnect for {duration:.1f}s")
        time.sleep(duration)
        
        mqtt_paused = False
        metrics.set_active(True)
        print(f"[RECOVERY] Device back online")
        return True
    return False

def maybe_inject_latency_spike():
    """Randomly inject latency spike."""
    if random.random() < FAILURE_LATENCY_SPIKE_PROB:
        metrics.inc_latency_spike()
        spike = random.uniform(1.0, FAILURE_LATENCY_SPIKE_MAX)
        print(f"[LATENCY] Injecting {spike:.2f}s spike")
        time.sleep(spike)
        return spike
    return 0

# =============================================================================
# MESSAGE GENERATION WITH REALISTIC VALUES & ANOMALY INJECTION
# =============================================================================

def generate_realistic_value(sensor_type, field, inject_anomaly=False):
    """Generate realistic sensor value within plausible ranges."""
    ranges = SENSOR_RANGES.get(sensor_type, {}).get(field, {})
    
    if "values" in ranges:
        # Discrete values (like power_on: True/False)
        return random.choice(ranges["values"])
    
    if inject_anomaly and "anomaly_min" in ranges:
        # Generate anomalous value
        return random.uniform(ranges["anomaly_min"], ranges["anomaly_max"])
    
    # Normal value
    return random.uniform(ranges.get("min", 0), ranges.get("max", 100))

def inject_anomaly_check():
    """Determine if this message should have an anomaly."""
    if random.random() < ANOMALY_RATE:
        metrics.inc_anomaly()
        return True
    return False

def generate_sensor_data():
    """Generate realistic sensor data based on device namespace with anomaly injection."""
    
    is_anomaly = inject_anomaly_check()
    
    base_data = {
        "device_id": POD_NAME,
        "namespace": DEVICE_NAMESPACE,
        "class": DEVICE_CLASS,
        "timestamp": time.time(),
        "iso_time": datetime.now().isoformat(),
        "is_anomaly": is_anomaly,  # Flag for validation
    }
    
    if DEVICE_NAMESPACE == "traffic":
        vehicle_count = generate_realistic_value("traffic", "vehicle_count", is_anomaly)
        speed = generate_realistic_value("traffic", "avg_speed_kmh", is_anomaly)
        congestion = min(1.0, vehicle_count / 100.0)  # Derived from vehicle count
        
        base_data["data"] = {
            "vehicle_count": int(vehicle_count),
            "avg_speed_kmh": round(speed, 1),
            "congestion_level": round(congestion, 2),
            "lane_occupancy_pct": random.uniform(10, 90),
        }
        
        # Burst events for collision detection
        if DEVICE_CLASS == "burst" and random.random() < 0.05:
            base_data["event"] = {
                "type": random.choice(["collision", "stalled_vehicle", "wrong_way", "debris"]),
                "severity": random.choice(["minor", "moderate", "severe"]),
                "lane": random.randint(1, 4),
            }
            
    elif DEVICE_NAMESPACE == "energy":
        voltage = generate_realistic_value("energy", "voltage_v", is_anomaly)
        current = generate_realistic_value("energy", "current_a", is_anomaly)
        power = voltage * current  # P = V * I
        
        base_data["data"] = {
            "voltage_v": round(voltage, 1),
            "current_a": round(current, 2),
            "power_w": round(power, 1),
            "frequency_hz": round(generate_realistic_value("energy", "frequency_hz", is_anomaly), 2),
            "power_factor": round(random.uniform(0.85, 0.99), 2),
        }
        
        # Anomaly descriptions for energy
        if is_anomaly:
            if power > 7500:
                base_data["anomaly_type"] = "overload"
            elif voltage < 200 or voltage > 250:
                base_data["anomaly_type"] = "voltage_anomaly"
                
    elif DEVICE_NAMESPACE == "environment":
        temp = generate_realistic_value("environment", "temperature_c", is_anomaly)
        humidity = generate_realistic_value("environment", "humidity_pct", False)
        aqi = generate_realistic_value("environment", "air_quality_index", is_anomaly)
        
        base_data["data"] = {
            "temperature_c": round(temp, 1),
            "humidity_pct": round(humidity, 1),
            "air_quality_index": int(aqi),
            "co2_ppm": int(generate_realistic_value("environment", "co2_ppm", is_anomaly)),
            "pressure_hpa": round(random.uniform(1000, 1030), 1),
        }
        
        # Anomaly descriptions
        if is_anomaly:
            if temp > 50 or temp < -20:
                base_data["anomaly_type"] = "temperature_extreme"
            elif aqi > 200:
                base_data["anomaly_type"] = "air_quality_hazardous"

    elif DEVICE_NAMESPACE == "lighting":
        power_on = generate_realistic_value("lighting", "power_on", False)
        
        base_data["data"] = {
            "power_on": power_on,
            "brightness_pct": int(generate_realistic_value("lighting", "brightness_pct", False)) if power_on else 0,
            "color_temp_k": int(generate_realistic_value("lighting", "color_temp_k", False)),
            "energy_kwh_today": round(random.uniform(0.1, 2.0), 2),
        }
        
        # Smart light events
        if random.random() < 0.02:
            base_data["event"] = {
                "type": random.choice(["flickering", "dimming_failure", "color_drift", "scheduled_change"]),
            }
    else:
        # Generic sensor
        base_data["data"] = {
            "value": round(random.uniform(0, 100), 2),
            "unit": "generic",
        }
        
    # Add device health metadata
    base_data["device_health"] = {
        "battery_pct": random.randint(20, 100) if random.random() > 0.1 else random.randint(1, 20),
        "signal_strength_dbm": random.randint(-90, -30),
        "uptime_hours": random.randint(1, 8760),
    }
        
    return base_data

def publish_message():
    """Publish a single MQTT message with failure injection and packet loss."""
    global mqtt_connected
    
    if mqtt_paused or not mqtt_connected:
        metrics.inc_failed()
        return False

    # Emulate packet loss (message never sent)
    if random.random() < NETWORK_PACKET_LOSS:
        metrics.inc_lost()
        print(f"[PACKET_LOSS] Message dropped (emulated)")
        return False
        
    # Maybe inject latency
    latency = maybe_inject_latency_spike()
    
    topic = f"sensors/{DEVICE_NAMESPACE}/{DEVICE_CLASS}/{POD_NAME}"
    payload = json.dumps(generate_sensor_data())
    
    try:
        start = time.time()
        result = mqtt_client.publish(topic, payload, qos=1)
        
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            elapsed = time.time() - start + latency
            metrics.inc_sent()
            metrics.record_latency(elapsed)
            return True
        else:
            metrics.inc_failed()
            return False
    except Exception as e:
        print(f"[ERROR] Publish failed: {e}")
        metrics.inc_failed()
        return False

# =============================================================================
# MAIN LOOPS
# =============================================================================

def mqtt_connection_loop():
    """Maintain MQTT connection."""
    global mqtt_connected
    
    while True:
        if not mqtt_paused and not mqtt_connected:
            try:
                mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
                mqtt_client.loop_start()
            except Exception as e:
                print(f"[ERROR] MQTT connection failed: {e}")
        time.sleep(5)

def message_generator_loop():
    """Generate messages following Poisson process."""
    
    print(f"[START] Device {POD_NAME} ({DEVICE_CLASS}) in {DEVICE_NAMESPACE}")
    print(f"[CONFIG] Base rate: {DEVICE_CLASS_RATES.get(DEVICE_CLASS, 6.0)} msg/min")
    
    # Wait for initial connection
    time.sleep(3)
    
    while True:
        # Check for disconnect injection
        if maybe_inject_disconnect():
            continue
            
        # Get current rate and calculate interval
        current_lambda = get_current_lambda()
        interval = poisson_interval(current_lambda)
        
        # Publish message
        publish_message()
        
        # Wait for next message (Poisson inter-arrival time)
        time.sleep(interval)

# =============================================================================
# HTTP ENDPOINTS
# =============================================================================

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy" if not mqtt_paused else "degraded",
        "device": POD_NAME,
        "class": DEVICE_CLASS,
        "namespace": DEVICE_NAMESPACE,
        "mqtt_connected": mqtt_connected,
    })

@app.route("/status", methods=["GET"])
def status():
    return jsonify({
        "device": POD_NAME,
        "class": DEVICE_CLASS,
        "namespace": DEVICE_NAMESPACE,
        "mqtt_connected": mqtt_connected,
        "mqtt_paused": mqtt_paused,
        "current_rate": metrics.current_rate,
        "burst_factor": metrics.burst_factor,
        "messages_sent": metrics.messages_sent,
        "messages_failed": metrics.messages_failed,
    })

@app.route("/metrics", methods=["GET"])
def prometheus_metrics():
    return Response(metrics.get_prometheus_metrics(), mimetype="text/plain")

@app.route("/config", methods=["GET"])
def config():
    return jsonify({
        "device_class_rates": DEVICE_CLASS_RATES,
        "rush_hour_multipliers": RUSH_HOUR_MULTIPLIERS,
        "weekday_multipliers": WEEKDAY_MULTIPLIERS,
        "failure_disconnect_prob": FAILURE_DISCONNECT_PROB,
        "failure_latency_spike_prob": FAILURE_LATENCY_SPIKE_PROB,
        "network_packet_loss": NETWORK_PACKET_LOSS,
        "anomaly_rate": ANOMALY_RATE,
        "sensor_ranges": SENSOR_RANGES.get(DEVICE_NAMESPACE, {}),
    })

@app.route("/stats", methods=["GET"])
def stats():
    """Statistical validation endpoint - verify realistic patterns."""
    return jsonify(metrics.get_stats())

@app.route("/validate", methods=["GET"])
def validate():
    """
    Validate that traffic patterns match expected Poisson distribution.
    Returns pass/fail for competition judges to verify realism.
    """
    stats = metrics.get_stats()
    validations = []
    
    # Check 1: Anomaly rate should be ~1% (0.5% - 2%)
    anomaly_rate = stats["anomaly_rate"]
    anomaly_ok = 0.005 <= anomaly_rate <= 0.02
    validations.append({
        "check": "anomaly_rate",
        "expected": "0.5% - 2%",
        "actual": f"{anomaly_rate:.2%}",
        "passed": anomaly_ok,
    })
    
    # Check 2: Message rate should be close to configured rate
    expected_rate = DEVICE_CLASS_RATES.get(DEVICE_CLASS, 6.0)
    actual_rate = stats["avg_rate_per_min"]
    rate_ok = 0.5 * expected_rate <= actual_rate <= 2.0 * expected_rate
    validations.append({
        "check": "message_rate",
        "expected": f"{expected_rate} msg/min (±50%)",
        "actual": f"{actual_rate:.2f} msg/min",
        "passed": rate_ok,
    })
    
    # Check 3: Latency P95 should be < 5s (unless spikes injected)
    latency_p95 = stats["latency_p95"]
    latency_ok = latency_p95 < 5.0
    validations.append({
        "check": "latency_p95",
        "expected": "< 5 seconds",
        "actual": f"{latency_p95:.3f} seconds",
        "passed": latency_ok,
    })
    
    # Check 4: Loss rate should match configured NETWORK_PACKET_LOSS
    loss_rate = stats["loss_rate"]
    loss_ok = abs(loss_rate - NETWORK_PACKET_LOSS) < 0.03  # Within 3%
    validations.append({
        "check": "packet_loss_rate",
        "expected": f"{NETWORK_PACKET_LOSS:.1%} (±3%)",
        "actual": f"{loss_rate:.2%}",
        "passed": loss_ok,
    })
    
    all_passed = all(v["passed"] for v in validations)
    
    return jsonify({
        "device": POD_NAME,
        "namespace": DEVICE_NAMESPACE,
        "class": DEVICE_CLASS,
        "uptime_seconds": stats["uptime_seconds"],
        "validations": validations,
        "all_passed": all_passed,
        "verdict": "✅ REALISTIC" if all_passed else "⚠️ CHECK NEEDED",
    })

@app.route("/trigger-event", methods=["POST"])
def trigger_event():
    """
    Manually trigger a burst event (for demo/testing).
    POST /trigger-event {"type": "collision", "severity": "severe"}
    """
    data = request.json or {}
    event_type = data.get("type", "manual_trigger")
    severity = data.get("severity", "moderate")
    
    # Generate special event message
    event_data = generate_sensor_data()
    event_data["event"] = {
        "type": event_type,
        "severity": severity,
        "triggered_manually": True,
        "trigger_time": datetime.now().isoformat(),
    }
    
    topic = f"sensors/{DEVICE_NAMESPACE}/{DEVICE_CLASS}/{POD_NAME}/events"
    payload = json.dumps(event_data)
    
    try:
        result = mqtt_client.publish(topic, payload, qos=1)
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            return jsonify({"status": "sent", "topic": topic, "event": event_data["event"]})
        else:
            return jsonify({"status": "failed", "error": "MQTT publish failed"}), 500
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

# =============================================================================
# ENTRYPOINT
# =============================================================================

if __name__ == "__main__":
    # Start background threads
    threading.Thread(target=mqtt_connection_loop, daemon=True).start()
    threading.Thread(target=message_generator_loop, daemon=True).start()
    
    # Start HTTP server
    app.run(host="0.0.0.0", port=5000)
