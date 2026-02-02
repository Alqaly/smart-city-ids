#!/usr/bin/env python3
"""
Smart City IDS - Enhanced IoT Device Simulator
Implements realistic IoT traffic patterns for Capstone II validation.

Features:
- Poisson arrival process with time-of-day λ(t)
- Rush-hour burst multipliers (10x at 08:00, 17:00)
- Three device classes (high-freq, medium-freq, burst)
- Failure injection (disconnects, latency spikes)
- Prometheus metrics for observability
"""

import os
import threading
import time
import random
import json
import math
from datetime import datetime
from flask import Flask, request, jsonify, Response
import paho.mqtt.client as mqtt

app = Flask(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

POD_NAME = os.environ.get("POD_NAME", "iot-device-0")
MQTT_BROKER = os.environ.get("MQTT_BROKER", "mqtt-broker")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))
DEVICE_CLASS = os.environ.get("DEVICE_CLASS", "medium")  # high, medium, burst
DEVICE_NAMESPACE = os.environ.get("DEVICE_NAMESPACE", "traffic")  # traffic, energy, environment

# Poisson base rates (λ) per device class - messages per minute
DEVICE_CLASS_RATES = {
    "high": 60.0,      # 1 msg/sec - continuous sensors
    "medium": 6.0,     # 1 msg/10sec - standard sensors  
    "burst": 0.5,      # 1 msg/2min baseline, burst on events
}

# Rush hour multipliers (hour: multiplier)
RUSH_HOUR_MULTIPLIERS = {
    7: 3.0,
    8: 10.0,   # Morning rush peak
    9: 5.0,
    16: 3.0,
    17: 10.0,  # Evening rush peak
    18: 5.0,
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
        self.disconnects_total = 0
        self.latency_spikes_total = 0
        self.current_rate = 0.0
        self.burst_factor = 1.0
        self.device_active = 1
        self.latencies = []
        
    def inc_sent(self):
        with self.lock:
            self.messages_sent += 1
            
    def inc_received(self):
        with self.lock:
            self.messages_received += 1
            
    def inc_failed(self):
        with self.lock:
            self.messages_failed += 1
            
    def inc_disconnect(self):
        with self.lock:
            self.disconnects_total += 1
            
    def inc_latency_spike(self):
        with self.lock:
            self.latency_spikes_total += 1
            
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
                "# HELP iot_device_disconnects_total Total simulated disconnects",
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
        print(f"[FAILURE] Simulating disconnect for {duration:.1f}s")
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
# MESSAGE GENERATION
# =============================================================================

def generate_sensor_data():
    """Generate realistic sensor data based on device class."""
    
    base_data = {
        "device": POD_NAME,
        "namespace": DEVICE_NAMESPACE,
        "class": DEVICE_CLASS,
        "timestamp": time.time(),
        "iso_time": datetime.now().isoformat(),
    }
    
    if DEVICE_NAMESPACE == "traffic":
        base_data.update({
            "vehicle_count": random.randint(0, 50),
            "avg_speed_kmh": random.uniform(20, 80),
            "congestion_level": random.choice(["low", "medium", "high"]),
        })
    elif DEVICE_NAMESPACE == "energy":
        base_data.update({
            "power_kw": random.uniform(0.5, 15.0),
            "voltage": random.uniform(218, 242),
            "frequency_hz": random.uniform(49.9, 50.1),
        })
    elif DEVICE_NAMESPACE == "environment":
        base_data.update({
            "temperature_c": random.uniform(15, 35),
            "humidity_pct": random.uniform(30, 90),
            "air_quality_index": random.randint(0, 300),
        })
    else:
        base_data.update({
            "value": random.uniform(0, 100),
            "unit": "generic",
        })
        
    # Burst devices may include "event" data
    if DEVICE_CLASS == "burst" and random.random() < 0.1:
        base_data["event"] = random.choice([
            "motion_detected",
            "anomaly_detected", 
            "threshold_exceeded",
            "maintenance_required",
        ])
        
    return base_data

def publish_message():
    """Publish a single MQTT message with failure injection."""
    global mqtt_connected
    
    if mqtt_paused or not mqtt_connected:
        metrics.inc_failed()
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
    })

# =============================================================================
# ENTRYPOINT
# =============================================================================

if __name__ == "__main__":
    # Start background threads
    threading.Thread(target=mqtt_connection_loop, daemon=True).start()
    threading.Thread(target=message_generator_loop, daemon=True).start()
    
    # Start HTTP server
    app.run(host="0.0.0.0", port=5000)
