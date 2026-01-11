# Capstone II: Kubernetes Operator for Autonomous Threat Response

**Document Version:** 1.0  
**Date:** January 2026  
**Status:** Design Phase (OPS-1)  
**Author:** Smart City IDS Team  

---

## Executive Summary

This document outlines the design of a **Kubernetes Operator** that autonomously responds to security threats detected by the LLM-enhanced IDS. The operator will:

- ✅ Watch for threat alerts from the FastAPI backend
- ✅ Validate LLM recommendations via a Custom Resource Definition (CRD)
- ✅ Execute Kubernetes-native security actions (pod isolation, NetworkPolicy, node cordoning)
- ✅ Track threat lifecycle with automatic reconciliation
- ✅ Support rollback mechanisms for mistaken actions

**Technology Choice:** **Kopf (Python)** — best suited for rapid development, team expertise, and integration with existing Python codebase.

---

## 1. Framework Selection & Justification

### 1.1 Comparison Matrix

| Criterion | Kopf (Python) | Operator SDK (Go) | Kubebuilder (Go) |
|-----------|--------------|------------------|------------------|
| **Language** | Python | Go | Go |
| **Learning Curve** | Very low | Moderate | Moderate |
| **Performance** | Good (async) | Excellent | Excellent |
| **Team Fit** | ✅ Existing Python codebase | ❌ New language | ❌ New language |
| **Community** | Growing | Mature | Mature |
| **Development Speed** | Fast (decorators) | Slower (verbose) | Slower (verbose) |
| **Prod-Ready** | ✅ Yes (many examples) | ✅ Yes | ✅ Yes |

### 1.2 Selection Rationale

**Kopf is chosen because:**

1. **Team Expertise** — Your IDS backend is Python (FastAPI). Operators written in same language reduce context switching.
2. **Rapid Development** — Kopf's decorator-based API allows quick prototyping and iteration (critical for semester timeline).
3. **Ecosystem Fit** — Can reuse `k8s_automation.py` logic directly in operator handlers.
4. **Async Support** — Built-in async/await for calling external APIs (LLM validation).
5. **Testing** — pytest familiar; easier mocking of K8s API calls.

### 1.3 Kopf Scaffolding Example

```python
import kopf
import kubernetes.client
from kubernetes.client.rest import ApiException

@kopf.on.event("v1", "Pod", labels={"threat": "detected"})
def respond_to_threat(event, name, namespace, **kwargs):
    """Reconcile threat detected on Pod"""
    pod = event['object']
    threat_level = pod.metadata.labels.get('threat-level', 'unknown')
    
    if threat_level == 'critical':
        # Isolate pod
        isolate_pod(name, namespace)
        # Log action
        kopf.info(f"Isolated pod {name} in {namespace}")

if __name__ == '__main__':
    kopf.run()
```

---

## 2. Architecture Design

### 2.1 Component Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    Smart City IDS System                    │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────┐        ┌──────────────────┐           │
│  │  Falco / Suricata│        │  Detection Rules │           │
│  │   (Rule Engine)  │───────▶│  (Log Events)    │           │
│  └──────────────────┘        └──────────────────┘           │
│            │                                                 │
│            │ JSON Alert                                      │
│            ▼                                                 │
│  ┌──────────────────────────────────────────┐              │
│  │      IDS FastAPI Backend                 │              │
│  │  - Alert Ingestion (/api/alerts)         │              │
│  │  - LLM Analysis (Groq/OpenAI)            │              │
│  │  - ThreatResponse CRD Creation           │              │
│  └──────────────────────────────────────────┘              │
│            │                                                 │
│            │ POST /api/operator/threats                      │
│            ▼                                                 │
│  ┌──────────────────────────────────────────┐              │
│  │   Kubernetes Operator (Kopf)             │              │
│  │  - Watches ThreatResponse CRDs          │              │
│  │  - Validates LLM recommendations         │              │
│  │  - Executes security actions             │              │
│  │  - Updates status & metrics              │              │
│  └──────────────────────────────────────────┘              │
│            │         │              │                       │
│            ▼         ▼              ▼                       │
│      ┌─────────┐┌──────────┐┌──────────────┐              │
│      │ Isolate ││NetworkPol││ Cordon Node  │              │
│      │  Pods   ││icies     ││ (Delete Pod) │              │
│      └─────────┘└──────────┘└──────────────┘              │
│                                                              │
│  ┌──────────────────────────────────────────┐              │
│  │   Monitoring & Observability              │              │
│  │  - Prometheus metrics (/metrics)          │              │
│  │  - Grafana dashboards                     │              │
│  │  - Alert audit logs                       │              │
│  └──────────────────────────────────────────┘              │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Sequence Diagram: Alert → Action

```
Falco            IDS API           Operator        Kubernetes
  │                │                  │               │
  │ Trigger Rule   │                  │               │
  ├──────────────▶ │                  │               │
  │                │ LLM Analysis     │               │
  │                │ (Groq)           │               │
  │                │                  │               │
  │                │ Create           │               │
  │                │ ThreatResponse   │               │
  │                │ CRD              │               │
  │                ├─────────────────▶│               │
  │                │                  │ Watch        │
  │                │                  │ ThreatResponse
  │                │                  ├──────────────▶│
  │                │                  │               │
  │                │                  │ Validate      │
  │                │                  │ LLM Rec.      │
  │                │                  │               │
  │                │                  │ Execute       │
  │                │                  │ Actions       │
  │                │                  ├──────────────▶│
  │                │                  │               │
  │                │                  │ Update Status │
  │                │                  │◀──────────────┤
  │                │◀─────────────────┤               │
  │                │ Webhook notify   │               │
  │                │                  │               │
  │    ✓ Logged    │                  │               │
  │◀───────────────┤                  │               │
  │                │                  │               │
```

### 2.3 ThreatResponse Lifecycle State Machine

```
                ┌─────────────┐
                │   PENDING   │ (CRD created by API)
                └──────┬──────┘
                       │ Kopf watches
                       ▼
                ┌─────────────┐
                │ VALIDATING  │ (Checking LLM rec. + permissions)
                └──────┬──────┘
                       │
                ┌──────┴──────┐
                │             │
                ▼             ▼
        ┌──────────────┐ ┌──────────┐
        │  VALIDATION  │ │VALIDATION│
        │     PASS     │ │  FAILED  │
        └──────┬───────┘ └──────┬───┘
               │                │
               ▼                ▼
        ┌──────────────┐ ┌──────────────┐
        │  EXECUTING   │ │    FAILED    │
        └──────┬───────┘ └──────────────┘
               │
        ┌──────┴──────┐
        │             │
        ▼             ▼
  ┌─────────────┐ ┌──────────────┐
  │ COMPLETED   │ │ROLLBACK      │
  │  SUCCESS    │ │SCHEDULED     │
  └─────────────┘ └──────────────┘
```

---

## 3. Custom Resource Definition (CRD) Schema

### 3.1 ThreatResponse CRD Structure

```yaml
apiVersion: ids.smartcity.local/v1alpha1
kind: ThreatResponse
metadata:
  name: threat-ddos-2026-01-12-001
  namespace: smart-city
  labels:
    severity: critical
    alert-source: falco
spec:
  # Alert information
  alertId: "falco-alert-12345"
  alertTime: "2026-01-12T10:30:45Z"
  alertRule: "Suspicious Process Spawned"
  alertPriority: "Critical"
  
  # Target information
  targetPod:
    name: "traffic-camera-01"
    namespace: "smart-city"
    container: "camera-app"
  
  # LLM Analysis Result
  llmRecommendation:
    summary: "DDoS attack detected on traffic monitoring service"
    severity: 9  # 1-10 scale
    threatType: "Volumetric Attack"
    confidence: 0.98
    recommendations:
      - "Isolate pod from network"
      - "Enable rate limiting"
      - "Scale up replica count"
  
  # Requested actions
  actions:
    - type: "isolate"
      params:
        networkPolicy: "deny-all-ingress"
    - type: "scale"
      params:
        replicas: 5
    - type: "log"
      params:
        level: "critical"
  
  # Auto-rollback configuration
  rollback:
    enabled: true
    timeoutSeconds: 300
    rollbackActions:
      - type: "restore-network"
      - type: "scale-down"

status:
  # Current phase
  phase: "Executing"
  
  # Execution details
  appliedAt: "2026-01-12T10:31:00Z"
  appliedActions:
    - type: "isolate"
      status: "success"
      appliedAt: "2026-01-12T10:31:01Z"
      details: "NetworkPolicy created: threat-ddos-2026-01-12-001-isolation"
    - type: "scale"
      status: "in-progress"
      details: "Scaling deployment from 2 to 5 replicas"
  
  # Rollback information
  rollbackScheduled: false
  rollbackAt: null
  
  # Error tracking
  lastError: null
  retryCount: 0
  
  # Observability
  conditions:
    - type: "Validated"
      status: "True"
      lastTransitionTime: "2026-01-12T10:30:50Z"
      reason: "LLMValidationPassed"
    - type: "Executing"
      status: "True"
      lastTransitionTime: "2026-01-12T10:31:00Z"
      reason: "ActionsInProgress"
```

### 3.2 CRD Definition (v1alpha1)

```yaml
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
      - threat
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
                alertTime:
                  type: string
                  format: date-time
                alertRule:
                  type: string
                targetPod:
                  type: object
                  required:
                    - name
                    - namespace
                  properties:
                    name:
                      type: string
                    namespace:
                      type: string
                    container:
                      type: string
                llmRecommendation:
                  type: object
                  properties:
                    summary:
                      type: string
                    severity:
                      type: integer
                      minimum: 1
                      maximum: 10
                    threatType:
                      type: string
                    confidence:
                      type: number
                      minimum: 0
                      maximum: 1
                    recommendations:
                      type: array
                      items:
                        type: string
                actions:
                  type: array
                  items:
                    type: object
                    required:
                      - type
                    properties:
                      type:
                        type: string
                        enum:
                          - isolate
                          - scale
                          - cordon
                          - log
                      params:
                        type: object
            status:
              type: object
              properties:
                phase:
                  type: string
                  enum:
                    - Pending
                    - Validating
                    - Executing
                    - Completed
                    - Failed
                appliedAt:
                  type: string
                  format: date-time
                conditions:
                  type: array
                  items:
                    type: object
                    properties:
                      type:
                        type: string
                      status:
                        type: string
                      reason:
                        type: string
```

---

## 4. Operator Implementation Design

### 4.1 Kopf Handler Structure

```python
# kopf_operator/handlers.py

import kopf
import kubernetes.client
from kubernetes.client.rest import ApiException
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# ============================================================================
# HANDLER 1: On ThreatResponse Creation
# ============================================================================

@kopf.on.event(
    "ids.smartcity.local", "v1alpha1", "ThreatResponse",
    labels={"handled": "false"}
)
def validate_threat(body, spec, status, **kwargs):
    """
    Validate ThreatResponse and check LLM recommendation.
    
    Phase: Pending → Validating
    """
    name = body['metadata']['name']
    namespace = body['metadata']['namespace']
    
    logger.info(f"Validating threat response: {name}")
    
    try:
        # Step 1: Validate alert data
        alert_id = spec.get('alertId')
        llm_rec = spec.get('llmRecommendation', {})
        severity = llm_rec.get('severity', 0)
        
        if severity < 5:
            raise kopf.PermanentError(
                f"Severity too low ({severity}). Ignoring."
            )
        
        # Step 2: Check if target pod exists
        v1 = kubernetes.client.CoreV1Api()
        pod_name = spec['targetPod']['name']
        pod_namespace = spec['targetPod']['namespace']
        
        try:
            pod = v1.read_namespaced_pod(pod_name, pod_namespace)
            logger.info(f"Found target pod: {pod_name}")
        except ApiException as e:
            raise kopf.TemporaryError(
                f"Target pod {pod_name} not found: {e}"
            )
        
        # Step 3: Update status to Validating
        kopf.patch(
            body,
            {'status': {
                'phase': 'Validating',
                'conditions': [{
                    'type': 'Validated',
                    'status': 'True',
                    'lastTransitionTime': datetime.utcnow().isoformat(),
                    'reason': 'LLMValidationPassed'
                }]
            }},
            body=body
        )
        
        logger.info(f"Validation passed: {name}")
        
    except kopf.TemporaryError as e:
        logger.warning(f"Temporary validation error: {e}")
        raise
    except kopf.PermanentError as e:
        logger.error(f"Permanent validation error: {e}")
        # Mark as failed
        kopf.patch(body, {'status': {
            'phase': 'Failed',
            'lastError': str(e)
        }})
        raise


# ============================================================================
# HANDLER 2: Execute Security Actions
# ============================================================================

@kopf.on.event(
    "ids.smartcity.local", "v1alpha1", "ThreatResponse",
    labels={"phase": "Validating"}
)
def execute_actions(body, spec, status, **kwargs):
    """
    Execute security actions from ThreatResponse.
    
    Phase: Validating → Executing → Completed
    """
    name = body['metadata']['name']
    namespace = body['metadata']['namespace']
    actions = spec.get('actions', [])
    
    logger.info(f"Executing {len(actions)} actions for: {name}")
    
    applied_actions = []
    
    for action in actions:
        action_type = action.get('type')
        params = action.get('params', {})
        
        try:
            if action_type == 'isolate':
                result = execute_isolate(namespace, spec, **params)
            elif action_type == 'scale':
                result = execute_scale(namespace, spec, **params)
            elif action_type == 'cordon':
                result = execute_cordon(spec, **params)
            elif action_type == 'log':
                result = execute_log(spec, **params)
            else:
                raise kopf.PermanentError(f"Unknown action: {action_type}")
            
            applied_actions.append({
                'type': action_type,
                'status': 'success',
                'appliedAt': datetime.utcnow().isoformat(),
                'details': result
            })
            
        except Exception as e:
            logger.error(f"Action {action_type} failed: {e}")
            applied_actions.append({
                'type': action_type,
                'status': 'failed',
                'details': str(e)
            })
            # Don't fail entirely; log and continue
    
    # Update status to Completed
    kopf.patch(body, {'status': {
        'phase': 'Completed',
        'appliedAt': datetime.utcnow().isoformat(),
        'appliedActions': applied_actions
    }})
    
    logger.info(f"Actions completed for: {name}")


# ============================================================================
# HANDLER 3: Auto-Rollback on Timeout
# ============================================================================

@kopf.timer(
    "ids.smartcity.local", "v1alpha1", "ThreatResponse",
    interval=30.0  # Check every 30 seconds
)
def check_rollback_timeout(body, spec, status, **kwargs):
    """
    Check if threat response should be rolled back due to timeout.
    
    If rollback.enabled and timeout expired, revert actions.
    """
    name = body['metadata']['name']
    rollback_config = spec.get('rollback', {})
    
    if not rollback_config.get('enabled'):
        return
    
    applied_at = status.get('appliedAt')
    if not applied_at:
        return
    
    timeout_seconds = rollback_config.get('timeoutSeconds', 300)
    timeout_delta = timedelta(seconds=timeout_seconds)
    
    applied_time = datetime.fromisoformat(applied_at.replace('Z', '+00:00'))
    now = datetime.utcnow().replace(tzinfo=applied_time.tzinfo)
    
    if now - applied_time > timeout_delta:
        logger.warning(f"Rollback timeout triggered for: {name}")
        execute_rollback(body, rollback_config)


# ============================================================================
# ACTION EXECUTORS (Called by execute_actions)
# ============================================================================

def execute_isolate(namespace, spec, networkPolicy="deny-all-ingress"):
    """Isolate pod via NetworkPolicy"""
    pod_name = spec['targetPod']['name']
    v1 = kubernetes.client.CoreV1Api()
    
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
            'egress': [
                {'to': [{'namespaceSelector': {'matchLabels': {'name': 'kube-system'}}}]}
            ]
        }
    }
    
    # Apply NetworkPolicy
    custom_api = kubernetes.client.CustomObjectsApi()
    custom_api.create_namespaced_custom_object(
        group='networking.k8s.io',
        version='v1',
        namespace=namespace,
        plural='networkpolicies',
        body=np
    )
    
    return f"NetworkPolicy created: {pod_name}-isolation"


def execute_scale(namespace, spec, replicas=1):
    """Scale deployment/statefulset"""
    deployment_name = spec['targetPod']['name']  # Assume deployment name = pod label
    apps_api = kubernetes.client.AppsV1Api()
    
    deployment = apps_api.read_namespaced_deployment(deployment_name, namespace)
    deployment.spec.replicas = replicas
    
    apps_api.patch_namespaced_deployment(deployment_name, namespace, deployment)
    
    return f"Scaled {deployment_name} to {replicas} replicas"


def execute_cordon(spec, **params):
    """Cordon node (prevent new pods)"""
    node_name = params.get('nodeName')
    if not node_name:
        return "No node to cordon"
    
    v1 = kubernetes.client.CoreV1Api()
    node = v1.read_node(node_name)
    node.spec.unschedulable = True
    
    v1.patch_node(node_name, node)
    
    return f"Node cordoned: {node_name}"


def execute_log(spec, level="critical"):
    """Log alert details"""
    logger.log(
        getattr(logging, level.upper(), logging.INFO),
        f"Security alert logged: {spec.get('alertRule', 'Unknown')}"
    )
    return f"Logged at level: {level}"


def execute_rollback(body, rollback_config):
    """Execute rollback actions"""
    logger.warning("Executing rollback...")
    # Implementation would reverse applied actions
    pass
```

### 4.2 Kopf Operator Deployment

```dockerfile
# Dockerfile for Kopf operator
FROM python:3.11-slim

WORKDIR /app

COPY requirements-operator.txt .
RUN pip install -r requirements-operator.txt

COPY kopf_operator/ .

CMD ["kopf", "run", "--liveness=http://0.0.0.0:8080/healthz", "handlers.py"]
```

```yaml
# k8s-manifests/operator-deployment.yaml
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
  # ThreatResponse CRUD
  - apiGroups: ["ids.smartcity.local"]
    resources: ["threatresponses"]
    verbs: ["get", "list", "watch", "patch", "update"]
  
  # Pod operations
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list", "delete", "patch"]
  
  # Deployments
  - apiGroups: ["apps"]
    resources: ["deployments", "statefulsets"]
    verbs: ["get", "list", "patch", "update"]
  
  # NetworkPolicies
  - apiGroups: ["networking.k8s.io"]
    resources: ["networkpolicies"]
    verbs: ["get", "create", "patch", "delete"]
  
  # Nodes (for cordoning)
  - apiGroups: [""]
    resources: ["nodes"]
    verbs: ["get", "list", "patch"]
  
  # Events (for logging)
  - apiGroups: [""]
    resources: ["events"]
    verbs: ["create", "patch"]

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

---

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
        imagePullPolicy: Never  # For local development
        env:
          - name: KOPF_LOG_LEVEL
            value: "info"
        livenessProbe:
          httpGet:
            path: /healthz
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
        resources:
          requests:
            memory: "256Mi"
            cpu: "100m"
          limits:
            memory: "512Mi"
            cpu: "500m"
```

---

## 5. Security & RBAC Requirements

### 5.1 Principle of Least Privilege

The operator ServiceAccount should only have permissions necessary for its actions:

| Resource | Verbs | Reason |
|----------|-------|--------|
| `threatresponses` | get, list, watch, patch, update | Read alerts, update status |
| `pods` | get, list, delete, patch | Isolate/evict compromised pods |
| `deployments` | get, list, patch | Scale services |
| `networkpolicies` | get, create, patch, delete | Enforce network isolation |
| `nodes` | get, list, patch | Cordon affected nodes |
| `events` | create, patch | Record actions in audit log |

### 5.2 Network Security

```yaml
# NetworkPolicy: Operator can only reach API server
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: ids-operator-policy
  namespace: smart-city
spec:
  podSelector:
    matchLabels:
      app: ids-operator
  policyTypes:
    - Egress
  egress:
    # Allow to K8s API
    - to:
        - namespaceSelector:
            matchLabels:
              name: kube-system
      ports:
        - port: 443
          protocol: TCP
    # Allow DNS
    - to:
        - namespaceSelector: {}
      ports:
        - port: 53
          protocol: UDP
```

---

## 6. Error Handling Strategy

### 6.1 Error Classification

| Error Type | Example | Handling |
|------------|---------|----------|
| **Transient** | Pod temporarily unavailable | Retry with exponential backoff (max 5 retries) |
| **Permanent** | CRD schema invalid | Fail immediately, mark as Failed |
| **Partial** | 1 of 3 actions succeeds | Log failure, continue, mark as Completed (with warnings) |

### 6.2 Retry Logic with Exponential Backoff

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=10)
)
def execute_action_with_retry(action, spec):
    """Execute action with automatic retries"""
    return execute_action(action, spec)
```

### 6.3 Dead Letter Queue (DLQ)

```python
# Store failed ThreatResponses in a separate ConfigMap for manual review
def send_to_dlq(body, reason):
    """Log unrecoverable threat to DLQ"""
    v1 = kubernetes.client.CoreV1Api()
    
    dlq_cm = v1.read_namespaced_config_map(
        'ids-dlq', 'smart-city'
    )
    
    dlq_entry = {
        'name': body['metadata']['name'],
        'reason': reason,
        'timestamp': datetime.utcnow().isoformat()
    }
    
    dlq_cm.data[body['metadata']['name']] = json.dumps(dlq_entry)
    v1.patch_namespaced_config_map('ids-dlq', 'smart-city', dlq_cm)
```

---

## 7. Testing Strategy

### 7.1 Unit Tests (pytest)

```python
# tests/test_operator_handlers.py

import pytest
from unittest.mock import MagicMock, patch
from kopf_operator.handlers import validate_threat, execute_actions

def test_validate_threat_success():
    """Test successful threat validation"""
    body = {
        'metadata': {'name': 'test-threat', 'namespace': 'smart-city'},
        'spec': {
            'alertId': 'alert-123',
            'targetPod': {'name': 'test-pod', 'namespace': 'smart-city'},
            'llmRecommendation': {'severity': 9},
            'actions': []
        }
    }
    
    with patch('kubernetes.client.CoreV1Api') as mock_api:
        mock_api.return_value.read_namespaced_pod.return_value = MagicMock()
        
        # Should succeed
        validate_threat(body, body['spec'], {})

def test_validate_threat_pod_not_found():
    """Test validation when target pod doesn't exist"""
    from kubernetes.client.rest import ApiException
    
    body = {
        'metadata': {'name': 'test-threat', 'namespace': 'smart-city'},
        'spec': {
            'targetPod': {'name': 'nonexistent', 'namespace': 'smart-city'},
            'llmRecommendation': {'severity': 9}
        }
    }
    
    with patch('kubernetes.client.CoreV1Api') as mock_api:
        mock_api.return_value.read_namespaced_pod.side_effect = ApiException()
        
        with pytest.raises(Exception):  # TemporaryError expected
            validate_threat(body, body['spec'], {})
```

### 7.2 Integration Tests (K3s Cluster)

```python
# tests/integration/test_operator_e2e.py

@pytest.mark.integration
def test_threat_response_full_lifecycle(k3s_cluster):
    """Test full ThreatResponse lifecycle in real K3s cluster"""
    # Create test pod
    pod_name = "test-camera-pod"
    k3s_cluster.create_pod(pod_name, "smart-city")
    
    # Create ThreatResponse CRD
    threat_response = {
        'apiVersion': 'ids.smartcity.local/v1alpha1',
        'kind': 'ThreatResponse',
        'metadata': {'name': 'test-ddos'},
        'spec': {
            'alertId': 'test-123',
            'targetPod': {'name': pod_name, 'namespace': 'smart-city'},
            'llmRecommendation': {'severity': 9},
            'actions': [{'type': 'isolate', 'params': {}}]
        }
    }
    
    k3s_cluster.apply(threat_response)
    
    # Wait for operator to process (max 10 seconds)
    for _ in range(10):
        status = k3s_cluster.get_threat_response_status('test-ddos')
        if status['phase'] == 'Completed':
            break
        time.sleep(1)
    
    assert status['phase'] == 'Completed'
    assert any(a['type'] == 'isolate' for a in status.get('appliedActions', []))
```

---

## 8. Monitoring & Observability

### 8.1 Prometheus Metrics (Kopf exports automatically)

```python
# Additional custom metrics
from prometheus_client import Counter, Histogram, Gauge

threats_processed = Counter(
    'ids_threats_processed_total',
    'Total ThreatResponses processed',
    ['outcome']  # Labels: success, failed, skipped
)

threat_latency = Histogram(
    'ids_threat_execution_seconds',
    'Threat response execution time',
    buckets=(1, 5, 10, 30, 60, 300)
)

active_threats = Gauge(
    'ids_active_threats_count',
    'Currently executing threats'
)
```

### 8.2 Grafana Dashboard

Dashboard should display:
- ✅ Threats processed (success rate, latency)
- ✅ Active threat executions
- ✅ Failed actions (by type)
- ✅ Rollback events
- ✅ Operator health (uptime, restarts)

---

## 9. Deployment Phases

### Phase 1: Research & Design (Week 1) ✅ **Current**
- [x] Framework selection (Kopf)
- [x] CRD schema design
- [x] Architecture diagrams
- [x] Error handling strategy

### Phase 2: Implementation (Week 2-3)
- [ ] Implement Kopf handlers
- [ ] Create ThreatResponse CRD
- [ ] Integrate with FastAPI backend
- [ ] Add unit & integration tests

### Phase 3: Testing (Week 3-4)
- [ ] Deploy to K3s cluster
- [ ] Run attack simulations
- [ ] Verify auto-rollback
- [ ] Performance testing

### Phase 4: Observability (Week 4-5)
- [ ] Add Prometheus metrics
- [ ] Build Grafana dashboards
- [ ] Document operational procedures
- [ ] Create runbooks

### Phase 5: Documentation & Demo (Week 5)
- [ ] Complete API documentation
- [ ] Record demo video
- [ ] Prepare presentation slides
- [ ] Submit Capstone II final report

---

## 10. Next Steps (OPS-2: Implementation)

1. **Create CRD manifest** → Save to `k8s-manifests/threat-response-crd.yaml`
2. **Bootstrap Kopf project** → `kopf-init` in `services/ids-operator/`
3. **Implement handlers** → Port logic from `k8s_automation.py`
4. **Build Docker image** → Test locally with K3s
5. **Deploy operator** → Test with sample ThreatResponse objects

---

## References

- [Kopf Documentation](https://kopf.readthedocs.io/)
- [Kubernetes Operator Best Practices](https://kubernetes.io/docs/concepts/extend-kubernetes/operator/)
- [CRD Best Practices](https://kubernetes.io/docs/tasks/extend-kubernetes/custom-resources/custom-resource-definitions/)
- [K3s Documentation](https://docs.k3s.io/)
- [RBAC Best Practices](https://kubernetes.io/docs/reference/access-authn-authz/rbac/)

---

**Document Status:** Design Phase Complete  
**Next Review:** After OPS-2 (Implementation) checkpoint
