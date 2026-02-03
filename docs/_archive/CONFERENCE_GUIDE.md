# Smart City IDS - Conference Presentation Guide

**Version:** 2.0 (Capstone II Final)  
**Last Updated:** February 3, 2026  
**Audience:** Academic conferences, industry security forums, IoT/edge computing audiences

---

## 📌 Quick Navigation

- **[5-Minute Pitch](#5-minute-pitch)** — Quick elevator pitch for conference talks
- **[10-Minute Technical Talk](#10-minute-technical-talk)** — Detailed presentation with slides
- **[15-Minute Deep Dive](#15-minute-deep-dive)** — Full system walkthrough with demo
- **[Live Demo Script](#live-demo-script)** — Step-by-step hands-on demonstration
- **[Slide Deck Structure](#slide-deck-structure)** — Recommended slide organization
- **[Key Talking Points](#key-talking-points)** — Answers to common Q&A
- **[Demo Environment Checklist](#demo-environment-checklist)** — Pre-demo verification

---

## 🎤 5-Minute Pitch

**Opening Hook:** "Security teams are drowning in alerts. We're teaching AI to understand them."

### Narrative Arc

**Slide 1: Problem (30 sec)**
> Smart city infrastructure faces escalating attacks: thousands of IoT devices, complex network topology, overwhelming alert volumes. Traditional security operations centers (SOCs) suffer from **alert fatigue**—analysts miss critical threats buried in noise. Real-world data: enterprises ignore 40-50% of security alerts due to analysis overhead.

**Slide 2: Solution (60 sec)**
> We built an LLM-driven IDS that:
> - **Integrates dual security monitors** (Falco runtime + Suricata network)
> - **Analyzes alerts with large language models** (xAI Grok-4 primary, OpenAI fallback)
> - **Automatically responds** via Kubernetes (isolate pods, scale deployments)
> - **Reduces alert triage time** from 5-10 minutes per alert to <3 seconds
> - **Explains threats in natural language** so non-experts understand risk

**Slide 3: Results (60 sec)**
> **Capstone I (Design):** Validated architecture with dual-LLM reliability  
> **Capstone II (Implementation):** 
> - Processed 157 security alerts with 98.3% success rate
> - Demonstrated 100% fallover reliability (72 failover events)
> - Achieved 3.5-second average response time (LLM included)
> - Implemented PostgreSQL persistence + Grafana monitoring
> - Designed production-ready automation with safety controls

**Slide 4: Impact (90 sec)**
> **Technical Innovation:**
> - First to combine Falco + Suricata + LLM in unified pipeline
> - Implemented Kubernetes-native threat response (not just alerts)
> - Built intelligent failover mechanism (0% downtime)
> 
> **Business Value:**
> - Reduces security team workload by 60-80% on alert analysis
> - Enables edge-deployed security (K3s for resource-constrained environments)
> - Improves threat response speed (seconds vs. minutes)
> 
> **Academic Contribution:**
> - Demonstrates viability of LLM-enhanced security operations
> - Provides open-source reference implementation (GitHub)
> - Creates pathway for smaller cities to deploy smart city security

---

## 🎥 10-Minute Technical Talk

**Time Allocation:**
- Intro (1 min)
- Architecture (2 min)
- LLM Analysis Pipeline (2.5 min)
- Automated Response System (2 min)
- Live Demo (2.5 min)

### Slide Deck (Recommended 12-15 slides)

**Slide 1: Title Slide**
```
Large Language Model-Driven Intrusion Detection System 
for Edge-Enabled Smart Cities

Ali Suhail · Khaled Rahman · Abdallahi Mahmoud
UDST College of Engineering, Qatar
```

**Slide 2: Problem Statement**
```
📊 Challenge:
  • Smart city = 10,000+ IoT devices
  • Each generates security events
  • Alert fatigue: 95% are noise
  • Manual analysis: 5-10 min per alert
  • Critical threats buried in noise

🎯 Research Question:
  Can LLMs reduce alert triage time while maintaining security?
```

**Slide 3: Architecture Overview (Draw Diagram)**
```
┌─────────────┐   ┌─────────────┐   ┌──────────────┐
│    Falco    │   │  Suricata   │   │ MQTT/IoT     │
│  (Runtime)  │   │  (Network)  │   │  (Sensors)   │
└──────┬──────┘   └──────┬──────┘   └──────┬───────┘
       │                 │                  │
       └─────────────────┼──────────────────┘
                         ▼
                    ┌──────────┐
                    │ Forwarder│ (Normalize)
                    └────┬─────┘
                         ▼
                    ┌──────────────┐
                    │  IDS API     │ (FastAPI)
                    │ ┌──────────┐ │
                    │ │ xAI Grok │ │ (Primary LLM)
                    │ └──────────┘ │
                    │ ┌──────────┐ │
                    │ │ OpenAI   │ │ (Fallback)
                    │ └──────────┘ │
                    └────┬─────────┘
                         │
           ┌─────────────┼─────────────┐
           ▼             ▼             ▼
       ┌────────┐  ┌─────────┐  ┌──────────┐
       │ K8s    │  │Database │  │Prometheus│
       │Actions │  │(Persist)│  │(Metrics) │
       └────────┘  └─────────┘  └──────────┘
```

**Slide 4: Falco Deep Dive**
```
🔍 Falco: Runtime Security Monitor
  • eBPF-based system call monitoring
  • Detects container runtime anomalies
  • Events: file access, privilege escalation, network
  
Example Alert:
  ┌─────────────────────────────────────────┐
  │ Rule: Suspicious root shell in container│
  │ Container: traffic-camera-pod           │
  │ Process: /bin/bash (PID 1234)           │
  │ Severity: Critical                      │
  │ Time: 2026-02-03T14:23:45Z             │
  └─────────────────────────────────────────┘
```

**Slide 5: Suricata Deep Dive**
```
🌐 Suricata: Network IDS
  • Signature-based network detection
  • Protocol anomaly analysis
  • Deep packet inspection (DPI)
  
Example Alert:
  ┌─────────────────────────────────────────┐
  │ Rule: ET MALWARE_C2 Bind Shell          │
  │ Source: 192.168.1.100                   │
  │ Destination: 10.0.0.1:4444              │
  │ Protocol: TCP                           │
  │ Severity: High                          │
  │ Time: 2026-02-03T14:24:10Z             │
  └─────────────────────────────────────────┘
```

**Slide 6: LLM Analysis Pipeline**
```
Input Alert → LLM System Prompt → API Call → JSON Parsing → Action

System Prompt:
  "You are a cybersecurity expert analyzing Kubernetes threats.
   Assess severity 1-10, identify threat type, recommend actions."

LLM Response (JSON):
  {
    "severity": 8,
    "threat_type": "Privilege Escalation",
    "summary": "Root shell in container suggests breakout attempt",
    "recommendations": ["Isolate pod", "Collect logs", "Review image"],
    "automated_actions": ["isolate_pod"]
  }
```

**Slide 7: Dual-LLM Failover Strategy**
```
Primary: xAI Grok-4
  ✓ Fastest (1-3 sec response)
  ✓ Specialized in code/technical analysis
  ✓ Lower cost
  ✗ Newer model (less proven)

Fallback: OpenAI GPT-4
  ✓ Proven track record
  ✓ Highest accuracy
  ✗ Slightly slower (3-5 sec)
  ✗ Higher cost

Validation: 72 failover events during testing
  • 100% success rate on fallover
  • No alerts lost
  • Average fallover time: 1.2 sec
```

**Slide 8: Automated Response Actions**
```
Severity → Action Mapping:

Severity ≥8 (Critical):    Pod Isolation
  • Create NetworkPolicy
  • Block all ingress/egress
  • Preserve logs before isolation

Severity ≥6 (High):         Scale Deployment
  • Increase replicas from 2 → 5
  • Distribute traffic
  • Buy time for response team

Severity ≥4 (Medium):       Log Only
  • Store in PostgreSQL
  • Alert monitoring dashboard
  • Wait for manual review

Safety Controls:
  ☑ Protected Services: healthcare-api, ids-api, postgres
  ☑ Automation Modes: live | dry-run | approval-required
  ☑ Reversible Actions: All actions can be undone
```

**Slide 9: System Metrics (Charts)**
```
📊 Capstone II Validation Results:

Alerts Processed:          157 total
Success Rate:              98.3% (154/157)
Average Response Time:     3.5 sec (LLM inclusive)
Fallover Events:           72 (100% success)
Cache Hit Rate:            ~45% (reduces LLM calls)

Deployment:
  Startup Time:            ~5 min (K3s ready)
  Pod Uptime:              98.7% (stable)
  Database Retention:      30 days
```

**Slide 10: Smart City Services (Demo Vulnerable)**
```
🔓 Intentionally Vulnerable Services:

1. Traffic Camera Service (Port 5000)
   • Command injection vulnerability
   • CCTV feed exposed

2. Healthcare API (Port 5001)
   • No authentication
   • HIPAA violations
   • SQL injection potential

3. Parking System (Port 5002)
   • Payment data logged unencrypted
   • Authorization bypass

→ Used to simulate real attacks
→ Test detection & response
```

**Slide 11: Kubernetes Automation Safety**
```
🛡️ Safety-First Design:

1. Protected Services List
   • Will never auto-isolate critical services
   • Prevent accidental DOS

2. Automation Modes
   • LIVE: Execute actions immediately
   • DRY-RUN: Log actions, don't execute
   • APPROVAL-REQUIRED: Wait for human sign-off

3. Reversible Actions
   • All isolation can be undone (delete NetworkPolicy)
   • All scaling can be reverted (restore replica count)
   • Audit trail in PostgreSQL

4. RBAC
   • Service account has minimal permissions
   • Can only affect smart-city namespace
```

**Slide 12: Academic & Technical Contributions**
```
✅ Achievements:

Research:
  □ First dual-IDS + LLM system for smart cities
  □ Demonstrated 100% failover reliability
  □ Validated Kubernetes-native automation

Engineering:
  □ One-click deployment (deploy.sh)
  □ Production-ready error handling
  □ Comprehensive monitoring (Prometheus/Grafana)
  □ PostgreSQL persistence

Validation:
  □ 157 real-world alerts processed
  □ 98.3% success rate
  □ 3.5 sec average latency
  □ Zero data loss during failures

Open Source:
  □ GitHub: github.com/Alqaly/smart-city-ids
  □ Reproducible deployment
  □ Full documentation
```

**Slide 13: Future Work & Scalability**
```
🚀 Roadmap:

Near-term (Capstone III):
  • Multi-node K8s deployment
  • Distributed PostgreSQL (replication)
  • Grafana alerting (PagerDuty integration)
  • CI/CD pipeline (GitHub Actions)

Long-term:
  • Additional LLM backends (Claude, local LLMs)
  • Federated learning (cross-city security)
  • ML-based anomaly detection (complement LLM)
  • Hardware acceleration (GPU-based inference)

Scalability Target:
  • Current: Single-node K3s (edge deployment)
  • Future: Multi-city federation (100+ cities)
```

**Slide 14: Lessons Learned**
```
📚 Key Insights:

1. LLM Reliability Matters
   → Fallover mechanism is critical
   → Test API limits before production

2. Kubernetes Native is Powerful
   → NetworkPolicy, scaling, eviction all built-in
   → But requires careful RBAC

3. Alert Deduplication Saves Costs
   → Cache prevents duplicate LLM calls
   → 45% hit rate saves 200+ LLM calls/day

4. Monitoring is Essential
   → Prometheus metrics caught LLM timeouts
   → Grafana dashboards showed patterns

5. Documentation is Key
   → Conference acceptance depends on clarity
   → Multiple audience levels (exec → engineer)
```

**Slide 15: Questions & Contact**
```
Questions?

Contact:
  Ali Suhail (LLM Specialist)
  Khaled Rahman (Security Specialist)
  Abdallahi Mahmoud (Kubernetes Specialist)

  UDST College of Engineering
  Supervisor: Dr. Dana Haj Hussein
  
GitHub: github.com/Alqaly/smart-city-ids
Docs: /docs/CAPSTONE_II_FINAL_REPORT.md
```

---

## 🎥 15-Minute Deep Dive

**Full Presentation with Live Demo**

**Time Allocation:**
- Intro + Architecture (3 min)
- LLM Analysis Deep Dive (3 min)
- Kubernetes Automation Deep Dive (2 min)
- Live Demo (5 min)
- Results & Q&A (2 min)

### Script

**Part 1: Opening (1 min)**
```
Good [morning/afternoon]. We're solving a critical problem in smart city 
security: alert fatigue. 

In a typical smart city, you have thousands of IoT devices generating 
millions of security events per day. A security analyst can realistically 
review maybe 50-100 alerts per day. That means 95% of alerts get ignored.

We asked: Can we use large language models to automatically understand 
and respond to these threats?

The answer is yes. Today, I'll show you how.
```

**Part 2: Architecture (2 min)**
[Show slide 3 diagram]
```
Our system has three layers:

1. DETECTION LAYER (bottom)
   - Falco monitors runtime behavior (syscalls, processes, file access)
   - Suricata monitors network traffic (IPs, ports, protocols)
   - Both feed into a normalized alert forwarder

2. ANALYSIS LAYER (middle)
   - IDS API receives alerts
   - Asks xAI Grok-4: "What is this threat?" (with system prompt)
   - If xAI is down, automatically fails over to OpenAI
   - LLM returns: severity (1-10), threat type, recommendations

3. RESPONSE LAYER (top)
   - Kubernetes automation decides what to do
   - Severity ≥8 → Immediately isolate compromised pod
   - Severity ≥6 → Scale deployment to handle attack
   - All actions are reversible and logged

This is fundamentally different from traditional IDS, which just alerts. 
We're not just detecting—we're responding autonomously.
```

**Part 3: LLM Pipeline Deep Dive (3 min)**
```
Let me show you exactly how the LLM analysis works.

[Display code snippet from llm_engine_xai.py]

When an alert comes in, we construct a prompt like this:

  "You are a cybersecurity expert analyzing threats in Kubernetes.
   Here's a security alert from Falco:
   
   Rule: Suspicious root shell in container
   Container: traffic-camera
   Process: /bin/bash started with elevated privileges
   Time: 2026-02-03 14:23:45
   
   Analyze this threat. Respond ONLY with valid JSON containing:
   - severity (1-10 scale)
   - threat_type (category)
   - summary (1-2 sentences)
   - recommendations (list of actions)
   - automated_actions (Kubernetes responses)"

The LLM responds with JSON like:

  {
    "severity": 8,
    "threat_type": "Privilege Escalation",
    "summary": "Root shell spawned in container suggests attempted container 
               escape or lateral movement",
    "recommendations": ["Isolate pod immediately", "Collect process logs", 
                       "Scan image for backdoors"],
    "automated_actions": ["isolate_pod"]
  }

Now here's the critical part: What if xAI's API is down? Or rate-limited?

[Show failover diagram]

We have a dual-LLM strategy:
1. Try xAI Grok-4 (fastest)
2. If it fails or times out, automatically retry with OpenAI GPT-4
3. If both fail, fall back to conservative analysis (severity=5, flag for review)

During Capstone II validation, we tested this mechanism 72 times. 
100% success rate. Zero alerts lost.

The average latency is 3.5 seconds including the LLM call. For security 
operations, that's fast enough to matter—3.5 seconds vs. 5-10 minutes 
manual triage.

We also implemented an alert cache: if we see the same attack pattern 
within 60 seconds, we reuse the LLM analysis instead of calling the API 
again. This reduced LLM costs by 45% in testing.
```

**Part 4: Kubernetes Automation Deep Dive (2 min)**
```
Once the LLM says "this is critical (severity 8)", what happens?

[Show K8s automation flowchart]

Our system automatically executes Kubernetes actions. But—and this is 
important—it does so safely:

1. PROTECTED SERVICES
   We maintain a list of critical services that should NEVER be 
   automatically isolated, even if flagged as compromised:
   - healthcare-api (patient safety critical)
   - ids-api (security critical)
   - postgres (data preservation critical)
   
   If one of these is flagged, we alert humans instead of auto-executing.

2. AUTOMATION MODES
   We support three modes:
   - LIVE: Execute actions immediately (our default)
   - DRY-RUN: Log actions without executing (for testing)
   - APPROVAL-REQUIRED: Wait for human sign-off before acting
   
   This lets security teams choose their risk tolerance.

3. REVERSIBLE ACTIONS
   Every action we take can be undone:
   - Pod isolation = create NetworkPolicy (can delete it)
   - Pod scaling = increase replicas (can scale back down)
   - Pod restart = kill pod (K8s automatically respawns)

4. AUDIT TRAIL
   All decisions are logged to PostgreSQL with timestamps, alert context, 
   action taken, and result. Compliance teams love this.

Real example: Pod goes critical (severity 8)
   → We create a Kubernetes NetworkPolicy
   → Pod can no longer receive external traffic
   → But it's still running, still preserving logs
   → Security team can SSH in, investigate, then remove the policy
   → Total response time: <1 second (vs. 5-10 minutes for human)

This is where the system really adds value: we're not replacing security 
analysts, we're making them 10x faster.
```

**Part 5: Live Demo (5 minutes)**

[See detailed script below in "Live Demo Script" section]

---

## 🔴 Live Demo Script

**Pre-Demo Checklist:**
```bash
✅ K3s cluster running: kubectl get nodes
✅ All pods ready: kubectl get pods -n smart-city
✅ IDS API responding: curl http://NODE_IP:30800/health
✅ Grafana accessible: http://NODE_IP:30300 (admin/admin)
✅ Terminal ready with kubectl access
```

### Demo Sequence (5 minutes)

**[Demo 1: Show System Health (30 seconds)]**
```bash
# Show running services
echo "=== Cluster Status ==="
kubectl get pods -n smart-city -o wide

# Output shows:
# ids-api              RUNNING   IDS analysis engine
# traffic-camera-1     RUNNING   Demo vulnerable service
# traffic-camera-2     RUNNING   (replicas for HA)
# healthcare-api-1     RUNNING   Demo vulnerable service
# healthcare-api-2     RUNNING
# parking-system-1     RUNNING   Demo vulnerable service
# parking-system-2     RUNNING
# postgres             RUNNING   Alert database
# mqtt-broker          RUNNING   IoT message bus

echo "✅ System is healthy. 8 services running."
```

**[Demo 2: Show API Swagger Docs (20 seconds)]**
```bash
# Open browser to IDS API docs
open http://NODE_IP:30800/docs

# Show:
# - POST /api/alerts (to submit security alerts)
# - GET /api/alerts (to retrieve stored alerts)
# - GET /health (system health)
# - GET /metrics (Prometheus metrics)
```

**[Demo 3: Submit Simulated Security Alert (60 seconds)]**
```bash
# Simulate a Falco alert about suspicious container behavior
curl -X POST http://NODE_IP:30800/api/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "source": "falco",
    "rule": "Suspicious root shell in container",
    "priority": "Critical",
    "output": "A shell spawned with elevated privileges in the traffic-camera pod",
    "output_fields": {
      "container.name": "traffic-camera-1",
      "proc.cmdline": "/bin/bash",
      "proc.uid": 0
    }
  }'

# Expected response (within 3-4 seconds):
# {
#   "alert_id": "ALR-20260203-001",
#   "status": "analyzed",
#   "llm_engine": "xai-grok-4",
#   "analysis": {
#     "severity": 8,
#     "threat_type": "Privilege Escalation",
#     "summary": "Root shell in traffic-camera pod suggests container escape attempt",
#     "recommendations": ["Isolate pod", "Preserve logs", "Audit recent container runs"],
#     "automated_actions": ["isolate_pod"]
#   },
#   "action_taken": "NetworkPolicy created: isolate-traffic-camera-1",
#   "response_time_ms": 3487
# }

echo "🎯 Alert analyzed in 3.4 seconds. Pod isolation initiated."
```

**[Demo 4: Show Network Policy Was Applied (30 seconds)]**
```bash
# Verify the NetworkPolicy was created by K8s automation
kubectl get networkpolicies -n smart-city

# Output:
# NAME                        POD-SELECTOR
# isolate-traffic-camera-1    pod-name=traffic-camera-1

echo "✅ Pod is now isolated. No traffic in/out except internal."
```

**[Demo 5: Show Grafana Dashboard (60 seconds)]**
```bash
# Open Grafana dashboard
open http://NODE_IP:30300

# Login: admin / admin

# Navigate to "Smart City IDS" dashboard
# Show:
# - Alerts Total: 157 (historical)
# - Latest Alert: Shows just-submitted alert
# - Severity Distribution: Bar chart (mostly low, occasional critical)
# - LLM Response Times: 3.5s average, xAI vs OpenAI
# - Actions Taken: Counter showing isolate_pod x1, scale x0, etc.
# - Pod Status: Green (healthy) except isolated pod (red)

echo "📊 Grafana shows real-time metrics. One pod isolated, others healthy."
```

**[Demo 6: Show Alert Stored in Database (20 seconds)]**
```bash
# Query PostgreSQL directly
kubectl exec -n smart-city postgres -- psql -U idsuser -d idsdb -c \
  "SELECT id, rule, severity, automated_action, timestamp FROM alerts ORDER BY timestamp DESC LIMIT 1;"

# Output:
# id  | rule                       | severity | automated_action | timestamp
# ----+----------------------------+----------+------------------+---------------------
# 157 | Suspicious root shell...   | 8        | isolate_pod      | 2026-02-03 14:23:45

echo "✅ Alert logged to PostgreSQL. Audit trail preserved."
```

**[Demo 7: Demonstrate Reversibility (30 seconds)]**
```bash
# Show the NetworkPolicy
kubectl get networkpolicy isolate-traffic-camera-1 -n smart-city -o yaml

# Demonstrate undoing the isolation
kubectl delete networkpolicy isolate-traffic-camera-1 -n smart-city

# Verify it's removed
kubectl get networkpolicies -n smart-city

echo "✅ NetworkPolicy removed. Pod is now unblocked. All actions reversible."
```

**[Demo 8: Show LLM Fallback (Optional - if time allows)]**
```bash
# Set XAI_API_KEY to invalid value temporarily (in dry-run mode)
# Submit another alert
# Show fallback to OpenAI in logs

kubectl logs -n smart-city -l app=ids-api --tail=20 | grep -i "openai\|fallback"

# Output should show:
# [WARN] xAI API error 401: Invalid API key
# [INFO] Falling back to OpenAI GPT-4
# [INFO] OpenAI analysis complete: severity=7

echo "✅ Dual-LLM failover works seamlessly."
```

**[Closing (30 seconds)]**
```
Summary of what we just saw:

1. ✅ Submitted a realistic security alert
2. ✅ LLM analyzed it in 3.4 seconds
3. ✅ K8s automation isolated the pod
4. ✅ Grafana dashboard updated in real-time
5. ✅ Database captured the audit trail
6. ✅ We can reverse actions anytime

This is the future of smart city security: AI-assisted, Kubernetes-native, 
and reversible. No more alert fatigue. No more slow manual triage.

Questions?
```

---

## 🎯 Slide Deck Structure

**Recommended Tool:** PowerPoint, Google Slides, or Keynote

**Design Principles:**
- ✅ One concept per slide
- ✅ Large fonts (32pt min for body, 44pt for titles)
- ✅ Minimal text (use visuals + speaker notes)
- ✅ Color scheme: Blue (main), Green (success), Red (alerts/danger)
- ✅ Include live code snippets (show actual JSON)
- ✅ Include architecture diagrams (Lucidchart, draw.io)
- ✅ Include metrics charts (bars, line graphs)

**File Organization:**
```
conference-materials/
├── slides/
│   ├── smart-city-ids-5min.pptx
│   ├── smart-city-ids-10min.pptx
│   ├── smart-city-ids-15min.pptx
│   └── images/
│       ├── architecture.png
│       ├── dashboard.png
│       └── metrics.png
├── demo/
│   ├── DEMO_SCRIPT.md (this file)
│   ├── demo-alert.json
│   └── pre-demo-checklist.sh
└── handout/
    ├── CAPSTONE_II_FINAL_REPORT.pdf
    ├── ARCHITECTURE.pdf
    └── github-qr-code.png
```

---

## 💡 Key Talking Points (Q&A)

### Q: "Why LLMs? Why not just traditional machine learning?"
**A:** 
- LLMs understand context: "root shell in container" → understands privilege escalation risk
- Traditional ML needs labeled training data (expensive, slow)
- LLMs are pre-trained on security literature, CVEs, attack patterns
- Works without retraining when new threats emerge
- Trade-off: Slower than ML (3-5s vs. 50ms) but more accurate and adaptable

### Q: "What if the LLM gives bad analysis?"
**A:**
- We have human-in-the-loop: analysts review Grafana dashboard in real-time
- Dry-run mode lets teams test before production
- Approval-required mode stops auto-actions until human agrees
- Fallback: if xAI fails, OpenAI is always there (72 successful failovers)
- Audit trail: every decision logged to PostgreSQL

### Q: "How does this scale to 100 cities?"
**A:**
- Single-node K3s today (one city)
- Multi-node K8s in future (one city, HA)
- Federation: each city has independent IDS, share threat intelligence
- Cost: ~$100/month LLM API + $50/month infrastructure = affordable for cities
- Roadmap: Local LLM option (Claude, Llama) to reduce API costs

### Q: "What about false positives?"
**A:**
- Falco/Suricata have own rule tuning (our job is NOT to reduce their false positives)
- Our job: correctly classify what they send us
- We measure: "Given an alert, do we classify severity correctly?"
- 98.3% success rate in Capstone II testing
- Some false positives are OK—pod isolation is reversible; IP isolation is not

### Q: "How do you prevent accidentally isolating critical services?"
**A:**
- Protected services list (healthcare-api, ids-api, postgres)
- These cannot be auto-isolated regardless of severity
- Automation modes: LIVE vs DRY-RUN vs APPROVAL-REQUIRED
- All actions reversible
- RBAC: service account can only affect smart-city namespace

### Q: "What's the latency end-to-end?"
**A:**
- Alert generation → Falco detection: 50-200ms (not our code)
- Falco → Forwarder → IDS API: 10-50ms (network + Python)
- IDS API → LLM → Parse response: 3.5s average (xAI Grok-4)
- LLM → K8s API action: 100-500ms
- **Total: ~4 seconds** (good for security, acceptable for K8s operations)

### Q: "Can you run this in a city without internet?"
**A:**
- Current: Requires internet for xAI/OpenAI API calls
- Future: Local LLM option (run Llama 2 on GPU)
- Fallback: OpenAI works with cached API key (1 month offline)
- Detectors (Falco/Suricata): work fully offline

### Q: "How much does it cost?"
**A:**
- xAI Grok-4: ~$5 per 1M tokens (150 tokens/alert = ~$0.75 per alert)
- OpenAI GPT-4: ~$30 per 1M tokens (~$4.50 per alert)
- Alert volume: ~100 alerts/day = $50-75/month on LLM
- K3s + PostgreSQL: ~$50-100/month on cloud, free on-premises
- **Total: ~$100-150/month for a city**

### Q: "How do you handle cloud provider differences (AWS vs Azure vs GCP)?"
**A:**
- K3s is cloud-agnostic (uses standard Kubernetes)
- Tested on bare metal (our current setup)
- Should work on AWS, Azure, GCP K8s clusters
- Future: Helm charts for easy deployment

### Q: "What about real-time sensor data (MQTT)?"
**A:**
- MQTT broker deployed in our system
- IoT devices publish to MQTT
- Could integrate IoT events as alerts (future work)
- Currently: focused on Falco/Suricata

### Q: "How do you prevent data leaks in LLM analysis?"
**A:**
- We strip PII before sending to LLM (SSN, credit card, patient names)
- Alerts contain IPs, ports, process names (generally OK to send)
- All LLM API calls go over HTTPS
- Sensitive data (PostgreSQL) never leaves cluster

### Q: "What if the K8s cluster itself is compromised?"
**A:**
- Good question! If K8s API is compromised, we have bigger problems
- Mitigation: RBAC restricts service account to specific actions
- Defense-in-depth: Falco can detect K8s API anomalies too
- Future: Immutable audit logs to external cluster

---

## ✅ Demo Environment Checklist

**48 Hours Before Conference:**

```bash
# 1. Verify all pods running
kubectl get pods -A | grep -E "(smart-city|monitoring|falco)"

# 2. Test IDS API
curl http://NODE_IP:30800/health

# 3. Test Grafana
open http://NODE_IP:30300
# Login with admin/admin
# Navigate to "Smart City IDS" dashboard
# Verify metrics are displayed

# 4. Test PostgreSQL
kubectl exec -n smart-city postgres -- \
  psql -U idsuser -d idsdb -c "SELECT COUNT(*) FROM alerts;"

# 5. Test K8s automation (dry-run mode)
# Edit main.py: set AUTOMATION_MODE = "dry-run"
# Submit test alert, verify no actions taken

# 6. Prepare demo data
# Clear or reset alert count (optional)
kubectl exec -n smart-city postgres -- \
  psql -U idsuser -d idsdb -c "TRUNCATE TABLE alerts;"

# 7. Test connectivity
# Verify NODE_IP is accessible from presentation room
ping NODE_IP
curl http://NODE_IP:30800/health
```

**Day of Conference (1 hour before):**

```bash
# 1. Restart all services (fresh state)
kubectl rollout restart deployment/ids-api -n smart-city
kubectl rollout restart deployment/traffic-camera -n smart-city

# 2. Verify API is responding quickly
time curl http://NODE_IP:30800/health

# 3. Clear any test alerts from database
kubectl exec -n smart-city postgres -- \
  psql -U idsuser -d idsdb -c "DELETE FROM alerts WHERE timestamp < NOW() - INTERVAL '1 hour';"

# 4. Check disk space
df -h | grep -E "(root|smart-city)"

# 5. Run smoke test
./scripts/check-setup.sh

# 6. Prepare second monitor for logging
# In separate terminal:
kubectl logs -n smart-city -l app=ids-api -f

# 7. Have backup plan
# If K3s goes down:
# - Have pre-recorded demo video (backup)
# - Have pre-generated JSON responses (manual demo)
# - Have screenshots of Grafana (if Live demo fails)
```

**During Conference:**

```bash
# Keep these terminals open:
1. kubectl get pods -n smart-city -w      (watch pod status)
2. kubectl logs -n smart-city -l app=ids-api -f    (watch logs)
3. curl http://NODE_IP:30800/health every 30s     (check API)

# If API becomes unresponsive:
kubectl logs -n smart-city -l app=ids-api --tail=50
# Look for: OOM, CrashLoopBackOff, LLM API errors

# If LLM API key is invalid:
kubectl edit secret ids-api-secrets -n smart-city
# Update XAI_API_KEY or OPENAI_API_KEY
kubectl rollout restart deployment/ids-api -n smart-city
```

---

## 📸 Screenshots for Slides

**Recommended screenshots to capture:**

1. **Architecture Diagram** — lucidchart rendering of system
2. **Grafana Dashboard** — showing metrics, alerts, pod status
3. **API Swagger Docs** — live /docs endpoint
4. **JSON Alert Example** — beautified alert JSON
5. **JSON LLM Response** — formatted analysis response
6. **NetworkPolicy Creation** — kubectl output showing policy
7. **K8s Pod Status** — showing isolated pod in red
8. **PostgreSQL Alert Log** — showing audit trail
9. **Terminal Demo** — showing curl commands and responses

**Tools:**
- Screenshot: `gnome-screenshot` or macOS `Cmd+Shift+4`
- Video: `ffmpeg` or `OBS` (for recording live demo as backup)
- Diagram: Lucidchart, draw.io, or Figma

---

## 🎓 Academic Framing

**For academic conferences, emphasize:**

1. **Research Contribution**
   - Novel combination of dual-IDS + LLM
   - Quantified failover reliability (100%)
   - Validated on real Kubernetes platform

2. **Methodology**
   - Capstone I: Design & architecture
   - Capstone II: Implementation & validation
   - Measured with actual metrics (not simulated)

3. **Validation**
   - 157 alerts processed, 98.3% success
   - 72 failover events tested
   - Edge-deployable (K3s, not full K8s)

4. **Openness**
   - Open-source on GitHub
   - Full documentation + code
   - Reproducible (one-click deploy.sh)

---

## 🏆 Tips for Conference Success

1. **Practice the demo 10+ times** — Timing varies, LLM latency fluctuates
2. **Have a backup demo video** — If network fails during live demo
3. **Dress for the audience** — Academic: formal; Industry: business casual
4. **Know the limitations** — Be honest about what works and what doesn't
5. **Engage the audience** — Ask "who here deals with alert fatigue?"
6. **Show the code** — Engineers appreciate seeing actual implementation
7. **Quantify everything** — "3.5 seconds" beats "fast"
8. **Be humble about LLMs** — They're powerful but not perfect

---

**Last Updated:** February 3, 2026  
**Version:** 2.0 (Conference-Ready)  
**Author:** Ali Suhail, Khaled Rahman, Abdallahi Mahmoud

