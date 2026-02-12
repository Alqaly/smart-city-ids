# Smart City IDS Documentation

Welcome to the Smart City IDS documentation. This directory contains all guides for understanding, deploying, and operating the system.

---

## Start Here

**New to the project?**

1. Read: [Quick Start Guide (5 minutes)](QUICKSTART.md) - Get the system running
2. Read: [How It Works (10 minutes)](HOW_IT_WORKS.md) - Understand the architecture
3. Explore: [Architecture (15 minutes)](ARCHITECTURE.md) - Deep dive into components

---

## Documentation Structure

### Core Guides

| Document | Purpose | Audience | Time |
|----------|---------|----------|------|
| **[QUICKSTART.md](QUICKSTART.md)** | Install and verify the system | Everyone | 5 min |
| **[HOW_IT_WORKS.md](HOW_IT_WORKS.md)** | Understand component behavior | Developers, Operators | 10 min |
| **[ARCHITECTURE.md](ARCHITECTURE.md)** | System design and data flow | Architects, Engineers | 15 min |
| **[OPERATIONS.md](OPERATIONS.md)** | Operational tasks and commands | Operators, DevOps | 10 min |
| **[SETUP.md](SETUP.md)** | Detailed installation guide | Deployers | 20 min |
| **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** | Common issues and solutions | Everyone | 10 min |

### Academic & Justification

| Document | Purpose | Audience |
|----------|---------|----------|
| **[ACADEMIC_CONTEXT.md](ACADEMIC_CONTEXT.md)** | Why this is "emulation, not simulation" | Examiners, Reviewers |
| **[EXAMINER_DEFENSE.md](EXAMINER_DEFENSE.md)** | Ready-to-use answers to common questions | Students, Presenters |
| **[METRICS_AUDIT.md](METRICS_AUDIT.md)** | Validation that metrics are realistic | Analysts |
| **[LLM_REALITY_CHECK.md](LLM_REALITY_CHECK.md)** | LLM capabilities and limitations | Engineers |

### Reference

| Document | Purpose |
|----------|---------|
| **[SECURITY_MODEL.md](SECURITY_MODEL.md)** | MITRE ATT&CK mapping and threat model |
| **[LOG_FORMAT_GUIDE.md](LOG_FORMAT_GUIDE.md)** | Alert JSON schema and field reference |
| **[VALIDATION_CHECKLIST.md](VALIDATION_CHECKLIST.md)** | Verification checklist for production use |

### Archive

| Document | Purpose |
|----------|---------|
| **[ARCHIVE_INDEX.md](ARCHIVE_INDEX.md)** | Inventory of archived/legacy docs |
| **[_archive/](./_archive/)** | Historical reports, old checklists, and drafts |

---

## Use Cases

### "I want to..."

#### Get the system running
→ [QUICKSTART.md](QUICKSTART.md)

#### Understand how the system works
→ [HOW_IT_WORKS.md](HOW_IT_WORKS.md)

#### Learn the system architecture
→ [ARCHITECTURE.md](ARCHITECTURE.md)

#### Deploy to production
→ [SETUP.md](SETUP.md)

#### Operate and monitor the system
→ [OPERATIONS.md](OPERATIONS.md)

#### Fix a problem
→ [TROUBLESHOOTING.md](TROUBLESHOOTING.md)

#### Defend the system to an examiner
→ [EXAMINER_DEFENSE.md](EXAMINER_DEFENSE.md)

#### Understand why the approach is valid
→ [ACADEMIC_CONTEXT.md](ACADEMIC_CONTEXT.md)

#### Check if the metrics are realistic
→ [METRICS_AUDIT.md](METRICS_AUDIT.md)

#### Learn what the system can't do
→ [LLM_REALITY_CHECK.md](LLM_REALITY_CHECK.md)

#### See which attacks are detected
→ [SECURITY_MODEL.md](SECURITY_MODEL.md)

#### Parse alert data
→ [LOG_FORMAT_GUIDE.md](LOG_FORMAT_GUIDE.md)

---

## Key Concepts

### What Is This System?

The **Smart City IDS** is an **LLM-driven Intrusion Detection System** that:

1. **Detects** security threats using runtime monitoring (Falco) and network monitoring (Suricata)
2. **Analyzes** threats using Large Language Models (xAI Grok or OpenAI GPT)
3. **Responds** automatically with Kubernetes actions (pod isolation, scaling, eviction)
4. **Observes** the entire process through Prometheus/Grafana dashboards
5. **Persists** decisions in PostgreSQL for auditing and forensics

### Why "Emulation" Not "Simulation"?

The system uses:
- **Real** security detection tools (Falco, Suricata)
- **Real** container monitoring (Kubernetes)
- **Real** LLM API calls
- **Real** response automation

The IoT devices and attack scenarios are **emulated at scale** (not deployed to actual cities), but the **security processing is entirely real**.

### System Architecture (30-second version)

```
IoT Devices (30-100 MQTT pods)
    ↓
    ├─→ Falco (Runtime IDS) ──→ Alert
    │
    ├─→ Suricata (Network IDS) ─→ Alert
    │
    └─→ Smart City Services ────→ Alert

    IDS API (Decision Engine)
    ↓
    [1] Receive alert
    [2] Call LLM (xAI/OpenAI) for analysis
    [3] Decide: Is this a real threat?
    [4] Execute Kubernetes action if yes
    [5] Log to PostgreSQL
    
    Prometheus collects metrics
    ↓
    Grafana displays dashboards
```

---

## Quick Reference

### Service URLs (After Deployment)

```
Grafana (Dashboards):        http://<YOUR-IP>:30300
Prometheus (Metrics):         http://<YOUR-IP>:31106
IDS API (Docs):               http://<YOUR-IP>:30800/docs
```

### Essential Commands

```bash
# Check all pods
kubectl get pods -A

# Watch real-time events
kubectl get events -A --sort-by='.lastTimestamp' -w

# View IDS API logs
kubectl logs -n smart-city -l app=ids-api -f

# Query stored alerts
curl http://<YOUR-IP>:30800/api/alerts
```

---

## Before You Start

### System Requirements

- **OS:** Linux (Kali, Ubuntu 22.04+, Debian 12+)
- **RAM:** 4GB minimum, 8GB recommended
- **CPU:** 2 cores minimum, 4 cores recommended
- **Disk:** 20GB free space

### Prerequisites

- `kubectl` installed
- `git` installed
- At least one LLM API key (XAI_API_KEY or OPENAI_API_KEY)

---

## Documentation Glossary

| Term | Meaning |
|------|---------|
| **Alert** | Security event detected by Falco or Suricata |
| **Analysis** | LLM evaluation of alert severity and threat type |
| **Action** | Automated response executed based on analysis |
| **Emulation** | Real process in controlled environment at scale |
| **Pod** | Kubernetes smallest deployment unit |
| **Falco** | Runtime security tool (detects suspicious behavior) |
| **Suricata** | Network IDS (detects suspicious network traffic) |
| **MQTT** | Protocol used by IoT devices |
| **Prometheus** | Time-series metrics database |
| **Grafana** | Visualization and dashboarding platform |

---

## License

This documentation and the Smart City IDS project are licensed under the repository LICENSE file.

---

**Last Updated:** February 2026  
**Status:** Production Ready
