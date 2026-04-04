# LLM-Driven Intrusion Detection System for Edge-Enabled Smart Cities
## Capstone II — Spring 2026 Presentation
### 15 minutes + 5 min Q&A

---

## Slide 1: Project Title

**LLM-Driven Intrusion Detection System for Edge-Enabled Smart Cities**

- Ali Suhail (60106420)
- Khaled Rahman (60104156)
- Abdullah Mahmoud (60300336)

Supervisor: Dr. Dana Haj Hussein
University of Doha for Science and Technology
Department of Computer Science — Spring 2026

---

## Slide 2: Problem Statement

- Smart cities deploy thousands of IoT devices (cameras, sensors, traffic controllers, smart meters)
- These devices generate **10,000+ security events per day** per district
- Human analysts need **5–15 minutes per alert** — they cannot keep up
- Traditional IDS tools detect threats but do not explain or prioritize them
- Industrial protocols (Modbus, MQTT, ONVIF) are often ignored by conventional IDS
- Delayed response means threats persist and spread across the network

**Gap:** No existing open-source IDS combines LLM-based analysis with automated Kubernetes response for smart city infrastructure.

---

## Slide 3: Objectives and Criteria

**Capstone II Objectives:**

1. Integrate **5 LLM providers** with automatic failover and circuit breakers
2. Implement **Human-in-the-Loop** governance (3 operating modes)
3. Add **PostgreSQL persistence** with full audit trail
4. Build **alert deduplication** to reduce LLM costs
5. Deploy **Prometheus metrics** with counter restoration
6. Create **transparent reasoning** so operators understand AI decisions
7. Conduct **formal LLM evaluation** scored against ground truth
8. Reproduce **real attacks** (DDoS, privilege escalation) and validate detection

**Success Criteria:**
- Alert processing < 2 seconds end-to-end
- System uptime > 99%
- All 5 LLM providers operational with < 1s failover
- 100% unit test pass rate

---

## Slide 4: Hardware & Software — Overview

**Hardware:**
- K3s Kubernetes cluster on Ubuntu 22.04 (local lab environment)
- 34 pods running in `smart-city` namespace
- Simulated IoT devices: cameras, traffic lights, environmental sensors, smart meters

**Software Stack:**

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.10+, FastAPI |
| AI Analysis | xAI, OpenAI, Google Gemini, Anthropic, Kimi (5 LLMs) |
| Detection | Falco (runtime security), Suricata (network IDS) |
| Orchestration | Kubernetes (K3s) |
| Database | PostgreSQL (8 tables, 12 indexes) |
| Monitoring | Prometheus + Grafana |
| IoT | MQTT broker (Mosquitto), Modbus, ONVIF protocols |

---

## Slide 5: System Architecture

**Five Processing Layers:**

```
┌──────────────────────────────────────────────────┐
│  Layer 5: Operator Dashboard (Grafana + API)     │
├──────────────────────────────────────────────────┤
│  Layer 4: Kubernetes Orchestration (K3s)         │
│  → Pod isolation, auto-scaling, NetworkPolicies  │
├──────────────────────────────────────────────────┤
│  Layer 3: IDS Core + LLM Analysis                │
│  → 5 LLM providers, dedup cache, governance     │
├──────────────────────────────────────────────────┤
│  Layer 2: Detection Engines                      │
│  → Falco (syscall) + Suricata (network)          │
├──────────────────────────────────────────────────┤
│  Layer 1: IoT Devices & Smart City Services      │
│  → 8 device types, MQTT/Modbus/ONVIF             │
└──────────────────────────────────────────────────┘
```

Alerts flow bottom-up: IoT → Detection → LLM Analysis → K8s Response → Dashboard

---

## Slide 6: Prototype Development — Key Modules

| Module | What It Does |
|--------|-------------|
| **Multi-LLM Manager** | Routes alerts to 5 providers with circuit breakers; fails over in < 0.5s |
| **Governance Controller** | 3 modes: Autopilot (auto), Assisted (human approval for critical), Manual (all require approval) |
| **Alert Deduplication** | LRU cache with MD5 fingerprints → 42% fewer LLM calls → 42% cost savings |
| **K8s Automation** | Isolates pods, scales deployments, blocks IPs based on severity |
| **Database Layer** | PostgreSQL with 8 tables — stores alerts, analyses, actions, audit logs |
| **Operator Interface** | REST API for incident listing, evidence retrieval, reasoning chains |
| **Metrics Engine** | 14 Prometheus metrics with persistence across pod restarts |

5,000+ lines of new Python code across 24 source files

---

## Slide 7: Prototype Development — Alert Pipeline

**How an alert is processed (end-to-end):**

1. **IoT device** sends telemetry via MQTT
2. **Falco/Suricata** detects anomaly → generates alert
3. **Forwarder** sends alert to IDS API
4. **Dedup cache** checks if duplicate (42% hit rate)
5. **LLM provider** analyzes alert → returns severity, threat type, recommendations
6. **Governance** decides: execute automatically or queue for human approval
7. **K8s automation** takes action (isolate pod, scale service, block IP)
8. **Database** persists everything with full audit trail
9. **Prometheus** emits metrics → **Grafana** dashboards update

**Average total time: 1.9 seconds**

---

## Slide 8: Prototype Development — LLM Failover

**5 LLM providers with independent circuit breakers:**

| Provider | Model | Role |
|----------|-------|------|
| xAI | grok-4-latest | Primary |
| OpenAI | gpt-4o | Secondary |
| Gemini | gemini-2.5-flash-lite | Cost-optimal ($0.50/1M tokens) |
| Anthropic | claude-sonnet-4-20250514 | Backup |
| Kimi | moonshot-v1-128k | Fallback |

- If one provider fails → circuit opens → next provider takes over in **< 0.5s**
- Circuit self-heals after cooldown (HALF_OPEN → test → CLOSED)
- **Safe mode:** If all providers fail, system uses deterministic rules (no LLM needed)

---

## Slide 9: Results — LLM Evaluation (5 Providers)

**Evaluated 5 providers on 20 real alerts across 10 attack families:**

| Provider | Model | Quality | Severity Acc. | Threat Acc. | Latency | Cost/1M |
|----------|-------|:-------:|:-------:|:----------:|:-------:|:-------:|
| Kimi | moonshot-v1-128k | **76.0%** | 100% | 50% | 2.9s | $6.00 |
| OpenAI | gpt-4o | **76.0%** | 100% | 50% | 2.5s | $10.00 |
| xAI | grok-4-latest | **76.0%** | 100% | 50% | 3.4s | $8.00 |
| Gemini | gemini-2.5-flash-lite | 74.0% | 100% | 45% | 2.7s | **$0.50** |
| Anthropic | claude-sonnet-4-20250514 | 68.0% | 80% | 50% | 5.0s | $16.00 |

- **100/100 attempts succeeded** — all providers 100% reliable
- Tight quality band (68–76%) validates multi-provider approach
- Gemini achieves 97% of top quality at **5% of the cost**

---

## Slide 10: Results — Attack Reproduction

**Two real attack scenarios reproduced on the live cluster:**

### DDoS Attack
| Metric | Target | Result |
|--------|--------|--------|
| Detection time | < 30s | **8.2s** |
| Severity classified | 7–9 | **8** |
| Auto-scaling triggered | Yes | **Yes** |
| Attack traffic | > 100 RPS | **450 RPS** |

### Privilege Escalation
| Metric | Target | Result |
|--------|--------|--------|
| Detection time | < 5s | **0.3s** |
| Severity classified | 8–10 | **9** |
| Pod isolation | Yes | **Yes** (queued in Assisted mode) |

8 attack families tested total (DDoS, privilege escalation, data exfiltration, lateral movement, Modbus tampering, MQTT abuse, ONVIF tampering, ONVIF recon)

---

## Slide 11: Results — Performance & Reliability

**End-to-End Processing:**

| Step | Time |
|------|------|
| Alert ingestion | 45 ms |
| Deduplication check | 3 ms |
| LLM analysis | 1.8s avg |
| K8s action | 280 ms |
| Database write | 65 ms |
| **Total** | **~1.9s** (target: < 2s ✅) |

**System Reliability:**

| Metric | Target | Achieved |
|--------|--------|----------|
| Uptime (7-day test) | 99% | **99.4%** |
| LLM availability (with failover) | 95% | **98.2%** |
| Unit tests | Pass | **50/50 (100%)** |
| Throughput | 50 alerts/min | **100 alerts/min** |

---

## Slide 12: Results — Capstone I vs Capstone II

| Metric | Capstone I | Capstone II |
|--------|-----------|------------|
| LLM providers | 1 (single) | **5 (with failover)** |
| Governance | None | **3-mode Human-in-the-Loop** |
| Persistence | In-memory | **PostgreSQL** |
| Alert deduplication | None | **42% cost savings** |
| Metrics | Basic | **14 Prometheus metrics** |
| Unit tests | Basic | **50 tests, 100% pass** |
| Uptime | 99.23% | **99.4%** |
| LLM evaluation | None | **5-provider scored eval** |

**Transformation: proof-of-concept → production-ready system**

---

## Slide 13: Results — Bug Discovery & Fix (Gemini)

**During evaluation, we discovered a critical Gemini parsing bug:**

- `gemini-2.5-flash` is a "thinking model" — its reasoning tokens consumed the output budget
- Only ~28 tokens left for JSON → **100% parse failure**
- Quality dropped to **21%**

**Our fix:**
1. Disabled thinking tokens (`thinkingBudget: 0`)
2. Increased output budget to 2048 tokens
3. Added structured JSON schema
4. Added brace-matching fallback parser

**Result:** Quality jumped from **21% → 74%**, severity accuracy from **12.5% → 100%**

This demonstrates real engineering problem-solving during the project.

---

## Slide 14: Conclusion & Future Work

**What We Achieved:**
- Built a **working AI-driven IDS** with 5 LLM providers for smart city security
- Alerts processed in **< 2 seconds** with **99.4% uptime**
- All providers scored within a **68–76% quality band** — multi-provider approach works
- **42% cost reduction** through deduplication
- **Human-in-the-Loop** governance enables safe, transparent AI-driven security

**Limitations:**
- 20-alert evaluation dataset (larger corpus would improve statistical power)
- Threat-type accuracy capped at ~50% (LLM taxonomy ≠ IDS categories)
- Not yet tested on resource-constrained edge hardware

**Future Work:**
- Expand evaluation to 100+ alerts with multiple runs
- Raspberry Pi edge deployment
- Federated learning across city districts
- Cross-city threat intelligence sharing

---

## Slide 15: References

1. Cloud Native Computing Foundation, "Falco — Runtime Security," 2024
2. Open Information Security Foundation, "Suricata IDS/IPS," 2024
3. MITRE Corporation, "ATT&CK for ICS," 2024
4. K. Ren et al., "LLM-based security analysis for IoT systems," *IEEE IoT Journal*, 2024
5. S. Chen and P. Liu, "AI-driven intrusion detection: A survey," *ACM Computing Surveys*, 2024
6. Kubernetes Documentation, "Network Policies," 2024
7. OWASP Foundation, "Smart City Security Top 10," 2024
8. M. Antonakakis et al., "Understanding the Mirai Botnet," *USENIX Security*, 2017
9. OpenAI, "GPT-4o API Documentation," 2025
10. xAI, "Grok API Reference," 2025
11. Google, "Gemini API — Thinking Models," 2025
12. Anthropic, "Claude API Documentation," 2025
13. Moonshot AI, "Kimi/Moonshot API Reference," 2025
14. FastAPI Documentation, 2024
15. Prometheus Authors, "Prometheus Monitoring," 2024

---

## Slide 16: Thank You & Questions

**LLM-Driven Intrusion Detection System for Edge-Enabled Smart Cities**

**Key Numbers:**
- 5 LLM providers, 100% evaluation reliability
- < 2s alert processing, 99.4% uptime
- 42% cost savings through deduplication
- 8 attack families detected and responded to
- 50 unit tests, 100% pass rate

Ali Suhail · Khaled Rahman · Abdullah Mahmoud
Supervisor: Dr. Dana Haj Hussein

**Questions?**
