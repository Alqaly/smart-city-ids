#!/usr/bin/env python3
"""
Healthcare IoT Emulator — HL7 FHIR R4 / Medical Device (IEEE 11073)
====================================================================
Faithfully emulates a healthcare IoT gateway serving:

  • HL7 FHIR R4 REST API  (Patient, Observation, MedicationRequest, Bundle)
  • FHIR CapabilityStatement  (/metadata)
  • Medical device telemetry  (IEEE 11073 PHD data model)
  • Real LOINC codes for vital signs
  • FHIR resource references, proper IDs, meta.versionId

Emulated devices:
  - Pulse Oximeter  (SpO2 + pulse rate, IEEE 11073-10404)
  - Blood Pressure Monitor  (systolic/diastolic/MAP, IEEE 11073-10407)
  - ECG/Heart Rate Monitor  (HR + rhythm, IEEE 11073-10406)
  - Infusion Pump  (rate, volume, drug, IEEE 11073-10101)
  - Bed Sensor  (patient presence, fall detection)

Intentionally VULNERABLE for Smart City IDS demo:
  - No OAuth2 / SMART on FHIR — PHI exposed without auth
  - No TLS — all medical data in plaintext
  - HIPAA violations by design (PII in responses)
  - Admin endpoint exposes all patient data in bulk
"""

from flask import Flask, Response, jsonify, request
import time
import os
import random
import math
import threading
import logging
import json
import uuid
import hashlib
from datetime import datetime, timezone, timedelta
from copy import deepcopy

# ─── App ────────────────────────────────────────────────────────────────────────

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("fhir-gateway")

FHIR_BASE = os.environ.get("FHIR_BASE", "http://healthcare-api.smart-city:5001")
SYSTEM_ID = os.environ.get("SYSTEM_ID", "smart-city-health-gw-001")
FHIR_VERSION = "4.0.1"

# ═════════════════════════════════════════════════════════════════════════════════
# LOINC Codes  (Logical Observation Identifiers Names and Codes)
# ═════════════════════════════════════════════════════════════════════════════════

LOINC = {
    "heart_rate":          {"code": "8867-4",  "display": "Heart rate",             "unit": "/min",   "ucum": "/min"},
    "spo2":                {"code": "2708-6",  "display": "Oxygen saturation",      "unit": "%",      "ucum": "%"},
    "systolic_bp":         {"code": "8480-6",  "display": "Systolic blood pressure", "unit": "mmHg",  "ucum": "mm[Hg]"},
    "diastolic_bp":        {"code": "8462-4",  "display": "Diastolic blood pressure","unit": "mmHg",  "ucum": "mm[Hg]"},
    "body_temperature":    {"code": "8310-5",  "display": "Body temperature",       "unit": "°C",     "ucum": "Cel"},
    "respiratory_rate":    {"code": "9279-1",  "display": "Respiratory rate",        "unit": "/min",   "ucum": "/min"},
    "blood_glucose":       {"code": "2339-0",  "display": "Glucose [Mass/volume]",  "unit": "mg/dL",  "ucum": "mg/dL"},
    "weight":              {"code": "29463-7", "display": "Body weight",            "unit": "kg",     "ucum": "kg"},
    "mean_arterial":       {"code": "8478-0",  "display": "Mean arterial pressure", "unit": "mmHg",   "ucum": "mm[Hg]"},
    "pulse_oximetry_wave": {"code": "59408-5", "display": "Oxygen saturation (pulse ox)", "unit": "%", "ucum": "%"},
}


# ═════════════════════════════════════════════════════════════════════════════════
# Patient Registry
# ═════════════════════════════════════════════════════════════════════════════════

def _make_patient(pid: str, family: str, given: str, gender: str,
                  birth_date: str, mrn: str, conditions: list):
    """Build a FHIR R4 Patient resource."""
    return {
        "resourceType": "Patient",
        "id": pid,
        "meta": {
            "versionId": "1",
            "lastUpdated": datetime.now(timezone.utc).isoformat(),
            "profile": ["http://hl7.org/fhir/us/core/StructureDefinition/us-core-patient"],
        },
        "identifier": [
            {
                "system": "http://hospital.smartcity.local/mrn",
                "value": mrn,
                "type": {
                    "coding": [{"system": "http://terminology.hl7.org/CodeSystem/v2-0203", "code": "MR"}]
                },
            }
        ],
        "active": True,
        "name": [{"family": family, "given": [given], "use": "official"}],
        "gender": gender,
        "birthDate": birth_date,
        "address": [{"city": "Smart City", "state": "CA", "postalCode": "94000", "country": "US"}],
        "telecom": [
            {"system": "phone", "value": f"555-{random.randint(1000,9999)}", "use": "home"},
        ],
        "_conditions": conditions,  # Non-FHIR extension for demo
    }

PATIENTS = {
    "P001": _make_patient("P001", "Anderson", "Sarah",  "female", "1979-03-15", "MRN-10001",
                          ["Diabetes mellitus type 2", "Hypertension"]),
    "P002": _make_patient("P002", "Chen",     "Robert", "male",   "1962-11-28", "MRN-10002",
                          ["Atrial fibrillation", "Heart failure"]),
    "P003": _make_patient("P003", "Martinez", "Elena",  "female", "1986-07-22", "MRN-10003",
                          ["Asthma", "Allergic rhinitis"]),
    "P004": _make_patient("P004", "Williams", "James",  "male",   "1955-01-09", "MRN-10004",
                          ["COPD", "Hypertension", "Type 2 diabetes"]),
    "P005": _make_patient("P005", "Kim",      "Yuna",   "female", "1991-09-03", "MRN-10005",
                          ["Pregnancy (34 weeks)", "Gestational diabetes"]),
}


# ═════════════════════════════════════════════════════════════════════════════════
# Medical Device Emulation  (IEEE 11073 PHD)
# ═════════════════════════════════════════════════════════════════════════════════

class MedicalDevice:
    """Emulates a bedside medical IoT device (IEEE 11073 Personal Health Device)."""

    def __init__(self, device_id: str, device_type: str, patient_id: str,
                 ieee_type: str, location: str):
        self.device_id = device_id
        self.device_type = device_type
        self.patient_id = patient_id
        self.ieee_type = ieee_type
        self.location = location
        self.boot_time = time.time()
        self.status = "active"
        self.battery_pct = round(random.uniform(50, 100), 1)
        self.firmware = "v3.1.0"
        self.readings = {}
        self.alarm_active = False
        self.alarm_type = None

    def tick(self):
        """Generate physiologically realistic readings."""
        self.battery_pct = max(0, self.battery_pct - random.uniform(0, 0.005))
        patient = PATIENTS.get(self.patient_id, {})
        conditions = patient.get("_conditions", [])

        if self.device_type == "pulse_oximeter":
            # SpO2 + pulse — affected by COPD/asthma
            base_spo2 = 92 if any("COPD" in c for c in conditions) else 97
            spo2 = max(70, min(100, round(random.gauss(base_spo2, 1.5))))
            hr = round(random.gauss(75, 8))
            self.readings = {"spo2": spo2, "heart_rate": hr}
            self.alarm_active = spo2 < 90
            self.alarm_type = "LOW_SPO2" if self.alarm_active else None

        elif self.device_type == "blood_pressure":
            # BP affected by hypertension
            base_sys = 145 if any("Hypertension" in c for c in conditions) else 120
            sys = round(random.gauss(base_sys, 8))
            dia = round(random.gauss(sys * 0.55, 5))
            map_val = round(dia + (sys - dia) / 3)
            self.readings = {"systolic_bp": sys, "diastolic_bp": dia, "mean_arterial": map_val}
            self.alarm_active = sys > 180 or dia > 120
            self.alarm_type = "HYPERTENSIVE_CRISIS" if self.alarm_active else None

        elif self.device_type == "ecg_monitor":
            # HR + rhythm — affected by AF
            has_af = any("Atrial fibrillation" in c for c in conditions)
            hr = round(random.gauss(85 if has_af else 72, 12 if has_af else 5))
            self.readings = {
                "heart_rate": max(30, min(220, hr)),
                "rhythm": "Atrial Fibrillation" if has_af and random.random() < 0.7 else "Normal Sinus",
                "qt_interval_ms": round(random.gauss(400, 20)),
                "pr_interval_ms": round(random.gauss(160, 10)),
            }
            self.alarm_active = hr > 150 or hr < 45
            self.alarm_type = ("TACHYCARDIA" if hr > 150 else "BRADYCARDIA") if self.alarm_active else None

        elif self.device_type == "infusion_pump":
            rate = round(random.gauss(125, 5), 1)
            self.readings = {
                "infusion_rate_ml_hr": max(0, rate),
                "volume_infused_ml": round(rate * (time.time() - self.boot_time) / 3600, 1),
                "volume_remaining_ml": max(0, round(1000 - rate * (time.time() - self.boot_time) / 3600, 1)),
                "drug": "Normal Saline 0.9%",
                "occlusion_detected": random.random() < 0.005,
            }
            self.alarm_active = self.readings.get("occlusion_detected", False)
            self.alarm_type = "OCCLUSION" if self.alarm_active else None

        elif self.device_type == "bed_sensor":
            # Patient presence + fall risk
            in_bed = random.random() < 0.85
            self.readings = {
                "patient_in_bed": in_bed,
                "weight_kg": round(random.gauss(70, 0.5), 1),
                "movement_index": round(random.uniform(0, 10 if in_bed else 0), 1),
                "fall_detected": not in_bed and random.random() < 0.01,
                "bed_angle_degrees": round(random.gauss(30, 2)),
            }
            self.alarm_active = self.readings.get("fall_detected", False)
            self.alarm_type = "FALL_DETECTED" if self.alarm_active else None

        elif self.device_type == "thermometer":
            base_temp = 38.2 if random.random() < 0.1 else 36.8
            temp = round(random.gauss(base_temp, 0.3), 1)
            self.readings = {"body_temperature": temp}
            self.alarm_active = temp > 38.5 or temp < 35.0
            self.alarm_type = ("HYPERTHERMIA" if temp > 38.5 else "HYPOTHERMIA") if self.alarm_active else None

    def to_fhir_device(self):
        """FHIR R4 Device resource."""
        return {
            "resourceType": "Device",
            "id": self.device_id,
            "meta": {"versionId": "1", "lastUpdated": datetime.now(timezone.utc).isoformat()},
            "status": self.status,
            "manufacturer": "SmartCity MedTech",
            "deviceName": [{"name": f"{self.device_type.replace('_', ' ').title()}", "type": "manufacturer-name"}],
            "modelNumber": f"SC-{self.ieee_type}",
            "serialNumber": self.device_id,
            "version": [{"value": self.firmware}],
            "patient": {"reference": f"Patient/{self.patient_id}"},
            "location": {"display": self.location},
            "property": [
                {"type": {"text": "battery"}, "valueQuantity": [{"value": round(self.battery_pct, 1), "unit": "%"}]},
                {"type": {"text": "ieee_type"}, "valueCode": [{"value": self.ieee_type}]},
            ],
        }


DEVICES = {
    "DEV-PO-001":  MedicalDevice("DEV-PO-001",  "pulse_oximeter",  "P001", "11073-10404", "ICU Bed 1"),
    "DEV-BP-001":  MedicalDevice("DEV-BP-001",  "blood_pressure",  "P001", "11073-10407", "ICU Bed 1"),
    "DEV-ECG-001": MedicalDevice("DEV-ECG-001", "ecg_monitor",     "P002", "11073-10406", "ICU Bed 2"),
    "DEV-INF-001": MedicalDevice("DEV-INF-001", "infusion_pump",   "P002", "11073-10101", "ICU Bed 2"),
    "DEV-BED-001": MedicalDevice("DEV-BED-001", "bed_sensor",      "P003", "custom-bed",  "Ward B Bed 5"),
    "DEV-TH-001":  MedicalDevice("DEV-TH-001",  "thermometer",     "P004", "11073-10408", "Ward A Bed 3"),
    "DEV-PO-002":  MedicalDevice("DEV-PO-002",  "pulse_oximeter",  "P004", "11073-10404", "Ward A Bed 3"),
    "DEV-BP-002":  MedicalDevice("DEV-BP-002",  "blood_pressure",  "P005", "11073-10407", "OB Bed 1"),
    "DEV-ECG-002": MedicalDevice("DEV-ECG-002", "ecg_monitor",     "P005", "11073-10406", "OB Bed 1"),
}


def _device_ticker():
    while True:
        for d in DEVICES.values():
            d.tick()
        time.sleep(2.0)

threading.Thread(target=_device_ticker, daemon=True).start()


# ═════════════════════════════════════════════════════════════════════════════════
# Observation Store  (rolling buffer of vital signs)
# ═════════════════════════════════════════════════════════════════════════════════

OBSERVATIONS = []  # List of FHIR Observation resources
OBS_MAX = 5000
_obs_counter = 0


def _create_observation(device: MedicalDevice):
    """Create FHIR R4 Observation resources from device readings."""
    global _obs_counter
    now = datetime.now(timezone.utc).isoformat()
    results = []
    for key, value in device.readings.items():
        if key not in LOINC:
            continue
        if not isinstance(value, (int, float)):
            continue
        _obs_counter += 1
        loinc = LOINC[key]
        obs = {
            "resourceType": "Observation",
            "id": f"obs-{_obs_counter:06d}",
            "meta": {
                "versionId": "1",
                "lastUpdated": now,
                "profile": ["http://hl7.org/fhir/us/core/StructureDefinition/us-core-vital-signs"],
            },
            "status": "final",
            "category": [
                {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                            "code": "vital-signs",
                            "display": "Vital Signs",
                        }
                    ]
                }
            ],
            "code": {
                "coding": [
                    {
                        "system": "http://loinc.org",
                        "code": loinc["code"],
                        "display": loinc["display"],
                    }
                ],
                "text": loinc["display"],
            },
            "subject": {"reference": f"Patient/{device.patient_id}"},
            "effectiveDateTime": now,
            "device": {"reference": f"Device/{device.device_id}"},
            "valueQuantity": {
                "value": round(value, 1),
                "unit": loinc["unit"],
                "system": "http://unitsofmeasure.org",
                "code": loinc["ucum"],
            },
        }
        # Add interpretation for abnormal values
        if device.alarm_active:
            obs["interpretation"] = [
                {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
                            "code": "A",
                            "display": "Abnormal",
                        }
                    ]
                }
            ]
        results.append(obs)
        OBSERVATIONS.append(obs)
    # Trim buffer
    while len(OBSERVATIONS) > OBS_MAX:
        OBSERVATIONS.pop(0)
    return results


def _observation_generator():
    """Background thread — create observations every 5 seconds."""
    while True:
        for d in DEVICES.values():
            _create_observation(d)
        time.sleep(5.0)

threading.Thread(target=_observation_generator, daemon=True).start()


# ═════════════════════════════════════════════════════════════════════════════════
# Medication Requests
# ═════════════════════════════════════════════════════════════════════════════════

MEDICATIONS = [
    {
        "resourceType": "MedicationRequest",
        "id": "medrx-001",
        "status": "active",
        "intent": "order",
        "medicationCodeableConcept": {
            "coding": [{"system": "http://www.nlm.nih.gov/research/umls/rxnorm", "code": "860975", "display": "Metformin 500mg"}],
            "text": "Metformin 500mg oral tablet",
        },
        "subject": {"reference": "Patient/P001"},
        "dosageInstruction": [{"text": "Take 1 tablet twice daily with meals", "timing": {"repeat": {"frequency": 2, "period": 1, "periodUnit": "d"}}}],
    },
    {
        "resourceType": "MedicationRequest",
        "id": "medrx-002",
        "status": "active",
        "intent": "order",
        "medicationCodeableConcept": {
            "coding": [{"system": "http://www.nlm.nih.gov/research/umls/rxnorm", "code": "197361", "display": "Lisinopril 10mg"}],
            "text": "Lisinopril 10mg oral tablet",
        },
        "subject": {"reference": "Patient/P001"},
        "dosageInstruction": [{"text": "Take 1 tablet daily", "timing": {"repeat": {"frequency": 1, "period": 1, "periodUnit": "d"}}}],
    },
    {
        "resourceType": "MedicationRequest",
        "id": "medrx-003",
        "status": "active",
        "intent": "order",
        "medicationCodeableConcept": {
            "coding": [{"system": "http://www.nlm.nih.gov/research/umls/rxnorm", "code": "855332", "display": "Warfarin 5mg"}],
            "text": "Warfarin 5mg oral tablet",
        },
        "subject": {"reference": "Patient/P002"},
        "dosageInstruction": [{"text": "Take 1 tablet daily at bedtime", "timing": {"repeat": {"frequency": 1, "period": 1, "periodUnit": "d"}}}],
    },
    {
        "resourceType": "MedicationRequest",
        "id": "medrx-004",
        "status": "active",
        "intent": "order",
        "medicationCodeableConcept": {
            "coding": [{"system": "http://www.nlm.nih.gov/research/umls/rxnorm", "code": "835829", "display": "Albuterol 90mcg inhaler"}],
            "text": "Albuterol 90mcg/actuation inhalation aerosol",
        },
        "subject": {"reference": "Patient/P003"},
        "dosageInstruction": [{"text": "2 puffs every 4-6 hours as needed", "asNeededBoolean": True}],
    },
    {
        "resourceType": "MedicationRequest",
        "id": "medrx-005",
        "status": "active",
        "intent": "order",
        "medicationCodeableConcept": {
            "coding": [{"system": "http://www.nlm.nih.gov/research/umls/rxnorm", "code": "253182", "display": "Insulin Glargine"}],
            "text": "Insulin Glargine 100 units/mL injection",
        },
        "subject": {"reference": "Patient/P005"},
        "dosageInstruction": [{"text": "20 units subcutaneous injection at bedtime"}],
    },
]


# ═════════════════════════════════════════════════════════════════════════════════
# FHIR Bundle helper
# ═════════════════════════════════════════════════════════════════════════════════

def _fhir_bundle(resources, bundle_type="searchset", total=None):
    """Wrap resources in a FHIR R4 Bundle."""
    if total is None:
        total = len(resources)
    return {
        "resourceType": "Bundle",
        "id": str(uuid.uuid4()),
        "meta": {"lastUpdated": datetime.now(timezone.utc).isoformat()},
        "type": bundle_type,
        "total": total,
        "entry": [
            {
                "fullUrl": f"{FHIR_BASE}/{r['resourceType']}/{r['id']}",
                "resource": r,
            }
            for r in resources
        ],
    }


def _fhir_response(data, status=200):
    """Return JSON with FHIR content type."""
    return Response(
        json.dumps(data, default=str),
        status=status,
        content_type="application/fhir+json; charset=utf-8",
    )


# ═════════════════════════════════════════════════════════════════════════════════
# FHIR R4 REST Endpoints
# ═════════════════════════════════════════════════════════════════════════════════

@app.route("/metadata", methods=["GET"])
def capability_statement():
    """FHIR CapabilityStatement — server capability discovery."""
    cs = {
        "resourceType": "CapabilityStatement",
        "id": "smart-city-healthcare",
        "status": "active",
        "date": datetime.now(timezone.utc).isoformat(),
        "kind": "instance",
        "fhirVersion": FHIR_VERSION,
        "format": ["json"],
        "implementation": {
            "description": "Smart City Healthcare IoT Gateway (FHIR R4)",
            "url": FHIR_BASE,
        },
        "rest": [
            {
                "mode": "server",
                "security": {
                    "cors": True,
                    "service": [],
                    "description": "WARNING: No OAuth2/SMART — intentionally insecure for IDS demo",
                },
                "resource": [
                    {
                        "type": rt,
                        "interaction": [{"code": "read"}, {"code": "search-type"}],
                        "searchParam": sp,
                    }
                    for rt, sp in [
                        ("Patient", [
                            {"name": "_id", "type": "token"},
                            {"name": "name", "type": "string"},
                        ]),
                        ("Observation", [
                            {"name": "patient", "type": "reference"},
                            {"name": "code", "type": "token"},
                            {"name": "category", "type": "token"},
                        ]),
                        ("MedicationRequest", [
                            {"name": "patient", "type": "reference"},
                            {"name": "status", "type": "token"},
                        ]),
                        ("Device", [
                            {"name": "patient", "type": "reference"},
                            {"name": "type", "type": "token"},
                        ]),
                    ]
                ],
            }
        ],
    }
    return _fhir_response(cs)


# ─── Patient ────────────────────────────────────────────────────────────────────

@app.route("/Patient", methods=["GET"])
def search_patients():
    """FHIR Patient search — VULNERABLE: no auth, PHI exposed!"""
    name_filter = request.args.get("name", "").lower()
    pid_filter = request.args.get("_id")
    results = []
    for p in PATIENTS.values():
        if pid_filter and p["id"] != pid_filter:
            continue
        if name_filter:
            full_name = f"{p['name'][0]['given'][0]} {p['name'][0]['family']}".lower()
            if name_filter not in full_name:
                continue
        # Return without internal fields
        clean = {k: v for k, v in p.items() if not k.startswith("_")}
        results.append(clean)
    return _fhir_response(_fhir_bundle(results))


@app.route("/Patient/<patient_id>", methods=["GET"])
def read_patient(patient_id):
    """FHIR Patient read."""
    p = PATIENTS.get(patient_id)
    if not p:
        return _fhir_response({"resourceType": "OperationOutcome", "issue": [
            {"severity": "error", "code": "not-found", "diagnostics": f"Patient/{patient_id} not found"}
        ]}, 404)
    clean = {k: v for k, v in p.items() if not k.startswith("_")}
    return _fhir_response(clean)


# ─── Observation ────────────────────────────────────────────────────────────────

@app.route("/Observation", methods=["GET"])
def search_observations():
    """FHIR Observation search — vital signs with real LOINC codes."""
    patient_filter = request.args.get("patient")
    code_filter = request.args.get("code")
    category_filter = request.args.get("category")
    count = min(int(request.args.get("_count", 50)), 200)
    results = []
    for obs in reversed(OBSERVATIONS):
        if patient_filter and f"Patient/{patient_filter}" != obs.get("subject", {}).get("reference"):
            continue
        if code_filter:
            codes = [c["code"] for c in obs.get("code", {}).get("coding", [])]
            if code_filter not in codes:
                continue
        results.append(obs)
        if len(results) >= count:
            break
    return _fhir_response(_fhir_bundle(results, total=len(OBSERVATIONS)))


@app.route("/Observation/<obs_id>", methods=["GET"])
def read_observation(obs_id):
    """FHIR Observation read."""
    for obs in OBSERVATIONS:
        if obs["id"] == obs_id:
            return _fhir_response(obs)
    return _fhir_response({"resourceType": "OperationOutcome", "issue": [
        {"severity": "error", "code": "not-found", "diagnostics": f"Observation/{obs_id} not found"}
    ]}, 404)


# ─── MedicationRequest ─────────────────────────────────────────────────────────

@app.route("/MedicationRequest", methods=["GET"])
def search_medication_requests():
    """FHIR MedicationRequest search — VULNERABLE: prescriptions without auth!"""
    patient_filter = request.args.get("patient")
    results = MEDICATIONS
    if patient_filter:
        results = [m for m in results if m.get("subject", {}).get("reference") == f"Patient/{patient_filter}"]
    return _fhir_response(_fhir_bundle(results))


@app.route("/MedicationRequest/<med_id>", methods=["GET"])
def read_medication_request(med_id):
    for m in MEDICATIONS:
        if m["id"] == med_id:
            return _fhir_response(m)
    return _fhir_response({"resourceType": "OperationOutcome", "issue": [
        {"severity": "error", "code": "not-found"}
    ]}, 404)


# ─── Device ─────────────────────────────────────────────────────────────────────

@app.route("/Device", methods=["GET"])
def search_devices():
    """FHIR Device search — medical device inventory."""
    patient_filter = request.args.get("patient")
    results = []
    for d in DEVICES.values():
        if patient_filter and d.patient_id != patient_filter:
            continue
        results.append(d.to_fhir_device())
    return _fhir_response(_fhir_bundle(results))


@app.route("/Device/<device_id>", methods=["GET"])
def read_device(device_id):
    d = DEVICES.get(device_id)
    if not d:
        return _fhir_response({"resourceType": "OperationOutcome", "issue": [
            {"severity": "error", "code": "not-found"}
        ]}, 404)
    return _fhir_response(d.to_fhir_device())


# ═════════════════════════════════════════════════════════════════════════════════
# Device Telemetry  (IEEE 11073 + real-time)
# ═════════════════════════════════════════════════════════════════════════════════

@app.route("/api/devices/telemetry", methods=["GET"])
def device_telemetry():
    """Real-time device telemetry — IEEE 11073 data model."""
    patient_filter = request.args.get("patient")
    result = []
    for d in DEVICES.values():
        if patient_filter and d.patient_id != patient_filter:
            continue
        result.append({
            "device_id": d.device_id,
            "type": d.device_type,
            "ieee_standard": d.ieee_type,
            "patient": d.patient_id,
            "location": d.location,
            "status": d.status,
            "battery_pct": round(d.battery_pct, 1),
            "alarm_active": d.alarm_active,
            "alarm_type": d.alarm_type,
            "readings": d.readings,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    return jsonify({"devices": result, "count": len(result)})


@app.route("/api/devices/alarms", methods=["GET"])
def device_alarms():
    """Active medical device alarms."""
    alarms = []
    for d in DEVICES.values():
        if d.alarm_active:
            alarms.append({
                "device_id": d.device_id,
                "patient": d.patient_id,
                "alarm_type": d.alarm_type,
                "readings": d.readings,
                "location": d.location,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
    return jsonify({"alarms": alarms, "count": len(alarms)})


# ═════════════════════════════════════════════════════════════════════════════════
# Legacy REST endpoints  (backward-compatible)
# ═════════════════════════════════════════════════════════════════════════════════

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy",
        "service": "healthcare-fhir-emulator",
        "protocol": "HL7 FHIR R4",
        "fhir_version": FHIR_VERSION,
        "system_id": SYSTEM_ID,
        "patients": len(PATIENTS),
        "devices": len(DEVICES),
        "observations": len(OBSERVATIONS),
    }), 200


@app.route("/api/patients", methods=["GET"])
def legacy_patients():
    """Legacy patient list — VULNERABLE: PHI without auth!"""
    return jsonify({
        "patients": list(PATIENTS.keys()),
        "total": len(PATIENTS),
        "WARNING": "HIPAA_VIOLATION_NO_AUTH",
        "fhir_endpoint": f"{FHIR_BASE}/Patient",
    }), 200


@app.route("/api/patient/<patient_id>", methods=["GET"])
def legacy_patient(patient_id):
    p = PATIENTS.get(patient_id)
    if not p:
        return jsonify({"error": "Patient not found"}), 404
    clean = {k: v for k, v in p.items() if not k.startswith("_")}
    return jsonify({
        "patient_id": patient_id,
        "data": clean,
        "fhir_url": f"{FHIR_BASE}/Patient/{patient_id}",
    }), 200


@app.route("/api/prescriptions/<patient_id>", methods=["GET", "POST"])
def prescriptions(patient_id):
    """Prescription endpoint — VULNERABLE: no input validation!"""
    if request.method == "POST":
        rx = request.json or {}
        logger.warning(f"UNVALIDATED PRESCRIPTION from {request.remote_addr}: {json.dumps(rx)}")
        return jsonify({
            "message": "Prescription added (NO VALIDATION — VULNERABLE!)",
            "data": rx,
            "WARNING": "NO_CLINICAL_DECISION_SUPPORT",
        }), 201
    meds = [m for m in MEDICATIONS if m.get("subject", {}).get("reference") == f"Patient/{patient_id}"]
    return jsonify({"prescriptions": meds}), 200


@app.route("/api/admin/export", methods=["GET"])
def admin_export():
    """VULNERABILITY: Bulk PHI export without auth — HIPAA violation!"""
    logger.warning(f"BULK PHI EXPORT from {request.remote_addr} — HIPAA VIOLATION")
    return jsonify({
        "WARNING": "UNAUTHORIZED_BULK_PHI_EXPORT",
        "patients": {pid: {k: v for k, v in p.items() if not k.startswith("_")}
                     for pid, p in PATIENTS.items()},
        "medications": MEDICATIONS,
        "observations_count": len(OBSERVATIONS),
        "devices": {did: d.to_fhir_device() for did, d in DEVICES.items()},
    })


@app.route("/api/stats", methods=["GET"])
def get_stats():
    active_alarms = sum(1 for d in DEVICES.values() if d.alarm_active)
    return jsonify({
        "service": "healthcare-fhir-emulator",
        "protocol": "HL7 FHIR R4 + IEEE 11073",
        "fhir_version": FHIR_VERSION,
        "active_patients": len(PATIENTS),
        "active_devices": len(DEVICES),
        "observations_total": len(OBSERVATIONS),
        "active_alarms": active_alarms,
        "medications_active": len(MEDICATIONS),
    }), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    logger.info(f"Starting Healthcare FHIR R4 Emulator ({SYSTEM_ID}) on port {port}")
    logger.info(f"  Patients: {len(PATIENTS)} | Devices: {len(DEVICES)}")
    logger.info(f"  FHIR Base:     {FHIR_BASE}")
    logger.info(f"  Metadata:      http://0.0.0.0:{port}/metadata")
    logger.info(f"  Patient:       http://0.0.0.0:{port}/Patient")
    logger.info(f"  Observation:   http://0.0.0.0:{port}/Observation")
    logger.info(f"  Device:        http://0.0.0.0:{port}/Device")
    logger.info(f"  Telemetry:     http://0.0.0.0:{port}/api/devices/telemetry")
    logger.info(f"  WARNING: No OAuth2/SMART — PHI exposed without auth (IDS demo)")
    app.run(host="0.0.0.0", port=port, debug=False)
