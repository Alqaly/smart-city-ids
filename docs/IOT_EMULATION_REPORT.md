# IoT Device Emulation — Technical Report

> [!IMPORTANT]
> Historical / snapshot document. This file may contain time-bound results, legacy route names, or report-only summaries.
> Do not use it as the current API/runtime contract. Verify current behavior using `docs/INDEX.md`, `docs/API_REFERENCE.md`,
> and live checks (`/health`, `/api/alerts`, `/api/metrics`).


## 1. Overview

This document describes the design, implementation, and deployment of **protocol-accurate IoT device emulators** for the Smart City Intrusion Detection System (IDS) capstone project. The emulation layer replaces the prior simulation approach (random number generators) with realistic, standards-compliant protocol implementations that generate authentic network traffic and data patterns for intrusion detection analysis.

Related attack documentation and appendix artifacts:
- Attack Simulation UX + governance: [ATTACK_SIMULATION_GUIDE.md](ATTACK_SIMULATION_GUIDE.md)
- Machine-readable coverage matrix (67 scenarios + 5 campaigns):
  - [ATTACK_COVERAGE_MATRIX.json](ATTACK_COVERAGE_MATRIX.json)
  - [ATTACK_COVERAGE_MATRIX.csv](ATTACK_COVERAGE_MATRIX.csv)

Realism scope note: this project prioritizes **protocol and application-layer fidelity** (network traffic, state, and semantics) for IDS/LLM evaluation. Hardware-level side channels (thermal/power/PMU) are not currently modeled and should be documented as out-of-scope unless explicitly required by the evaluation.

### 1.1 Emulation vs. Simulation — Why It Matters

| Aspect | Simulation (before) | Emulation (after) |
|--------|--------------------|--------------------|
| Data generation | `random.randint()`, hardcoded dicts | Physics-based models, protocol state machines |
| Protocol fidelity | None — plain JSON REST only | Industry-standard protocols (ONVIF, MQTT, FHIR, Modbus, DALI) |
| Network traffic | Artificial HTTP payloads | Protocol-accurate frames, register maps, SOAP envelopes |
| IDS relevance | Detects fake patterns | Tests against real-world protocol anomalies |
| Academic credibility | Low — oversimplified synthetic data | High — references ISO/IEC/IEEE/IETF standards |

**Key distinction:** A *simulator* approximates behavior with random outputs. An *emulator* faithfully reproduces the interfaces, protocols, and data structures of the real device, allowing the IDS to be evaluated against authentic traffic patterns.

---

## 2. Emulated IoT Device Types

### 2.1 Traffic Camera — ONVIF Profile S (SOAP 1.2)

**Standards:** ONVIF Profile S (Streaming), SOAP 1.2, WS-Discovery, WS-Security

**Implementation:** `smart-city-services/traffic-camera/app.py` (~530 lines)

| Feature | Detail |
|---------|--------|
| Protocol | ONVIF Profile S with SOAP 1.2 XML envelopes |
| Device service | `GetDeviceInformation`, `GetCapabilities`, `GetSystemDateAndTime` |
| Media service | `GetProfiles`, `GetStreamUri` (RTSP), `GetSnapshotUri` |
| PTZ service | `GetStatus`, `AbsoluteMove`, `ContinuousMove`, `Stop` |
| Event service | `GetEventProperties`, `PullMessages` (motion, tampering, storage) |
| WS-Discovery | UUID-based multicast probe matching |
| ANPR engine | Realistic plate generation (US format), Gaussian confidence, vehicle classification (sedan, SUV, truck, motorcycle, bus) |
| Telemetry | Frame counter, CMOS temperature, bitrate, H.264 codec stats, IR status, WDR, storage usage |
| Camera model | SC-IPC-B628H-Z, firmware v6.5.82-230615 |

**ANPR data generation:**
- Plates follow US state prefix format (CA-, NV-, TX-, etc.)
- Confidence distribution: `random.gauss(0.88, 0.07)`, clamped to [0.60, 0.99]
- Speed model: `random.gauss(50, 15)` km/h with zone-based limits
- Vehicle class probabilities weighted realistically

**Endpoints:**
- `/onvif/device_service` — SOAP 1.2 (POST)
- `/onvif/media_service` — SOAP 1.2 (POST)
- `/onvif/ptz_service` — SOAP 1.2 (POST)
- `/onvif/event_service` — SOAP 1.2 (POST)
- `/ws-discovery` — WS-Discovery probe response
- `/snap.jpg` — Simulated JPEG snapshot (1×1 pixel)
- `/api/telemetry`, `/api/stats`, `/api/cameras`, `/api/anpr/detections`, `/api/anpr/statistics`

---

### 2.2 Smart Parking System — MQTT/CoAP/SenML/LWM2M

**Standards:** MQTT v3.1.1 (OASIS), CoAP (RFC 7252), SenML (RFC 8428), LWM2M (OMA-TS), Link-Format (RFC 6690)

**Implementation:** `smart-city-services/parking-system/app.py` (~500 lines)

| Feature | Detail |
|---------|--------|
| Sensors | 450 sensors across 3 parking lots (100 + 200 + 150 capacity) |
| Detection method | Magnetometer + ultrasonic dual-sensor fusion |
| MQTT topics | `smartcity/parking/{lot}/sensor/{id}/status`, `telemetry`, `health` |
| CoAP discovery | `/.well-known/core` (RFC 6690 Link-Format) |
| SenML payloads | RFC 8428 compliant with base name, base time, units (T for tesla, m for meters) |
| LWM2M objects | Object 3302 (Presence), Object 3323 (Parking Spot) |
| Gateway | GW-PARK-001, LoRaWAN EU868 SF7BW125 uplink |
| Battery model | Lithium thionyl chloride, 2% daily drain, voltage curve 3.0–3.6V |
| Fault injection | Random sensor faults (stuck, drift, intermittent) at configurable rates |

**Sensor state machine:**
```
vacant → occupied (vehicle arrival, Poisson λ based on time-of-day)
occupied → vacant (dwell time ~ Exponential(μ=120 min))
any → fault (random, 0.1% per cycle)
```

**SenML output example (RFC 8428):**
```json
{
  "e": [
    {"n": "magnetometer", "u": "T", "v": 0.000045},
    {"n": "ultrasonic_cm", "u": "m", "v": 0.15},
    {"n": "occupied", "vb": true}
  ],
  "bn": "urn:dev:mac:LOT_A-SENS-001:",
  "bt": 1707840000
}
```

---

### 2.3 Healthcare API — HL7 FHIR R4

**Standards:** HL7 FHIR R4 (v4.0.1), LOINC coding, RxNorm, IEEE 11073 Medical Device Communication

**Implementation:** `smart-city-services/healthcare-api/app.py` (~600 lines)

| Feature | Detail |
|---------|--------|
| FHIR version | 4.0.1 |
| Resources | Patient, Observation, MedicationRequest, Device, CapabilityStatement |
| Patients | 5 demo patients with realistic demographics |
| Devices | 9 IEEE 11073 medical devices (pulse oximeter, BP monitor, thermometer, ECG, glucose meter, ventilator, infusion pump, weight scale, spirometer) |
| Observations | LOINC-coded vital signs (SpO2: 59408-5, HR: 8867-4, BP: 85354-9, Temp: 8310-5) |
| Medications | RxNorm-coded (Metformin: 860975, Lisinopril: 314076, Aspirin: 1191) |
| Alarms | IEEE 11073 alarm types (low_spo2, high_heart_rate, critical_bp, high_glucose, etc.) |
| Vital signs model | Physiologically correlated — SpO2 inversely affects HR, temperature rises gradually |

**Device emulation (IEEE 11073):**
- **Pulse Oximeter (11073-10404):** SpO2 range 88–100%, HR 55–110 bpm
- **Blood Pressure (11073-10407):** Systolic 100–180, diastolic 60–110
- **Thermometer (11073-10408):** 36.0–39.5°C with circadian rhythm
- **ECG (11073-10406):** HR 50–120, rhythm classification (normal_sinus, sinus_tachycardia, atrial_fibrillation)
- **Glucose (11073-10417):** 70–400 mg/dL with meal-related spikes
- **Ventilator (11073-10101):** Tidal volume 300–700 mL, PEEP 3–15 cmH2O, FiO2 21–100%

**Alarm generation:** Threshold-based with configurable trigger rates, provides `alarm_type`, `severity`, and FHIR `DetectedIssue` resource linking.

---

### 2.4 Environmental Sensor — Modbus TCP + OPC UA

**Standards:** Modbus TCP (IEC 61131), OPC UA (IEC 62541), EPA AQI Standard

**Implementation:** `smart-city-services/environmental-sensor/app.py` (~350 lines)

| Feature | Detail |
|---------|--------|
| Stations | 5 monitoring stations across city zones (downtown, industrial, residential, highway, waterfront) |
| Modbus registers | 16 holding registers per station (function code 0x03) |
| OPC UA | Information model with namespace `urn:smartcity:env:monitor`, browse/read operations |
| Air quality | PM2.5, PM10 (EN 12341), CO, NO2, O3, SO2 (EN 14211/14212/14625) |
| Noise | dBA measurement (IEC 61672-1 Class 1) |
| Weather | Temperature, humidity, pressure, wind speed/direction, UV index, rainfall |
| AQI calculation | EPA standard breakpoint interpolation for PM2.5 |
| Diurnal pattern | Rush-hour pollution peaks (7–9 AM, 5–7 PM), nighttime baseline reduction |

**Modbus register map:**
| Register | Measurement | Unit | Scale |
|----------|------------|------|-------|
| 0 | PM2.5 | µg/m³ | ×10 |
| 1 | PM10 | µg/m³ | ×10 |
| 2 | CO | ppm | ×100 |
| 3 | NO2 | ppb | ×10 |
| 4 | O3 | ppb | ×10 |
| 5 | SO2 | ppb | ×10 |
| 6 | Noise | dBA | ×10 |
| 7 | Temperature | °C | ×100 |
| 8 | Humidity | % | ×100 |
| 9 | Pressure | hPa | ×10 |
| 10 | Wind Speed | m/s | ×100 |
| 11 | Wind Direction | ° | ×1 |
| 12 | UV Index | — | ×10 |
| 13 | Rainfall Rate | mm/h | ×100 |
| 14 | AQI Index | — | ×1 |
| 15 | Station Status | — | ×1 |

**Zone-based pollution baselines:** Each zone has unique pollutant profiles — industrial zones show elevated PM and NO2, residential zones are cleaner, highway zones have high CO/NO2 from traffic.

---

### 2.5 Smart Street Lighting — DALI-2 + TALQ v2.4

**Standards:** DALI-2 (IEC 62386), TALQ Smart City Protocol v2.4

**Implementation:** `smart-city-services/street-lighting/app.py` (~380 lines)

| Feature | Detail |
|---------|--------|
| Luminaires | 120 LED street lights across 6 zones |
| DALI-2 commands | Forward frames: OFF, RECALL_MAX, QUERY_ACTUAL_LEVEL, QUERY_STATUS, QUERY_LAMP_FAILURE |
| TALQ API | Gateway info, OutdoorLightPoint resource with pagination |
| Dimming profiles | Zone-specific astronomical clock + motion-adaptive boost |
| Luminaire models | SL-LED-150W (21 klm), SL-LED-100W (14 klm), SL-LED-50W (7 klm, 3000K) |
| Monitoring | Per-luminaire power draw, LED/driver temperature, tilt sensor, operating hours |
| Energy metering | Accumulated kWh per luminaire with non-linear dimming power curve |
| Fault types | Lamp failure, driver fault, communication loss — with auto-recovery |
| Motion detection | PIR sensor simulation for pedestrian, park, parking-lot zones |

**Dimming zones:**
| Zone | Evening | Late Night | Deep Night | Dawn |
|------|---------|-----------|------------|------|
| Main Road | 100% | 70% | 50% | 80% |
| Residential | 80% | 50% | 30% | 60% |
| Park | 70% | 40% | 20% | 50% |
| Highway | 100% | 100% | 80% | 100% |
| Pedestrian | 90% | 60% | 30% | 70% |
| Parking Lot | 100% | 60% | 40% | 80% |

---

## 3. Architecture & Deployment

### 3.1 Kubernetes Deployment Pattern

All emulators follow the same deployment pattern:
1. Python Flask application mounted via `ConfigMap` (no Docker build needed)
2. Uses pre-built `smart-city-ids/smart-city-service:latest` base image
3. Each service runs as a K8s `Deployment` with a `ClusterIP Service`
4. IDS API proxies telemetry via `/api/iot/telemetry` endpoint using `httpx` async client

```
┌─────────────────────────────────────────────────────────┐
│                    K3s Cluster                          │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐        │
│  │ Traffic     │  │ Parking    │  │ Healthcare │        │
│  │ Camera ×3  │  │ System ×3  │  │ API ×3     │        │
│  │ ONVIF      │  │ MQTT/CoAP  │  │ FHIR R4    │        │
│  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘        │
│        │               │               │               │
│  ┌─────┴──────┐  ┌─────┴──────┐  ┌─────┴──────┐        │
│  │ Env Sensor │  │ Street     │  │ MQTT       │        │
│  │ ×2         │  │ Lighting×2 │  │ Broker ×1  │        │
│  │ Modbus/OPC │  │ DALI+TALQ  │  │            │        │
│  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘        │
│        │               │               │               │
│        └───────────┬────┘───────────────┘               │
│              ┌─────┴──────┐                             │
│              │  IDS API   │ ← /api/iot/telemetry        │
│              │  (FastAPI) │ ← Security Analyst Dashboard│
│              └────────────┘                             │
└─────────────────────────────────────────────────────────┘
```

### 3.2 Fleet Composition

| Service | Replicas | Protocol | Virtual Devices |
|---------|----------|----------|-----------------|
| Traffic Camera | 3 | ONVIF Profile S | 1 camera per pod |
| Parking System | 3 | MQTT/CoAP/SenML | 450 sensors per pod |
| Healthcare API | 3 | HL7 FHIR R4 | 9 IEEE 11073 devices per pod |
| Environmental Sensor | 2 | Modbus TCP + OPC UA | 5 stations × 16 registers per pod |
| Street Lighting | 2 | DALI-2 + TALQ | 120 luminaires per pod |
| MQTT Simulators | 10 | MQTT v3.1.1 | Variable rate generators |
| MQTT High-Freq | 4 | MQTT | Poisson λ=2.0 events/sec |
| MQTT Medium-Freq | 5 | MQTT | λ=0.5 events/sec |
| MQTT Burst | 1 | MQTT | Periodic burst mode |
| MQTT Broker | 1 | MQTT v3.1.1 | Message bus |
| **Total** | **34 pods** | **7 protocols** | **~600+ virtual devices** |

### 3.3 Resource Usage

On the single-node K3s cluster (8 vCPU, 8 GB RAM):
- CPU: ~17% utilization
- Memory: ~76% utilization
- All 34 pods running without OOM kills

---

## 4. Security Analyst Dashboard — IoT Tab

The dashboard IoT Devices tab was enhanced to provide:

1. **Protocol Emulator Status Cards** — 5 service cards showing online/offline status, protocol name, and key telemetry for each emulator
2. **ANPR & Camera Telemetry** — Live plate detections, speed readings, vehicle classification, camera feed status
3. **Medical Device Table** — 9 IEEE 11073 devices with patient assignments, vital sign readings, battery levels, and alarm status
4. **Air Quality Index** — City-wide AQI with per-station breakdown, EPA color-coded categories
5. **Lighting Zone Dashboard** — DALI-2 dimming levels per zone, power consumption, fault counts
6. **Parking Lot Occupancy** — Per-lot occupancy bars with sensor fusion data and fault tracking
7. **Fleet Table** — All 34 IoT pods with status, type, IP address

The dashboard calls `/api/iot/telemetry` which aggregates live data from all 5 emulators in parallel using `httpx.AsyncClient`.

---

## 5. IDS Relevance

These emulators generate realistic attack surfaces for the IDS:

| Emulator | Attack Vector | IDS Detection |
|----------|--------------|---------------|
| ONVIF Camera | Unauthorized PTZ control, stream hijacking, firmware exploitation | Falco detects unexpected SOAP requests, process spawns |
| MQTT Parking | Topic injection, broker DoS, sensor spoofing | Network anomaly detection on MQTT patterns |
| FHIR Healthcare | Patient data exfiltration, unauthorized observations, device tampering | API abuse detection, unusual data access patterns |
| Modbus Sensor | Register write attacks, coil manipulation, holding register overflows | Industrial protocol anomaly detection |
| DALI Lighting | Unauthorized dimming commands, gear reconfiguration, broadcast attacks | Command injection detection on DALI bus |

---

## 6. Standards Referenced

| Standard | Usage |
|----------|-------|
| ONVIF Profile S | Traffic camera SOAP web services |
| SOAP 1.2 (W3C) | Camera device/media/PTZ service messaging |
| WS-Discovery | Camera network discovery |
| MQTT v3.1.1 (OASIS) | Parking sensor publish/subscribe |
| CoAP (RFC 7252) | Parking sensor constrained protocol |
| SenML (RFC 8428) | Parking sensor data format |
| Link-Format (RFC 6690) | CoAP resource discovery |
| LWM2M (OMA-TS) | Parking sensor device management |
| HL7 FHIR R4 (v4.0.1) | Healthcare resource modeling |
| LOINC | Clinical observation coding |
| RxNorm | Medication coding |
| IEEE 11073 | Medical device communication (10404, 10406, 10407, 10408, 10417, 10101) |
| Modbus TCP (IEC 61131) | Environmental sensor registers |
| OPC UA (IEC 62541) | Environmental sensor information model |
| EPA AQI Standard | Air quality index calculation |
| EN 12341/14211/14212/14625 | Air quality measurement methods |
| IEC 61672-1 | Noise measurement (Class 1 sound level meter) |
| DALI-2 (IEC 62386) | Street lighting digital control |
| TALQ v2.4 | Smart city outdoor lighting management |

---

## 7. Files Modified / Created

### New files:
- `smart-city-services/environmental-sensor/app.py` — Modbus TCP + OPC UA emulator
- `smart-city-services/street-lighting/app.py` — DALI-2 + TALQ emulator
- `docs/IOT_EMULATION_REPORT.md` — This document

### Modified files:
- `services/ids-api/src/main.py` — Added `/api/iot/telemetry` proxy endpoint, updated `_IOT_POD_PREFIXES` for all 5 device types
- `services/ids-api/static/index.html` — Enhanced IoT Devices tab with protocol-specific telemetry cards, AQI dashboard, lighting zones, medical device table

### Previously created (prior session):
- `smart-city-services/traffic-camera/app.py` — ONVIF camera emulator
- `smart-city-services/parking-system/app.py` — MQTT/CoAP/SenML emulator
- `smart-city-services/healthcare-api/app.py` — HL7 FHIR R4 emulator
