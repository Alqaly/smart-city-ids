# Capstone II: Getting Started with Kubernetes Operator Development

**Status:** Ready to start OPS-2 implementation  
**Timeline:** 5 weeks (Jan 12 - Jan 31)  
**Core Deliverable:** Kubernetes Operator for autonomous threat response

---

## What You're Building

A **Kubernetes Operator** that automatically responds to security threats detected by your IDS:

```
Falco Alert → IDS API → LLM Analysis → ThreatResponse CRD → Operator → Security Actions
                                                              (Kopf)   ├─ Isolate Pod
                                                                       ├─ Scale Service
                                                                       ├─ Cordon Node
                                                                       └─ Auto-Rollback
```

**Key Advantage:** Operator runs **inside Kubernetes**, not external scripts. Native K8s resource → automatic reconciliation → auditable history.

---

## Quick Start (30 minutes)

### Step 1: Read the Design Document (15 min)

```bash
# Open and skim through:
less docs/CAPSTONE_II_KUBERNETES_OPERATOR.md
```

Key sections to understand:
- Section 1: Why Kopf (Python framework)
- Section 3: CRD schema (ThreatResponse custom resource)
- Section 4.1: Kopf handler example (40 lines of code)
- Section 5: RBAC requirements

### Step 2: Review the Task Checklist (10 min)

```bash
less docs/CAPSTONE_II_IMPLEMENTATION_CHECKLIST.md
```

Focus on:
- **OPS-2.1 to OPS-2.6** (Implementation phase — Week 2-3)
- Critical path diagram
- Success criteria checklist

### Step 3: Set Up Your Development Environment (5 min)

```bash
# Create project structure
mkdir -p services/ids-operator/{src,tests/{unit,integration}}

# Initialize Git for new directory (optional, already tracked)
cd services/ids-operator

# Copy requirements template
cat > requirements.txt << 'EOF'
kopf==1.36.0
kubernetes==28.0.0
pydantic==2.0.0
prometheus-client==0.19.0
python-dotenv==1.0.0
pytest==7.4.0
pytest-asyncio==0.21.0
EOF

# Create virtualenv
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Verify installation
python -c "import kopf; print(f'Kopf {kopf.__version__} ready')"
```

✅ You're ready to start coding!

---

## Implementation Steps (OPS-2)

### Phase 1: Define the CRD (Day 1 — 2 hours)

**Goal:** Kubernetes understands what a ThreatResponse is

```bash
# 1. Create CRD manifest
cat > ../../k8s-manifests/threat-response-crd.yaml << 'EOF'
apiVersion: apiextensions.k8s.io/v1
kind: CustomResourceDefinition
metadata:
  name: threatresponses.ids.smartcity.local
spec:
  group: ids.smartcity.local
  names:
    kind: ThreatResponse
    plural: threatresponses
    shortNames:
      - tr
  scope: Namespaced
  versions:
    - name: v1alpha1
      served: true
      storage: true
      schema:
        openAPIV3Schema:
          type: object
          properties:
            spec:
              type: object
              required:
                - alertId
                - targetPod
                - llmRecommendation
                - actions
              properties:
                alertId:
                  type: string
                targetPod:
                  type: object
                  properties:
                    name:
                      type: string
                    namespace:
                      type: string
                llmRecommendation:
                  type: object
                  properties:
                    severity:
                      type: integer
                      minimum: 1
                      maximum: 10
                    summary:
                      type: string
                    threatType:
                      type: string
                actions:
                  type: array
                  items:
                    type: object
                    properties:
                      type:
                        type: string
            status:
              type: object
              properties:
                phase:
                  type: string
                appliedAt:
                  type: string
                appliedActions:
                  type: array
                lastError:
                  type: string
EOF

# 2. Deploy to K3s
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
kubectl apply -f ../../k8s-manifests/threat-response-crd.yaml

# 3. Verify
kubectl get crd | grep threatresponse
kubectl explain threatresponse.spec
```

**Success Criteria:**
```bash
$ kubectl get crd | grep threatresponse
threatresponses.ids.smartcity.local   2026-01-12T...   True
```

### Phase 2: Create RBAC Permissions (Day 1 — 1 hour)

**Goal:** Operator has K8s permissions to perform security actions

```bash
# 1. Create RBAC manifest
cat > ../../k8s-manifests/operator-rbac.yaml << 'EOF'
apiVersion: v1
kind: ServiceAccount
metadata:
  name: ids-operator
  namespace: smart-city

---

apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: ids-operator
rules:
  - apiGroups: ["ids.smartcity.local"]
    resources: ["threatresponses"]
    verbs: ["get", "list", "watch", "patch", "update"]
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list", "delete", "patch"]
  - apiGroups: ["apps"]
    resources: ["deployments"]
    verbs: ["get", "list", "patch", "update"]
  - apiGroups: ["networking.k8s.io"]
    resources: ["networkpolicies"]
    verbs: ["get", "create", "patch", "delete"]
  - apiGroups: [""]
    resources: ["nodes"]
    verbs: ["get", "list", "patch"]

---

apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: ids-operator
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: ids-operator
subjects:
  - kind: ServiceAccount
    name: ids-operator
    namespace: smart-city
EOF

# 2. Deploy RBAC
kubectl apply -f ../../k8s-manifests/operator-rbac.yaml

# 3. Verify
kubectl get serviceaccount ids-operator -n smart-city
kubectl get clusterrole ids-operator
```

### Phase 3: Write First Kopf Handler (Days 2-3 — 6 hours)

**Goal:** Kopf watches ThreatResponse and validates incoming threats

**Step 1:** Create basic handler file

```python
# services/ids-operator/src/handlers.py

import kopf
import kubernetes.client
from kubernetes.client.rest import ApiException
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

@kopf.on.event(
    "ids.smartcity.local", "v1alpha1", "ThreatResponse",
    labels={"phase": "pending"}
)
def validate_and_execute(body, spec, status, **kwargs):
    """
    Main handler: Validate threat and execute security actions
    """
    name = body['metadata']['name']
    namespace = body['metadata']['namespace']
    
    logger.info(f"[HANDLER] Processing threat: {name}")
    
    try:
        # Step 1: Extract alert data
        alert_id = spec.get('alertId', 'unknown')
        llm_rec = spec.get('llmRecommendation', {})
        severity = llm_rec.get('severity', 0)
        target_pod = spec.get('targetPod', {})
        
        logger.info(f"  Alert: {alert_id}, Severity: {severity}")
        
        # Step 2: Validate severity threshold
        if severity < 5:
            logger.info(f"  Severity too low ({severity}). Skipping.")
            return
        
        # Step 3: Check if target pod exists
        v1 = kubernetes.client.CoreV1Api()
        pod_name = target_pod.get('name')
        pod_namespace = target_pod.get('namespace', namespace)
        
        try:
            pod = v1.read_namespaced_pod(pod_name, pod_namespace)
            logger.info(f"  ✅ Found target pod: {pod_name}")
        except ApiException as e:
            logger.warning(f"  ⚠️ Target pod not found: {e}")
            raise kopf.TemporaryError(f"Pod {pod_name} not found")
        
        # Step 4: Update status to validating
        kopf.patch(
            body,
            {'status': {
                'phase': 'Validating',
                'conditions': [{
                    'type': 'Validated',
                    'status': 'True',
                    'reason': 'ValidationPassed'
                }]
            }},
            body=body
        )
        
        logger.info(f"  ✅ Validation passed. Ready to execute actions.")
        
    except Exception as e:
        logger.error(f"  ❌ Error: {e}")
        kopf.patch(body, {'status': {
            'phase': 'Failed',
            'lastError': str(e)
        }})
        raise

if __name__ == '__main__':
    kopf.run()
```

**Step 2:** Run locally in development

```bash
# Terminal 1: Start K3s (if not running)
sudo systemctl start k3s

# Terminal 2: Run operator locally
cd services/ids-operator
source venv/bin/activate
kopf run --liveness=http://0.0.0.0:8080/healthz src/handlers.py
```

**Step 3:** Test with a sample ThreatResponse

```bash
# Terminal 3: Create test CRD object
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

kubectl apply -f - << 'EOF'
apiVersion: ids.smartcity.local/v1alpha1
kind: ThreatResponse
metadata:
  name: test-ddos-001
  namespace: smart-city
spec:
  alertId: "falco-12345"
  targetPod:
    name: traffic-camera-01
    namespace: smart-city
  llmRecommendation:
    severity: 9
    summary: "DDoS detected"
    threatType: "Volumetric"
  actions:
    - type: isolate
EOF

# Watch operator logs (Terminal 2)
# Should see:
# [HANDLER] Processing threat: test-ddos-001
# Alert: falco-12345, Severity: 9
# ✅ Found target pod: traffic-camera-01
# ✅ Validation passed
```

✅ **Your first Kopf handler is working!**

### Phase 4: Add Action Executors (Days 4-5 — 8 hours)

Now implement the actual security actions:

```python
# services/ids-operator/src/actions.py

import kubernetes.client
import logging

logger = logging.getLogger(__name__)

def execute_isolate(namespace, spec):
    """Isolate pod via NetworkPolicy"""
    pod_name = spec['targetPod']['name']
    
    logger.info(f"  [ACTION] Isolating pod: {pod_name}")
    
    # Create restrictive NetworkPolicy
    np = {
        'apiVersion': 'networking.k8s.io/v1',
        'kind': 'NetworkPolicy',
        'metadata': {
            'name': f"{pod_name}-isolation",
            'namespace': namespace
        },
        'spec': {
            'podSelector': {'matchLabels': {'app': pod_name}},
            'policyTypes': ['Ingress', 'Egress'],
            'ingress': [],  # Deny all
            'egress': []    # Deny all
        }
    }
    
    custom_api = kubernetes.client.CustomObjectsApi()
    result = custom_api.create_namespaced_custom_object(
        group='networking.k8s.io',
        version='v1',
        namespace=namespace,
        plural='networkpolicies',
        body=np
    )
    
    logger.info(f"  ✅ NetworkPolicy created: {pod_name}-isolation")
    return result

def execute_scale(namespace, spec, replicas=3):
    """Scale deployment"""
    logger.info(f"  [ACTION] Scaling deployment to {replicas} replicas")
    
    deployment_name = spec['targetPod']['name']
    apps_api = kubernetes.client.AppsV1Api()
    
    deployment = apps_api.read_namespaced_deployment(deployment_name, namespace)
    deployment.spec.replicas = replicas
    
    result = apps_api.patch_namespaced_deployment(deployment_name, namespace, deployment)
    
    logger.info(f"  ✅ Scaled {deployment_name} to {replicas} replicas")
    return result

# Add more actions (cordon, log) following the same pattern
```

Update your handlers.py to call these actions:

```python
# In handlers.py, after validation passes:

from actions import execute_isolate, execute_scale

# Step 5: Execute actions
actions = spec.get('actions', [])
applied_actions = []

for action in actions:
    action_type = action.get('type')
    
    try:
        if action_type == 'isolate':
            execute_isolate(namespace, spec)
        elif action_type == 'scale':
            execute_scale(namespace, spec, replicas=5)
        else:
            raise ValueError(f"Unknown action: {action_type}")
        
        applied_actions.append({
            'type': action_type,
            'status': 'success'
        })
    except Exception as e:
        logger.error(f"  ❌ Action {action_type} failed: {e}")
        applied_actions.append({
            'type': action_type,
            'status': 'failed'
        })

# Update status to completed
kopf.patch(body, {'status': {
    'phase': 'Completed',
    'appliedActions': applied_actions,
    'appliedAt': datetime.utcnow().isoformat()
}})
```

### Phase 5: Unit & Integration Tests (Days 5-6 — 6 hours)

```python
# services/ids-operator/tests/unit/test_handlers.py

import pytest
from unittest.mock import MagicMock, patch
from src.handlers import validate_and_execute

def test_validation_success():
    """Test successful validation"""
    body = {
        'metadata': {'name': 'test-threat', 'namespace': 'smart-city'},
        'spec': {
            'alertId': 'test-123',
            'targetPod': {'name': 'test-pod', 'namespace': 'smart-city'},
            'llmRecommendation': {'severity': 9},
            'actions': []
        }
    }
    
    with patch('kubernetes.client.CoreV1Api') as mock_api:
        mock_api.return_value.read_namespaced_pod.return_value = MagicMock()
        
        # Should not raise
        validate_and_execute(body, body['spec'], {})

def test_severity_threshold():
    """Test that low severity threats are ignored"""
    body = {
        'metadata': {'name': 'low-threat', 'namespace': 'smart-city'},
        'spec': {
            'targetPod': {'name': 'test', 'namespace': 'smart-city'},
            'llmRecommendation': {'severity': 2},  # Low severity
            'actions': []
        }
    }
    
    # Should return early without raising
    validate_and_execute(body, body['spec'], {})
```

Run tests:

```bash
pytest tests/unit/ -v
# Expected: 2+ tests pass
```

### Phase 6: Dockerize & Deploy (Day 6 — 4 hours)

```dockerfile
# services/ids-operator/Dockerfile

FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ .

CMD ["kopf", "run", "--liveness=http://0.0.0.0:8080/healthz", "handlers.py"]
```

```bash
# Build
docker build -t ids-operator:latest services/ids-operator/

# Create deployment manifest
cat > k8s-manifests/operator-deployment.yaml << 'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ids-operator
  namespace: smart-city
spec:
  replicas: 1
  selector:
    matchLabels:
      app: ids-operator
  template:
    metadata:
      labels:
        app: ids-operator
    spec:
      serviceAccountName: ids-operator
      containers:
      - name: operator
        image: ids-operator:latest
        imagePullPolicy: Never
        livenessProbe:
          httpGet:
            path: /healthz
            port: 8080
          initialDelaySeconds: 30
        resources:
          requests:
            memory: "256Mi"
            cpu: "100m"
EOF

# Deploy
kubectl apply -f k8s-manifests/operator-deployment.yaml

# Watch
kubectl logs -n smart-city -l app=ids-operator -f
```

---

## Testing Your Work

### Quick Validation Checklist

```bash
# ✅ CRD exists
kubectl get crd threatresponses.ids.smartcity.local

# ✅ RBAC configured
kubectl get clusterrole ids-operator
kubectl get serviceaccount ids-operator -n smart-city

# ✅ Operator running
kubectl get pods -n smart-city -l app=ids-operator

# ✅ Can create ThreatResponse
kubectl apply -f - << 'EOF'
apiVersion: ids.smartcity.local/v1alpha1
kind: ThreatResponse
metadata:
  name: test-threat
  namespace: smart-city
spec:
  alertId: "test-001"
  targetPod:
    name: traffic-camera-01
    namespace: smart-city
  llmRecommendation:
    severity: 8
    summary: "Test threat"
    threatType: "Test"
  actions:
    - type: isolate
EOF

# ✅ Operator processed it
kubectl get threatresponse -n smart-city
kubectl describe threatresponse test-threat -n smart-city
# Look for: phase = Completed, appliedActions = [success]

# ✅ NetworkPolicy created
kubectl get networkpolicy -n smart-city
kubectl describe networkpolicy traffic-camera-01-isolation -n smart-city
```

---

## Next Milestones

| Phase | Deadline | Deliverable |
|-------|----------|-------------|
| **OPS-2** (You are here) | Jan 18 | Working operator + tests |
| **OPS-3** | Jan 22 | Attack simulations + rollback |
| **OPS-4** | Jan 25 | Prometheus metrics + Grafana |
| **OPS-5** | Jan 31 | Docs + demo + final report |

---

## Troubleshooting

### Q: Kopf handler not triggering?

**A:** Check logs for errors and verify CRD exists:

```bash
# Check handler logs
kopf run -v src/handlers.py

# Verify CRD
kubectl explain threatresponse

# Try creating manually
kubectl apply -f threat-response.yaml
```

### Q: "Pod not found" error?

**A:** Make sure target pod exists:

```bash
kubectl get pods -n smart-city
# If empty, create a test pod:
kubectl run traffic-camera-01 --image=nginx -n smart-city
```

### Q: NetworkPolicy not isolating traffic?

**A:** Check if NetworkPolicy is applied:

```bash
kubectl get networkpolicy -n smart-city
kubectl describe networkpolicy <name> -n smart-city

# Test isolation with curl (should timeout)
kubectl exec -it <pod> -- curl https://external.com
```

---

## Key Files You'll Edit

```
services/ids-operator/
├── src/
│   ├── handlers.py          ← Main Kopf handlers (starts empty)
│   ├── actions.py           ← Action executors (isolate, scale)
│   └── validators.py        ← Validation logic (optional)
├── tests/
│   └── unit/test_handlers.py  ← Unit tests with mocks
├── Dockerfile               ← Docker image definition
└── requirements.txt         ← Python dependencies

k8s-manifests/
├── threat-response-crd.yaml      ← CRD definition
├── operator-rbac.yaml            ← ServiceAccount + RBAC roles
└── operator-deployment.yaml      ← Operator deployment manifest
```

---

## Success Metrics (For Your Grading)

By end of OPS-2, you should have:

✅ CRD that K8s recognizes (`kubectl get threatresponses`)  
✅ Operator that watches ThreatResponse objects  
✅ At least 3 working actions (isolate, scale, log)  
✅ Unit tests with 70%+ code coverage  
✅ Pod isolation confirmed (NetworkPolicy created)  
✅ Auto-rollback working (timeout triggers revert)  
✅ Docker image builds and deploys  

---

## Let's Build! 🚀

Ready? Start with **Step 1** above (reading design doc) and work through Phase 1 & 2 today.

**Need help?** Reference these:
- Design doc: `docs/CAPSTONE_II_KUBERNETES_OPERATOR.md` (section 4.1 for code examples)
- Task checklist: `docs/CAPSTONE_II_IMPLEMENTATION_CHECKLIST.md`
- Existing automation logic: `services/ids-api/src/k8s_automation.py` (can port to operator)

**Let's ship this! ⚡**
