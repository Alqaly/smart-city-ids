#!/usr/bin/env python3
"""
Traffic Camera Service - Smart City IDS
Simulates traffic camera feeds and vehicle detection (intentionally vulnerable for demo)
"""

from flask import Flask, jsonify, request
import time
import random
import os
import logging

app = Flask(__name__)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Simulated camera feeds (UNPROTECTED!)
CAMERAS = {
    "CAM_001": {"location": "Main St & 1st Ave", "status": "active", "vehicles_detected": 0},
    "CAM_002": {"location": "Highway 101 On-Ramp", "status": "active", "vehicles_detected": 0},
    "CAM_003": {"location": "Downtown Parking Garage", "status": "active", "vehicles_detected": 0},
}

# Simulated license plate log (SENSITIVE!)
LICENSE_PLATES = []

request_count = 0


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "traffic-camera",
        "timestamp": time.time()
    }), 200


@app.route('/api/cameras', methods=['GET'])
def get_cameras():
    """List all cameras - VULNERABLE: No authentication!"""
    global request_count
    request_count += 1

    # Simulate real-time vehicle counts
    for cam in CAMERAS.values():
        cam["vehicles_detected"] += random.randint(0, 5)

    return jsonify({
        "cameras": CAMERAS,
        "count": len(CAMERAS)
    }), 200


@app.route('/api/camera/<camera_id>', methods=['GET'])
def get_camera(camera_id):
    """Get individual camera data - VULNERABLE: No auth"""
    global request_count
    request_count += 1

    if camera_id not in CAMERAS:
        return jsonify({"error": "Camera not found"}), 404

    return jsonify({
        "camera_id": camera_id,
        "data": CAMERAS[camera_id],
        "timestamp": time.time()
    }), 200


@app.route('/api/plates', methods=['GET'])
def get_plates():
    """Get license plate log - VULNERABLE: Exposes PII without auth!"""
    global request_count
    request_count += 1

    logger.warning("GET /api/plates - EXPOSING SENSITIVE LICENSE PLATE DATA!")
    return jsonify({
        "plates": LICENSE_PLATES[-50:],
        "total": len(LICENSE_PLATES)
    }), 200


@app.route('/api/plates', methods=['POST'])
def add_plate():
    """Log a plate detection - VULNERABLE: No input validation!"""
    global request_count
    request_count += 1

    data = request.get_json()

    # NO VALIDATION! Attacker can inject anything
    plate = {
        "plate": data.get("plate", "UNKNOWN"),
        "camera_id": data.get("camera_id", "CAM_001"),
        "timestamp": time.time(),
        "speed": data.get("speed", random.randint(20, 80))
    }
    LICENSE_PLATES.append(plate)

    return jsonify({
        "status": "logged",
        "plate": plate
    }), 201


@app.route('/api/analytics', methods=['GET'])
def get_analytics():
    """Traffic analytics - VULNERABLE: No auth"""
    global request_count
    request_count += 1

    total_vehicles = sum(cam["vehicles_detected"] for cam in CAMERAS.values())
    return jsonify({
        "total_vehicles": total_vehicles,
        "active_cameras": sum(1 for c in CAMERAS.values() if c["status"] == "active"),
        "plates_logged": len(LICENSE_PLATES),
        "avg_speed": round(random.uniform(25, 55), 1)
    }), 200


@app.route('/api/stats', methods=['GET'])
def get_stats():
    return jsonify({
        "requests_total": request_count,
        "active_cameras": len(CAMERAS),
        "service": "traffic-camera"
    }), 200


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Starting Traffic Camera Service on port {port}")
    app.run(host='0.0.0.0', port=port, debug=True)
