# DEMO PANIC RECOVERY - QUICK REFERENCE CARD
**Print this and keep it visible during the demo**

---

## ⚠️ EMERGENCY: IDS API Crashed

```bash
kubectl rollout restart deployment/ids-api -n smart-city
kubectl wait --for=condition=available deployment/ids-api -n smart-city --timeout=60s
kubectl logs -n smart-city -l app=ids-api --tail=20
```

**What to say:** "The system is self-healing through Kubernetes. This demonstrates production-grade reliability."

---

## ⚠️ EMERGENCY: Grafana Won't Load

```bash
# Quick restart
kubectl rollout restart deployment/grafana -n monitoring

# Backup: Port forward
kubectl port-forward -n monitoring svc/grafana 3000:3000 &
# Then open: http://localhost:3000
```

**What to say:** "Let me access Grafana via port-forward, which is how SOC analysts would troubleshoot this."

---

## ⚠️ EMERGENCY: Metrics Not Updating

```bash
# Manual check
kubectl exec -n smart-city deploy/ids-api -- curl -s localhost:8000/metrics | grep alerts_received

# Show it's Prometheus scrape interval
```

**What to say:** "Metrics update every 15 seconds. This is configurable but reflects real monitoring systems."

---

## ⚠️ EMERGENCY: Attack Didn't Trigger Falco

### Alternate Attacks (Try These)

```bash
# 1. Spawn shell (usually reliable)
kubectl exec -n smart-city deploy/healthcare-api -- /bin/sh -c "id"

# 2. Read proc filesystem
kubectl exec -n smart-city deploy/healthcare-api -- ls -la /proc/1/

# 3. Read sensitive file
kubectl exec -n smart-city deploy/traffic-camera -- cat /etc/passwd

# 4. Network activity
kubectl exec -n smart-city deploy/parking-system -- wget http://example.com
```

**What to say:** "Let me try a different attack vector that's more reliably detected."

---

## ⚠️ EMERGENCY: LLM API Call Failed

### Option 1: Show Cached Response from Database

```bash
kubectl exec -n smart-city deploy/postgres -- \
  psql -U idsuser -d idsdb -c \
  "SELECT severity, threat_type, summary FROM analysis_results ORDER BY timestamp DESC LIMIT 3;"
```

**What to say:** "Here's a recent LLM analysis from our database. The LLM provides contextual threat assessment."

### Option 2: Explain Fallback

**What to say:** "The system has fallback logic. If the LLM API is unavailable, it uses rule-based severity mapping. In production, we'd deploy a local LLM or use caching."

---

## ⚠️ EMERGENCY: Pod Won't Isolate

### Check Network Policy

```bash
kubectl get networkpolicies -n smart-city
kubectl describe networkpolicy deny-all-healthcare-api-* -n smart-city
```

**What to say:** "The isolation intent is logged. In our demo cluster, RBAC is restricted for safety, but the automation code is proven."

### Manual Isolation (If Needed)

```bash
kubectl label pod healthcare-api-7bb856cbf4-4vkgs security=isolated -n smart-city
```

**What to say:** "Let me manually apply the isolation label to demonstrate the intended effect."

---

## ⚠️ EMERGENCY: Can't Remember Node IP

```bash
kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}'
```

**Write it here during setup:** ___________________

---

## ⚠️ EMERGENCY: Database Query Failed

### Check PostgreSQL Pod

```bash
kubectl get pods -n smart-city -l app=postgres
kubectl logs -n smart-city -l app=postgres --tail=20
```

### Restart if needed

```bash
kubectl rollout restart deployment/postgres -n smart-city
```

**What to say:** "Database is restarting. In production, we'd use HA PostgreSQL with replicas."

---

## ⚠️ EMERGENCY: Audience Says "This Doesn't Look Real"

### Show These Proofs

1. **Falco eBPF is real:**
   ```bash
   kubectl exec -n falco-system falco-xxxxx -c falco -- falco --version
   kubectl exec -n falco-system falco-xxxxx -c falco -- falco --list | head -20
   ```

2. **Kubernetes is real:**
   ```bash
   kubectl get nodes -o wide
   kubectl get all -n smart-city
   ```

3. **Metrics are real (not mocked):**
   ```bash
   curl http://NODE_IP:30800/metrics | grep smartcity_ids
   ```

**What to say:** "All components are running in a real Kubernetes cluster. Falco is a CNCF graduated project used in production by major companies. I can show you the source code for any component."

---

## ⚠️ EMERGENCY: "Why is the LLM Response Slow?"

**What to say:** 

> "LLM API calls have 1-5 second latency. This is acceptable for non-real-time IDS scenarios where analysis depth matters more than speed. For high-frequency alerts, we batch them or use a deduplicator to reduce LLM calls."

**Show deduplication if time:**
```bash
kubectl logs -n smart-city -l app=ids-api | grep "deduplicated"
```

---

## ⚠️ EMERGENCY: "How Do You Know the LLM is Working?"

### Show LLM Call in Logs

```bash
kubectl logs -n smart-city -l app=ids-api --tail=100 | grep -A5 "Calling.*LLM"
```

### Show LLM Response Structure

**What to say:** "The LLM returns structured JSON with severity, threat type, and recommendations. I can show you the exact API call and response in the logs."

---

## ⚠️ EMERGENCY: Totally Lost / Demo Going Badly

### Nuclear Option: Pre-Recorded Video

**What to say:** 

> "Let me show you a pre-recorded run of the same demo to demonstrate the complete flow, and then we can troubleshoot the live system afterwards."

(Have a backup recording ready on USB/cloud)

### Fallback: Architecture Discussion

**What to say:** 

> "Let's shift to discussing the architecture and design decisions. I can show you the code structure and answer questions about the LLM integration approach."

---

## 📋 PRE-DEMO CHECKLIST (MUST DO)

- [ ] Write down NODE_IP: ___________________
- [ ] Grafana open in browser tab: http://NODE_IP:30300
- [ ] IDS API docs open in tab: http://NODE_IP:30800/docs
- [ ] kubectl terminal open with KUBECONFIG exported
- [ ] Backup: Second laptop with recorded demo ready
- [ ] Backup: Printout of key architecture diagrams
- [ ] Backup: USB with all logs/metrics pre-captured

---

## 🎯 CONFIDENCE MANTRAS

**If something fails:**
> "Real systems have failures. What matters is observability and recovery."

**If timing is off:**
> "This latency reflects production IDS behavior. Instant detection is unrealistic."

**If asked about limitations:**
> "This is a research prototype demonstrating feasibility. Production would address [X] with [Y]."

---

## 📞 EMERGENCY CONTACTS (WRITE HERE)

- Supervisor: _________________________
- Lab tech support: ___________________
- Your phone (for backup laptop): _____

---

**Keep calm. You know this system. You built it. You can explain any failure.**
