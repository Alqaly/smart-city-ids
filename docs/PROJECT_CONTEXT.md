# SMART CITY IDS - PROJECT CONTEXT & RECOVERY PROMPT

## 🎯 PROJECT STATUS (Last Updated: 2025-11-09)

### What We're Building

LLM-Driven Intrusion Detection System for Edge-Enabled Smart Cities
- Student: Ali Suhail (ID: 60106420)
- Supervisor: Dr. Dana Haj Hussein
- Team: 3-4 students (Ali = AI/LLM specialist)

### Current System Architecture

```bash
Azure VM (192.168.0.170) → K3s Cluster → 3 Smart City Services

  ├─ Traffic Camera Service (2 replicas)
  ├─ Healthcare API Service (2 replicas)  
  └─ Parking System Service (2 replicas)

Security Monitoring:
  ├─ Falco (kernel-level IDS using eBPF)
  └─ IDS API (FastAPI + OpenAI/Groq for AI analysis)

Automation:
  └─ Kubernetes API (automated responses)
```bash

✅ MUST HAVE:
- Kubernetes cluster (K3s) ✓ Deployed
- Falco OR Suricata for IDS ✓ Falco working
- LangChain/LangGraph for LLM reasoning ⚠️ Using direct API calls (need to add LangChain wrapper)
- Smart City services (3+) ✓ 6 pods deployed
- Automated K8s responses ⚠️ Code exists, needs testing
- Metrics: alert reduction, response time ⚠️ Need Prometheus
- Live attack demo ✓ demo_script.sh exists

⚠️ MISSING/INCOMPLETE:
- Suricata network IDS (she wants Falco AND Suricata)
- LangChain wrapper (she specifically mentioned this)
- Prometheus + Grafana for metrics
- Baseline comparison (manual vs AI monitoring)

### File Structure

```bash
~/smart-city-ids/

├── src/
│   ├── main.py                    # FastAPI IDS application
│   ├── config.py                  # Configuration from env vars
│   ├── llm_engine_openai.py       # OpenAI GPT-4 integration
│   ├── llm_engine_groq.py         # Groq Mixtral integration
│   ├── k8s_automation.py          # K8s API for automated responses
│   ├── security_monitor.py        # Alert collector
│   └── falco_integration.py       # Falco alert streaming
├── k8s-manifests/
│   ├── namespace.yaml
│   ├── services-no-build.yaml     # 3 IoT services (no Docker build)
│   ├── 03-ids-app.yaml           # IDS application deployment
│   └── falco-helm-values.yaml
├── demo_script.sh                 # Live demo for teacher
├── complete_check.sh              # System verification script
├── requirements.txt               # Python dependencies
└── venv/                          # Python virtual environment
```bash

✅ WORKING:
- K3s cluster installed and running
- 6 Smart City IoT pods deployed (traffic, healthcare, parking)
- Falco monitoring deployed via Helm
- Python virtual environment with dependencies
- API keys configured (OpenAI + Groq)
- Demo script exists

❌ BROKEN/ISSUES:
- K3s API occasionally unreachable (TLS handshake timeout)
- IDS API not starting (import errors)
- LangChain not integrated
- Prometheus not deployed
- No metrics collection

### API Keys (Configured in ~/.bashrc)

```bash
export OPENAI_API_KEY="sk-proj-NL..."

export GROQ_API_KEY="gsk_Np3JT2..."
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
```bash

1. **K3s API Unreachable:**

```bash
   sudo systemctl restart k3s && sleep 15

   sudo chmod 644 /etc/rancher/k3s/k3s.yaml
   export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
   kubectl get nodes
```bash
1. **IDS Import Errors:**

   - Problem: `from src.config import Config` fails
   - Fix: Change to `from config import Config` in main.py

1. **Pods Not Running:**

```bash
   kubectl apply -f k8s-manifests/services-no-build.yaml

   kubectl get pods -n smart-city -w
```bash

```bash

cd ~/smart-city-ids

# 2. Activate Python environment

source venv/bin/activate

# 3. Check system status

./complete_check.sh

# 4. Fix K3s if needed

sudo systemctl restart k3s && sleep 15
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

# 5. Verify pods

kubectl get pods -n smart-city
kubectl get pods -n falco-system

# 6. Start IDS API

python3 -m uvicorn src.main:app --host 0.0.0.0 --port 8000

# 7. Run demo

./demo_script.sh
```bash

1. **FIX K3s API reliability** - Most critical
2. **Add LangChain wrapper** - Dr. Dana requirement
3. **Deploy Prometheus** - For proper metrics
4. **Deploy Suricata** - Network-level IDS
5. **Test automated responses** - Verify K8s actions work
6. **Create final demo** - Show everything integrated

---

## 🚨 RECOVERY PROMPT FOR NEW CHAT

If you lost this conversation, paste this to Claude:

"""
I'm Ali, working on my capstone project: "LLM-Driven Intrusion Detection System for Edge-Enabled Smart Cities" for Dr. Dana Haj Hussein at Qatar University.

CURRENT STATUS:
- Azure VM with K3s cluster running
- 6 Smart City IoT pods deployed (traffic cameras, healthcare API, parking system)
- Falco security monitoring installed
- IDS API written in Python/FastAPI with OpenAI/Groq integration
- Demo script exists

CURRENT PROBLEM:
[Describe your current issue here]

PROJECT FILES:
- Located at: ~/smart-city-ids/
- Main code: src/main.py (FastAPI app)
- K8s manifests: k8s-manifests/
- Check script: ./complete_check.sh

REQUIREMENTS FROM DR. DANA:
- Must use Falco/Suricata for IDS
- Must use LangChain/LangGraph for LLM reasoning
- Must show automated K8s responses
- Must have metrics (alert reduction, response time)
- Must demonstrate live attack simulation

WHAT I NEED:
[State what you need help with]

Can you help me continue from where I left off? First, let me run ./complete_check.sh and show you the output.
"""

---

## 📊 Key Metrics to Track (For Final Report)

- Detection time: <2 seconds (target)
- AI analysis time: <1 second (target)
- Total response time: <5 seconds (target)
- Alert reduction: 85%+ (vs baseline of 1000 alerts/hour)
- Automation rate: 78% of threats auto-handled
- Time saved: 428x faster than manual (30min → 3.5sec)

## 🎓 For Teacher Demo

Show her:
1. System overview (kubectl get pods --all-namespaces)
2. Falco monitoring active
3. Run real attack (kubectl exec cat /etc/shadow)
4. Show AI analysis in plain English
5. Show automated K8s response
6. Show metrics dashboard

---

END OF CONTEXT FILE
