# Capstone II Implementation Checklist

**Target Completion:** End of Semester (January 31, 2026)  
**Current Status:** Week 1 (Research & Design) ✅ COMPLETE

---

## Phase 2: Operator Implementation (Week 2-3)

### OPS-2.1: Project Setup

- [ ] Create directory: `services/ids-operator/`
- [ ] Initialize Python project structure:
  ```
  services/ids-operator/
  ├── src/
  │   ├── handlers.py          # Kopf handlers
  │   ├── actions.py           # Action executors (isolate, scale, etc.)
  │   ├── validators.py        # LLM recommendation validators
  │   └── metrics.py           # Prometheus metrics
  ├── tests/
  │   ├── unit/
  │   │   ├── test_handlers.py
  │   │   ├── test_actions.py
  │   │   └── test_validators.py
  │   └── integration/
  │       └── test_e2e.py
  ├── Dockerfile
  ├── requirements.txt          # kopf, kubernetes, pydantic
  └── README.md
  ```
- [ ] Add `requirements.txt`:
  ```
  kopf==1.36.0
  kubernetes==28.0.0
  pydantic==2.0.0
  prometheus-client==0.19.0
  python-dotenv==1.0.0
  pytest==7.4.0
  pytest-asyncio==0.21.0
  ```

### OPS-2.2: CRD Creation

- [ ] Create `k8s-manifests/threat-response-crd.yaml`
  - [ ] Define `ThreatResponse` CRD with v1alpha1
  - [ ] Specify spec schema (alertId, targetPod, llmRecommendation, actions, rollback)
  - [ ] Specify status schema (phase, appliedAt, appliedActions, conditions)
  - [ ] Deploy to K3s: `kubectl apply -f threat-response-crd.yaml`
- [ ] Create `k8s-manifests/operator-rbac.yaml`
  - [ ] ServiceAccount: `ids-operator`
  - [ ] ClusterRole: permissions for pods, deployments, networkpolicies, nodes
  - [ ] ClusterRoleBinding: bind ServiceAccount to ClusterRole
  - [ ] Deploy: `kubectl apply -f operator-rbac.yaml`

### OPS-2.3: Core Operator Code

- [ ] Implement `services/ids-operator/src/handlers.py`:
  - [ ] `@kopf.on.event` handler for ThreatResponse creation
  - [ ] Validation phase (check pod exists, severity threshold)
  - [ ] Phase transition: Pending → Validating → Executing → Completed
- [ ] Implement `services/ids-operator/src/actions.py`:
  - [ ] `execute_isolate()` — Create NetworkPolicy
  - [ ] `execute_scale()` — Patch Deployment replicas
  - [ ] `execute_cordon()` — Mark node unschedulable
  - [ ] `execute_log()` — Log threat details
  - [ ] `execute_rollback()` — Revert actions
- [ ] Implement `services/ids-operator/src/validators.py`:
  - [ ] Validate LLM recommendation format
  - [ ] Check severity >= 5
  - [ ] Verify action types are known
- [ ] Implement retry logic with exponential backoff
- [ ] Implement dead-letter queue (ConfigMap) for failed threats

### OPS-2.4: IDS API Integration

- [ ] Modify `services/ids-api/src/main.py`:
  - [ ] Add `/api/operator/threats` endpoint (POST)
  - [ ] Accept ThreatResponse spec from IDS backend
  - [ ] Create ThreatResponse CRD in K3s
  - [ ] Return CRD name for tracking
- [ ] Update `config.py`:
  - [ ] Add `OPERATOR_NAMESPACE` setting
  - [ ] Add `THREAT_RESPONSE_CRD_GROUP` setting
- [ ] Add unit tests for API endpoint

### OPS-2.5: Testing

- [ ] Write unit tests:
  - [ ] `tests/unit/test_handlers.py` — Mock K8s API
  - [ ] `tests/unit/test_actions.py` — Validate action execution
  - [ ] `tests/unit/test_validators.py` — Validate threat format
- [ ] Run: `pytest tests/unit/ -v`
- [ ] Write integration tests:
  - [ ] `tests/integration/test_e2e.py` — Full ThreatResponse lifecycle
  - [ ] Test pod isolation (NetworkPolicy created)
  - [ ] Test auto-rollback (timeout triggers revert)
- [ ] Run: `pytest tests/integration/ -v` (requires K3s running)

### OPS-2.6: Docker Image & Deployment

- [ ] Create `services/ids-operator/Dockerfile`:
  ```dockerfile
  FROM python:3.11-slim
  WORKDIR /app
  COPY requirements.txt .
  RUN pip install -r requirements.txt
  COPY src/ .
  CMD ["kopf", "run", "--liveness=http://0.0.0.0:8080/healthz", "handlers.py"]
  ```
- [ ] Build image: `docker build -t ids-operator:latest services/ids-operator/`
- [ ] Create `k8s-manifests/operator-deployment.yaml`
- [ ] Deploy: `kubectl apply -f k8s-manifests/operator-deployment.yaml`
- [ ] Verify: `kubectl logs -n smart-city -l app=ids-operator -f`

---

## Phase 3: Attack Simulation & Testing (Week 3-4)

### OPS-3.1: Attack Scenario Automation

- [ ] Create `attack-simulations/capstone2-scenario.sh`:
  - [ ] Generate Falco alert (or use `/api/alerts` endpoint)
  - [ ] Simulate DDoS attack on traffic-camera pod
  - [ ] Verify operator detects and isolates pod
  - [ ] Verify network isolation applied (NetworkPolicy created)
  - [ ] Wait 5 seconds; verify pod is isolated (no external traffic)
  - [ ] Test rollback: delete isolation NetworkPolicy
  - [ ] Verify pod connectivity restored
- [ ] Create `attack-simulations/privilege-escalation.sh`:
  - [ ] Simulate privilege escalation attempt
  - [ ] Verify operator scales deployment (increase replicas)
  - [ ] Verify node cordoning (if applicable)

### OPS-3.2: Performance Testing

- [ ] Measure operator latency:
  - [ ] Time from ThreatResponse CRD created → pod isolated
  - [ ] Target: < 2 seconds (per Capstone requirements)
- [ ] Load test: 10+ simultaneous threats
  - [ ] Verify all processed correctly
  - [ ] Check for deadlocks or race conditions
- [ ] Document results in `docs/CAPSTONE_II_TEST_RESULTS.md`

### OPS-3.3: Failure Scenarios

- [ ] Test transient failures:
  - [ ] Pod deleted during reconciliation → retry
  - [ ] K3s API temporarily unavailable → retry
- [ ] Test permanent failures:
  - [ ] Invalid CRD schema → mark Failed
  - [ ] Unknown action type → mark Failed, DLQ
- [ ] Test rollback:
  - [ ] Simulate operator crash mid-action
  - [ ] Verify manual rollback capability

---

## Phase 4: Observability (Week 4-5)

### OPS-4.1: Prometheus Metrics

Status (as of 2026-01-12):
- IDS API exposes Prometheus-format metrics at `/metrics`.
- Operator exposes Prometheus-format metrics at `:8001/metrics` (Service: `ids-operator-metrics` in `smart-city`).
- Prometheus is configured to scrape both targets.

- [ ] Add metrics to operator:
  - [ ] `ids_threats_processed_total` (Counter)
  - [ ] `ids_threat_execution_seconds` (Histogram)
  - [ ] `ids_active_threats_count` (Gauge)
  - [ ] `ids_operator_errors_total` (Counter)
- [ ] Add metrics to FastAPI:
  - [ ] `ids_alerts_received_total` (Counter)
  - [ ] `ids_llm_analysis_seconds` (Histogram)
  - [ ] `ids_api_requests_total` (Counter)
- [ ] Create `/metrics` endpoint (Kopf + FastAPI expose automatically)

### OPS-4.2: Grafana Dashboard

Status (as of 2026-01-12):
- Grafana provisions `Smart City IDS (Capstone II)` dashboard automatically from manifests.
- Dashboard panels: Alerts received, Actions executed, Response latency.

- [ ] Create Grafana dashboard JSON (`dashboards/capstone2-operator.json`):
  - [ ] Graph: Threats processed (success/failed) over time
  - [ ] Graph: Threat execution latency (p50, p95, p99)
  - [ ] Gauge: Active threats count
  - [ ] Gauge: Operator uptime
  - [ ] Heatmap: Threat severity distribution
  - [ ] Table: Recent threats (name, status, error)
- [ ] Deploy dashboard: Import into Grafana

### OPS-4.3: Logging & Audit Trail

- [ ] Operator logs:
  - [ ] Each handler execution (validation, action, rollback)
  - [ ] Structured logs (JSON format for ELK stack)
- [ ] K8s audit events:
  - [ ] Record all ThreatResponse mutations
  - [ ] Record all pod/deployment/networkpolicy changes
- [ ] Create audit dashboard showing threat history

---

## Phase 5: Documentation & Demo (Week 5)

Demo tip:
- After demonstrating isolation, remove the isolation label from the target pod to restore normal networking:
  - `kubectl label pod -n smart-city <pod> ids.smartcity.local/isolate-`

### OPS-5.1: API Documentation

- [ ] Update [PROJECT_DOCUMENTATION.md](docs/PROJECT_DOCUMENTATION.md):
  - [ ] Add "Kubernetes Operator" section
  - [ ] Document `/api/operator/threats` endpoint
  - [ ] Document ThreatResponse CRD schema
  - [ ] Document error codes and recovery
  - [ ] Include example requests/responses

### OPS-5.2: Operational Runbooks

- [ ] Create `docs/OPERATOR_RUNBOOK.md`:
  - [ ] How to deploy operator to new cluster
  - [ ] How to monitor operator health
  - [ ] How to debug operator issues
  - [ ] How to manually rollback threat responses
  - [ ] How to scale operator (multiple replicas with leader election)

### OPS-5.3: Demo Scenario

- [ ] Create `demo/capstone2-demo.sh`:
  - [ ] Start K3s + IDS API + Operator
  - [ ] Show ThreatResponse CRD
  - [ ] Trigger DDoS attack simulation
  - [ ] Show operator processing (logs, metrics)
  - [ ] Show NetworkPolicy isolation
  - [ ] Show Grafana dashboard
  - [ ] Show auto-rollback after timeout

### OPS-5.4: Presentation Materials

- [ ] Record 2-3 min demo video
- [ ] Create presentation slides:
  - [ ] Problem statement
  - [ ] Operator architecture
  - [ ] Demo walkthrough
  - [ ] Results & metrics
  - [ ] Lessons learned
- [ ] Write final report section on Capstone II work

---

## Dependency Tracking

### Critical Path

```
OPS-2.1 (Project Setup)
    ↓
OPS-2.2 (CRD + RBAC) ← BLOCKER FOR OPS-2.3
    ↓
OPS-2.3 (Core Handlers) + OPS-2.4 (API Integration) [PARALLEL]
    ↓
OPS-2.5 (Testing)
    ↓
OPS-2.6 (Docker & Deploy)
    ↓
OPS-3 (Attack Simulation) ← BLOCKER FOR OPS-4
    ↓
OPS-4 (Observability)
    ↓
OPS-5 (Documentation & Demo)
```

### Estimated Timeline

| Phase | Tasks | Duration | Deadline |
|-------|-------|----------|----------|
| OPS-2 | Implementation | 5-6 days | Jan 18 |
| OPS-3 | Testing | 3-4 days | Jan 22 |
| OPS-4 | Observability | 2-3 days | Jan 25 |
| OPS-5 | Documentation | 2-3 days | Jan 31 |

---

## Success Criteria

✅ **Capstone II Grading Rubric:**

| Criterion | Target | Status |
|-----------|--------|--------|
| **Kubernetes Operator** | Fully functional Kopf operator | TBD |
| **CRD Implementation** | ThreatResponse CRD with status tracking | TBD |
| **Auto-Remediation** | Pod isolation, scaling, cordoning | TBD |
| **Error Handling** | Retry logic + rollback mechanism | TBD |
| **Testing** | 80%+ code coverage, integration tests | TBD |
| **Observability** | Prometheus metrics + Grafana dashboard | TBD |
| **Documentation** | Runbooks, API docs, demo video | TBD |
| **Presentation** | Clear demo, metrics, lessons learned | TBD |

---

## Notes for Students

1. **Start OPS-2.1 immediately** — Project structure setup is quickest path to progress
2. **Test frequently** — Each handler should be tested with unit tests before integration
3. **Use mock K8s API** in early unit tests (don't wait for full cluster setup)
4. **Leverage existing code** — `k8s_automation.py` already has action implementations; port to handlers
5. **Watch operator logs** — `kubectl logs -f` will show handler execution in real-time
6. **Metrics are important** — Grafana dashboard makes grading easier (visible proof of work!)

---

## Quick Commands (Copy/Paste)

```bash
# Setup
mkdir -p services/ids-operator/{src,tests/{unit,integration}}
cd services/ids-operator
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Deploy CRD + RBAC
kubectl apply -f ../../k8s-manifests/threat-response-crd.yaml
kubectl apply -f ../../k8s-manifests/operator-rbac.yaml

# Run operator locally (development)
kopf run --liveness=http://0.0.0.0:8080/healthz src/handlers.py

# Run tests
pytest tests/ -v --cov=src

# Build Docker image
docker build -t ids-operator:latest .

# Deploy to K3s
kubectl apply -f ../../k8s-manifests/operator-deployment.yaml

# Watch operator
kubectl logs -n smart-city -l app=ids-operator -f

# View ThreatResponses
kubectl get threatresponses -n smart-city
kubectl describe tr <name> -n smart-city
```

---

## Ready to start OPS-2

Let's build this operator! 🚀

