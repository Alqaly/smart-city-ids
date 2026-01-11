#!/usr/bin/env python3
"""
Traffic Camera Service - Smart City IDS
Monitors traffic and exposes vulnerable endpoints for demonstration
"""

from flask import Flask, jsonify, request
import os
import logging
from datetime import datetime

app = Flask(__name__)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Simulated camera database
CAMERAS = {
    "CAM-001": {"location": "Downtown-Main", "status": "active", "fps": 30},
    "CAM-002": {"location": "Highway-North", "status": "active", "fps": 24},
    "CAM-003": {"location": "Airport-Terminal", "status": "inactive", "fps": 0},
    "CAM-004": {"location": "Port-East", "status": "active", "fps": 30},
}

ADMIN_CONFIG = {
    "recording_enabled": True,
    "alert_threshold": 0.8,
    "retention_days": 30
}


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "traffic-camera",
        "timestamp": datetime.now().isoformat()
    }), 200


@app.route('/api/cameras', methods=['GET'])
def get_cameras():
    """List all cameras - VULNERABLE: No authentication"""
    logger.info("GET /api/cameras - Retrieving camera list")
    return jsonify({
        "cameras": CAMERAS,
        "total": len(CAMERAS)
    }), 200


@app.route('/api/camera/<camera_id>/stream', methods=['GET'])
def get_stream(camera_id):
    """Get video stream URL - VULNERABLE: No rate limiting"""
    if camera_id not in CAMERAS:
        return jsonify({"error": "Camera not found"}), 404
    
    logger.info(f"GET /api/camera/{camera_id}/stream")
    return jsonify({
        "camera_id": camera_id,
        "stream_url": f"rtsp://stream.local/{camera_id}",
        "resolution": "1080p",
        "bitrate": "5000kbps"
    }), 200


@app.route('/api/analytics', methods=['GET'])
def analytics():
    """Traffic analytics - VULNERABLE: Exposes sensitive data without auth"""
    logger.info("GET /api/analytics - Retrieving analytics (SENSITIVE!)")
    
    # This would normally contain sensitive traffic data
    return jsonify({
        "timestamp": datetime.now().isoformat(),
        "total_vehicles": 1247,
        "average_speed": 45,
        "congestion_level": "moderate",
        "incidents": [
            {"time": "14:23", "type": "accident", "location": "CAM-001"},
            {"time": "14:45", "type": "stalled_vehicle", "location": "CAM-002"}
        ]
    }), 200


@app.route('/admin/config', methods=['GET', 'POST', 'PUT'])
def admin_config():
    """Admin configuration - VULNERABLE: NO AUTHENTICATION! 🚨"""
    logger.warning(f"{request.method} /admin/config - NO AUTH CHECK!")
    
    if request.method == 'GET':
        return jsonify(ADMIN_CONFIG), 200
    
    elif request.method in ['POST', 'PUT']:
        # Attacker can modify this!
        data = request.get_json()
        ADMIN_CONFIG.update(data)
        logger.critical(f"Admin config modified: {data}")
        return jsonify({
            "message": "Configuration updated",
            "config": ADMIN_CONFIG
        }), 200


@app.route('/api/status', methods=['GET'])
def status():
    """System status"""
    return jsonify({
        "service": "traffic-camera",
        "version": "1.0.0",
        "uptime": "stable",
        "cameras_active": sum(1 for c in CAMERAS.values() if c['status'] == 'active')
    }), 200


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Starting Traffic Camera Service on port {port}")
    app.run(host='0.0.0.0', port=port, debug=True)
