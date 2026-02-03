# Infrastructure Issues Found & Fixes

## 🔴 CRITICAL ISSUES

### Issue 1: NO PostgreSQL DATABASE DEPLOYED ⚠️
- **Problem**: Database.py tries to connect to PostgreSQL but no postgres pod exists in K8s
- **Location**: `services/ids-api/src/database.py` tries to connect to `DB_HOST=postgres` on startup
- **Result**: Falls back to in-memory storage (data lost when pod restarts)
- **Impact**: NO PERSISTENT STORAGE → Grafana has NO DATA to display

### Issue 2: Grafana No Datasource Connection
- **Problem**: `load-dashboards.sh` tries to configure Prometheus but doesn't check if it succeeded
- **Location**: `scripts/load-dashboards.sh` line 80-100
- **Issue**: Script runs but may fail silently if Prometheus URL is wrong or service not ready
- **Impact**: Dashboards import but have no data

### Issue 3: Prometheus Not Scraping IDS API Metrics
- **Problem**: No ServiceMonitor configured to tell Prometheus to scrape IDS API
- **Impact**: Prometheus has 0 metrics from IDS API, dashboards show empty graphs

### Issue 4: Database Migrations Never Run
- **Problem**: `infrastructure/database/migrations/001_initial_schema.sql` exists but never executed
- **Location**: Only one migration file (001_initial_schema.sql) with full schema
- **Issue**: No init-container or post-deployment hook to run migrations
- **Impact**: Tables never created, alerts not persisted

---

## 🟠 WHAT'S NEEDED TO FIX

### Step 1: Create PostgreSQL Deployment
```yaml
# k8s-manifests/postgres-deployment.yaml
apiVersion: v1
kind: Service
metadata:
  name: postgres
  namespace: smart-city
spec:
  ports:
  - port: 5432
    targetPort: 5432
  selector:
    app: postgres

---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgres
  namespace: smart-city
spec:
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
      - name: postgres
        image: postgres:15-alpine
        ports:
        - containerPort: 5432
        env:
        - name: POSTGRES_DB
          value: smartcity_ids
        - name: POSTGRES_USER
          value: postgres
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: postgres-credentials
              key: password
        volumeMounts:
        - name: db-data
          mountPath: /var/lib/postgresql/data
        - name: migrations
          mountPath: /docker-entrypoint-initdb.d
      volumes:
      - name: db-data
        emptyDir: {}  # Use PersistentVolume in production
      - name: migrations
        configMap:
          name: postgres-migrations
```

### Step 2: Create Database Migrations ConfigMap
```bash
kubectl create configmap postgres-migrations \
  --from-file=infrastructure/database/migrations/ \
  -n smart-city
```

### Step 3: Configure Prometheus to Scrape IDS API
```yaml
# infrastructure/monitoring/servicemonitor-ids-api.yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: ids-api
  namespace: smart-city
spec:
  selector:
    matchLabels:
      app: ids-api
  endpoints:
  - port: metrics
    interval: 30s
    path: /metrics
```

### Step 4: Update IDS API Deployment
```yaml
spec:
  containers:
  - name: ids-api
    ports:
    - containerPort: 8000
      name: http
    - containerPort: 8001
      name: metrics  # Expose Prometheus metrics
    env:
    - name: DB_HOST
      value: postgres  # Connect to postgres service
    - name: DB_NAME
      value: smartcity_ids
```

### Step 5: Improve load-dashboards.sh
Add datasource validation and error checking.

---

## 📋 CURRENT STATE

```
❌ PostgreSQL: NOT RUNNING
   └─ IDS API uses in-memory storage (data lost on restart)

❌ Database Migrations: NOT EXECUTED
   └─ Tables never created in DB

❌ Prometheus ServiceMonitor: MISSING
   └─ Prometheus doesn't know to scrape /metrics from IDS API

⚠️  Grafana Datasource: Configured but pointing to empty Prometheus
   └─ Dashboards load but show no data (because metrics not scraped)

❌ load-dashboards.sh: Doesn't validate success
   └─ Script runs but fails silently
```

---

## WHAT'S IN infrastructure/ TODAY

### infrastructure/database/
```
migrations/
├── 001_initial_schema.sql  ← Full schema with 6 tables
                               (users, api_keys, alerts, analysis_results, 
                                automation_actions, audit_logs)
```

**Status**: Migration file exists but NEVER RUNS during K8s deployment.

### infrastructure/monitoring/
```
grafana-dashboard-ids.json              ← IDS alert processing dashboard
grafana-dashboard-ieee-improved.json    ← IEEE format dashboard
grafana-dashboard-ieee.json             ← IEEE format dashboard v1
grafana-dashboard-iot-load.json         ← IoT load testing dashboard
grafana-dashboard-llm-performance.json  ← LLM latency/performance
grafana-dashboard-production.json       ← Production SOC overview
grafana-dashboard-soc-overview.json     ← SOC metrics dashboard
prometheus-alerts.yaml                  ← Alert rules for Prometheus
```

**Status**: Dashboards exist, but Prometheus has NO DATA to display them.

---

## WHY GRAFANA SHOWS NO DATA

```
┌─────────────────────┐
│   IDS API Pod       │
│ - Generates metrics │
│   (Counter, Gauge)  │
│ - Has /metrics      │
│   endpoint          │
└──────────┬──────────┘
           │
           │ ❌ Prometheus NOT scraping this!
           │ (No ServiceMonitor configured)
           ↓
        (void)
        
┌─────────────────────┐
│   Prometheus Pod    │
│ - Empty! (0 targets)│
│ - Has no data from  │
│   IDS API           │
└──────────┬──────────┘
           │
           │ ✅ Grafana queries this
           │    but gets empty responses
           ↓
┌─────────────────────┐
│   Grafana Pod       │
│ - Dashboards load   │
│ - All graphs empty! │
│ - No data points    │
└─────────────────────┘
```

---

## FIXES NEEDED (In Order)

### Priority 1: Deploy PostgreSQL
- [ ] Create `k8s-manifests/postgres-deployment.yaml`
- [ ] Create postgres secret with credentials
- [ ] Create configmap with migrations
- [ ] Update `deploy.sh` to deploy postgres before IDS API

### Priority 2: Configure Prometheus Scraping
- [ ] Create `infrastructure/monitoring/servicemonitor-ids-api.yaml`
- [ ] Verify IDS API exposes metrics on `/metrics`
- [ ] Check Prometheus targets show IDS API endpoint

### Priority 3: Fix load-dashboards.sh
- [ ] Add datasource validation
- [ ] Add dashboard import error checking
- [ ] Retry logic for Grafana readiness
- [ ] Log what datasources/dashboards were created

### Priority 4: Documentation
- [ ] Create `docs/INFRASTRUCTURE_SETUP.md`
- [ ] Explain database persistence
- [ ] Explain monitoring data flow
- [ ] Add troubleshooting section

---

## QUICK VERIFICATION AFTER FIXES

```bash
# Check postgres is running
kubectl get pods -n smart-city | grep postgres

# Check database connected
kubectl logs -n smart-city -l app=ids-api | grep "Connected to PostgreSQL"

# Check alerts in database
kubectl exec -it <postgres-pod> -n smart-city -- psql -U postgres -d smartcity_ids -c "SELECT COUNT(*) FROM alerts;"

# Check Prometheus scrapes IDS API
kubectl port-forward -n monitoring svc/prometheus 9090:9090 &
# Open http://localhost:9090/targets
# Should show ids-api endpoint as "UP"

# Check Grafana datasource works
kubectl port-forward -n monitoring svc/grafana 3000:3000 &
# Open http://localhost:3000
# Check data source health (should be green)
# Dashboards should show metrics

# Check IDS metrics are being recorded
curl http://localhost:30800/metrics | grep ids_
```

---

## SUMMARY

| Component | Current | Needed |
|-----------|---------|--------|
| PostgreSQL | ❌ Not deployed | ✅ Deploy postgres service + configmap |
| Database migrations | ❌ Not running | ✅ Create configmap, run on startup |
| Prometheus ServiceMonitor | ❌ Missing | ✅ Create servicemonitor resource |
| IDS API metrics endpoint | ✅ Has /metrics | ✅ Already working |
| Grafana datasource | ✅ Configured | ⚠️ Need to verify it works |
| Dashboard imports | ✅ Script exists | ✅ Fix validation + error handling |

---

## FILES TO CREATE/MODIFY

1. **k8s-manifests/postgres-deployment.yaml** - NEW
2. **k8s-manifests/postgres-secret.yaml** - NEW
3. **infrastructure/monitoring/servicemonitor-ids-api.yaml** - NEW
4. **scripts/load-dashboards.sh** - IMPROVE error handling
5. **deploy.sh** - ADD postgres deployment step
6. **docs/INFRASTRUCTURE_SETUP.md** - NEW guide

---

**Bottom Line**: The infrastructure is CONFIGURED but not DEPLOYED. Database exists in code but no postgres pod. Prometheus configured but not scraping. Dashboards exist but have no data.

All pieces are there—just need to wire them together correctly during K8s deployment.
