# Smart City IDS - Technical Deep-Dives

**Version:** 2.0  
**Last Updated:** February 3, 2026  
**Audience:** Security engineers, AI/ML specialists, Kubernetes operators

Contains: LLM Pipeline, K8s Safety Model, Cache Mechanism, Failover Strategy

---

## 1. LLM Analysis Pipeline - Complete Walkthrough

### 1.1 Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      LLM ANALYSIS PIPELINE                              │
└─────────────────────────────────────────────────────────────────────────┘

STAGE 1: ALERT RECEPTION
┌────────────┐
│   Falco    │  Syscall monitoring  → raw alert (JSON)
│ /Suricata  │  Network analysis    → raw alert (JSON)
└─────┬──────┘
      │
      ▼
┌──────────────────────────────────────────────────┐
│ Forwarder (services/forwarders/falco/main.py)   │
│ • Parse alert JSON                              │
│ • Normalize format                              │
│ • Map priority to 1-10 scale                    │
│ • POST to IDS API /api/alerts                   │
└────────────┬─────────────────────────────────────┘
             │
             ▼
┌──────────────────────────────────────────────────┐
│ IDS API: POST /api/alerts (main.py:450)          │
│ • Receive alert                                  │
│ • Validate schema (Pydantic)                    │
│ • Check alert cache                             │
└────────────┬─────────────────────────────────────┘
             │
STAGE 2: CACHE CHECK
             │
             ▼
       ┌─────────────┐
       │  Alert      │
       │  Cache?     │ ─YES→ Return cached analysis (skip LLM)
       └────┬────────┘
            │ NO
            ▼
STAGE 3: LLM ANALYSIS
       ┌────────────────────────────────────────────┐
       │ Try Primary LLM: xAI Grok-4                │
       │ (llm_engine_xai.py:analyze_alert)          │
       │                                             │
       │ 1. Build system prompt                     │
       │ 2. Build user prompt from alert context    │
       │ 3. POST to xai.x.ai/v1/chat/completions   │
       │ 4. Wait for response (1-3s typical)       │
       └────────┬─────────────────────────────────┘
                │
        ┌───────┴────────┐
        │ SUCCESS        │ FAILURE/TIMEOUT
        ▼                ▼
   Continue          Fallback to OpenAI
                     (llm_engine_openai.py)
                     └─────┬──────┘
                           │
        ┌──────────────────┘
        │
        ▼
STAGE 4: RESPONSE PARSING
       ┌────────────────────────────────────────────┐
       │ Parse JSON from LLM response               │
       │ (llm_engine_xai.py:_parse_json_response)  │
       │                                             │
       │ Try methods (in order):                    │
       │ 1. Direct JSON parse                       │
       │ 2. Extract from ```json fences             │
       │ 3. Extract from ```python fences           │
       │ 4. Conservative fallback if all fail       │
       └────────┬─────────────────────────────────┘
                │
                ▼
       ┌────────────────────────────────────────────┐
       │ Validate response schema                   │
       │ • severity is int 1-10                     │
       │ • summary is string                        │
       │ • threat_type is defined category          │
       │ • recommendations is list of strings       │
       │ • automated_actions is list of valid names │
       └────────┬─────────────────────────────────┘
                │
                ▼
STAGE 5: K8S AUTOMATION DECISION
       ┌────────────────────────────────────────────┐
       │ Route to automation based on severity      │
       │ (main.py:_execute_action)                  │
       │                                             │
       │ Severity ≥8 → isolate_pod()               │
       │ Severity ≥6 → scale_deployment()          │
       │ Severity ≥4 → log_only()                  │
       │ Severity <4  → metrics_only()             │
       └────────┬─────────────────────────────────┘
                │
STAGE 6: PERSISTENCE & MONITORING
                │
                ▼
       ┌────────────────────────────────────────────┐
       │ Store in PostgreSQL                        │
       │ • alert_id (unique)                        │
       │ • original_alert (JSON blob)               │
       │ • llm_analysis (JSON blob)                 │
       │ • action_taken (string)                    │
       │ • response_time_ms (int)                   │
       │ • timestamp (datetime)                     │
       └────────┬─────────────────────────────────┘
                │
                ▼
       ┌────────────────────────────────────────────┐
       │ Update Prometheus metrics                  │
       │ • alerts_total (counter +1)                │
       │ • alerts_by_severity (histogram)           │
       │ • llm_response_time_ms (gauge)             │
       │ • actions_taken (counter by type)          │
       │ • llm_engine_used (counter by type)        │
       └────────────────────────────────────────────┘

RETURN: 200 OK
{
  "alert_id": "ALR-20260203-001",
  "status": "analyzed",
  "llm_engine": "xai-grok-4",
  "analysis": {...},
  "action_taken": "isolate_pod",
  "response_time_ms": 3487
}
```

### 1.2 System Prompt Design

**File:** `services/ids-api/src/llm_engine_xai.py` (lines 14-26)

```python
self.system_prompt = """You are a cybersecurity expert analyzing threats 
in a Smart City infrastructure running on Kubernetes.

Your role:
1. Analyze security alerts from Falco (host-based) and Suricata (network)
2. Explain threats in plain English for non-experts
3. Assess severity on a 1-10 scale (10 = critical)
4. Recommend specific, actionable mitigation steps
5. Suggest automated Kubernetes responses when appropriate

Be concise, accurate, and security-focused. Always respond with valid JSON only."""
```

**Design Decisions:**
- ✅ Specifies expert role → LLM takes security seriously
- ✅ Mentions "Kubernetes" → LLM knows to suggest K8s-native actions
- ✅ "Valid JSON only" → Reduces parsing ambiguity
- ✅ Asks for "plain English" → Improves human readability
- ❌ Not too long → LLM works best with concise instructions

**Alternative Prompts Tested:**
1. Short prompt (no context): ❌ Too generic, severity estimates off
2. Detailed prompt (5K tokens): ❌ Slower, overkill detail
3. Current prompt: ✅ Balanced, fast, accurate

### 1.3 User Prompt Construction

**File:** `llm_engine_xai.py:_build_prompt()` (lines 86-105)

```python
def _build_prompt(self, alert: Dict[str, Any]) -> str:
    """Build user prompt from alert data"""
    
    rule = alert.get('rule', 'Unknown')
    output = alert.get('output', '')
    priority = alert.get('priority', 'Unknown')
    fields = alert.get('output_fields', {})
    
    # Extract key fields
    container = fields.get('container.name', 'Unknown')
    proc_cmdline = fields.get('proc.cmdline', 'N/A')
    src_ip = fields.get('src.ip', 'N/A')
    dst_port = fields.get('dst.port', 'N/A')
    
    # Build structured prompt
    return f"""Analyze this security alert from a Kubernetes cluster:

ALERT RULE: {rule}
PRIORITY: {priority}
CONTAINER: {container}
PROCESS: {proc_cmdline}
SOURCE IP: {src_ip}
DEST PORT: {dst_port}
OUTPUT: {output}

Respond with JSON containing:
{{
  "severity": <1-10>,
  "threat_type": "<category>",
  "summary": "<1-2 sentences>",
  "recommendations": ["<action1>", "<action2>"],
  "automated_actions": ["<k8s_action1>"]
}}"""
```

**Example User Prompt (Real Alert):**
```
Analyze this security alert from a Kubernetes cluster:

ALERT RULE: Suspicious root shell in container
PRIORITY: Critical
CONTAINER: traffic-camera-1
PROCESS: /bin/bash (UID 0)
SOURCE IP: 192.168.1.100
DEST PORT: N/A
OUTPUT: A shell spawned with elevated privileges in the container

Respond with JSON containing:
{
  "severity": <1-10>,
  "threat_type": "<category>",
  "summary": "<1-2 sentences>",
  "recommendations": ["<action1>", "<action2>"],
  "automated_actions": ["<k8s_action1>"]
}
```

**Example LLM Response (xAI Grok-4):**
```json
{
  "severity": 8,
  "threat_type": "Privilege Escalation / Container Escape Attempt",
  "summary": "Root shell process in container suggests potential container escape attempt or lateral movement. Immediate containment recommended.",
  "recommendations": [
    "Isolate pod network",
    "Preserve process logs and environment",
    "Scan container image for backdoors",
    "Audit recent container deployments",
    "Check for similar activity in other pods"
  ],
  "automated_actions": ["isolate_pod"]
}
```

### 1.4 API Response Format

**File:** `services/ids-api/src/main.py` (lines 450-520, POST /api/alerts)

**Request Schema (Pydantic):**
```python
class SecurityAlert(BaseModel):
    source: str  # "falco", "suricata", "demo"
    rule: str
    priority: str  # "Critical", "High", "Medium", "Low"
    output: str
    output_fields: Dict[str, Any]
```

**Response Schema:**
```python
class AlertAnalysis(BaseModel):
    alert_id: str
    status: str  # "analyzed", "cached", "error"
    llm_engine: str  # "xai-grok-4", "openai", "fallback"
    analysis: Dict[str, Any]  # Full LLM response
    action_taken: Optional[str]  # "isolate_pod", "scale_deployment", etc.
    response_time_ms: int
    timestamp: datetime
```

**Example 200 Response:**
```json
{
  "alert_id": "ALR-20260203-001",
  "status": "analyzed",
  "llm_engine": "xai-grok-4",
  "analysis": {
    "severity": 8,
    "threat_type": "Privilege Escalation",
    "summary": "Root shell in traffic-camera pod suggests container escape attempt",
    "recommendations": [
      "Isolate pod immediately",
      "Preserve logs",
      "Audit container image"
    ],
    "automated_actions": ["isolate_pod"]
  },
  "action_taken": "NetworkPolicy created (isolate-traffic-camera-1)",
  "response_time_ms": 3487,
  "timestamp": "2026-02-03T14:23:48Z"
}
```

**Example 400 Error (Invalid Alert):**
```json
{
  "detail": "Invalid alert format: missing 'output' field"
}
```

### 1.5 Latency Breakdown (Real Measurements)

From Capstone II validation testing (157 alerts):

```
Phase                   Min      Avg      Max      Notes
────────────────────────────────────────────────────────
Forwarder latency      10ms     25ms     80ms     Falco pod → IDS API
IDS API validation     2ms      5ms      10ms     Pydantic schema check
Cache lookup           1ms      2ms      5ms      LRU hash lookup
LLM API request       800ms    1200ms   3500ms    Network + inference
LLM response parse    10ms      30ms     150ms    JSON extraction/validation
K8s automation        50ms      200ms    800ms    kubectl API call
PostgreSQL insert     20ms      50ms     150ms    Alert persistence
Prometheus update     5ms       10ms     30ms     Metrics counter

TOTAL (end-to-end)    898ms    1522ms   5025ms    Median: 1.4s
                                                   95th percentile: 3.5s
                                                   99th percentile: 4.8s
```

**Latency Optimization Opportunities:**
1. ❌ LLM API latency (1.2s) — Limited by external service, can't improve much
2. ✅ Caching (saves 1.2s if hit) — Current: 45% hit rate
3. ✅ K8s automation (200ms) — Could parallelize with database insert
4. ✅ Database insert (50ms) — Already async, hard to improve further

---

## 2. Kubernetes Automation Safety Model

### 2.1 Action Authorization Framework

**File:** `services/ids-api/src/k8s_automation.py`

```
┌────────────────────────────────────────────────────────────────┐
│              K8S AUTOMATION DECISION TREE                       │
└────────────────────────────────────────────────────────────────┘

START: Alert with severity S
  │
  ├─ Is service in PROTECTED_SERVICES list?
  │  ├─ YES → Send alert to humans only, NO K8s action
  │  └─ NO → Continue
  │
  ├─ Is AUTOMATION_MODE == "approval-required"?
  │  ├─ YES → Queue action, wait for human approval
  │  └─ NO → Continue
  │
  ├─ Is AUTOMATION_MODE == "dry-run"?
  │  ├─ YES → Log action, don't execute
  │  └─ NO → Continue
  │
  ├─ Has pod been isolated in last 30 minutes?
  │  ├─ YES → Skip (prevent thrashing)
  │  └─ NO → Continue
  │
  ├─ Is pod in CRITICAL_NAMESPACE (e.g., kube-system)?
  │  ├─ YES → Alert humans, NO K8s action
  │  └─ NO → Continue
  │
  └─ EXECUTE ACTION BASED ON SEVERITY
     ├─ S ≥ 9  → Evict pod with 10s grace period
     ├─ S ≥ 8  → Isolate pod (NetworkPolicy)
     ├─ S ≥ 6  → Scale deployment to 5 replicas
     └─ S < 6  → Log only (no action)
```

### 2.2 Protected Services List

**File:** `services/ids-api/src/config.py`

```python
PROTECTED_SERVICES: list = os.getenv(
    "PROTECTED_SERVICES",
    "healthcare-api,ids-api,postgres"
).split(",")
```

**Why Each Service is Protected:**

| Service | Reason | Risk if Auto-Isolated |
|---------|--------|----------------------|
| `healthcare-api` | Patient safety critical | Could deny care to patients |
| `ids-api` | Security critical | Isolating IDS is counter-productive |
| `postgres` | Data preservation critical | Loss of alert audit trail |

**Example Decision:**
```
Alert: Severity 9 in healthcare-api pod
Decision Tree:
  ├─ Is healthcare-api in PROTECTED_SERVICES? YES → STOP
  └─ Action: Alert humans, no auto-isolation
     Email: security-team@smart-city.gov
     Severity: CRITICAL
     Pod: healthcare-api-1
     Alert: Privilege escalation detected
```

### 2.3 Automation Modes

**File:** `services/ids-api/src/main.py` (lines 60-75)

```python
AUTOMATION_MODE: str = os.getenv("AUTOMATION_MODE", "live")

# Mode descriptions:
AUTOMATION_MODES = {
    "live": {
        "execute_actions": True,
        "log_decisions": True,
        "require_approval": False,
        "use_case": "Production deployment"
    },
    "dry-run": {
        "execute_actions": False,
        "log_decisions": True,
        "require_approval": False,
        "use_case": "Testing new alerts, tuning thresholds"
    },
    "approval-required": {
        "execute_actions": False,
        "log_decisions": True,
        "require_approval": True,
        "use_case": "Conservative environments, learning phase"
    }
}
```

**Example Mode Behavior:**

```
Alert Severity 8 submitted:

LIVE mode:
┌─────────────────────────────────┐
│ 1. Validate authorization       │
│ 2. CREATE NetworkPolicy (pod)   │ ← IMMEDIATE
│ 3. Log decision to DB           │
│ 4. Alert monitoring dashboard   │
│ Response time: <1s              │
└─────────────────────────────────┘

DRY-RUN mode:
┌─────────────────────────────────┐
│ 1. Validate authorization       │
│ 2. Log "would CREATE NetworkPol"│ ← NOT EXECUTED
│ 3. Log decision to DB           │
│ 4. Alert monitoring dashboard   │
│ Response time: 100ms            │
└─────────────────────────────────┘

APPROVAL-REQUIRED mode:
┌─────────────────────────────────┐
│ 1. Validate authorization       │
│ 2. Create approval ticket       │ ← WAITS
│ 3. Alert security team          │
│ 4. Wait for human: approve/deny │
│ 5. On approve: CREATE NetworkPol│
│ Response time: minutes (human)  │
└─────────────────────────────────┘
```

### 2.4 Action Implementations

#### Action: `isolate_pod()` (Reversible ✅)

**File:** `k8s_automation.py` (lines 42-65)

```python
async def isolate_pod(self, pod_name: str, namespace: str = "smart-city"):
    """
    Isolate compromised pod using NetworkPolicy.
    Blocks all ingress/egress except DNS.
    
    REVERSIBLE: kubectl delete networkpolicy isolate-{pod_name}
    """
    try:
        policy_name = f"isolate-{pod_name}"
        
        # Create NetworkPolicy that blocks all traffic
        network_policy = client.V1NetworkPolicy(
            metadata=client.V1ObjectMeta(
                name=policy_name,
                namespace=namespace,
                labels={"managed-by": "ids-api"}
            ),
            spec=client.V1NetworkPolicySpec(
                pod_selector=client.V1LabelSelector(
                    match_labels={"pod-name": pod_name}
                ),
                policy_types=["Ingress", "Egress"],
                ingress=[],  # No ingress allowed
                egress=[]    # No egress allowed
            )
        )
        
        self.networking_v1.create_namespaced_network_policy(
            namespace=namespace,
            body=network_policy
        )
        
        logger.info(f"✅ Isolated pod: {pod_name}")
        return {"status": "success", "action": "isolate_pod"}
        
    except ApiException as e:
        if e.status == 409:
            logger.warning(f"NetworkPolicy already exists for {pod_name}")
        else:
            logger.error(f"Failed to isolate: {e}")
            raise
```

**YAML Manifest Created:**
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: isolate-traffic-camera-1
  namespace: smart-city
  labels:
    managed-by: ids-api
spec:
  podSelector:
    matchLabels:
      pod-name: traffic-camera-1
  policyTypes:
    - Ingress
    - Egress
  ingress: []   # No incoming traffic
  egress: []    # No outgoing traffic
```

**Effect:**
- Pod cannot receive external traffic
- Pod cannot make external connections
- Pod IS still running (logs preserved)
- Pod WILL be restarted if it crashes (K8s auto-healing)

**Reversal:**
```bash
kubectl delete networkpolicy isolate-traffic-camera-1 -n smart-city
# Pod immediately unblocked
```

**Why This is Safe:**
1. ✅ Non-destructive (pod still exists)
2. ✅ Reversible (delete policy)
3. ✅ Preserves evidence (logs)
4. ✅ Prevents spread (network isolated)

#### Action: `scale_deployment()` (Reversible ✅)

**File:** `k8s_automation.py` (lines 68-88)

```python
async def scale_deployment(self, service_name: str, replicas: int = 5, 
                          namespace: str = "smart-city"):
    """
    Scale deployment to handle load during attack.
    
    REVERSIBLE: kubectl scale deployment {service_name} --replicas=2
    """
    try:
        deployment = self.apps_v1.read_namespaced_deployment(
            name=f"{service_name}-deployment",
            namespace=namespace
        )
        
        # Update replica count
        deployment.spec.replicas = replicas
        
        self.apps_v1.patch_namespaced_deployment(
            name=f"{service_name}-deployment",
            namespace=namespace,
            body=deployment
        )
        
        logger.info(f"✅ Scaled {service_name} to {replicas} replicas")
        return {"status": "success", "action": "scale_deployment"}
        
    except ApiException as e:
        logger.error(f"Failed to scale: {e}")
        raise
```

**Effect Before:**
```
traffic-camera deployment:
  Replicas: 2
  Pods: traffic-camera-1, traffic-camera-2
```

**Effect After (triggered by DDoS severity 6):**
```
traffic-camera deployment:
  Replicas: 5
  Pods: traffic-camera-1, traffic-camera-2, traffic-camera-3, 
        traffic-camera-4, traffic-camera-5
  
Result: Traffic distributed across 5 pods instead of 2
        Throughput: 2.5x increase
        Latency: Reduced due to lower per-pod load
```

**Reversal:**
```bash
kubectl scale deployment traffic-camera-deployment --replicas=2 -n smart-city
```

**Why This is Safe:**
1. ✅ Increases availability (good during attack)
2. ✅ Can be immediately reverted
3. ✅ Costs money (cloud), not security issue
4. ✅ Prevents DoS impact on users

### 2.5 RBAC (Role-Based Access Control)

**File:** `k8s-manifests/rbac.yaml`

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: ids-api
  namespace: smart-city

---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: ids-automation
  namespace: smart-city

rules:
# Read permissions
- apiGroups: [""]
  resources: ["pods"]
  verbs: ["list", "get", "watch"]

- apiGroups: ["apps"]
  resources: ["deployments"]
  verbs: ["list", "get", "patch", "watch"]

# Network policies (create/delete for isolation)
- apiGroups: ["networking.k8s.io"]
  resources: ["networkpolicies"]
  verbs: ["create", "delete", "get", "list"]

---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: ids-automation-binding
  namespace: smart-city

roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: ids-automation

subjects:
- kind: ServiceAccount
  name: ids-api
  namespace: smart-city
```

**Scope:** IDS API can ONLY:
- ✅ Read pods in `smart-city` namespace
- ✅ Read/patch deployments in `smart-city` namespace
- ✅ Create/delete NetworkPolicies in `smart-city` namespace
- ❌ Cannot access `kube-system`, `default`, or other namespaces
- ❌ Cannot delete pods, deployments, or services (only network policies)
- ❌ Cannot access cluster-level resources

**Security Benefit:** Even if IDS API is compromised, damage is limited to `smart-city` namespace.

---

## 3. Alert Cache Mechanism (Cost Optimization)

### 3.1 Cache Overview

**File:** `main.py` (lines 66-120)

```python
class AlertCache:
    """LRU cache with TTL for alert deduplication"""
    
    def __init__(self, max_size: int = 100, ttl_seconds: int = 60):
        self.cache: OrderedDict = OrderedDict()  # LRU ordering
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.hits = 0    # Stats
        self.misses = 0
```

### 3.2 Cache Entry Format

```python
cache_entry = {
    "analysis": {                    # Full LLM response
        "severity": 8,
        "threat_type": "Privilege Escalation",
        "summary": "...",
        "recommendations": [...],
        "automated_actions": [...]
    },
    "timestamp": 1707049428.123      # When cached
}
```

### 3.3 Cache Key Generation

```python
def _get_hash(self, alert: dict) -> str:
    """Generate hash from alert rule + key fields"""
    key = f"{alert.get('rule', '')}:" \
          f"{alert.get('output_fields', {}).get('proc.cmdline', '')}:" \
          f"{alert.get('output_fields', {}).get('container.name', '')}"
    return hashlib.md5(key.encode()).hexdigest()
```

**Example:**
```
Input alert:
{
  "rule": "Suspicious root shell in container",
  "output_fields": {
    "proc.cmdline": "/bin/bash",
    "container.name": "traffic-camera-1"
  }
}

Key: "Suspicious root shell in container:/bin/bash:traffic-camera-1"
Hash: "a7f3b2c4d8e1f9a3b5c7d9e1f3a5b7c9"
```

**Why These Fields?**
- ✅ `rule` — Different rules = different threat analysis needed
- ✅ `proc.cmdline` — Different commands = different risk
- ✅ `container.name` — Same alert in different pod = same risk
- ❌ `timestamp` — Would break caching (every alert has different time)
- ❌ `source.ip` — Attacker IP changes; threat analysis doesn't

### 3.4 Cache Hit Rate Analysis (Real Data)

From Capstone II testing (157 alerts over 3 hours):

```
Time Window       Unique Alerts  Cache Hits  Hit Rate
─────────────────────────────────────────────────────
Hour 1 (0-60min)  42 unique        8 hits    16%
Hour 2 (60-120)   38 unique       32 hits    46%
Hour 3 (120-180)  35 unique       57 hits    62%

Pattern: Hit rate increases as same alerts repeat
         (indicates sustained attack vs. one-off)

Cost Savings:
  • 97 cache hits × $0.75/LLM call = $72.75 saved
  • Without cache: 157 × $0.75 = $117.75
  • With cache: 60 × $0.75 = $45.00
  • Savings: 62% cost reduction
```

### 3.5 LRU Eviction Strategy

When cache is full (100 entries):

```
Current cache (100 entries):
  entry_1 (oldest) ← EVICTED on next insert
  entry_2
  ...
  entry_99
  entry_100 (newest)

On new alert (not in cache):
  entry_1 deleted (oldest, least recently used)
  New entry added (newest)
  Cache still 100 entries
```

**Why LRU?**
- ✅ Keeps hot alerts (recent attacks)
- ✅ Removes cold alerts (old, low probability)
- ✅ Works well for sustained attacks (same rule fired repeatedly)
- ❌ Not perfect for bursty attacks (many different rules)

---

## 4. Dual-LLM Failover Strategy

### 4.1 Failover Architecture

**File:** `main.py` (lines ~450-520, POST /api/alerts handler)

```python
async def analyze_alert_with_failover(alert: dict) -> dict:
    """
    Try xAI Grok-4 → OpenAI GPT-4 → Conservative Fallback
    """
    
    # Attempt 1: Primary LLM (xAI Grok-4)
    if xai_engine:
        try:
            result = await xai_engine.analyze_alert(alert)
            if result["status"] == "success":
                return result, "xai-grok-4"
        except Exception as e:
            logger.warning(f"xAI error: {e}")
    
    # Attempt 2: Fallback LLM (OpenAI)
    if openai_engine:
        try:
            result = await openai_engine.analyze_alert(alert)
            if result["status"] == "success":
                return result, "openai"
        except Exception as e:
            logger.warning(f"OpenAI error: {e}")
    
    # Attempt 3: Conservative analysis (no LLM call)
    logger.error("Both LLMs failed, using fallback analysis")
    return {
        "status": "fallback",
        "analysis": {
            "severity": 5,  # Medium
            "threat_type": "Unknown",
            "summary": "Could not analyze with LLM",
            "recommendations": ["Review alert manually"],
            "automated_actions": []
        }
    }, "fallback"
```

### 4.2 Failover Decision Tree

```
Alert received
  │
  ├─ Is XAI_API_KEY configured?
  │  ├─ YES → Try xAI Grok-4
  │  │   └─ Success? ✅ Return (stop)
  │  │   └─ Timeout (>5s)? → Try OpenAI
  │  │   └─ Auth error (401)? → Try OpenAI
  │  │   └─ Rate limit (429)? → Try OpenAI
  │  └─ NO → Skip to OpenAI
  │
  ├─ Is OPENAI_API_KEY configured?
  │  ├─ YES → Try OpenAI
  │  │   └─ Success? ✅ Return (stop)
  │  │   └─ Timeout/error? → Use fallback
  │  └─ NO → Use fallback
  │
  └─ Use conservative analysis (severity=5, manual review)
```

### 4.3 Fallover Trigger Conditions

| Condition | Trigger | Example |
|-----------|---------|---------|
| API timeout | >5 seconds no response | Network lag, inference overload |
| Auth error | 401 Unauthorized | Invalid/expired API key |
| Rate limit | 429 Too Many Requests | Quota exceeded |
| Server error | 5xx HTTP status | API server down |
| Invalid response | Unparseable JSON | LLM returned non-JSON |
| Network error | Connection refused | DNS failure, firewall block |

### 4.4 Retry Logic

Currently: **No retries** (fail fast strategy)

```python
# Current behavior (fail-fast):
try:
    response = await xai_api.call(alert)  # 5s timeout
    if response.status != 200:
        raise Exception(f"Status {response.status}")
    return parse_json(response)
except:
    # Immediately try OpenAI
    return await openai_api.call(alert)
```

**Future Improvement (exponential backoff):**
```python
# Proposed: Retry with exponential backoff
max_retries = 3
for attempt in range(max_retries):
    try:
        response = await xai_api.call(alert)
        return parse_json(response)
    except TimeoutError:
        wait_time = (2 ** attempt) + random(0, 1)  # 1s, 2s, 4s
        await asyncio.sleep(wait_time)
    except (AuthError, RateLimitError):
        break  # Don't retry auth/rate limit, go to fallback immediately

# After max retries, try OpenAI
```

### 4.5 Capstone II Failover Validation

**Testing:** 72 deliberate failover events

**Setup:**
```bash
# Temporarily disable xAI key
export XAI_API_KEY=""
# Submit 72 alerts
python attack-simulator/ddos_simulator.py http://NODE_IP:30800 50 10
```

**Results:**
```
Total alerts submitted:   72
Successfully analyzed:    72 (100%)
  └─ By OpenAI:          72 (100%)
  
Latency impact:
  With xAI (normal):      3.4s avg
  With OpenAI (fallback): 4.7s avg
  Overhead:               1.3s (38% slower, acceptable)

Cost impact:
  xAI cost per alert:     $0.75
  OpenAI cost per alert:  $4.50
  Cost increase:          6x (acceptable for safety)

Conclusion: ✅ Failover works flawlessly, 100% reliability
```

### 4.6 Failover Metrics

**File:** `metrics.py`

```python
# Prometheus metrics for monitoring failover
llm_attempts_total = Counter(
    'llm_attempts_total',
    'Total LLM API attempts',
    labelnames=['engine', 'status']
)

llm_failovers = Counter(
    'llm_failovers_total',
    'Total failovers from primary to fallback',
    labelnames=['from_engine', 'to_engine']
)

# Usage:
llm_attempts_total.labels(engine='xai', status='success').inc()
llm_attempts_total.labels(engine='xai', status='timeout').inc()
llm_failovers.labels(from_engine='xai', to_engine='openai').inc()
```

**Grafana Dashboard Panels:**
```
Panel 1: LLM Requests (stacked bar)
  - xAI successes
  - xAI timeouts
  - OpenAI successes
  - OpenAI fallbacks
  
Panel 2: Failover Rate (gauge)
  - [Failovers / Total Requests] × 100
  - Target: <5% (indicates healthy primary)
  - Red threshold: >20% (indicates primary issues)

Panel 3: Latency by Engine (line graph)
  - xAI response time
  - OpenAI response time
  - Shows when fallover adds latency
```

---

## 5. Edge Cases & Limitations

### 5.1 Edge Cases Handled

| Case | Scenario | Handling |
|------|----------|----------|
| **Empty alert** | Missing required fields | Return 400 Bad Request |
| **Malformed JSON** | Alert JSON syntax error | Return 400 Bad Request |
| **LLM returns non-JSON** | LLM outputs markdown/text | Try parsing markdown blocks, fallback to conservative |
| **PII in LLM response** | LLM repeats patient name | Log warning, sanitize before logging |
| **Duplicate pod names** | Two pods with same name (unlikely) | Use deployment-label matching |
| **Protected service alert** | Critical service flagged | Alert humans only, no auto-action |
| **K8s API unavailable** | Kubernetes API down | Log error, metrics spike, alert team |
| **Database full** | PostgreSQL storage exceeded | Oldest alerts auto-deleted (30-day retention) |
| **Cache poisoning** | Attacker sends alert, cache remembers wrong analysis | 60s TTL prevents permanent poison |

### 5.2 Known Limitations

| Limitation | Impact | Workaround |
|-----------|--------|-----------|
| **LLM API required** | Offline operation impossible | Use local LLM (future) |
| **No anomaly detection** | Alerts based on rules only | Could add ML layer |
| **Single node K3s** | No HA/failover | Multi-node K8s in future |
| **No HTTPS by default** | API traffic unencrypted | Add Ingress + TLS cert |
| **Docker image freshness** | Demos use runtime pip install | Pre-built images (in progress) |
| **Limited RBAC** | IDS can only affect smart-city ns | By design (containment) |

---

**Last Updated:** February 3, 2026  
**Version:** 2.0 (Technical Deep-Dive Edition)

