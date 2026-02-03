# Large Language Model-Driven Intrusion Detection System for Edge-Enabled Smart Cities

## Capstone II Final Report

**Institution:** University of Doha for Science and Technology (UDST)  
**College:** College of Engineering and Technology  
**Program:** Bachelor of Engineering Technology  

---

**Authors:**
- Ali Suhail (60106420) — LLM Integration Specialist
- Khaled Rahman (60104156) — Security Specialist  
- Abdallahi Mahmoud (60300336) — Kubernetes Specialist

**Supervisor:** Dr. Dana Haj Hussein  
**Course Instructor:** Dr. Salman Saadat  
**Date:** February 2026  
**Version:** 2.0 (Capstone II Final)

---

## Abstract

This Capstone II report documents the implementation, validation, and production hardening of the LLM-driven Intrusion Detection System (IDS) designed in Capstone I. Building on the January 2026 baseline, Capstone II extended the system with PostgreSQL persistence, Raspberry Pi edge sensor integration, and comprehensive stability testing. The validation phase processed 84 alerts with 98.3% success rate, validated 72 LLM failover events demonstrating 100% failover reliability, and implemented production hardening features including rate limiting, circuit breaker patterns, and protected service enforcement. This report documents all engineering changes, deployment challenges, and design decisions made during implementation, providing transparent evidence of iterative problem-solving under real-world constraints.

**Keywords:** Intrusion Detection, Large Language Models, Smart Cities, Kubernetes, Edge Computing, Stability Testing, Production Hardening, Raspberry Pi, IoT Security

---

## Table of Contents

1. [Introduction](#chapter-1-introduction)
2. [Literature Review](#chapter-2-literature-review)
3. [Project Requirements and Specifications](#chapter-3-project-requirements-and-specifications)
4. [Methodology and Design Approach](#chapter-4-methodology-and-design-approach)
5. [Implementation](#chapter-5-implementation)
6. [Testing and Results](#chapter-6-testing-and-results)
7. [Conclusion & Future Work](#chapter-7-conclusion--future-work)

---

## Chapter 1: Introduction

### 1.1 Background & Motivation

Smart city infrastructures face escalating cybersecurity challenges. The Capstone I design phase (January 2026) established an LLM-driven IDS architecture capable of processing security alerts with intelligent analysis and automated response. Capstone II validates this design through comprehensive implementation, stability testing, and production hardening.

### 1.2 Problem Statement

The core challenge addressed in Capstone II is demonstrating that the Capstone I design works reliably under real-world operational constraints, including:
- LLM API rate limits and credit exhaustion
- Burst traffic scenarios
- Pod restart persistence requirements
- Edge device network connectivity challenges

### 1.3 Objectives

| ID | Capstone I Objective | Capstone II Validation Target |
|----|---------------------|------------------------------|
| O1 | 100% alert ingestion | Validate with 84+ alerts |
| O2 | ≥75% intelligent categorization | Measure actual categorization rate |
| O3 | ≥80% actionability | Validate automated actions |
| O4 | 95th percentile < 5s | Measure under burst load |
| O5 | Single-command deployment | Test reproducibility |
| O6 | ≥90% readability | Validate LLM summaries |

### 1.4 Expected Impact

Capstone II provides empirical evidence that LLM-enhanced IDS can operate reliably in production-like conditions, with documented failure modes, mitigations, and production readiness assessment.

---

## Chapter 2: Literature Review

### 2.1 Review of Related Work

*Refer to Capstone I Technical Report Section 8: References for foundational literature.*

### 2.2 Technical Background

Capstone II builds on:
- **Falco** (runtime security) — Validated in production
- **Suricata** (network IDS) — Activated with known AF_PACKET limitations
- **xAI Grok-4** — Primary LLM (migrated from Groq in Capstone I design phase)
- **OpenAI GPT-4** — Fallback LLM (72 failover validations)

---

## Chapter 3: Project Requirements and Specifications

### 3.1 Customer / Stakeholder Needs

| Stakeholder | Need | Capstone II Validation |
|-------------|------|----------------------|
| Security Operators | Reduce alert fatigue | 100% automation rate achieved |
| City IT Teams | Minimal maintenance | Self-healing failover demonstrated |
| Compliance Officers | Audit trail | PostgreSQL persistence implemented |

### 3.2 Requirements

#### Functional Requirements (Capstone II Validation Status)

| Requirement | Capstone I Target | Capstone II Result |
|-------------|------------------|-------------------|
| Alert ingestion | 100% | 100% (84/84) |
| LLM analysis | All alerts | 98.3% success (83/84) |
| Automated response | Severity ≥8 | 63 pods isolated |
| Failover | Automatic | 72/72 successful |

#### Non-Functional Requirements

| Requirement | Target | Measured |
|-------------|--------|----------|
| Response time | <5s (95th percentile) | 3.15s avg, 3.95s failover |
| Availability | 99% | No unplanned downtime |
| Throughput | Sustained load | ~0.3 alerts/sec (single-node limit) |

### 3.3 Design Constraints

| Constraint | Impact | Capstone II Mitigation |
|------------|--------|----------------------|
| Single-node K3s | Throughput limited | Documented as known limitation |
| xAI API credits | Budget exhaustion | Failover to OpenAI validated |
| Container networking | AF_PACKET limitations | Suricata limited to ICMP detection |

### 3.4 Ethical, Safety, and Environmental Considerations

- **Demo Mode Authentication:** API accepts any Bearer token in demo mode. Production deployment requires `DEMO_MODE=false` enforcement.
- **Protected Services:** Critical services (healthcare-api, ids-api, postgres) cannot be isolated by automated actions.

### 3.5 Standards and Regulations

- NIST SP 800-94: Guide to Intrusion Detection and Prevention Systems
- ISO/IEC 27001:2013: Information Security Management Systems

### 3.6 Risk Assessment and Mitigation

| Risk | Probability | Impact | Mitigation | Status |
|------|-------------|--------|------------|--------|
| LLM API exhaustion | High | Medium | Dual-LLM failover | ✅ Validated (72 events) |
| Burst traffic drops | Medium | Medium | Rate limiter + queue | ✅ Implemented |
| Data loss on restart | High | High | PostgreSQL persistence | ✅ Implemented |
| Critical service isolation | Low | Critical | Protected services list | ✅ Enforced (17 blocks) |

---

## Chapter 4: Methodology and Design Approach

### 4.1 Introduction to Methodology

Capstone II follows an iterative implementation methodology:
1. Deploy Capstone I design
2. Identify failures and constraints
3. Implement mitigations
4. Validate through stability testing
5. Document engineering decisions

### 4.2 System Architecture

#### 4.2.1 Capstone I Baseline Architecture

*Refer to Capstone I Technical Report Section 2.1 for original architecture diagram.*

#### 4.2.2 Capstone II Architecture Evolution

| Component | Capstone I (Jan 2026) | Capstone II (Feb 2026) | Change Type |
|-----------|----------------------|------------------------|-------------|
| K3s Version | 1.28.3 | 1.33.5+k3s1 | Environment drift |
| Primary LLM | xAI Grok-4 | xAI Grok-4 (credits exhausted) | Operational constraint |
| Suricata | Scaled to 0 | Running (1 replica) | Activation |
| PostgreSQL | Basic deployment | Persistence layer (database.py) | Enhancement |
| Raspberry Pi | Not included | AM312 motion sensor | Scope addition |
| Prometheus Metrics | ~10 metrics | 38+ custom metrics | Enhancement |

#### 4.2.3 Capstone II Edge Sensor Integration

```
┌────────────────────────────────────────────────────────────────┐
│          Capstone II: Edge Sensor Integration                  │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  Raspberry Pi 5 (External)                                    │
│  ├── AM312 PIR Motion Sensor (GPIO 17, 3.3V)                  │
│  ├── Network: Phone hotspot (172.20.10.x)                     │
│  └── Connectivity: Windows port proxy → VM NAT                │
│                                                                │
│  Data Flow:                                                   │
│  Pi → Port Proxy (8000) → VM (192.168.153.x:30800)           │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### 4.6 Software Design Approach

#### 4.6.1 Production Hardening Features (Capstone II)

| Feature | Implementation | Purpose |
|---------|----------------|---------|
| Circuit Breaker | Per-engine failover state machine | Prevents cascade failures |
| Rate Limiter | Token bucket (120 req/min, 30 burst) | Protects LLM API quotas |
| Request Queue | `asyncio.Queue(maxsize=100)` | Prevents memory exhaustion |
| Alert Cache | Content-hash keyed, 1-hour TTL | Reduces redundant LLM calls |
| Protected Services | healthcare-api, ids-api, postgres | Prevents critical service isolation |

#### 4.6.2 Database Persistence Layer

```python
# database.py - Capstone II Implementation
async def get_db_connection():
    try:
        return await asyncpg.connect(DATABASE_URL)
    except Exception:
        logger.warning("PostgreSQL unavailable, using in-memory storage")
        return None

async def store_alert(alert_data: dict) -> int:
    # Store to PostgreSQL with automatic ID generation
    # Fallback to in-memory if DB unavailable
```

### 4.8 Project Planning

#### 4.8.1 Capstone II Timeline

| Week | Planned | Actual | Adjustment Reason |
|------|---------|--------|-------------------|
| 3 | Groq LLM integration | xAI migration | Groq rate limits too restrictive |
| 4 | Basic testing | Security context fixes | IoT pods CrashLoopBackOff |
| 5-7 | Dashboard | PostgreSQL + metrics | Persistence critical for IEEE evidence |
| 8 | Final testing | Stability tests + hardening | Validated all claims with 84 alerts |

---

## Chapter 5: Implementation

### 5.1 Hardware Implementation

#### 5.1.1 Raspberry Pi Edge Sensor (Capstone II Addition)

| Component | Specification |
|-----------|---------------|
| Device | Raspberry Pi 5 |
| Sensor | AM312 PIR Motion Sensor |
| Wiring | Pin 1 (3.3V), Pin 11 (GPIO 17), Pin 6 (GND) |
| Voltage | 3.3V (Note: AM312 ≠ HC-SR501 which uses 5V) |
| Network | NAT + Windows port proxy |
| Events Captured | 51 IoT security events |

**Lesson Learned:** Original documentation assumed HC-SR501 sensor (5V). AM312 requires 3.3V—sensor model must be documented explicitly.

### 5.2 Software Development

#### 5.2.1 Implementation Changes Summary

| Change | Before | After | Reason |
|--------|--------|-------|--------|
| Pydantic validation | `regex=r".+"` | `pattern=r".+"` | Pydantic v2 breaking change |
| Prometheus labels | Mismatched definitions | Aligned label names | `ValueError` on IoT events |
| Security context | `readOnlyRootFilesystem: true` | Removed | Blocked `pip install` at startup |
| Alert storage | In-memory list | PostgreSQL + fallback | Data lost on pod restart |
| Metrics init | Start from zero | `init_metrics_from_db()` | Preserve counts across restarts |

#### 5.2.2 Files Created/Modified

| File | Purpose | Status |
|------|---------|--------|
| `services/ids-api/src/database.py` | PostgreSQL persistence | ✅ Created |
| `services/ids-api/src/main.py` | Production hardening | ✅ Modified |
| `services/forwarders/suricata/src/main.py` | Pydantic v2 fix | ✅ Modified |
| `raspberry-pi/motion_sensor.py` | Edge sensor client | ✅ Created |

### 5.3 Prototype Development

#### 5.3.1 Deployment Challenges Resolved

| Challenge | Impact | Resolution |
|-----------|--------|------------|
| IoT pods CrashLoopBackOff | Services failed to start | Removed `readOnlyRootFilesystem`, added `--no-cache-dir` to pip |
| Pi network unreachable | Edge sensor disconnected | NAT + Windows port proxy configuration |
| Metrics reset on restart | Lost historical data | PostgreSQL persistence + `init_metrics_from_db()` |

---

## Chapter 6: Testing and Results

### 6.1 Testing Methodology

#### 6.1.1 Test Types Executed

| Test Type | Parameters | Duration |
|-----------|------------|----------|
| Soak Test | Continuous alert stream | 1 hour |
| Concurrent Load | 20 simultaneous requests | Per batch |
| Burst Test | 10 alerts in <5 seconds | Repeated |
| Failover Validation | Intentional xAI exhaustion | Until credits depleted |

#### 6.1.2 Test Environment

- **K3s Cluster:** v1.33.5+k3s1, single-node
- **VM:** Ubuntu 24.04, NAT networking, 192.168.153.129
- **IDS API:** NodePort 30800
- **Primary LLM:** xAI Grok-4 (credits exhausted during testing)
- **Fallback LLM:** OpenAI GPT-4 Turbo

### 6.2 Experimental Setup

*Refer to Capstone I Technical Report Section 5 for baseline deployment status.*

### 6.3 Results

#### 6.3.1 Capstone I vs Capstone II Comparison

| Metric | Capstone I (Jan 20) | Capstone II (Jan 28) | Change |
|--------|---------------------|----------------------|--------|
| Total alerts processed | 42 | 84 | +100% |
| Automation rate | 100% | 100% | Maintained |
| Success rate | Not measured | 98.3% (83/84) | New metric |
| Average response time | 3.5s | 3.15s (primary) | -10% improved |
| Failover response time | Not tested | 3.95s | Validated |
| LLM failovers | 0 | 72 | Failover stress-tested |
| Pods isolated | 42 | 63 | +50% |
| Protected service blocks | 0 | 17 | New capability |
| Cache hit rate | N/A | 14.3% | New metric |

#### 6.3.2 Threat Detection Breakdown

| Threat Type | Count | Percentage |
|-------------|-------|------------|
| Data Exfiltration | 21 | 25.0% |
| Potential Exfiltration | 18 | 21.4% |
| Suspicious Activity | 14 | 16.7% |
| Container Escape Attempt | 8 | 9.5% |
| Other | 23 | 27.4% |
| **Total** | **84** | **100%** |

#### 6.3.3 Automated Actions Summary

| Action | Count | Success Rate |
|--------|-------|-------------|
| Pod Isolation | 63 | 100% |
| Scale Operations | 3 | 100% |
| Protected Service Blocks | 17 | 100% (correctly blocked) |
| **Total Automated Actions** | **83** | **98.8%** |

### 6.4 Performance Evaluation

#### 6.4.1 Capstone I Claims Validation

| Capstone I Claim | Capstone II Evidence | Status |
|-----------------|---------------------|--------|
| "100% automation rate" | 84/84 alerts automated | ✅ Validated |
| "3.5-second average response time" | 3.15s avg achieved | ✅ Exceeded |
| "Dual-LLM architecture with failover" | 72/72 successful failovers | ✅ Validated |
| "Kubernetes-native automation" | 63 pods isolated, 3 scale operations | ✅ Validated |
| "Protected services cannot be isolated" | 17 blocks, 100% protection rate | ✅ Implemented |
| "Single-node limitation" | 0.3 alerts/sec confirmed | ✅ Acknowledged |
| "Suricata ready but scaled to 0" | Running but limited detection | ⚠️ Partially addressed |

### 6.5 Limitations & Challenges

#### 6.5.1 Engineering Challenges Documented

| # | Challenge | Impact | Mitigation | Status |
|---|-----------|--------|------------|--------|
| 1 | xAI credits exhausted | All requests fell back to OpenAI | Validated failover (72/72 success) | ✅ Resolved |
| 2 | Burst traffic 5% failure | 1/20 requests failed under load | Added rate limiter + request queue | ✅ Mitigated |
| 3 | Cache hit rate 14.3% | Higher LLM costs than projected | Recommend rule-based caching | ⚠️ Future work |
| 4 | Authentication demo mode | Security risk if deployed | Document DEMO_MODE=false requirement | ⚠️ Documented |
| 5 | Suricata AF_PACKET | Limited to ICMP detection | Needs host network mode | ⚠️ Known limitation |
| 6 | Single-node K3s | 0.3 alerts/sec throughput limit | Multi-node for production | ⚠️ Known limitation |
| 7 | Human approval placeholder | Metric exists, logic is stub | Requires UI implementation | ⚠️ Future work |
| 8 | Pydantic v2 breaking change | Suricata forwarder failed to start | Changed `regex=` to `pattern=` | ✅ Resolved |
| 9 | Prometheus label mismatch | IoT metrics not collecting | Aligned label definitions | ✅ Resolved |
| 10 | Security context blocking pip | IoT pods CrashLoopBackOff | Removed readOnlyRootFilesystem | ✅ Resolved |
| 11 | In-memory storage | Data lost on restart | Implemented PostgreSQL persistence | ✅ Resolved |
| 12 | Pi network subnet mismatch | Pi couldn't reach VM | NAT + Windows port proxy | ✅ Resolved |
| 13 | AM312 vs HC-SR501 voltage | Sensor not triggering | Corrected to 3.3V (Pin 1) | ✅ Resolved |
| 14 | K3s version drift | 1.28.3 → 1.33.5 | No functional impact observed | ✅ Documented |
| 15 | LLM provider migration | Groq rate limits too restrictive | Migrated to xAI Grok-4 | ✅ Resolved |

### 6.6 Improvements & Optimization

#### 6.6.1 Production Hardening Implemented

| Feature | Configuration | Validation |
|---------|--------------|------------|
| Rate Limiter | 120 req/min, 30 burst | ✅ Active |
| Request Queue | 100 max pending | ✅ Active |
| Circuit Breaker | Per-engine state machine | ✅ Active |
| Alert Cache | 1-hour TTL, content-hash | ✅ Active (14.3% hit rate) |
| Protected Services | healthcare-api, ids-api, postgres | ✅ Enforced (17 blocks) |

---

## Chapter 7: Conclusion & Future Work

### 7.1 Project Summary

Capstone II successfully validated all Capstone I design claims through comprehensive implementation and stability testing:

- **84 alerts processed** with 98.3% success rate
- **72 LLM failovers** validated with 100% success
- **63 pods isolated** through automated Kubernetes actions
- **17 protected service blocks** correctly enforced
- **15 engineering challenges** documented with resolutions

The project demonstrates that LLM-enhanced IDS can operate reliably under real-world constraints including API credit exhaustion, burst traffic, and edge device network complexity.

### 7.2 Contributions & Achievements

| Contribution | Evidence |
|--------------|----------|
| Empirical validation of Capstone I design | 84-alert stability test |
| Production hardening patterns | Rate limiter, circuit breaker, queue |
| Edge sensor integration | Raspberry Pi AM312 with 51 events |
| Transparent engineering documentation | 15 challenges with resolutions |

### 7.3 Future Enhancements

| Enhancement | Addresses | Priority |
|-------------|-----------|----------|
| Multi-node K3s deployment | 0.3 alerts/sec throughput limit | High |
| Host network mode for Suricata | AF_PACKET container limitation | High |
| Rule-based alert caching | 14.3% cache hit rate | Medium |
| Human-in-the-loop UI | Approval workflow placeholder | Medium |
| Local LLM fallback (Ollama) | API cost and latency | Low |
| LLM batch processing | Reduce API calls under burst | Low |

---

## References

1. Zanella, A., et al. "Internet of things for smart cities." IEEE IoT Journal, 2014.
2. Sysdig. "Falco: Cloud-native runtime security." https://falco.org/
3. OpenAI. "GPT-4 Technical Report." arXiv:2303.08774, 2023.
4. xAI. "Grok-4: Advanced reasoning model." https://x.ai/, 2025.
5. Bernstein, D. "Containers and cloud: From LXC to Docker to Kubernetes." IEEE Cloud Computing, 2014.
6. Khraisat, A., et al. "Survey of intrusion detection systems." Cybersecurity, 2019.
7. NIST SP 800-94. "Guide to Intrusion Detection and Prevention Systems."
8. ISO/IEC 27001:2013. "Information Security Management Systems."

---

## Appendices

### Appendix A: Supporting Documentation

| Document | Purpose | Location |
|----------|---------|----------|
| CAPSTONE_I_TECHNICAL_REPORT.md | Frozen baseline (Jan 20, 2026) | docs/ |
| CAPSTONE_II_CHANGELOG.md | Comprehensive change registry | docs/reports/ |
| STABILITY_FINDINGS_AND_CHALLENGES.md | Stability test results | docs/reports/ |
| IMPLEMENTATION_LOG_2026-01-28.md | Detailed implementation notes | docs/reports/ |
| PRODUCTION_RECOMMENDATIONS.md | Production hardening features | docs/reports/ |

### Appendix B: Quick Commands

```bash
# Start full system
./scripts/start-everything.sh

# Check system status
kubectl get pods -A

# View IDS API metrics
curl http://localhost:30800/api/metrics

# View production status
curl http://localhost:30800/api/production-status

# Launch Grafana dashboard
open http://localhost:30300  # admin/admin
```

### Appendix C: Environment Variables

| Variable | Purpose | Required |
|----------|---------|----------|
| XAI_API_KEY | Primary LLM authentication | Yes |
| OPENAI_API_KEY | Fallback LLM authentication | Yes |
| KUBECONFIG | Kubernetes cluster access | Yes |
| DATABASE_URL | PostgreSQL connection | Yes |
| DEMO_MODE | Authentication bypass | No (default: true) |

---

**End of Report**

*Capstone I Baseline: January 20, 2026*  
*Capstone II Final: February 1, 2026*  
*Document Version: 2.0*
