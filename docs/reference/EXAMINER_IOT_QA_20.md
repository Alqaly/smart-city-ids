# IoT Specialist Examiner Q&A (20 Questions)

Based on live cluster verification (`kubectl`) plus current code/manifests in this repo.

## Q1. How many IoT device types are emulated, and what real-world smart city devices do they represent?
Q1: The live system represents **six IoT-related workload families** in `smart-city`: `traffic-camera`, `healthcare-api`, `parking-system`, `env-sensor`, `street-lighting`, and `mqtt-broker` (broker is support infrastructure, not a logical end device). The authoritative fleet view is `GET /api/iot/devices`, which reports hybrid inventory fields such as `total`, `logical_total`, `pod_backed_total`, and `counting_mode`.  
**Code ref:** `services/ids-api/src/api/iot.py`, `services/ids-api/src/api/_state.py`  
**Verify:** `kubectl get deploy -n smart-city` and `curl -s http://localhost:30800/api/iot/devices | jq '{total,logical_total,pod_backed_total,counting_mode}'`

## Q2. What Kubernetes resources represent individual IoT devices? Deployments, StatefulSets, DaemonSets? Why this choice?
Q2: IoT device families are modeled as **Kubernetes Deployments** (not StatefulSets/DaemonSets). A single pod often emulates many logical devices internally (e.g., many parking sensors, many luminaires, multiple environmental stations), so Deployment is simpler and scales horizontally.  
**Code ref:** `k8s-manifests/smart-city-services.yaml:4`, `k8s-manifests/smart-city-services.yaml:115`, `k8s-manifests/smart-city-services.yaml:225`, `k8s-manifests/mqtt-broker.yaml:1`, `smart-city-services/parking-system/app.py:296`, `smart-city-services/environmental-sensor/app.py:29`, `smart-city-services/street-lighting/app.py:70`  
**Verify:** `kubectl get deploy,statefulset,daemonset -n smart-city`

## Q3. How many replica pods per IoT device type, and why not 1:1 pod-to-device?
Q3: Replica counts and fleet counts are different. Pod-backed emulator rows come from Kubernetes, while external/logical devices come from the registry + heartbeat path. Use `/api/iot/devices` to show `total`, `logical_total`, `pod_backed_total`, and `counting_mode`. It is not 1:1 pod-to-device because each pod can emulate many logical devices internally.  
**Code ref:** `k8s-manifests/smart-city-services.yaml:11`, `k8s-manifests/smart-city-services.yaml:122`, `k8s-manifests/smart-city-services.yaml:232`, `services/ids-api/src/api/_state.py:1227`, `smart-city-services/parking-system/app.py:300`, `smart-city-services/environmental-sensor/app.py:29`, `smart-city-services/street-lighting/app.py:72`  
**Verify:** `kubectl get deploy -n smart-city traffic-camera healthcare-api parking-system env-sensor street-lighting mqtt-broker`

## Q4. Show the exact labels/selectors used to discover "13 IoT devices" on dashboard. Run `kubectl get pods -l=...` to verify.
Q4: The dashboard now distinguishes **pod-backed activity** from **logical registry inventory**. The legacy fixed “13 devices” explanation is no longer the correct primary answer. Pod-backed activity still comes from live workload discovery, but examiner-facing fleet claims should use `/api/iot/devices` because that view merges logical devices and pod-backed emulators.  
**Code ref:** `services/ids-api/src/api/iot.py`, `services/ids-api/src/api/_state.py`  
**Verify:** `kubectl get pods -n smart-city -l 'app in (traffic-camera,healthcare-api,parking-system,env-sensor,street-lighting,mqtt-broker)' -o name` and `curl -s http://localhost:30800/api/iot/devices | jq '.counting_mode'`

## Q5. Are IoT services using NodePort, ClusterIP, LoadBalancer? Why? Impact on Suricata detection?
Q5: IoT services are mostly **ClusterIP** (internal only); `ids-api` and `iot-stream-bridge` are NodePort. ClusterIP keeps attack traffic in-cluster (good for Suricata on `cni0`), while NodePort is only for operator UI/stream access.  
**Code ref:** `k8s-manifests/smart-city-services.yaml:74`, `k8s-manifests/smart-city-services.yaml:184`, `k8s-manifests/smart-city-services.yaml:294`, `k8s-manifests/mqtt-broker.yaml:44`, `k8s-manifests/iot-stream-bridge.yaml:160`, `k8s-manifests/suricata.yaml:126`, `k8s-manifests/suricata.yaml:139`  
**Verify:** `kubectl get svc -n smart-city`

## Q6. What HTTP endpoints do your IoT services expose, and how do they mimic real device APIs?
Q6: The IoT services expose realistic protocol-mimicking HTTP endpoints:
- Traffic camera: ONVIF SOAP, MJPEG, ANPR, WS-Discovery, telemetry
- Healthcare: FHIR R4 (`/Patient`, `/Observation`, `/MedicationRequest`, `/Device`, `/metadata`)
- Parking: CoAP-style discovery, MQTT topic browsing, SenML, LwM2M, lot/sensor APIs
- Env sensor: Modbus read + OPC UA browse/read + REST telemetry
- Street lighting: DALI command/gear + TALQ gateway/light points + telemetry  
**Code ref:** `services/ids-api/src/api/iot.py:72`, `smart-city-services/traffic-camera/app.py:300`, `smart-city-services/traffic-camera/app.py:560`, `smart-city-services/traffic-camera/app.py:594`, `smart-city-services/traffic-camera/app.py:669`, `smart-city-services/healthcare-api/app.py:449`, `smart-city-services/healthcare-api/app.py:506`, `smart-city-services/healthcare-api/app.py:539`, `smart-city-services/parking-system/app.py:333`, `smart-city-services/parking-system/app.py:356`, `smart-city-services/parking-system/app.py:397`, `smart-city-services/parking-system/app.py:433`, `smart-city-services/environmental-sensor/app.py:237`, `smart-city-services/environmental-sensor/app.py:282`, `smart-city-services/environmental-sensor/app.py:332`, `smart-city-services/street-lighting/app.py:203`, `smart-city-services/street-lighting/app.py:275`, `smart-city-services/street-lighting/app.py:302`  
**Verify:** `curl -s http://localhost:30800/api/iot/telemetry | jq '.services | keys'`

## Q7. Do IoT pods generate periodic "heartbeat" traffic? Show the code/config.
Q7: The **HTTP service emulators** mainly generate internal state updates (background ticker threads), not outbound heartbeat traffic. Actual periodic heartbeat MQTT traffic comes from `iot-simulator/mqtt_device.py` (every 10s) and `mqtt_device_enhanced.py` (Poisson-based loop).  
**Code ref:** `smart-city-services/traffic-camera/app.py:171`, `smart-city-services/environmental-sensor/app.py:226`, `smart-city-services/street-lighting/app.py:192`, `smart-city-services/parking-system/app.py:319`, `iot-simulator/mqtt_device.py:93`, `iot-simulator/mqtt_device.py:98`, `iot-simulator/mqtt_device.py:101`, `iot-simulator/mqtt_device_enhanced.py:568`, `iot-simulator/mqtt_device_enhanced.py:587`  
**Verify:** `nl -ba iot-simulator/mqtt_device.py | sed -n '90,110p'`

## Q8. How do IoT services simulate normal vs. anomalous traffic patterns? Examples?
Q8: Normal vs anomalous behavior is simulated in code:
- Normal: diurnal/rush-hour patterns (traffic camera motion, env pollution cycles)
- Anomalous: random fault injection, disconnects, latency spikes, packet loss, anomaly-rate in MQTT simulator  
**Code ref:** `smart-city-services/traffic-camera/app.py:108`, `smart-city-services/traffic-camera/app.py:121`, `smart-city-services/environmental-sensor/app.py:119`, `smart-city-services/environmental-sensor/app.py:160`, `smart-city-services/street-lighting/app.py:113`, `smart-city-services/street-lighting/app.py:172`, `iot-simulator/mqtt_device_enhanced.py:7`, `iot-simulator/mqtt_device_enhanced.py:68`, `iot-simulator/mqtt_device_enhanced.py:75`  
**Verify:** `curl -s http://localhost:30800/api/iot/telemetry | jq` (compare snapshots over time)

## Q9. What MQTT/UDP traffic do IoT devices generate for Suricata to detect?
Q9: MQTT traffic is explicitly modeled:
- Broker on `1883`/`9001`
- Parking service exposes MQTT topic tree and sample payloads (`qos`, `retain`)
- Enhanced simulator publishes `sensors/{namespace}/{class}/{pod}` with `qos=1`
UDP traffic is mostly DNS (Suricata watches DNS tunneling); CoAP is emulated via HTTP endpoints, not actual UDP CoAP server in the current running services.  
**Code ref:** `k8s-manifests/mqtt-broker.yaml:21`, `k8s-manifests/mqtt-broker.yaml:54`, `smart-city-services/parking-system/app.py:234`, `smart-city-services/parking-system/app.py:240`, `smart-city-services/parking-system/app.py:241`, `smart-city-services/parking-system/app.py:356`, `iot-simulator/mqtt_device_enhanced.py:531`, `iot-simulator/mqtt_device_enhanced.py:536`, `k8s-manifests/suricata.yaml:93`, `k8s-manifests/suricata.yaml:101`  
**Verify:** `kubectl get svc -n smart-city mqtt-broker` and `kubectl exec -n smart-city deploy/parking-system -- curl -s localhost:5002/api/mqtt/topics | head`

## Q10. How do you simulate IoT firmware vulnerabilities (SQLi, command injection) in the services?
Q10: SQLi/command injection are primarily **network detection simulations** (Suricata signatures on malicious HTTP payloads), not real SQL execution in the service code. The services themselves simulate insecure firmware/API design (no auth, debug endpoints, unsafe updates).  
**Code ref:** `k8s-manifests/suricata.yaml:59`, `k8s-manifests/suricata.yaml:65`, `scripts/run-live-attacks.sh:154`, `scripts/run-live-attacks.sh:166`, `smart-city-services/traffic-camera/app.py:700`, `smart-city-services/parking-system/app.py:618`, `smart-city-services/healthcare-api/app.py:704`  
**Verify:** `bash scripts/run-live-attacks.sh --duration 5 --mode sqli --show-alerts 2`

## Q11. Which IoT services are intentionally vulnerable to trigger Suricata rules? Code excerpts.
Q11: Intentionally vulnerable IoT services (explicitly documented in code) are:
- `traffic-camera` (no ONVIF auth/TLS, debug credential leak)
- `healthcare-api` (no OAuth2/TLS, PHI exposure, bulk admin export)
- `parking-system` (no auth/TLS, insecure payment logging, unauth OTA update)  
`env-sensor` and `street-lighting` focus on protocol emulation realism more than explicit vulnerability banners.  
**Code ref:** `smart-city-services/traffic-camera/app.py:13`, `smart-city-services/traffic-camera/app.py:700`, `smart-city-services/healthcare-api/app.py:20`, `smart-city-services/healthcare-api/app.py:719`, `smart-city-services/parking-system/app.py:16`, `smart-city-services/parking-system/app.py:585`, `smart-city-services/parking-system/app.py:618`  
**Verify:** `kubectl exec -n smart-city deploy/traffic-camera -- curl -s localhost:5000/api/debug/config | jq`

## Q12. How do Falco rules trigger on real IoT pod behaviors (shell spawn, file read)? Live demo command?
Q12: Falco triggers on **real runtime activity** because the attack runner uses `kubectl exec` into live service pods to run shell commands and read sensitive files (`/etc/passwd`, `/etc/shadow`). That generates syscall telemetry observed by Falco eBPF rules.  
**Code ref:** `scripts/run-live-attacks.sh:223`, `scripts/run-live-attacks.sh:235`, `scripts/run-live-attacks.sh:240`, `k8s-manifests/falco-values.yaml:84`, `k8s-manifests/falco-values.yaml:98`, `k8s-manifests/falco-values.yaml:124`  
**Verify:** `kubectl exec -n smart-city deploy/healthcare-api -- /bin/sh -lc 'cat /etc/passwd >/dev/null; cat /etc/shadow >/dev/null || true'` then `kubectl logs -n falco-system daemonset/falco --since=2m`

## Q13. What lateral movement scenarios are possible between IoT pods? (Service discovery, DNS queries.)
Q13: Lateral movement between IoT pods is currently possible because services are on ClusterIP and **no NetworkPolicies are applied** in `smart-city` right now. Pods can use service DNS (e.g., `traffic-camera-service`, `healthcare-api-service`, `parking-system-service`) for east-west traffic.  
**Code ref:** `scripts/run-live-attacks.sh:135`, `services/ids-api/src/api/iot.py:76`, `services/ids-api/src/api/iot.py:88`, `services/ids-api/src/api/iot.py:99`, `k8s-manifests/network-policies.yaml:1`  
**Verify:** `kubectl get netpol -n smart-city` (expected none); `kubectl exec -n smart-city deploy/parking-system -- getent hosts healthcare-api-service`

## Q14. How does the system detect IoT-to-IoT communication abuse (DDoS, C2)?
Q14: IoT-to-IoT abuse detection is handled by both Suricata and Falco:
- Suricata: HTTP flood, MQTT cleartext, DNS tunneling, exfil, mining ports
- Falco: unexpected outbound connections from IoT containers (custom rule)  
**Code ref:** `k8s-manifests/suricata.yaml:86`, `k8s-manifests/suricata.yaml:93`, `k8s-manifests/suricata.yaml:101`, `k8s-manifests/suricata.yaml:96`, `k8s-manifests/falco-values.yaml:71`  
**Verify:** `bash scripts/run-live-attacks.sh --duration 5 --mode ddos --show-alerts 3`

## Q15. How do you scale IoT attack surface for stress testing? HPA config?
Q15: Attack surface scaling is implemented with HPAs on the three HTTP IoT services (`traffic-camera`, `healthcare-api`, `parking-system`) and optional larger MQTT simulator deployments (`high/medium/burst`) in `iot-simulator/k8s-enhanced.yaml`.  
**Code ref:** `k8s-manifests/smart-city-services.yaml:90`, `k8s-manifests/smart-city-services.yaml:199`, `k8s-manifests/smart-city-services.yaml:309`, `iot-simulator/k8s-enhanced.yaml:45`, `iot-simulator/k8s-enhanced.yaml:53`, `iot-simulator/k8s-enhanced.yaml:128`, `iot-simulator/k8s-enhanced.yaml:136`, `iot-simulator/k8s-enhanced.yaml:211`, `iot-simulator/k8s-enhanced.yaml:219`  
**Verify:** `kubectl get hpa -n smart-city` and `rg -n 'replicas:' iot-simulator/k8s-enhanced.yaml`

## Q16. What resource limits/requests on IoT deployments mimic real edge device constraints?
Q16: Resource requests/limits mimic constrained edge workloads:
- HTTP IoT service pods (traffic/healthcare/parking): typically `100m/128Mi` request, `500m/256Mi` limit
- Env sensor + street lighting live deployments are smaller: `50m/64Mi` request, `300m/192Mi` limit
- Enhanced MQTT simulator pods: `50m/64Mi` request, `200m/128Mi` limit  
**Code ref:** `k8s-manifests/smart-city-services.yaml:44`, `k8s-manifests/smart-city-services.yaml:154`, `k8s-manifests/smart-city-services.yaml:264`, `iot-simulator/k8s-enhanced.yaml:74`, `iot-simulator/k8s-enhanced.yaml:157`, `iot-simulator/k8s-enhanced.yaml:240`  
**Verify:** `kubectl get deploy -n smart-city env-sensor street-lighting -o yaml | grep -A8 resources:`

## Q17. Do IoT pods have realistic network policies? Show `kubectl get netpol`.
Q17: **No NetworkPolicies are currently applied** in `smart-city` (live). There is a `k8s-manifests/network-policies.yaml` file defining IDS API, Postgres, IoT egress, and service ingress policies, but it is not active in the cluster right now.  
**Code ref:** `k8s-manifests/network-policies.yaml:4`, `k8s-manifests/network-policies.yaml:32`, `k8s-manifests/network-policies.yaml:56`, `k8s-manifests/network-policies.yaml:94`  
**Verify:** `kubectl get netpol -n smart-city` (expected `No resources found`)

## Q18. How do you inject realistic IoT noise traffic (sensor readings, status updates)? Scripts?
Q18: Realistic IoT “noise” traffic is injected mainly by the enhanced MQTT simulator:
- Poisson inter-arrival timing
- rush-hour multipliers
- anomaly injection
- packet loss / disconnect / latency spike injection
- topic namespaces (`traffic`, `environment`, `energy`, `lighting`)  
**Code ref:** `iot-simulator/mqtt_device_enhanced.py:7`, `iot-simulator/mqtt_device_enhanced.py:37`, `iot-simulator/mqtt_device_enhanced.py:40`, `iot-simulator/mqtt_device_enhanced.py:48`, `iot-simulator/mqtt_device_enhanced.py:68`, `iot-simulator/mqtt_device_enhanced.py:75`, `iot-simulator/mqtt_device_enhanced.py:568`, `iot-simulator/mqtt_device_enhanced.py:590`, `iot-simulator/k8s-enhanced.yaml:86`, `iot-simulator/k8s-enhanced.yaml:88`  
**Verify:** If deployed, `curl http://<iot-simulator-pod>:5000/validate`; otherwise review `iot-simulator/k8s-enhanced.yaml`

## Q19. What existing script tests full IoT attack lifecycle? Show output + dashboard impact.
Q19: The existing script that exercises a full live IoT attack lifecycle is `scripts/run-live-attacks.sh` (network attacks -> runtime behaviors -> IDS API verification). In a live run, it produced Suricata sample alerts (`SMARTCITY SQLi DROP TABLE`, `SMARTCITY HTTP flood`) even when the metrics delta counter path was `+0` (known script caveat).  
**Code ref:** `scripts/run-live-attacks.sh:1`, `scripts/run-live-attacks.sh:117`, `scripts/run-live-attacks.sh:223`, `scripts/run-live-attacks.sh:272`, `scripts/run-live-attacks.sh:303`  
**Verify:** `bash scripts/run-live-attacks.sh --duration 5 --show-alerts 2`

## Q20. If examiner asks to "add a new camera sensor", what exact `kubectl` commands would you run?
Q20: Fastest live-demo answer (no new files): **scale the existing `traffic-camera` Deployment** so a new camera pod is added behind the current Service selector.
```bash
kubectl scale deploy/traffic-camera -n smart-city --replicas=3
kubectl get pods -n smart-city -l app=traffic-camera
kubectl get svc -n smart-city traffic-camera-service -o yaml | grep -n 'app: traffic-camera'
```
This adds another emulated camera pod and keeps service routing unchanged.  
**Code ref:** `k8s-manifests/smart-city-services.yaml:6`, `k8s-manifests/smart-city-services.yaml:11`, `k8s-manifests/smart-city-services.yaml:68`, `k8s-manifests/smart-city-services.yaml:92`  
**Verify:** Commands above (expect traffic-camera pod count to increase from 2 to 3)

## Notes / Caveats (important for examiner honesty)

- Fleet claims should use `/api/iot/devices`, not a fixed “13 devices” explanation. The dashboard exposes both pod-backed activity and logical registry inventory; a registered logical device is not proof of live hardware unless recent heartbeat/telemetry exists.
- `env-sensor` and `street-lighting` live Deployments/Services are verified in cluster (`kubectl get deploy/svc -o yaml`) but their deployment manifests are not present under `k8s-manifests/` in this working copy.
- `k8s-manifests/network-policies.yaml` exists, but no NetworkPolicies are currently applied in the live `smart-city` namespace.
