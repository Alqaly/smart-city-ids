# Smart City Intrusion Detection System (IDS) with LLM-Based Threat Analysis

**Authors:** Smart City Security Team  
**Date:** November 3, 2025  
**Version:** 1.0  




cd ~/smart-city-ids
kubectl create configmap traffic-camera-code \
- Network policies (configured)
# Smart City IDS - Capstone II Technical Report (Aligned Scope)

**Authors:** Smart City Security Team  
**Date:** January 12, 2026  
**Version:** 2.0  
**Status:** Capstone II Prototype  

---

## Executive Summary

This document describes the design, implementation, and deployment of a prototype Intrusion Detection System (IDS) for Smart City infrastructure, strictly aligned to the Capstone II scope.

### Key Features

- LLM-based threat analysis (single pipeline, strict JSON schema validation)
- Kubernetes-native automation (Kopf operator, ThreatResponse CRD)
- Falco (runtime alerts) and Suricata (network alerts)
- FastAPI backend (async)
- PostgreSQL for alert storage, LLM results, actions, and audit trail
- Prometheus and Grafana for observability
- K3s (single edge node)

---

## System Architecture

```
Falco/Suricata Alerts → FastAPI IDS Backend → LLM Analysis → PostgreSQL Storage
         ↓
   Kopf Operator (CRD)
         ↓
   Automated K8s Actions (Pod Isolation, IP Blocking, Scaling)
         ↓
   Prometheus Metrics → Grafana Dashboards
```

## Technology Stack

| Layer | Technology | Why |
|-------|------------|-----|
| Container Orchestration | Kubernetes (K3s) | Lightweight, edge-ready |
| Security Monitoring | Falco, Suricata | Real-time detection |
| Web Framework | FastAPI | Async, modern API |
| LLM Analysis | xAI Grok-4/OpenAI API | Threat explanation |
| Database | PostgreSQL | Persistent storage |
| Operator | Kopf | K8s-native automation |
| Observability | Prometheus, Grafana | Metrics & dashboards |

---

## Implementation Steps (Capstone II Only)

1. Set up K3s (single node)
2. Deploy Falco and Suricata
3. Deploy FastAPI backend
4. Integrate LLM analysis pipeline (strict JSON schema)
5. Set up PostgreSQL for alert and audit storage
6. Implement Kopf operator and ThreatResponse CRD
7. Add Prometheus and Grafana for metrics/visualization
8. Configure RBAC, secrets, and audit logging

---

## Security & Compliance

- Input validation on all APIs
- Secrets managed via Kubernetes Secrets
- Least-privilege DB access
- Audit logging in PostgreSQL
- Proper error handling
- Kubernetes RBAC

---

## Out of Scope / Future Work

- Multi-node or multi-region Kubernetes
- Hardware sensors or IoT device integration
- Advanced user authentication (JWT, RBAC dashboards)
- CI/CD pipelines
- Event sourcing, async workers, message brokers
- Production hardening, SLA targets
- Chaos engineering, advanced test coverage targets
- User-facing dashboards

These are not part of Capstone II and may be considered for future enhancements.

---

## Conclusion

This technical report is now fully aligned with the Capstone II scope. All features and implementation steps are required, feasible, and defensible for the prototype. No forbidden or overengineered features remain.

- Host: Kali Linux WSL2
- CPU: 4 cores
- RAM: 4GB allocated

### Results

| Metric | Result |
|--------|--------|
| Attack Reception Latency | <100ms |
| LLM Analysis Time | 3-5 seconds |
| Pod Startup Time | 5-10 seconds |
| Health Check Response | <50ms |
| Database Query | <10ms |

---

## TROUBLESHOOTING

### Issue 1: "externally-managed-environment" Error

**Cause:** Kali Python system protection

### Fix

```bash
python3 -m venv venv

source venv/bin/activate
```bash

**Cause:** Port 6443 already in use

### Fix

```bash
sudo systemctl stop k3s

sleep 3
sudo systemctl start k3s
```bash

**Cause:** API usage limit reached

### Fix

1. Add payment: <https://platform.openai.com/account/billing>
2. Set usage limits
3. Use new API key

### Issue 4: Pods Not Starting

### Diagnosis

```bash
kubectl describe pod <pod-name> -n smart-city

kubectl logs <pod-name> -n smart-city
```bash

## FUTURE ENHANCEMENTS

### Short-Term (1-3 months)

1. **Actual Automated Actions**
   - Execute `kubectl scale` to isolate services
   - Use `iptables` to block IPs
   - Send email/Slack alerts

1. **Enhanced Analytics**
   - Attack pattern clustering
   - Anomaly detection
   - Predictive modeling

1. **Web Dashboard**
   - Real-time incident display
   - Attack statistics
   - Response metrics

### Medium-Term (3-6 months)

1. **Cloud Deployment**
   - AWS EKS integration
   - Azure AKS support
   - GCP Kubernetes Engine

1. **Monitoring Stack**
   - Prometheus metrics
   - Grafana dashboards
   - Alert management

1. **SIEM Integration**
   - Log forwarding
   - Threat intelligence feeds
   - Automated correlation

### Long-Term (6-12 months)

1. **Machine Learning**
   - Custom attack detection models
   - Behavioral analysis
   - Zero-day detection

1. **Enterprise Features**
   - Multi-tenancy
   - LDAP integration
   - Compliance reporting

1. **Ecosystem**
   - Industry standard APIs
   - Threat intelligence feeds
   - Playbook marketplace

---

## DEPLOYMENT CHECKLIST

Before Production:

- [ ] ChatGPT API key configured
- [ ] Cloud API credentials configured
- [ ] K3s cluster running
- [ ] All services deployed
- [ ] Health checks passing
- [ ] Attack receiver responding
- [ ] LLM analysis working
- [ ] Logging functional
- [ ] Documentation complete
- [ ] Team trained

---

## QUICK REFERENCE

### Your System Details

- IP Address: 192.168.0.170
- Port: 5555
- Location: /home/kali/smart-city-ids/
- K8s Namespace: smart-city
- K3s Version: v1.33.5+k3s1

### Key Commands

```bash

cd ~/smart-city-ids && source venv/bin/activate && python src/attack_receiver.py

# Check status

kubectl get pods -n smart-city

# View logs

kubectl logs -f deployment/traffic-camera -n smart-city

# Stop system

pkill -f "attack_receiver" && sudo systemctl stop k3s
```bash

**Document Version:** 1.0  
**Created:** November 3, 2025  
**Status:** Ready for GitHub/Academic Publication  
**Classification:** Open Source  
