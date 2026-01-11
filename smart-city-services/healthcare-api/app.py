from flask import Flask, jsonify, request
import time
import random
import os

app = Flask(__name__)

# Simulated patient data (HIPAA-sensitive)
patients = {
    "P001": {"name": "Patient_A", "age": 45, "condition": "Diabetes"},
    "P002": {"name": "Patient_B", "age": 62, "condition": "Hypertension"},
    "P003": {"name": "Patient_C", "age": 38, "condition": "Asthma"}
}

request_count = 0

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "service": "healthcare-api"}), 200

@app.route('/api/patients', methods=['GET'])
def get_patients():
    """List patients (should be protected but isn't)"""
    global request_count
    request_count += 1
    
    # VULNERABILITY: No authentication required for sensitive data
    return jsonify({
        "patients": list(patients.keys()),
        "total": len(patients),
        "warning": "SENSITIVE_MEDICAL_DATA"
    }), 200

@app.route('/api/patient/<patient_id>', methods=['GET'])
def get_patient(patient_id):
    """Get patient details"""
    global request_count
    request_count += 1
    
    if patient_id not in patients:
        return jsonify({"error": "Patient not found"}), 404
    
    return jsonify({
        "patient_id": patient_id,
        "data": patients[patient_id],
        "timestamp": time.time()
    }), 200

@app.route('/api/prescriptions/<patient_id>', methods=['GET', 'POST'])
def prescriptions(patient_id):
    """Prescription endpoint (vulnerable to injection)"""
    global request_count
    request_count += 1
    
    if request.method == 'POST':
        # VULNERABILITY: No input validation
        prescription = request.json
        return jsonify({
            "message": "Prescription added (VULNERABILITY: No validation!)",
            "data": prescription
        }), 201
    
    return jsonify({
        "prescriptions": [
            {"drug": "Medication_X", "dosage": "10mg"},
            {"drug": "Medication_Y", "dosage": "20mg"}
        ]
    }), 200

@app.route('/api/stats', methods=['GET'])
def get_stats():
    return jsonify({
        "requests_total": request_count,
        "active_patients": len(patients),
        "service": "healthcare-api"
    }), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=False)
