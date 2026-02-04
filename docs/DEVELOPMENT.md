# Developer Guide

Guidelines for contributing to the Smart City IDS project.

---

## Getting Started

### Prerequisites

- Python 3.10+
- Docker
- kubectl
- K3s or Kubernetes cluster
- Git

### Clone and Setup

```bash
git clone https://github.com/YOUR-USERNAME/smart-city-ids.git
cd smart-city-ids

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install development dependencies
pip install -r requirements-dev.txt
```

---

## Project Structure

```
smart-city-ids/
├── scripts/
│   └── start-everything.sh        # Main deployment script
├── k8s-manifests/                 # Kubernetes configuration
│   ├── ids-api-FINAL.yaml         # IDS API deployment
│   ├── postgres-deployment.yaml   # Database
│   ├── prometheus-deployment.yaml # Metrics
│   └── ...
├── services/
│   ├── ids-api/
│   │   └── src/
│   │       ├── main.py            # FastAPI application
│   │       ├── config.py          # Configuration
│   │       ├── llm_engine_xai.py  # xAI integration
│   │       ├── llm_engine_openai.py  # OpenAI integration
│   │       ├── k8s_automation.py  # Kubernetes actions
│   │       └── requirements.txt
│   ├── forwarders/
│   │   ├── falco/                 # Falco alert handler
│   │   └── suricata/              # Suricata alert handler
│   └── iot-simulator/             # IoT device emulation
├── smart-city-services/           # Vulnerable demo apps
│   ├── traffic-camera/
│   ├── healthcare-api/
│   └── parking-system/
├── attack-simulator/              # Attack tools
│   ├── ddos_simulator.py
│   ├── privilege_escalation.py
│   └── ...
├── tests/                         # Test suite
│   ├── test_llm_engine.py
│   └── ...
├── docs/                          # Documentation
└── docker/                        # Docker images
```

---

## Core Modules

### IDS API (`services/ids-api/src/main.py`)

**Purpose:** Alert processing engine

**Key Endpoints:**
```python
POST /api/alerts           # Receive new alert
GET  /api/alerts           # Query stored alerts
GET  /api/analysis         # Query analyses
GET  /health               # Health check
GET  /metrics              # Prometheus metrics
```

**Alert Processing Pipeline:**
```python
@app.post("/api/alerts")
async def receive_alert(alert: Alert):
    # 1. Validate and store
    db_alert = db.save_alert(alert)
    
    # 2. Analyze with LLM
    analysis = await llm_engine.analyze_alert(alert)
    db.save_analysis(db_alert.id, analysis)
    
    # 3. Execute actions
    if analysis["severity"] >= 8:
        k8s.isolate_pod(alert.container_name)
        metrics.actions_executed["isolate_pod"].inc()
    
    # 4. Return response
    return {"status": "processed", "alert_id": db_alert.id}
```

**To modify:**
- **Alert validation:** Edit `Alert` class in `main.py`
- **LLM prompt:** Edit `llm_engine_xai.py` or `llm_engine_openai.py`
- **Automation thresholds:** Edit `config.py`
- **Kubernetes actions:** Edit `k8s_automation.py`

### LLM Engines (`services/ids-api/src/llm_engine_*.py`)

**xAI Integration (`llm_engine_xai.py`):**
```python
async def analyze_alert(alert: Alert) -> dict:
    # Build prompt with context
    system_prompt = "You are a cybersecurity analyst..."
    user_message = f"Analyze this security alert: {alert.rule}"
    
    # Call xAI Grok API
    response = await client.messages.create(
        model="grok-4",
        messages=[{"role": "user", "content": user_message}],
        system=system_prompt,
        max_tokens=500
    )
    
    # Parse JSON response
    analysis_json = extract_json_from_response(response.text)
    
    return {
        "severity": analysis_json["severity"],
        "threat_type": analysis_json["threat_type"],
        "summary": analysis_json["summary"],
        "recommendations": analysis_json["recommendations"],
        "automated_actions": analysis_json["automated_actions"]
    }
```

**To modify:**
- **System prompt:** Update in `analyze_alert()` method
- **Model selection:** Change `model="grok-4"` to preferred version
- **Temperature/sampling:** Add parameters to API call
- **Response parsing:** Update `extract_json_from_response()` logic

**Expected Response Format:**
```json
{
  "severity": 8,
  "threat_type": "Privilege Escalation",
  "summary": "Unauthorized shell access...",
  "recommendations": ["Isolate pod", "Collect logs"],
  "automated_actions": ["isolate_pod"]
}
```

### Kubernetes Automation (`services/ids-api/src/k8s_automation.py`)

**Available Actions:**
```python
async def isolate_pod(pod_name: str, namespace: str = "smart-city"):
    # Creates NetworkPolicy to block all traffic
    policy = NetworkPolicy(
        metadata=V1ObjectMeta(name=f"isolate-{pod_name}"),
        spec=V1NetworkPolicySpec(
            pod_selector=V1LabelSelector(
                match_labels={"pod": pod_name}
            ),
            policy_types=["Ingress", "Egress"]
        )
    )
    await client.create_namespaced_network_policy(
        namespace=namespace,
        body=policy
    )

async def scale_up(deployment_name: str, namespace: str = "smart-city"):
    # Increase replicas
    deployment = await client.read_namespaced_deployment(
        name=deployment_name,
        namespace=namespace
    )
    deployment.spec.replicas = min(
        deployment.spec.replicas + 1,
        MAX_REPLICAS
    )
    await client.patch_namespaced_deployment(...)

async def evict_pod(pod_name: str, namespace: str = "smart-city"):
    # Force pod termination
    await client.delete_namespaced_pod(
        name=pod_name,
        namespace=namespace,
        grace_period_seconds=0
    )
```

**To Add New Action:**
```python
async def custom_action(target: str):
    # 1. Validate input
    if not is_valid_target(target):
        raise ValueError(f"Invalid target: {target}")
    
    # 2. Execute Kubernetes API call
    result = await k8s_client.custom_action(target)
    
    # 3. Log action
    metrics.actions_executed["custom_action"].inc()
    
    # 4. Return result
    return {"action": "custom_action", "result": result}

# 5. Add to decision logic in main.py
if analysis["severity"] >= CUSTOM_THRESHOLD:
    k8s.custom_action(target)
```

---

## Adding Tests

### Unit Tests

```python
# tests/test_llm_engine.py

import pytest
from services.ids_api.src.llm_engine_xai import LLMEngineXAI

@pytest.fixture
def llm_engine():
    return LLMEngineXAI()

@pytest.mark.asyncio
async def test_analyze_alert_valid_json(llm_engine, monkeypatch):
    """Test that LLM response is parsed correctly"""
    
    # Mock the API response
    async def mock_api_call(*args, **kwargs):
        return MockResponse(text='''
        ```json
        {
          "severity": 8,
          "threat_type": "Privilege Escalation",
          "summary": "Shell access detected",
          "recommendations": ["Isolate"],
          "automated_actions": ["isolate_pod"]
        }
        ```
        ''')
    
    monkeypatch.setattr(llm_engine, "client.messages.create", mock_api_call)
    
    # Test parsing
    result = await llm_engine.analyze_alert(mock_alert())
    
    assert result["severity"] == 8
    assert result["threat_type"] == "Privilege Escalation"
```

### Integration Tests

```python
@pytest.mark.asyncio
async def test_full_alert_pipeline(client):
    """Test complete alert → analysis → action flow"""
    
    # 1. Send alert
    alert_data = {
        "rule": "Terminal shell in container",
        "priority": "Critical",
        "output": "Shell spawned",
        "output_fields": {"container.name": "traffic-camera-xyz"}
    }
    
    response = await client.post("/api/alerts", json=alert_data)
    assert response.status_code == 200
    alert_id = response.json()["alert_id"]
    
    # 2. Verify stored
    response = await client.get(f"/api/alerts/{alert_id}")
    assert response.status_code == 200
    
    # 3. Verify action executed
    response = await client.get(f"/api/actions?alert_id={alert_id}")
    assert len(response.json()) > 0
```

### Run Tests

```bash
# All tests
pytest -v

# Specific test
pytest tests/test_llm_engine.py::test_analyze_alert_valid_json -v

# With coverage
pytest --cov=services/ids-api/src tests/
```

---

## Code Style & Quality

### Style Guide

```bash
# Format code
black services/ids-api/src/

# Lint
flake8 services/ids-api/src/ --max-line-length=100

# Type checking
mypy services/ids-api/src/ --ignore-missing-imports

# All together
make lint
```

### Requirements

- Follow PEP 8
- Use type hints
- Document complex functions with docstrings
- Write tests for new features
- Keep functions focused and small

### Example Function

```python
async def analyze_alert(
    alert: Alert,
    timeout: int = 30
) -> Dict[str, Any]:
    """Analyze security alert using LLM.
    
    Args:
        alert: Security alert to analyze
        timeout: API request timeout in seconds
        
    Returns:
        Analysis dict with keys: severity, threat_type, summary,
        recommendations, automated_actions
        
    Raises:
        APIError: If LLM API call fails
        ValidationError: If response format is invalid
    """
    try:
        # Implementation
        pass
    except APIError as e:
        logger.error(f"LLM API failed: {e}")
        return fallback_analysis(alert)
```

---

## Making Changes

### Development Workflow

```bash
# 1. Create feature branch
git checkout -b feature/my-feature

# 2. Make changes
# ... edit files ...

# 3. Test locally
pytest tests/
python3 -m flake8 services/ids-api/src/
```

### Running Locally (Without K3s)

```bash
# Terminal 1: Start services
cd services/ids-api/src
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: Run tests
pytest tests/test_llm_engine.py -v

# Terminal 3: Send test alert
curl -X POST http://localhost:8000/api/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "rule": "Test Alert",
    "priority": "High",
    "output": "Test output",
    "output_fields": {"container.name": "test-pod"}
  }'
```

### Debugging

```python
# Add debug logging
import logging
logger = logging.getLogger(__name__)

logger.debug(f"Alert received: {alert}")
logger.info(f"LLM analysis started for alert {alert.id}")
logger.warning(f"LLM response took {latency}ms (SLO: 5s)")
logger.error(f"Failed to isolate pod: {error}")

# Run with debug logging
export LOG_LEVEL=DEBUG
uvicorn main:app --log-level debug
```

---

## Adding New Components

### New Service

```bash
# 1. Create service directory
mkdir -p services/my-service/src

# 2. Create Dockerfile
# Build image

# 3. Create K8s manifest
# Add to k8s-manifests/

# 4. Update deployment script
# Add service deployment to scripts/start-everything.sh
```

### New Vulnerable App

```bash
# 1. Create app
mkdir -p smart-city-services/my-app
cd smart-city-services/my-app

# 2. Create Flask app with vulnerability
# vulnerability_example.py

# 3. Create Dockerfile
# Dockerfile

# 4. Add to services-no-build.yaml manifest

# 5. Update start script
```

### New Security Rule

```bash
# 1. Create Falco rule
# Edit k8s-manifests/falco-rules.yaml

- rule: Custom Suspicious Behavior
  desc: Description of what triggers this rule
  condition: >
    spawned_process and
    container and
    proc.name in (suspicious_binary, another_binary)
  output: >
    Suspicious process spawned
    (user=%user.name command=%proc.cmdline container_id=%container.id)
  priority: WARNING

# 2. Rebuild Falco image
docker build -f docker/falco/Dockerfile .

# 3. Test with attack simulator
python3 attack-simulator/ddos_simulator.py ...
```

---

## Deployment for Development

### Quick Deploy with Changes

```bash
# 1. Build and push image
docker build -t my-registry/smart-city-ids:latest .
docker push my-registry/smart-city-ids:latest

# 2. Update manifest with new image tag
# Edit k8s-manifests/ids-api-FINAL.yaml
# Change image: to point to new version

# 3. Redeploy
kubectl set image deployment/ids-api \
  ids-api=my-registry/smart-city-ids:latest \
  -n smart-city

# 4. Watch rollout
kubectl rollout status deployment/ids-api -n smart-city
```

### Local Testing with Docker Compose

```bash
# Create docker-compose.yml for local testing
version: '3'
services:
  ids-api:
    build: ./services/ids-api
    ports:
      - "8000:8000"
    environment:
      - XAI_API_KEY=${XAI_API_KEY}
  
  postgres:
    image: postgres:15
    environment:
      - POSTGRES_PASSWORD=password
    ports:
      - "5432:5432"

# Run
docker-compose up

# Test
curl http://localhost:8000/health
```

---

## Pull Request Process

1. **Create PR** with clear title and description
2. **Link issues** - Reference related GitHub issues
3. **Add tests** - All new code must have tests
4. **Run checks** - Ensure all CI checks pass
5. **Code review** - Address reviewer feedback
6. **Squash commits** - Clean up commit history
7. **Merge** - Maintainer merges to main

### PR Template

```markdown
## Description
Brief summary of changes

## Related Issues
Closes #123

## Changes
- Added feature X
- Fixed bug Y
- Updated documentation

## Testing
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Deployed and tested on K3s
- [ ] No regressions in existing functionality

## Screenshots (if UI changes)
[Optional screenshots]
```

---

## Documentation

### Update docs when you:
- Add new API endpoint
- Change configuration options
- Add new deployment feature
- Fix significant bug
- Change architecture

### Documentation Format

```markdown
## New Feature Title

**Purpose:** What does this feature do?

**Location:** Where in the codebase?

**Usage:**
\`\`\`python
# Example code
\`\`\`

**Configuration:**
| Option | Default | Description |
|--------|---------|-------------|
| option1 | value1 | What it does |

**See Also:**
- [Related Doc](link)
```

---

## Getting Help

- **Questions:** Open GitHub Discussions
- **Bugs:** Create GitHub Issue with reproduction steps
- **Design Discussion:** Start a Discussion for architecture questions

---

## Contributors

- Smart City IDS Development Team
- Contributors welcome! See [CONTRIBUTING.md](CONTRIBUTING.md)

---

**Last Updated:** January 2025  
**Maintained By:** Smart City IDS Team
