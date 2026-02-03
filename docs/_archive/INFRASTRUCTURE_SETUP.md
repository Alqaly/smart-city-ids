# Infrastructure Setup Guide

Complete guide to database, monitoring, and persistent storage configuration.

---

## Overview

The Smart City IDS infrastructure consists of three layers:

```
┌─────────────────────────────────────────────────────────────┐
│  DATA LAYER                                                 │
│  ├─ PostgreSQL Database (persistent alert storage)          │
│  ├─ In-memory fallback (if DB unavailable)                 │
│  └─ Configured via: infrastructure/database/               │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  ANALYSIS LAYER                                             │
│  ├─ IDS API (processes alerts)                             │
│  ├─ Exposes /metrics endpoint (Prometheus metrics)          │
│  └─ Stores results in PostgreSQL                           │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  MONITORING LAYER                                           │
│  ├─ Prometheus (scrapes metrics from IDS API)              │
│  ├─ Grafana (visualizes metrics in dashboards)             │
│  └─ ServiceMonitor (tells Prometheus what to scrape)       │
└─────────────────────────────────────────────────────────────┘
```

---

## Database Layer

### PostgreSQL Deployment

**Location**: `k8s-manifests/postgres-deployment.yaml`

**What it includes**:
- PostgreSQL 15 container
- Database initialization with migrations
- Connection pooling
- Health checks (liveness + readiness probes)

**Credentials**:
- Username: `postgres`
- Password: `idspassword` (from secret)
- Database: `smartcity_ids`

**Tables created by migrations**:
- `users` - System users
- `api_keys` - API authentication
- `alerts` - Security alerts (main data table)
- `analysis_results` - LLM analysis results
- `automation_actions` - K8s actions taken
- `audit_logs` - Change audit trail

### How Data Flows

```
1. Falco detects syscall anomaly
              ↓
2. Falco forwarder sends to IDS API (/api/alerts)
              ↓
3. IDS API receives alert
              ↓
4. IDS API calls LLM (xAI or OpenAI)
              ↓
5. LLM returns analysis (severity, threat_type, etc.)
              ↓
6. IDS API saves to PostgreSQL via database.py
              ↓
7. IDS API exposes metrics (/metrics)
              ↓
8. Prometheus scrapes /metrics every 30s
              ↓
9. Grafana queries Prometheus and updates dashboards
```

### Database Initialization

Migrations run automatically when PostgreSQL pod starts:

```bash
# PostgreSQL container runs all .sql files in /docker-entrypoint-initdb.d
# These are mounted from postgres-migrations ConfigMap

# To verify tables were created:
kubectl exec -it <postgres-pod> -n smart-city -- \
  psql -U postgres -d smartcity_ids -c "\dt"

# Output should show:
# alerts | table | postgres
# analysis_results | table | postgres
# automation_actions | table | postgres
# etc.
```

### Database Connection

**From IDS API**:
```python
# services/ids-api/src/database.py
DB_HOST = os.environ.get("DB_HOST", "postgres")  # Service DNS name
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "smartcity_ids")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "idspassword")

# Connects to: postgres.smart-city.svc.cluster.local:5432
```

### Fallback Behavior

If PostgreSQL is unavailable:
```python
# From database.py: _connect()
if PSYCOPG2_AVAILABLE and connection succeeds:
    use PostgreSQL (persistent)
else:
    use_memory = True  # In-memory storage (data lost on restart)
```

**⚠️ WARNING**: Data will be lost when pod restarts if using in-memory fallback. For production, ensure PostgreSQL is always running.

---

## Monitoring Layer

### Prometheus Configuration

**What Prometheus does**:
1. Scrapes metrics from IDS API every 30 seconds
2. Stores time-series data (memory-based, temporary)
3. Evaluates alerting rules
4. Serves data to Grafana

**Scrape targets**:
- Defined by ServiceMonitor: `k8s-manifests/servicemonitor.yaml`
- Selects pods with label `app: ids-api`
- Scrapes from port `metrics` (8001)
- Path: `/metrics`

### ServiceMonitor Explanation

**Location**: `k8s-manifests/servicemonitor.yaml`

**What it does**:
```yaml
spec:
  selector:
    matchLabels:
      app: ids-api  # Find pods with this label
  endpoints:
  - port: metrics  # Use this port
    path: /metrics # Scrape this path
    interval: 30s  # Every 30 seconds
```

**Without ServiceMonitor**:
- Prometheus won't know IDS API exists
- No metrics collected
- Grafana dashboards empty

**Verify it's working**:
```bash
# Check ServiceMonitor exists
kubectl get servicemonitor -n smart-city
# Should show: ids-api

# Check Prometheus can find IDS API
kubectl port-forward -n monitoring svc/prometheus 9090:9090 &
# Open http://localhost:9090/targets
# Should show: smart-city/ids-api (Up)

# If it says "Down", check:
# 1. IDS API pod is running
# 2. IDS API service exists and has metrics port
# 3. /metrics endpoint is accessible
```

### Grafana Configuration

**Datasource setup** (done by `scripts/load-dashboards.sh`):
```
Name: Prometheus
Type: prometheus
URL: http://prometheus.monitoring.svc.cluster.local:9090
Access: proxy
Default: yes
```

**Dashboard imports** (also done by `scripts/load-dashboards.sh`):
- grafana-dashboard-ids.json
- grafana-dashboard-production.json
- grafana-dashboard-soc-overview.json
- grafana-dashboard-llm-performance.json
- grafana-dashboard-iot-load.json

### Metrics Available

The IDS API exposes these metrics (visible in `/metrics`):

```
# Counter: Total alerts received
ids_alerts_received_total{source="falco"} 42

# Counter: Alerts by severity
ids_alerts_severity_total{severity="8"} 15

# Gauge: Current severity distribution
ids_alerts_in_queue 5

# Histogram: LLM response latency
ids_llm_latency_seconds_bucket{le="0.5"} 12
ids_llm_latency_seconds_bucket{le="1.0"} 18

# Gauge: Circuit breaker state
ids_circuit_breaker_state{engine="xai-grok-4"} 0  # 0=closed, 1=half_open, 2=open
```

---

## Common Issues & Fixes

### Issue 1: Grafana Shows No Data

**Symptoms**:
- Dashboards load but graphs are empty
- "No data" message in dashboard panels

**Causes**:
1. ❌ Prometheus not scraping IDS API
2. ❌ IDS API pod not running
3. ❌ /metrics endpoint not accessible
4. ❌ ServiceMonitor not deployed

**Fix**:
```bash
# Step 1: Check IDS API is running
kubectl get pods -n smart-city -l app=ids-api

# Step 2: Check /metrics is accessible
kubectl port-forward -n smart-city svc/ids-api 8001:8001 &
curl http://localhost:8001/metrics | head

# Step 3: Check ServiceMonitor exists
kubectl get servicemonitor -n smart-city

# Step 4: Check Prometheus can reach IDS API
kubectl port-forward -n monitoring svc/prometheus 9090:9090 &
# Open http://localhost:9090/targets
# Should show ids-api endpoint as "Up"

# If Down, check IDS API service:
kubectl get svc -n smart-city ids-api -o yaml
# Verify it has metrics port defined
```

### Issue 2: PostgreSQL Not Persisting Data

**Symptoms**:
- Alerts appear but disappear after pod restart
- Database shows "using in-memory storage" in logs

**Causes**:
1. ❌ PostgreSQL pod not running
2. ❌ IDS API can't connect to postgres
3. ❌ Using emptyDir volume (data lost on restart)

**Fix**:
```bash
# Step 1: Check postgres is running
kubectl get pods -n smart-city -l app=postgres

# Step 2: Check postgres is ready
kubectl logs -n smart-city -l app=postgres | tail -20
# Should show: "PostgreSQL Database directory appears to contain a database"

# Step 3: Verify tables exist
kubectl exec -it <postgres-pod> -n smart-city -- \
  psql -U postgres -d smartcity_ids -c "\dt"

# Step 4: Check IDS API connection logs
kubectl logs -n smart-city -l app=ids-api | grep "Database\|PostgreSQL"
# Should show: "Connected to PostgreSQL at postgres:5432/smartcity_ids"

# If shows "using in-memory storage":
# - Check postgres service DNS: ping postgres.smart-city.svc.cluster.local
# - Check DB_HOST env in IDS API pod
# - Check credentials match
```

### Issue 3: Database Migrations Didn't Run

**Symptoms**:
- PostgreSQL running but tables don't exist
- Error: "relation 'alerts' does not exist"

**Causes**:
1. ❌ postgres-migrations ConfigMap not created
2. ❌ Migrations not mounted in pod
3. ❌ Database already existed (migrations only run on init)

**Fix**:
```bash
# Check migrations ConfigMap exists
kubectl get configmap postgres-migrations -n smart-city

# Check it has the SQL file
kubectl get configmap postgres-migrations -n smart-city -o jsonpath='{.data}'

# If missing, create it:
kubectl create configmap postgres-migrations \
  --from-file=infrastructure/database/migrations/ \
  -n smart-city

# To re-run migrations (destructive - deletes database):
kubectl delete pod -l app=postgres -n smart-city
# Pod restarts and runs migrations again

# Better: Drop and recreate specific table:
kubectl exec -it <postgres-pod> -n smart-city -- \
  psql -U postgres -d smartcity_ids -c "DROP TABLE IF EXISTS alerts;"
# Then re-apply migration SQL
```

### Issue 4: Prometheus Discarding Data

**Symptoms**:
- Prometheus runs but metrics disappear after 24-48 hours
- Dashboard gaps in data

**Cause**:
- Prometheus retention is too short (default 15 days, but could be less)
- Or Prometheus pod restarted

**Fix**:
```bash
# Check Prometheus retention
kubectl exec -it <prometheus-pod> -n monitoring -- \
  ps aux | grep prometheus | grep retention

# Check Prometheus storage location
kubectl exec -it <prometheus-pod> -n monitoring -- \
  ls -la /prometheus/

# Increase retention in deployment (see k8s-manifests/prometheus-deployment.yaml):
# args:
# - '--storage.tsdb.retention.time=30d'
```

---

## Deployment Checklist

### Before Running `./deploy.sh`

- [ ] Have XAI_API_KEY or OPENAI_API_KEY set
- [ ] K3s installed and running
- [ ] Docker or nerdctl available
- [ ] At least 4GB RAM, 20GB disk free

### During Deployment

`./deploy.sh` automatically:
- [ ] Creates namespaces (smart-city, monitoring)
- [ ] Builds Docker images
- [ ] Deploys PostgreSQL
- [ ] Deploys IDS API
- [ ] Deploys Prometheus & Grafana
- [ ] Imports dashboards
- [ ] Waits for pods to be ready

### After Deployment

Verify everything is running:

```bash
# All pods ready
kubectl get pods -n smart-city
kubectl get pods -n monitoring

# PostgreSQL connected
kubectl logs -n smart-city -l app=ids-api | grep "Connected to PostgreSQL"

# Prometheus scraping
kubectl port-forward -n monitoring svc/prometheus 9090:9090 &
# Visit http://localhost:9090/targets (should show ids-api as Up)

# Grafana working
kubectl port-forward -n monitoring svc/grafana 3000:3000 &
# Visit http://localhost:3000 (admin/admin)
# Click Configuration → Data Sources → Prometheus → Test (should be green)
```

---

## Data Persistence in Production

### Current Setup (Development)

- PostgreSQL uses `emptyDir` volume
- ⚠️ Data lost when pod restarts

### For Production

Replace `emptyDir` with PersistentVolume:

```yaml
# In postgres-deployment.yaml
volumes:
- name: postgres-data
  persistentVolumeClaim:
    claimName: postgres-pvc

---
# Add this PersistentVolumeClaim:
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-pvc
  namespace: smart-city
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi  # Adjust as needed
  storageClassName: local-path  # Or your storage class
```

Similarly for Prometheus:
```yaml
# For Prometheus TSDB data
persistentVolumeClaim:
  claimName: prometheus-storage
```

---

## Monitoring the Monitoring

**Check Prometheus itself is healthy**:
```bash
kubectl logs -n monitoring -l app.kubernetes.io/name=prometheus
# Should show successful scrapes, not errors

# Check Prometheus data is being stored
kubectl exec -it <prometheus-pod> -n monitoring -- du -sh /prometheus/
# Should grow over time
```

**Check Grafana datasources**:
```bash
kubectl logs -n monitoring -l app=grafana | grep -i datasource
# Should show successful tests
```

**Check Alerts are firing** (if applicable):
```bash
# Query Prometheus for active alerts
kubectl port-forward -n monitoring svc/prometheus 9090:9090 &
# Visit http://localhost:9090/alerts
```

---

## Performance Tuning

### High Volume of Alerts

If you see:
- IDS API CPU/Memory increasing
- Prometheus unable to keep up
- Grafana slow

**Solutions**:

1. Increase resource limits in pod specs
2. Reduce Prometheus scrape interval (currently 30s, could increase to 60s)
3. Implement alert sampling/batching
4. Increase Prometheus retention time if data is being discarded

### Database Performance

If alerts are being stored slowly:

1. Check PostgreSQL logs for slow queries
2. Verify indexes are being used (check query plans)
3. Increase PostgreSQL shared_buffers for large deployments
4. Consider connection pooling (PgBouncer)

---

## Troubleshooting Commands

```bash
# Overall status
kubectl get all -n smart-city
kubectl get all -n monitoring

# Database health
kubectl logs -n smart-city -l app=postgres | tail -20
kubectl exec <postgres-pod> -n smart-city -- pg_isready

# IDS API metrics
kubectl logs -n smart-city -l app=ids-api | tail -50
kubectl exec <ids-api-pod> -n smart-city -- curl localhost:8001/metrics

# Prometheus targets
kubectl port-forward -n monitoring svc/prometheus 9090:9090 &
# Visit http://localhost:9090/targets and http://localhost:9090/graph

# Grafana datasource
kubectl port-forward -n monitoring svc/grafana 3000:3000 &
# Visit http://localhost:3000 and test datasource

# Check service connectivity
kubectl exec <ids-api-pod> -n smart-city -- \
  curl -v postgres.smart-city.svc.cluster.local:5432
```

---

## Summary

| Component | Purpose | Status | Config |
|-----------|---------|--------|--------|
| PostgreSQL | Store alerts persistently | ✅ Deployed | k8s-manifests/postgres-deployment.yaml |
| IDS API | Process alerts & expose metrics | ✅ Deployed | k8s-manifests/ids-api-FINAL.yaml |
| ServiceMonitor | Tell Prometheus to scrape IDS API | ✅ Deployed | k8s-manifests/servicemonitor.yaml |
| Prometheus | Collect metrics | ✅ Deployed | k8s-manifests/prometheus-deployment.yaml |
| Grafana | Visualize metrics | ✅ Deployed | k8s-manifests/grafana-deployment.yaml |

All components integrated and configured. Follow the troubleshooting guide if you encounter issues.
