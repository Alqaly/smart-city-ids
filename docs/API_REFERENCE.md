# Smart City IDS - API Reference Documentation

**Version:** 1.0.0  
**Base URL:** `http://<host>:8000` (or `http://localhost:30800` via NodePort)

---

## Table of Contents

1. [Overview](#overview)
2. [Authentication](#authentication)
3. [Core Endpoints](#core-endpoints)
4. [Alert Management](#alert-management)
5. [Governance & Automation](#governance--automation)
6. [Operator Interface](#operator-interface)
7. [IoT Integration](#iot-integration)
8. [Monitoring & Metrics](#monitoring--metrics)
9. [LLM Engine Status](#llm-engine-status)
10. [Error Handling](#error-handling)
11. [Rate Limiting](#rate-limiting)
12. [Examples](#examples)

---

## Overview

The Smart City IDS API provides a RESTful interface for:

- **Alert Ingestion**: Receive security alerts from Falco, Suricata, and other sources
- **LLM Analysis**: Multi-LLM threat analysis with automatic failover
- **Automated Response**: Kubernetes-native threat mitigation
- **Governance**: Human-in-the-loop approval workflow
- **Monitoring**: Real-time metrics and status endpoints

### Key Features

| Feature | Description |
|---------|-------------|
| Multi-LLM Support | xAI Grok-4, OpenAI GPT-4, Anthropic Claude, Google Gemini, Kimi |
| Circuit Breakers | Automatic failover when LLM APIs fail |
| Alert Deduplication | Reduces LLM API costs by deduplicating similar alerts |
| PostgreSQL Storage | Persistent alert and audit logging |
| Prometheus Metrics | Full observability integration |

---

## Authentication

All API endpoints (except `/health` and `/metrics`) require authentication.

### Login

```http
POST /api/auth/login
Content-Type: application/json
```

**Request Body:**
```json
{
  "username": "operator",
  "password": "operator"
}
```

**Response:**
```json
{
  "access_token": "b3BlcmF0b3I6MTc3MDIyOTQyMg==",
  "token_type": "bearer",
  "user": "operator"
}
```

### Using the Token

Include the token in the `Authorization` header:

```http
Authorization: Bearer <access_token>
```

### Logout

```http
POST /api/auth/logout
Authorization: Bearer <access_token>
```

---

## Core Endpoints

### Health Check

```http
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "components": {
    "llm_engines": {
      "xai": "connected (circuit: closed)",
      "anthropic": "no-api-key",
      "openai": "connected (circuit: closed)",
      "gemini": "connected (circuit: closed)",
      "kimi": "no-api-key"
    },
    "kubernetes": "connected",
    "database": "postgresql",
    "falco": "enabled",
    "suricata": "enabled"
  },
  "active_llm_engines": ["xai", "openai", "gemini"],
  "llm_priority": ["xai", "openai", "gemini"],
  "circuit_breaker_states": {
    "xai": "closed",
    "openai": "closed",
    "gemini": "closed"
  },
  "uptime_seconds": 3600.5,
  "total_alerts_processed": 228,
  "storage_type": "postgresql"
}
```

### Root / Web UI

```http
GET /
GET /ui
```

Returns the Operator Dashboard web interface.

---

## Alert Management

### Receive Alert (External)

Used by external systems (Falco forwarder, Suricata, etc.) to submit alerts.

```http
POST /api/alerts
Authorization: Bearer <token>
Content-Type: application/json
```

**Request Body (Falco format):**
```json
{
  "source": "falco",
  "output": "Detected privilege escalation: User ran sudo su in container",
  "priority": "Critical",
  "rule": "Privilege Escalation Attempt",
  "time": "2026-02-04T18:30:00.000Z",
  "output_fields": {
    "container.name": "traffic-camera-pod",
    "proc.cmdline": "sudo su -",
    "proc.name": "sudo",
    "user.name": "www-data",
    "fd.name": "/etc/shadow"
  }
}
```

**Response (Success):**
```json
{
  "status": "success",
  "alert_id": 229,
  "analysis": {
    "summary": "Privilege escalation attempt detected in traffic camera container",
    "severity": 9,
    "threat_type": "Privilege Escalation",
    "recommendations": [
      "Isolate the affected pod",
      "Review container security policies",
      "Check for lateral movement"
    ],
    "automated_actions": ["isolate_pod", "collect_evidence"]
  },
  "actions_taken": [
    {
      "type": "isolate_pod",
      "target": "traffic-camera-pod",
      "status": "pending_approval"
    }
  ]
}
```

**Response (LLM Failure):**
```json
{
  "status": "error",
  "alert_id": 230,
  "message": "All LLM engines failed or circuits open",
  "stored": true
}
```

### Receive Alert (Internal)

Used by internal forwarders (runs without authentication).

```http
POST /api/alerts/internal
Content-Type: application/json
```

### Get Recent Alerts

```http
GET /api/alerts
Authorization: Bearer <token>
```

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| limit | int | 100 | Maximum alerts to return |
| source | string | - | Filter by source (falco, suricata) |
| severity_min | int | - | Minimum severity (1-10) |

---

## Governance & Automation

### Get Governance Status

```http
GET /api/governance/status
Authorization: Bearer <token>
```

**Response:**
```json
{
  "mode": "assisted",
  "auto_approve_threshold": 8,
  "pending_actions": 3,
  "total_approved": 45,
  "total_rejected": 2
}
```

### Change Automation Mode

```http
POST /api/governance/mode
Authorization: Bearer <token>
Content-Type: application/json
```

**Request Body:**
```json
{
  "mode": "assisted"
}
```

**Modes:**
| Mode | Description |
|------|-------------|
| `manual` | All actions require human approval |
| `assisted` | Low-risk actions auto-approved, high-risk require approval |
| `autonomous` | All actions auto-approved (use with caution) |

### Get Pending Actions

```http
GET /api/governance/pending
Authorization: Bearer <token>
```

**Response:**
```json
{
  "pending_actions": [
    {
      "id": "action-123",
      "type": "isolate_pod",
      "target": "traffic-camera-pod",
      "severity": 9,
      "llm_reasoning": "High-severity privilege escalation requires immediate isolation",
      "created_at": "2026-02-04T18:30:00Z"
    }
  ]
}
```

### Approve Action

```http
POST /api/governance/approve/{action_id}
Authorization: Bearer <token>
```

### Reject Action

```http
POST /api/governance/reject/{action_id}
Authorization: Bearer <token>
Content-Type: application/json
```

**Request Body:**
```json
{
  "reason": "False positive - legitimate admin activity"
}
```

### Get Action History

```http
GET /api/governance/history
Authorization: Bearer <token>
```

---

## Operator Interface

### List Incidents

```http
GET /api/operator/incidents
Authorization: Bearer <token>
```

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| limit | int | 50 | Maximum incidents |
| status | string | - | Filter: open, investigating, resolved |

### Get Incident Details

```http
GET /api/operator/incident/{incident_id}
Authorization: Bearer <token>
```

### Get Evidence

```http
GET /api/operator/evidence/{incident_id}
Authorization: Bearer <token>
```

**Response:**
```json
{
  "incident_id": "inc-123",
  "evidence": {
    "raw_alerts": [...],
    "container_logs": "...",
    "network_flows": [...],
    "process_tree": {...}
  }
}
```

### Get LLM Reasoning

```http
GET /api/operator/reasoning/{incident_id}
Authorization: Bearer <token>
```

**Response:**
```json
{
  "incident_id": "inc-123",
  "llm_engine": "xai",
  "analysis": {
    "threat_assessment": "This appears to be an active privilege escalation attack...",
    "attack_chain": [
      "Initial access via web vulnerability",
      "Local privilege escalation",
      "Credential harvesting attempt"
    ],
    "confidence": 0.92,
    "mitre_techniques": ["T1068", "T1003"]
  }
}
```

### Get Operator Metrics

```http
GET /api/operator/metrics
Authorization: Bearer <token>
```

---

## IoT Integration

### Submit Sensor Data

```http
POST /api/iot/sensor
Authorization: Bearer <token>
Content-Type: application/json
```

**Request Body:**
```json
{
  "device_id": "sensor-001",
  "device_type": "motion_sensor",
  "location": "building-a-floor-3",
  "readings": {
    "motion_detected": true,
    "temperature": 22.5,
    "humidity": 45
  },
  "timestamp": "2026-02-04T18:30:00Z"
}
```

### List IoT Devices

```http
GET /api/iot/devices
Authorization: Bearer <token>
```

### Get IoT Events

```http
GET /api/iot/events
Authorization: Bearer <token>
```

---

## Monitoring & Metrics

### Prometheus Metrics

```http
GET /metrics
```

Returns Prometheus-format metrics. No authentication required.

**Key Metrics:**
```
# Alert metrics
smartcity_ids_alerts_received_total{source="falco",priority="Critical"}
smartcity_ids_alerts_processed_total{result="success"}
smartcity_ids_alert_severity_total{severity="high"}

# LLM metrics
smartcity_ids_llm_requests_total{engine="xai",result="success"}
smartcity_ids_llm_latency_seconds{engine="openai"}
smartcity_ids_circuit_breaker_state{engine="gemini"}
smartcity_ids_llm_failover_total{from_engine="xai",to_engine="openai"}

# Automation metrics
smartcity_ids_actions_executed_total{type="isolate_pod"}
smartcity_ids_governance_decisions_total{decision="approved"}
```

### Internal Metrics API

```http
GET /api/metrics
Authorization: Bearer <token>
```

### Database Stats

```http
GET /api/db/stats
Authorization: Bearer <token>
```

**Response:**
```json
{
  "total_alerts": 228,
  "alerts_by_source": {
    "falco": 220,
    "suricata": 8
  },
  "alerts_by_severity": {
    "critical": 15,
    "high": 45,
    "medium": 80,
    "low": 88
  },
  "storage_size_mb": 12.5
}
```

### Deduplicator Stats

```http
GET /api/deduplicator-stats
Authorization: Bearer <token>
```

**Response:**
```json
{
  "cache_size": 150,
  "hits": 45,
  "misses": 228,
  "hit_rate": 0.165,
  "cost_savings_estimate": "$2.25"
}
```

### Clear Deduplicator Cache

```http
POST /api/deduplicator/clear
Authorization: Bearer <token>
```

---

## LLM Engine Status

### Circuit Breaker States

| State | Value | Description |
|-------|-------|-------------|
| CLOSED | 0 | Normal operation, requests allowed |
| HALF_OPEN | 1 | Testing if service recovered |
| OPEN | 2 | Service failing, requests blocked |

### Failover Priority

The system automatically fails over to the next LLM engine in priority order:

1. xAI Grok-4 (primary)
2. OpenAI GPT-4
3. Anthropic Claude
4. Google Gemini
5. Kimi

---

## Error Handling

### Error Response Format

```json
{
  "detail": "Error message",
  "error_code": "AUTH_FAILED",
  "timestamp": "2026-02-04T18:30:00Z"
}
```

### Common Error Codes

| HTTP Code | Error | Description |
|-----------|-------|-------------|
| 401 | Not authenticated | Missing or invalid token |
| 403 | Forbidden | Insufficient permissions |
| 404 | Not found | Resource doesn't exist |
| 429 | Rate limited | Too many requests |
| 500 | Internal error | Server error (check logs) |
| 503 | Service unavailable | All LLM engines failing |

---

## Rate Limiting

| Endpoint | Limit |
|----------|-------|
| `/api/alerts` | 100/minute |
| `/api/auth/login` | 10/minute |
| Others | 1000/minute |

---

## Examples

### Complete Workflow: Receive and Analyze Alert

```bash
# 1. Login
TOKEN=$(curl -s -X POST http://localhost:30800/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"operator","password":"operator"}' | jq -r '.access_token')

# 2. Send alert
curl -X POST http://localhost:30800/api/alerts \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source": "falco",
    "output": "Shell spawned in container",
    "priority": "Critical",
    "rule": "Terminal shell in container",
    "output_fields": {"container.name": "web-app"}
  }'

# 3. Check pending actions
curl http://localhost:30800/api/governance/pending \
  -H "Authorization: Bearer $TOKEN"

# 4. Approve action
curl -X POST http://localhost:30800/api/governance/approve/action-123 \
  -H "Authorization: Bearer $TOKEN"
```

### Python Client Example

```python
import requests

class SmartCityIDSClient:
    def __init__(self, base_url, username, password):
        self.base_url = base_url
        self.session = requests.Session()
        self._login(username, password)
    
    def _login(self, username, password):
        resp = self.session.post(f"{self.base_url}/api/auth/login",
            json={"username": username, "password": password})
        token = resp.json()["access_token"]
        self.session.headers["Authorization"] = f"Bearer {token}"
    
    def send_alert(self, alert):
        return self.session.post(f"{self.base_url}/api/alerts", 
            json=alert).json()
    
    def get_health(self):
        return requests.get(f"{self.base_url}/health").json()
    
    def get_pending_actions(self):
        return self.session.get(f"{self.base_url}/api/governance/pending").json()
    
    def approve_action(self, action_id):
        return self.session.post(
            f"{self.base_url}/api/governance/approve/{action_id}").json()

# Usage
client = SmartCityIDSClient("http://localhost:30800", "operator", "operator")
print(client.get_health())
```

---

## OpenAPI Specification

Full OpenAPI 3.0 specification available at:

```
GET /openapi.json
```

Interactive documentation (Swagger UI):

```
GET /docs
```

Alternative documentation (ReDoc):

```
GET /redoc
```

---

## Support

- **GitHub Issues**: Report bugs and feature requests
- **Documentation**: See `/docs/` folder in repository
- **Logs**: `kubectl logs -n smart-city deploy/ids-api`

---

*Generated: February 4, 2026*  
*Smart City IDS v1.0.0 - LLM-Driven Intrusion Detection System*
