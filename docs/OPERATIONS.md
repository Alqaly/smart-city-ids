# Smart City IDS - Operations Guide

Day-to-day operations, monitoring, and demo procedures.

---

## Table of Contents

1. [Daily Operations](#daily-operations)
2. [Monitoring](#monitoring)
3. [Demo Procedures](#demo-procedures)
4. [Attack Simulation](#attack-simulation)
5. [Incident Response](#incident-response)
6. [Maintenance](#maintenance)

---

## Daily Operations

### Check System Health

```bash
# Quick status check
kubectl get pods -A | grep -E "(smart-city|monitoring)"

# Detailed status
kubectl get pods -n smart-city -o wide
kubectl get pods -n monitoring -o wide

# Check node resources
kubectl top nodes
kubectl top pods -n smart-city
```

### View Logs

```bash
# IDS API logs (follow mode)
kubectl logs -n smart-city -l app=ids-api -f

# Last 100 lines
kubectl logs -n smart-city -l app=ids-api --tail=100

# All containers in a pod
kubectl logs -n smart-city <pod-name> --all-containers

# Falco logs
kubectl logs -n falco-system -l app=falco --tail=50
```

### Common kubectl Commands

```bash
# Get node IP for external access
NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')
echo "Node IP: $NODE_IP"

# Port forward for local access
kubectl port-forward -n smart-city svc/ids-api 8000:8000

# Exec into pod for debugging
kubectl exec -it -n smart-city <pod-name> -- /bin/sh

# Restart deployment
kubectl rollout restart deployment/ids-api -n smart-city
```

---

## Monitoring

### Access Dashboards

| Dashboard | URL | Credentials |
|-----------|-----|-------------|
| Grafana | http://NODE_IP:30300 | admin / admin |
| Prometheus | http://NODE_IP:31701 | - |
| IDS API Docs | http://NODE_IP:30800/docs | - |

### Key Metrics to Watch

In Grafana, monitor these panels:

| Metric | Warning Threshold | Action |
|--------|-------------------|--------|
| `alerts_total` rate | >50/min | Check for attack or misconfiguration |
| `llm_response_time` | >5s | Check LLM API status |
| `severity_distribution` | Many 8+ | Review automated actions |
| Pod CPU/Memory | >80% | Consider scaling |

### Prometheus Queries

```promql
# Total alerts in last hour
increase(alerts_total[1h])

# Alerts by severity
sum by (severity) (alerts_total)

# LLM response time (95th percentile)
histogram_quantile(0.95, rate(llm_response_time_bucket[5m]))

# Actions taken
sum by (action) (actions_total)
```

---

## Demo Procedures

### Pre-Demo Checklist

- [ ] All pods running: `kubectl get pods -n smart-city`
- [ ] Grafana accessible: http://NODE_IP:30300
- [ ] IDS API responding: `curl http://NODE_IP:30800/health`
- [ ] Fresh logs: `kubectl logs -n smart-city -l app=ids-api --tail=10`

### Demo Script: Full System Walkthrough

**1. Show Architecture (2 min)**
```bash
# Show running pods
kubectl get pods -n smart-city -o wide
```

**2. Explain Smart City Services (2 min)**
- Open traffic camera: http://NODE_IP:30080 (if NodePort configured)
- Explain intentional vulnerabilities

**3. Show IDS API (2 min)**
```bash
# API documentation
open http://NODE_IP:30800/docs

# Health endpoint
curl http://NODE_IP:30800/health | jq .
```

**4. Demonstrate Attack Detection (5 min)**
```bash
# Run DDoS simulation
python attack-simulator/ddos_simulator.py http://NODE_IP:30800 5 10

# Watch logs in real-time (in another terminal)
kubectl logs -n smart-city -l app=ids-api -f
```

**5. Show LLM Analysis (3 min)**
- Point to Grafana dashboard
- Explain severity scoring
- Show automated action triggers

**6. Demonstrate Automated Response (3 min)**
```bash
# Generate high-severity alert
curl -X POST http://NODE_IP:30800/api/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "source": "demo",
    "rule": "Critical Security Event",
    "priority": "Critical",
    "output": "Suspicious root shell spawned in container",
    "output_fields": {
      "container.name": "traffic-camera",
      "proc.cmdline": "/bin/bash"
    }
  }'

# Check if network policy was created
kubectl get networkpolicies -n smart-city
```

---

## Attack Simulation

### Available Attack Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| `ddos_simulator.py` | DDoS attack | `python attack-simulator/ddos_simulator.py <url> <threads> <duration>` |
| `data_exfiltration.py` | Data theft | `python attack-simulator/data_exfiltration.py` |
| `privilege_escalation.py` | Privilege escalation | `python attack-simulator/privilege_escalation.py` |

### Basic Attack Demo

```bash
# DDoS (5 threads, 10 seconds)
python attack-simulator/ddos_simulator.py http://NODE_IP:30800 5 10

# Privilege escalation simulation
python attack-simulator/privilege_escalation.py

# Data exfiltration simulation
python attack-simulator/data_exfiltration.py
```

### Advanced Attack Scenarios

```bash
# Full smart city attack simulation
python attack-simulator/phase4-smart-city-attacks.py

# Generate security events
./attack-simulations/generate-security-events.sh

# Network-based attacks
./attack-simulations/generate-network-attacks.sh
```

### Manual Alert Injection

```bash
# Inject test alert directly to API
curl -X POST http://NODE_IP:30800/api/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "source": "manual-test",
    "rule": "Test Alert",
    "priority": "Warning",
    "output": "This is a test alert for demo purposes",
    "output_fields": {
      "container.name": "test-container"
    }
  }'
```

---

## Incident Response

### When High Severity Alert Occurs

1. **Check Alert Details**
   ```bash
   # View recent alerts
   curl http://NODE_IP:30800/api/alerts?limit=10 | jq .
   
   # Check specific alert
   curl http://NODE_IP:30800/api/alerts/{alert_id} | jq .
   ```

2. **Verify Automated Actions**
   ```bash
   # Check network policies (isolation)
   kubectl get networkpolicies -n smart-city
   
   # Check deployment replicas (scaling)
   kubectl get deployments -n smart-city
   ```

3. **Investigate Affected Pod**
   ```bash
   # Get pod details
   kubectl describe pod <affected-pod> -n smart-city
   
   # Check pod logs
   kubectl logs -n smart-city <affected-pod> --previous
   ```

4. **Manual Intervention (if needed)**
   ```bash
   # Manually isolate pod
   kubectl label pod <pod-name> -n smart-city quarantine=true
   
   # Delete suspicious pod (will recreate)
   kubectl delete pod <pod-name> -n smart-city
   
   # Scale down to zero
   kubectl scale deployment/<deployment-name> -n smart-city --replicas=0
   ```

### Reverting Automated Actions

```bash
# Remove isolation network policy
kubectl delete networkpolicy isolate-<pod-name> -n smart-city

# Scale back to normal
kubectl scale deployment/<deployment-name> -n smart-city --replicas=1
```

---

## Maintenance

### Backup Procedures

```bash
# Backup PostgreSQL data
kubectl exec -n smart-city $(kubectl get pods -n smart-city -l app=postgres -o jsonpath='{.items[0].metadata.name}') \
  -- pg_dump -U idsuser idsdb > backup-$(date +%Y%m%d).sql

# Backup Grafana dashboards
kubectl exec -n monitoring $(kubectl get pods -n monitoring -l app=grafana -o jsonpath='{.items[0].metadata.name}') \
  -- grafana-cli admin export > grafana-backup.json
```

### Update Procedures

```bash
# Update IDS API code
# 1. Edit services/ids-api/src/*.py

# 2. Rebuild image
./scripts/build-images.sh

# 3. Restart deployment
kubectl rollout restart deployment/ids-api -n smart-city

# 4. Watch rollout
kubectl rollout status deployment/ids-api -n smart-city
```

### Cleanup

```bash
# Delete all in namespace (careful!)
kubectl delete all --all -n smart-city

# Full cleanup script
./scripts/cleanup.sh

# Remove k3s completely
/usr/local/bin/k3s-uninstall.sh
```

### Log Rotation

Kubernetes handles container log rotation. For persistent logs:

```bash
# Export logs to file
kubectl logs -n smart-city -l app=ids-api --since=24h > ids-api-logs-$(date +%Y%m%d).txt

# Clean up old logs
find /var/log/pods -name "*.log" -mtime +7 -delete
```

---

## Troubleshooting Quick Reference

| Issue | Command | Solution |
|-------|---------|----------|
| Pod not starting | `kubectl describe pod <name> -n smart-city` | Check events for errors |
| API key error | `kubectl get secret ids-api-secrets -n smart-city` | Recreate secret |
| Database connection | `kubectl logs -n smart-city -l app=postgres` | Check postgres pod |
| LLM timeout | Check API status | Consider fallback provider |
| High CPU | `kubectl top pods -n smart-city` | Scale or optimize |

---

*For setup instructions, see [SETUP.md](SETUP.md)*  
*For architecture details, see [ARCHITECTURE.md](ARCHITECTURE.md)*
