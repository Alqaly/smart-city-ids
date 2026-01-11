# Capstone 2: Architecture Blueprint & Migration Guide
**Version:** 1.0  
**Status:** Planning Phase  
**Timeline:** 5 weeks (195 hours)

---

## 🎯 Capstone 2 Goals

### What's Working (Keep)
- ✅ K3s Kubernetes cluster architecture
- ✅ Falco runtime security monitoring
- ✅ LLM integration (Groq/OpenAI)
- ✅ FastAPI backend framework
- ✅ Demo IoT services (for attack simulation)

### What Needs to Change (Upgrade)
- ❌ Replace in-memory storage → PostgreSQL with encryption
- ❌ Add authentication/RBAC throughout
- ❌ Synchronous API → Async event-driven
- ❌ Monolithic structure → Microservices (optional)
- ❌ No persistence layer → Event sourcing
- ❌ Missing tests → Comprehensive test suite
- ❌ Scattered docs → Consolidated documentation

---

## 📁 RECOMMENDED PROJECT STRUCTURE (Capstone 2)

```
smart-city-ids/
│
├── .github/
│   ├── copilot-instructions.md
│   ├── SECURITY.md
│   └── workflows/
│       ├── ci.yaml                 # Lint, test, build
│       ├── security-scan.yaml      # Bandit, Trivy
│       └── deploy.yaml             # Auto-deploy on tag
│
├── src/
│   ├── __init__.py
│   │
│   ├── ids-api/                    # Main IDS service
│   │   ├── __init__.py
│   │   ├── main.py                 # FastAPI app definition
│   │   ├── requirements.txt        # Pinned versions
│   │   ├── Dockerfile
│   │   │
│   │   ├── api/
│   │   │   ├── routes.py           # Endpoint definitions
│   │   │   ├── models.py           # Request/response Pydantic models
│   │   │   ├── dependencies.py     # Auth, validators, middleware
│   │   │   └── __init__.py
│   │   │
│   │   ├── core/
│   │   │   ├── config.py           # Settings from env
│   │   │   ├── security.py         # JWT, encryption, RBAC
│   │   │   ├── logging.py          # Structured logging
│   │   │   ├── exceptions.py       # Custom exceptions
│   │   │   └── __init__.py
│   │   │
│   │   ├── domain/
│   │   │   ├── alert.py            # Alert domain logic
│   │   │   ├── analysis.py         # Analysis service
│   │   │   ├── automation.py       # K8s automation service
│   │   │   ├── events.py           # Event definitions
│   │   │   └── __init__.py
│   │   │
│   │   └── infrastructure/
│   │       ├── database.py         # SQLAlchemy + PostgreSQL
│   │       ├── cache.py            # Redis interface
│   │       ├── llm.py              # LLM abstraction (Groq/OpenAI)
│   │       ├── kubernetes.py       # K8s client wrapper
│   │       ├── message_queue.py    # RabbitMQ/Kafka interface
│   │       ├── repositories/       # Data access layer
│   │       │   ├── alert_repo.py
│   │       │   ├── analysis_repo.py
│   │       │   └── __init__.py
│   │       └── __init__.py
│   │
│   ├── alert-processor/            # Async worker for alerts
│   │   ├── main.py
│   │   ├── requirements.txt
│   │   ├── Dockerfile
│   │   └── processor.py            # Alert processing logic
│   │
│   ├── llm-analyzer/               # Async worker for LLM analysis
│   │   ├── main.py
│   │   ├── requirements.txt
│   │   ├── Dockerfile
│   │   └── analyzer.py
│   │
│   ├── shared/                     # Shared code
│   │   ├── models.py               # Shared Pydantic models
│   │   ├── events.py               # Event definitions
│   │   └── __init__.py
│   │
│   └── smart-city-services/        # Demo IoT services (secured)
│       ├── traffic-camera/
│       │   ├── app.py
│       │   ├── requirements.txt
│       │   └── Dockerfile
│       ├── healthcare-api/
│       │   ├── app.py
│       │   ├── requirements.txt
│       │   └── Dockerfile
│       └── parking-system/
│           ├── app.py
│           ├── requirements.txt
│           └── Dockerfile
│
├── k8s/
│   ├── namespace.yaml              # smart-city namespace
│   ├── manifests/
│   │   ├── ids-api.yaml
│   │   ├── alert-processor.yaml
│   │   ├── llm-analyzer.yaml
│   │   ├── postgres.yaml
│   │   ├── redis.yaml
│   │   ├── rabbitmq.yaml
│   │   └── services.yaml           # IoT services
│   ├── policies/
│   │   ├── network-policies.yaml   # Deny-all + allow rules
│   │   ├── rbac-ids-api.yaml       # IDS API service account + roles
│   │   ├── rbac-processors.yaml    # Worker service account
│   │   ├── pod-security.yaml       # Pod security policies
│   │   └── resource-quotas.yaml
│   ├── monitoring/
│   │   ├── prometheus.yaml
│   │   ├── grafana.yaml
│   │   └── alerts.yaml
│   └── helm/                       # Helm charts for production
│       └── smart-city-ids/
│
├── scripts/
│   ├── setup.sh                    # One-time setup
│   ├── start.sh                    # Start cluster
│   ├── stop.sh                     # Stop cluster
│   ├── cleanup.sh                  # Cleanup resources
│   ├── migrate.sh                  # Database migrations
│   ├── deploy.sh                   # Deploy to K8s
│   ├── monitor.sh                  # Monitor system
│   ├── test.sh                     # Run tests
│   └── security-scan.sh            # Local security scan
│
├── docs/
│   ├── README.md                   # Overview & quick start
│   ├── ARCHITECTURE.md             # System design
│   ├── SECURITY.md                 # Security model & audit
│   ├── API.md                      # API reference
│   ├── DEPLOYMENT.md               # Deployment guide
│   ├── TROUBLESHOOTING.md          # Common issues
│   └── MIGRATION.md                # Capstone 1→2 guide
│
├── tests/
│   ├── conftest.py                 # Pytest configuration
│   ├── unit/
│   │   ├── test_domain.py
│   │   ├── test_services.py
│   │   ├── test_llm.py
│   │   └── test_security.py
│   ├── integration/
│   │   ├── test_api.py
│   │   ├── test_database.py
│   │   ├── test_kubernetes.py
│   │   └── test_message_queue.py
│   ├── e2e/
│   │   ├── test_alert_pipeline.py
│   │   └── test_automation.py
│   └── fixtures/
│       ├── alerts.json
│       └── k8s_mocks.py
│
├── infrastructure/
│   ├── docker/
│   │   ├── Dockerfile.ids-api
│   │   ├── Dockerfile.processor
│   │   ├── Dockerfile.analyzer
│   │   └── docker-compose.yml      # Local development
│   ├── database/
│   │   ├── migrations/
│   │   │   ├── 001_initial.sql
│   │   │   └── 002_encryption.sql
│   │   └── schema.sql
│   └── monitoring/
│       ├── prometheus.yml
│       └── grafana-dashboard.json
│
├── .gitignore                      # Updated for new structure
├── .env.example                    # Environment template
├── pyproject.toml                  # Python project config
├── poetry.lock                     # Locked dependencies
├── requirements.txt                # Root dependencies
├── Makefile                        # Development commands
├── docker-compose.yml              # Local dev environment
│
└── README.md                       # Root readme
```

---

## 🔐 SECURITY LAYER (New)

### Authentication & Authorization

**File:** `src/ids-api/core/security.py`
```python
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthCredentials
from jose import JWTError, jwt
from datetime import datetime, timedelta
from enum import Enum

class Role(str, Enum):
    ADMIN = "admin"
    ANALYST = "analyst"
    MONITOR = "monitor"
    SERVICE = "service"

class TokenData:
    def __init__(self, sub: str, role: Role, exp: datetime):
        self.sub = sub  # User/service ID
        self.role = role
        self.exp = exp

async def verify_token(credentials: HTTPAuthCredentials) -> TokenData:
    """Verify JWT token and extract claims"""
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        sub: str = payload.get("sub")
        role: str = payload.get("role", Role.MONITOR)
        if sub is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        token_data = TokenData(sub=sub, role=Role(role))
    except JWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")
    return token_data

async def require_role(*roles: Role):
    """Dependency: Require specific role(s)"""
    async def check_role(token: TokenData = Depends(verify_token)):
        if token.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return token
    return check_role

# Usage:
# @app.post("/api/alerts")
# async def process_alert(
#     alert: Alert,
#     token: TokenData = Depends(require_role(Role.ANALYST, Role.SERVICE))
# ):
```

### Encrypted Storage

**File:** `src/ids-api/infrastructure/database.py`
```python
from sqlalchemy import Column, String, DateTime, JSON, LargeBinary
from sqlalchemy.ext.declarative import declarative_base
from cryptography.fernet import Fernet
import json

Base = declarative_base()

class AlertRecord(Base):
    __tablename__ = "alerts"
    
    id = Column(Integer, primary_key=True)
    source = Column(String(50))  # falco, suricata
    rule = Column(String(512))
    severity = Column(Integer)
    encrypted_alert_data = Column(LargeBinary)  # Encrypted JSON
    encrypted_analysis = Column(LargeBinary)
    actions_taken = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime)
    
    @staticmethod
    def encrypt(data: dict, key: bytes) -> bytes:
        """Encrypt alert data"""
        cipher = Fernet(key)
        json_str = json.dumps(data)
        return cipher.encrypt(json_str.encode())
    
    @staticmethod
    def decrypt(encrypted: bytes, key: bytes) -> dict:
        """Decrypt alert data"""
        cipher = Fernet(key)
        json_str = cipher.decrypt(encrypted).decode()
        return json.loads(json_str)
```

---

## 📨 EVENT-DRIVEN ARCHITECTURE

### Alert Processing Pipeline

**File:** `src/ids-api/domain/events.py`
```python
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

class AlertEventType(str, Enum):
    ALERT_RECEIVED = "alert.received"
    ALERT_ANALYZED = "alert.analyzed"
    ACTION_EXECUTED = "action.executed"
    ACTION_FAILED = "action.failed"

@dataclass
class AlertReceivedEvent:
    """Event emitted when alert is received"""
    event_id: str
    timestamp: datetime
    source: str  # falco, suricata
    alert_data: dict
    
    def to_message(self) -> str:
        """Serialize to message queue"""
        return json.dumps({
            "type": AlertEventType.ALERT_RECEIVED,
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "data": self.alert_data
        })

@dataclass
class AlertAnalyzedEvent:
    event_id: str
    alert_id: str
    severity: int
    threat_type: str
    recommendations: list
    
    # ... other fields
```

### Message Queue Integration

**File:** `src/ids-api/infrastructure/message_queue.py`
```python
import aio_pika
import json

class MessageQueueService:
    def __init__(self, url: str = "amqp://guest:guest@rabbitmq:5672/"):
        self.url = url
        self.connection = None
        self.channel = None
    
    async def connect(self):
        self.connection = await aio_pika.connect_robust(self.url)
        self.channel = await self.connection.channel()
    
    async def publish_alert(self, event: AlertReceivedEvent):
        """Publish alert to queue for async processing"""
        exchange = await self.channel.declare_exchange(
            'alerts', aio_pika.ExchangeType.TOPIC, durable=True
        )
        message = aio_pika.Message(
            body=event.to_message().encode(),
            content_type='application/json'
        )
        await exchange.publish(message, routing_key='alert.received')
    
    async def subscribe_analysis(self, callback):
        """Subscribe to analysis results"""
        queue = await self.channel.declare_queue('analysis_results')
        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                await callback(json.loads(message.body))
```

### Async Worker

**File:** `src/alert-processor/processor.py`
```python
import asyncio
import aio_pika
from src.ids_api.domain.analysis import AnalysisService
from src.ids_api.infrastructure.llm import LLMService

class AlertProcessor:
    def __init__(self):
        self.mq = MessageQueueService()
        self.llm = LLMService()
        self.analysis = AnalysisService()
    
    async def start(self):
        await self.mq.connect()
        await self.process_alerts()
    
    async def process_alerts(self):
        """Listen for alerts and process them"""
        queue = await self.mq.channel.declare_queue('incoming_alerts')
        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                alert_data = json.loads(message.body)
                try:
                    analysis = await self.llm.analyze(alert_data)
                    await self.analysis.save(alert_data, analysis)
                    await self.mq.publish_analysis(analysis)
                except Exception as e:
                    logger.error(f"Failed to analyze alert: {e}")
                    await self.mq.publish_error(alert_data, str(e))
                finally:
                    await message.ack()

if __name__ == "__main__":
    processor = AlertProcessor()
    asyncio.run(processor.start())
```

---

## 🧪 TESTING STRATEGY

### Unit Tests (60% coverage)

**File:** `tests/unit/test_security.py`
```python
import pytest
from src.ids_api.core.security import verify_token, Role
from jose import jwt

@pytest.fixture
def valid_token():
    payload = {"sub": "test_user", "role": "analyst"}
    return jwt.encode(payload, "secret", algorithm="HS256")

def test_verify_token_valid(valid_token):
    credentials = HTTPAuthCredentials(scheme="bearer", credentials=valid_token)
    token_data = verify_token(credentials)
    assert token_data.sub == "test_user"
    assert token_data.role == Role.ANALYST

def test_verify_token_invalid():
    with pytest.raises(HTTPException) as exc_info:
        verify_token(HTTPAuthCredentials(scheme="bearer", credentials="invalid"))
    assert exc_info.value.status_code == 401
```

### Integration Tests (20% coverage)

**File:** `tests/integration/test_alert_pipeline.py`
```python
@pytest.mark.asyncio
async def test_full_alert_pipeline():
    """Test: Alert → Analysis → Action"""
    # Setup
    alert = {
        "rule": "Unexpected process",
        "priority": "Critical",
        "output": "process executed",
        "output_fields": {"container.name": "traffic-camera-1"}
    }
    
    # Execute
    response = await client.post("/api/alerts", json=alert)
    
    # Verify
    assert response.status_code == 200
    assert "alert_id" in response.json()
    
    # Check analysis was performed
    alert_id = response.json()["alert_id"]
    stored_alert = await db.query(AlertRecord).filter_by(id=alert_id).first()
    assert stored_alert.severity >= 1
```

### E2E Tests (10% coverage)

**File:** `tests/e2e/test_attack_response.py`
```python
@pytest.mark.asyncio
async def test_critical_alert_isolation():
    """Test: Critical alert → Pod isolation"""
    # Trigger critical alert via API
    alert = create_critical_alert()
    response = await client.post("/api/alerts", json=alert)
    alert_id = response.json()["alert_id"]
    
    # Wait for async processing
    await asyncio.sleep(2)
    
    # Verify K8s action was taken
    pod = get_pod_by_name("traffic-camera-1")
    network_policies = get_network_policies(pod.namespace)
    
    assert any(
        "isolate-traffic-camera-1" in p.metadata.name 
        for p in network_policies
    )
```

---

## 🚀 DEPLOYMENT & CI/CD

### GitHub Actions Workflow

**File:** `.github/workflows/ci.yaml`
```yaml
name: CI/CD Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-cov bandit
      
      - name: Lint with ruff
        run: ruff check src/ tests/
      
      - name: Type check with mypy
        run: mypy src/ --ignore-missing-imports
      
      - name: Security scan with bandit
        run: bandit -r src/ -f json -o bandit-report.json || true
      
      - name: Run tests with coverage
        run: pytest tests/ --cov=src --cov-report=xml
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3
  
  container-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Build container images
        run: |
          docker build -t ids-api:${{ github.sha }} -f infrastructure/docker/Dockerfile.ids-api .
      
      - name: Scan with Trivy
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: ids-api:${{ github.sha }}
          format: 'sarif'
          output: 'trivy-results.sarif'
      
      - name: Upload Trivy results
        uses: github/codeql-action/upload-sarif@v2
        with:
          sarif_file: 'trivy-results.sarif'
  
  deploy:
    needs: [lint-and-test, container-scan]
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Deploy to K8s
        env:
          KUBECONFIG_B64: ${{ secrets.KUBECONFIG_B64 }}
        run: |
          echo $KUBECONFIG_B64 | base64 -d > /tmp/kubeconfig
          kubectl --kubeconfig=/tmp/kubeconfig apply -f k8s/manifests/
          kubectl rollout status deployment/ids-api -n smart-city
```

---

## 📊 MIGRATION EXECUTION TIMELINE

### Week 1: Security Foundation
**Days 1-2: Core Authentication**
- Implement JWT token generation/validation
- Add API key support for services
- Create users/roles table in PostgreSQL
- Deploy and test auth middleware

**Days 3-4: Data Encryption**
- Setup PostgreSQL + pgcrypto
- Implement Fernet encryption for sensitive fields
- Migrate in-memory storage to encrypted DB
- Test data persistence and recovery

**Days 5: Network Security**
- Deploy network policies (deny-all + allow rules)
- Setup pod security standards
- Enable RBAC for IDS API
- Validate all traffic is blocked except allowed

### Week 2: API Hardening
**Days 6-7: Input Validation**
- Add comprehensive Pydantic validators
- Implement rate limiting (slowapi)
- Add request logging/auditing
- Validate all user inputs

**Days 8-9: Error Handling**
- Define custom exception hierarchy
- Implement consistent error responses
- Add retry logic with exponential backoff
- Setup error alerting

**Days 10: Testing**
- Write unit tests for validation
- Integration tests for auth flow
- Fix any issues found

### Week 3: Event-Driven Architecture
**Days 11-12: Message Queue**
- Deploy RabbitMQ to K8s
- Implement message publishing
- Create consumer workers
- Setup DLQ (dead letter queue)

**Days 13-14: Async Workers**
- Build alert processor worker
- Build LLM analyzer worker
- Implement graceful shutdown
- Setup auto-scaling policies

**Days 15: Testing**
- Write integration tests
- Test failure scenarios
- Load test message queue

### Week 4: Quality & Testing
**Days 16-17: Comprehensive Tests**
- Unit tests (60% coverage)
- Integration tests (20% coverage)
- E2E tests (10% coverage)
- Security scanning

**Days 18-19: CI/CD Pipeline**
- GitHub Actions workflows
- Container scanning
- Automated deployments
- Rollback procedures

**Days 20: Documentation**
- Update all docs
- Create migration guide
- Write runbooks

### Week 5: Optimization & Cleanup
**Days 21-22: Refactoring**
- Code cleanup
- Dead code removal
- Performance optimization
- Structure finalization

**Days 23-24: Final Testing**
- Load testing
- Chaos engineering
- Security audit
- Performance benchmarks

**Day 25: Cutover**
- Final validation
- Data migration
- Deployment to production
- Monitoring and rollout

---

## ✅ CAPSTONE 2 SUCCESS CRITERIA

- [ ] All OWASP Top 10 vulnerabilities addressed
- [ ] 80%+ test coverage
- [ ] 0 critical security issues
- [ ] < 1s average alert processing time
- [ ] 99.9% uptime SLA
- [ ] Full audit trail of all actions
- [ ] Encrypted database with backups
- [ ] RBAC-enforced access control
- [ ] Comprehensive documentation
- [ ] Automated CI/CD pipeline
- [ ] Load tested to 1000 alerts/min

---

**Status:** Ready for Capstone 2 Implementation  
**Last Updated:** 2026-01-10
