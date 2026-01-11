import os
import threading
import time
import random
import json
from flask import Flask, request, jsonify
import paho.mqtt.client as mqtt

app = Flask(__name__)

POD_NAME = os.environ.get("POD_NAME", "device")
MQTT_BROKER = os.environ.get("MQTT_BROKER", "mqtt-broker")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))
MQTT_TOPIC = f"mqtt/{POD_NAME}"

mqtt_client = mqtt.Client()

# Metrics counters
sent_count = 0
recv_count = 0
latency_records = []

# Simulation parameters
SIM_LATENCY = float(os.environ.get("SIM_LATENCY", 0.1))  # seconds
SIM_LOSS = float(os.environ.get("SIM_LOSS", 0.1))        # probability (0.0-1.0)
FAIL_PROB = float(os.environ.get("FAIL_PROB", 0.05))     # probability (0.0-1.0)
FAIL_DUR = float(os.environ.get("FAIL_DUR", 40))         # seconds

# MQTT callbacks
def on_connect(client, userdata, flags, rc):
    print(f"Connected to MQTT broker with result code {rc}")
    client.subscribe("mqtt/#")

def on_message(client, userdata, msg):
    global recv_count
    recv_count += 1
    try:
        data = json.loads(msg.payload.decode())
        if "timestamp" in data:
            latency = time.time() - data["timestamp"]
            latency_records.append(latency)
            print(f"Received message from {msg.topic} with latency {latency:.3f} seconds")
        else:
            print(f"Received message from {msg.topic}: {msg.payload.decode()}")
    except Exception:
        print(f"Received message from {msg.topic}: {msg.payload.decode()}")

mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

@app.route("/status", methods=["GET"])
def status():
    return jsonify({"pod": POD_NAME, "status": "online"})

@app.route("/publish", methods=["POST"])
def publish():
    global sent_count
    data = request.json
    message = data.get("message", "hello")
    if simulate_network_conditions():
        payload = json.dumps({"pod": POD_NAME, "type": "custom", "message": message, "timestamp": time.time()})
        mqtt_client.publish(MQTT_TOPIC, payload)
        sent_count += 1
        return jsonify({"published": True, "topic": MQTT_TOPIC, "message": message})
    else:
        return jsonify({"published": False, "topic": MQTT_TOPIC, "message": message, "error": "Simulated packet loss"})

@app.route("/metrics", methods=["GET"])
def metrics():
    avg_latency = sum(latency_records) / len(latency_records) if latency_records else None
    return jsonify({
        "sent": sent_count,
        "received": recv_count,
        "avg_latency": avg_latency,
        "latency_samples": latency_records[-10:]  # last 10 samples
    })

def mqtt_loop():
    while True:
        if not getattr(mqtt_loop, "paused", False):
            try:
                mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 20)
                mqtt_client.loop_start()
                while not getattr(mqtt_loop, "paused", False):
                    time.sleep(1)
                mqtt_client.loop_stop()
                # Do NOT call mqtt_client.disconnect() here to allow broker-side timeout
            except Exception as e:
                print(f"[ERROR] MQTT loop error: {e}")
        else:
            time.sleep(1)

def periodic_publish():
    global sent_count
    while True:
        simulate_device_failure()
        if simulate_network_conditions():
            payload = json.dumps({"pod": POD_NAME, "type": "heartbeat", "timestamp": time.time()})
            mqtt_client.publish(MQTT_TOPIC, payload)
            sent_count += 1
        time.sleep(10)

def simulate_network_conditions():
    # Simulate network latency
    latency = random.uniform(0.01, SIM_LATENCY)
    time.sleep(latency)
    # Simulate packet loss
    if random.random() < SIM_LOSS:
        return False  # Simulate lost packet
    return True

def simulate_device_failure():
    # Simulate device failure
    if random.random() < FAIL_PROB:
        print(f"[FAILURE] {POD_NAME} is simulating a device failure. Stopping MQTT network loop for {FAIL_DUR} seconds.")
        mqtt_loop.paused = True
        time.sleep(FAIL_DUR)
        mqtt_loop.paused = False
        print(f"[RECOVERY] {POD_NAME} is back online and reconnecting to broker.")

if __name__ == "__main__":
    mqtt_loop.paused = False
    threading.Thread(target=mqtt_loop, daemon=True).start()
    threading.Thread(target=periodic_publish, daemon=True).start()
    app.run(host="0.0.0.0", port=5000)
