#!/usr/bin/env python3
"""
Healthcare API Service - Smart City IDS
Manages patient data and prescriptions (intentionally vulnerable for demo)
"""

from flask import Flask, jsonify, request
import logging
from datetime import datetime

app = Flask(__name__)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Simulated patient database (UNENCRYPTED!)
PATIENTS = {
    "P001": {
        "name": "John Smith",
        "ssn": "123-45-6789",
        "age": 45,
        "conditions": ["Hypertension", "Diabetes"]
    },
    "P002": {
        "name": "Jane Doe",
        "ssn": "987-65-4321",
        "age": 32,
        "conditions": ["Asthma"]
    },
}

PRESCRIPTIONS = {}


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "healthcare-api",
        "timestamp": datetime.now().isoformat()
    }), 200


@app.route('/api/patients', methods=['GET'])
def get_patients():
    """List all patients - VULNERABLE: No authentication!"""
    logger.warning("GET /api/patients - EXPOSING SENSITIVE PATIENT DATA (HIPAA VIOLATION!)")
    return jsonify({
        "patients": PATIENTS,
        "count": len(PATIENTS)
    }), 200


@app.route('/api/patient/<patient_id>', methods=['GET'])
def get_patient(patient_id):
    """Get individual patient data - VULNERABLE: No auth"""
    if patient_id not in PATIENTS:
        return jsonify({"error": "Patient not found"}), 404
    
    logger.warning(f"GET /api/patient/{patient_id} - EXPOSING PII!")
    return jsonify(PATIENTS[patient_id]), 200


@app.route('/api/prescriptions/<patient_id>', methods=['POST'])
def add_prescription(patient_id):
    """Add prescription - VULNERABLE: No input validation!"""
    if patient_id not in PATIENTS:
        return jsonify({"error": "Patient not found"}), 404
    
    data = request.get_json()
    
    # NO VALIDATION! Attacker can inject anything
    logger.critical(f"Adding prescription for {patient_id}: {data}")
    
    prescription_id = f"RX-{len(PRESCRIPTIONS) + 1}"
    PRESCRIPTIONS[prescription_id] = {
        "patient_id": patient_id,
        "drug": data.get("drug"),
        "dosage": data.get("dosage"),
        "duration": data.get("duration"),
        "timestamp": datetime.now().isoformat()
    }
    
    return jsonify({
        "prescription_id": prescription_id,
        "status": "created"
    }), 201


@app.route('/api/prescriptions/<patient_id>', methods=['GET'])
def get_prescriptions(patient_id):
    """Get patient prescriptions - VULNERABLE: No auth"""
    patient_rxs = [rx for rx in PRESCRIPTIONS.values() if rx['patient_id'] == patient_id]
    return jsonify(patient_rxs), 200


@app.route('/admin/logs', methods=['GET'])
def admin_logs():
    """Admin logs - VULNERABLE: Exposes all activities"""
    logger.warning("GET /admin/logs - UNAUTHORIZED ACCESS TO LOGS!")
    return jsonify({
        "logs": [
            "Patient P001 accessed",
            "Prescription added for P002",
            "Admin config changed"
        ]
    }), 200


if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5001))
    logger.info(f"Starting Healthcare API on port {port}")
    app.run(host='0.0.0.0', port=port, debug=True)
