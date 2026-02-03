# IoT Simulation Realism - Technical Specification

**Version:** 2.1  
**Status:** Capstone II Integration  
**Last Updated:** 2026-02-02

---

## Academic Disclaimer

> **"All traffic and attacks are emulated but statistically grounded, reproducible, and mapped to real-world threat behaviors. The objective is not to mirror a specific city, but to evaluate system behavior under realistic operational stress."**

This document provides IEEE-defensible justification for the IoT simulation model used in this project.

---

## Data Classification

This project explicitly distinguishes three types of data:

| Category | Description | Source |
|----------|-------------|--------|
| **A. Synthetic IoT Traffic** | Statistically modeled sensor data | Poisson process generator |
| **B. Emulated Attacks** | Mapped to real threat techniques | Attack simulator → Falco/Suricata |
| **C. Measured System Behavior** | Actual latency, throughput, actions | Prometheus metrics |

**We do not claim "real city data."**  
**We claim realistic, research-grade emulation.**

---

## Overview

This document describes the enhanced IoT device simulation system implementing IEEE-defensible traffic patterns for the Smart City IDS project.

---

## Statistical Model

### Assumption

> Sensor events are modeled as a **non-homogeneous Poisson process**.

### Justification

This model is widely used in network traffic and IoT literature to represent independent event-driven systems with time-varying intensity:

1. **Independence**: Each sensor reports independently
2. **Stationarity within intervals**: Rate is constant within short time windows
3. **No simultaneous events**: Continuous-time approximation is valid
4. **Memoryless property**: Inter-arrival times are exponentially distributed

**Why Poisson?**  
Because independent sensor reporting with varying intensity converges to a Poisson process. Bursts are injected to violate the baseline and test system robustness.

### Mathematical Model

### 1. Poisson Arrival Process

Messages are generated following a **Poisson arrival process** with time-varying rate λ(t):

```
λ(t) = λ_base × multiplier_rush(hour) × multiplier_weekday(day)
```

**Mathematical Properties:**
- Inter-arrival times follow an exponential distribution: `T ~ Exp(λ)`
- `interval = random.expovariate(λ/60)` (converted from msg/min to msg/sec)
- Clamped to [0.1s, 300s] for stability
- **Expected variance**: High variability is intentional and realistic

---

## Device Classes with Justification

| Class | Base Rate (λ) | Real-World Analog | Justification |
|-------|---------------|-------------------|---------------|
| `high` | 60 msg/min (1/sec) | Traffic cameras, flow meters | Typical telemetry sensors sending continuous updates |
| `medium` | 6 msg/min (1/10sec) | Environmental monitors, parking sensors | Standard IoT polling intervals for non-critical data |
| `burst` | 0.5 msg/min baseline, 100 msg/sec during events | Motion detectors, alarms | Event-driven sensors with sparse baseline and burst activity |

Configure via environment variable:
```bash
DEVICE_CLASS=high|medium|burst
```

---

## Rush Hour Multipliers (Time-Varying λ)

### 3. Rush Hour Multipliers

Traffic patterns reflect real-world urban activity based on observed human mobility patterns:

| Hour | Multiplier | Description |
|------|------------|-------------|
| 00-06 | 1.0x | Night baseline |
| 07 | 3.0x | Morning ramp-up |
| **08** | **10.0x** | **Morning rush peak** |
| 09 | 5.0x | Post-rush |
| 10-15 | 1.0x | Midday baseline |
| 16 | 3.0x | Evening ramp-up |
| **17** | **10.0x** | **Evening rush peak** |
| 18 | 5.0x | Post-rush |
| 19-23 | 1.0x | Evening baseline |

**Justification**: Rush hour peaks (08:00, 17:00) match observed urban traffic patterns where sensor activity correlates with human commute times.

---

### 4. Weekday Patterns

| Day | Multiplier |
|-----|------------|
| Monday-Friday | 1.0x |
| Saturday | 0.3x |
| Sunday | 0.2x |

**Justification**: Weekend traffic reduction reflects observed patterns in urban mobility studies.

---

### 5. Failure Injection

Realistic failure scenarios for resilience testing:

| Failure Type | Default Probability | Duration |
|--------------|---------------------|----------|
| Disconnect | 1% per interval | 5-30 seconds |
| Latency Spike | 2% per message | 1-5 seconds |

**Environment Variables:**
```bash
FAILURE_DISCONNECT_PROB=0.01
FAILURE_DISCONNECT_DURATION=30
FAILURE_LATENCY_SPIKE_PROB=0.02
FAILURE_LATENCY_SPIKE_MAX=5.0
```

**Justification**: Real IoT networks experience transient failures. Failure injection tests system resilience without masking normal operation.

---

## Prometheus Metrics

The enhanced simulator exposes metrics at `/metrics`:

```prometheus
# Message counters
iot_messages_sent_total{device, namespace, class}
iot_messages_received_total{device, namespace, class}
iot_messages_failed_total{device, namespace, class}

# Failure counters
iot_device_disconnects_total{device}
iot_latency_spikes_total{device}

# Gauges
iot_device_active{device, namespace, class}  # 1=active, 0=disconnected
iot_current_message_rate{device, class}       # Current λ(t)
iot_burst_factor{device}                      # Current rush multiplier

# Histogram
iot_message_latency_seconds{device}           # Send latency distribution
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `POD_NAME` | `iot-device-0` | Unique device identifier |
| `MQTT_BROKER` | `mqtt-broker` | MQTT broker hostname |
| `MQTT_PORT` | `1883` | MQTT broker port |
| `DEVICE_CLASS` | `medium` | Device class (high/medium/burst) |
| `DEVICE_NAMESPACE` | `traffic` | Sensor namespace (traffic/energy/environment) |

### MQTT Topics

Messages are published to:
```
sensors/{namespace}/{class}/{device}
```

Example: `sensors/traffic/high/traffic-camera-1`

## Deployment

### Kubernetes Manifest

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: iot-simulator-traffic
  namespace: smart-city
spec:
  replicas: 10
  selector:
    matchLabels:
      app: iot-simulator
      class: high
  template:
    metadata:
      labels:
        app: iot-simulator
        class: high
        namespace: traffic
    spec:
      containers:
      - name: simulator
        image: iot-simulator:latest
        command: ["python", "mqtt_device_enhanced.py"]
        env:
        - name: POD_NAME
          valueFrom:
            fieldRef:
              fieldPath: metadata.name
        - name: DEVICE_CLASS
          value: "high"
        - name: DEVICE_NAMESPACE
          value: "traffic"
        - name: MQTT_BROKER
          value: "mqtt-broker.smart-city.svc.cluster.local"
        ports:
        - containerPort: 5000
          name: http
```

### Scaling for Load Testing

```bash
# Scale to 100 devices
kubectl scale deployment/iot-simulator-traffic -n smart-city --replicas=100

# Scale to 1000 devices (distributed across classes)
kubectl scale deployment/iot-simulator-traffic -n smart-city --replicas=400
kubectl scale deployment/iot-simulator-energy -n smart-city --replicas=300
kubectl scale deployment/iot-simulator-environment -n smart-city --replicas=300
```

## Observable Outcomes

### Falsifiability Tests

The following behaviors can be verified and falsified:

1. **Poisson Arrival Validation**
   - Message inter-arrival times follow exponential distribution
   - Visible in `iot_message_latency_seconds` histogram
   - **Test**: Chi-squared goodness-of-fit test on inter-arrival times

2. **Rush Hour Bursts**
   - 10x message rate increase at 08:00 and 17:00
   - Visible in `iot_current_message_rate` and `iot_burst_factor` metrics
   - **Test**: Compare metrics at 03:00 vs 08:00 → expect 10x difference

3. **Failure Injection**
   - Random disconnects visible in `iot_device_disconnects_total`
   - Latency spikes visible in histogram tail
   - Device status toggles in `iot_device_active`
   - **Test**: Over 1000 messages, expect ~10 disconnects (1%) and ~20 latency spikes (2%)

4. **Cause-Effect Correlation**
   - When IoT message rate increases, detection latency increases slightly
   - When attacks stop, alert rate decreases
   - **Test**: Overlay `iot_message_rate` with `llm_reasoning_latency_seconds` in Grafana

---

## HTTP Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Kubernetes health probe |
| `/status` | GET | Detailed device status |
| `/metrics` | GET | Prometheus metrics |
| `/config` | GET | Current configuration |

## Testing

### Unit Test (Message Rate)
```python
def test_poisson_rate_rush_hour():
    """Verify 10x burst at rush hour."""
    # Mock datetime to 08:00 Monday
    with mock_datetime(hour=8, weekday=0):
        rate = get_current_lambda()
        base = DEVICE_CLASS_RATES["medium"]
        assert rate == base * 10.0
```

### Integration Test (End-to-End)
```bash
# Deploy single device
kubectl apply -f iot-simulator-test.yaml

# Check metrics after 1 minute
curl http://<pod-ip>:5000/metrics | grep iot_messages_sent_total
# Expected: > 0 messages sent
```

## References

- IEEE IoT Journal: "Traffic Pattern Modeling in Smart Cities"
- Poisson Process Theory: https://en.wikipedia.org/wiki/Poisson_point_process
- MQTT Protocol: https://mqtt.org/mqtt-specification/
- Kingman, J.F.C. "Poisson Processes" (1993) - Theoretical foundation
- Harchol-Balter, M. "Performance Modeling and Design of Computer Systems" - Queuing theory

---

## Examiner FAQ

**Q: Why Poisson?**  
A: Because independent sensor reporting with varying intensity converges to a Poisson process. Bursts are injected to violate the baseline and test system robustness.

**Q: Is this real city data?**  
A: No. This is statistically modeled synthetic data designed to be reproducible and falsifiable. The goal is to evaluate system behavior, not replicate a specific city.

**Q: How do you know the data is realistic?**  
A: The model parameters (rates, multipliers, failure probabilities) are configurable and can be calibrated against real-world datasets if available. The structure (Poisson arrivals, diurnal patterns, failure injection) matches established IoT traffic models.
