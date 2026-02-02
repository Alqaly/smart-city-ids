# Changelog

All notable changes to the Smart City IDS project.

---

## [2.1.0] - Capstone II Integration Plan - 2025-01-20

### Added - IoT Simulation Realism (TASK 1)

- **Poisson Arrival Process** - Messages now follow exponential inter-arrival times with `λ(t) = λ_base × rush_multiplier × weekday_multiplier`
- **Rush Hour Multipliers** - 10x message rate increase at 08:00 and 17:00 peaks
- **Three Device Classes**:
  - `high` (60 msg/min) - Continuous sensors like traffic cameras
  - `medium` (6 msg/min) - Standard environment sensors
  - `burst` (0.5 msg/min) - Event-driven motion sensors
- **Failure Injection** - 1% random disconnects, 2% latency spikes for resilience testing
- **Weekday Patterns** - Weekend traffic reduced to 20-30% of weekday baseline

### New Files (TASK 1)

- `iot-simulator/mqtt_device_enhanced.py` - Full-featured IoT simulator with Poisson processes
- `iot-simulator/k8s-enhanced.yaml` - Multi-class K8s deployment (high/medium/burst)
- `docs/IOT_SIMULATION.md` - Technical specification for IoT realism features

### Added - Scalability Evidence (TASK 5)

**Script:** `scripts/scalability-test.sh`

Tests system at four scale levels:
| Level | Devices | Distribution |
|-------|---------|--------------|
| 1 | 10 | 4 high, 5 medium, 1 burst |
| 2 | 100 | 40 high, 50 medium, 10 burst |
| 3 | 500 | 200 high, 250 medium, 50 burst |
| 4 | 1000 | 400 high, 500 medium, 100 burst |

**Output:** Generates IEEE-defensible report in `scalability-results/`:
- Markdown report with tables at each scale level
- JSON files with raw metrics for analysis
- IoT message rates, LLM latencies, system health

**Metrics Captured:**
- IoT message/failure rates
- LLM latency p50/p95
- Alert and action rates
- Cache hit rate
- Pod counts, CPU, memory usage

### Added - Grafana Dashboards (TASK 3)

Three specialized dashboards per integration plan requirements:

1. **SOC Overview** (`grafana-dashboard-soc-overview.json`)
   - Alert counts (24h), critical alerts active, actions executed
   - Alert rate by source (time series)
   - Severity heatmap (hourly)
   - Threat type distribution (donut chart)
   - Actions blocked by safety controls
   - Time to mitigation (p50/p95/p99)

2. **LLM Performance** (`grafana-dashboard-llm-performance.json`)
   - xAI Grok-4 & OpenAI status indicators
   - Cache hit rate (%) and cache size
   - Failover count (24h)
   - Circuit breaker state
   - Latency percentiles by engine (histogram)
   - Request throughput (success/failure)

3. **IoT Load** (`grafana-dashboard-iot-load.json`)
   - Active devices, messages sent/failed
   - Disconnect and latency spike totals
   - Rush hour status indicator
   - Poisson rate λ(t) by device class
   - Burst factor timeline
   - Message rate distribution histogram
   - Device class breakdown (high/medium/burst)
   - Scalability evidence panel

### Added - Human-in-the-Loop Governance (TASK 4)

**Three Automation Modes:**

| Mode | Behavior | Response Time | Use Case |
|------|----------|---------------|----------|
| **AUTOPILOT** | All actions auto-execute | Seconds | Known threat patterns |
| **ASSISTED** | Severity ≥8 requires approval | Seconds-Minutes | Production with SOC |
| **MANUAL** | All actions need approval | Operator-dependent | Testing, compliance |

**New Module:** `services/ids-api/src/governance.py`
- `GovernanceController` - Thread-safe singleton for action management
- `PendingAction` - Dataclass for queued actions with expiry
- Audit logging for IEEE-defensible compliance trail

**New API Endpoints:**
- `GET /api/governance/status` - Current mode and metrics
- `GET /api/governance/mode` - Get current mode
- `POST /api/governance/mode` - Change mode (autopilot/assisted/manual)
- `GET /api/governance/pending` - List actions awaiting approval
- `POST /api/governance/approve/{id}` - Approve and execute action
- `POST /api/governance/reject/{id}` - Reject action with reason
- `GET /api/governance/history` - Audit trail of all actions

**Configuration:**
```bash
AUTOMATION_MODE=assisted       # autopilot | assisted | manual
ASSISTED_THRESHOLD=8           # Severity threshold for ASSISTED mode
ACTION_EXPIRY_SECONDS=300      # Pending action timeout
```

### New Prometheus Metrics (IoT)

- `iot_messages_sent_total{device, namespace, class}`
- `iot_messages_failed_total{device, namespace, class}`
- `iot_device_disconnects_total{device}`
- `iot_latency_spikes_total{device}`
- `iot_device_active{device, namespace, class}`
- `iot_current_message_rate{device, class}`
- `iot_burst_factor{device}`
- `iot_message_latency_seconds{device}` (histogram)

### Added - Prometheus Metrics Expansion (TASK 2)

- **40+ Prometheus Metrics** - Comprehensive observability per integration plan
- **Metrics Module** - New centralized `services/ids-api/src/metrics.py` with:
  - Alert ingestion metrics (received, processed, deduplicated, dropped)
  - LLM analysis metrics (latency histograms, cache hit rate, fallbacks)
  - Automated action metrics (by type, outcome, mode)
  - System health metrics (rate limiter, circuit breaker, queue depth)
  - Database metrics (operations, latency, connections)
  - IoT aggregate metrics (active devices, message rates, rush hour status)
- **Decorators** - `@track_llm_latency`, `@track_action_execution`, `@track_db_operation`
- **Thread-safe** - All metrics use proper locking for concurrent access

### New Prometheus Metrics (IDS Core)

```
# Alert Metrics
ids_alerts_received_total{source, severity, rule}
ids_alerts_processed_total{source}
ids_alerts_deduplicated_total{rule}
ids_alerts_dropped_total{reason}
ids_alerts_queued (gauge)
ids_alert_severity_bucket (histogram)
ids_alerts_by_threat_type_total{threat_type}

# LLM Metrics
ids_llm_requests_total{engine, status}
ids_llm_latency_seconds{engine} (histogram)
ids_llm_latency_summary_seconds{engine} (summary)
ids_llm_tokens_total{engine, type}
ids_llm_cache_hit_rate (gauge)
ids_llm_cache_operations_total{operation}
ids_llm_cache_size (gauge)
ids_llm_fallback_total{primary_engine, fallback_engine}
ids_llm_primary_available{engine} (gauge)

# Action Metrics
ids_actions_executed_total{action_type, outcome}
ids_actions_by_mode_total{mode, action_type}
ids_actions_blocked_total{reason}
ids_actions_pending_approval (gauge)
ids_action_execution_seconds{action_type} (histogram)
ids_response_time_seconds (histogram)
ids_pods_isolated{namespace} (gauge)

# System Health
ids_rate_limiter_tokens (gauge)
ids_rate_limiter_rejections_total
ids_circuit_breaker_state{engine} (gauge)
ids_circuit_breaker_state_changes_total{engine, from_state, to_state}
ids_request_queue_depth (gauge)
ids_uptime_seconds (gauge)
ids_info{version, capstone, llm_primary, llm_fallback} (info)

# Database Metrics
ids_db_operations_total{operation, status}
ids_db_latency_seconds{operation} (histogram)
ids_db_connections_active (gauge)
ids_db_alerts_total (gauge)

# IoT Aggregate Metrics
ids_iot_devices_active{class, namespace} (gauge)
ids_iot_message_rate{class} (gauge)
ids_iot_rush_hour_active (gauge)
```

---

## [2.0.0] - Capstone II - 2026-02-02

### Major Features

- **LLM Integration** - Full integration with xAI Grok and OpenAI GPT for intelligent threat analysis
- **Automated Kubernetes Response** - Severity-based automated actions (isolate, scale, evict)
- **PostgreSQL Persistence** - Alert history and metric recovery on restart
- **Prometheus Counter Restoration** - Metrics survive pod restarts via database sync
- **Enhanced Grafana Dashboards** - Real-time visualization with LLM decision metrics

### Added

- `services/ids-api/src/llm_engine_xai.py` - xAI Grok-4 integration
- `services/ids-api/src/llm_engine_openai.py` - OpenAI GPT fallback
- `services/ids-api/src/k8s_automation.py` - Kubernetes automation actions
- `services/ids-api/src/database.py` - PostgreSQL persistence layer
- `services/ids-api/src/metrics.py` - Prometheus metrics with DB restoration
- `infrastructure/database/migrations/` - Database schema management
- `deploy.sh` - One-click deployment script
- `docker/ids-api/Dockerfile` - Pre-built IDS API image
- `docker/smart-city-service/Dockerfile` - Pre-built demo service image
- `docs/SETUP.md` - Installation guide
- `docs/ARCHITECTURE.md` - System design documentation
- `docs/OPERATIONS.md` - Operations guide
- `docs/PROJECT_AUDIT.md` - Codebase assessment

### Changed

- Migrated from mock LLM to real xAI/OpenAI integration
- Enhanced `main.py` with async alert processing
- Improved error handling throughout codebase
- Refactored configuration to use environment variables
- Updated Grafana dashboards with new metrics panels

### Fixed

- Prometheus counter reset on pod restart (now persisted in PostgreSQL)
- Missing health check endpoints
- RBAC permissions for K8s automation
- Config validation for required API keys

### Security

- API keys moved to Kubernetes Secrets
- Network policies for pod isolation
- RBAC with least-privilege principle

---

## [1.0.0] - Capstone I - 2025-12-15

### Initial Release

- Basic IDS architecture on Kubernetes
- Falco integration for runtime security
- Suricata integration for network IDS
- Mock LLM analysis (placeholder)
- Simple alert forwarding pipeline
- Basic Prometheus metrics
- Initial Grafana dashboard
- Smart city demo services:
  - Traffic Camera (Flask)
  - Healthcare API (Flask)
  - Parking System (Flask)
- MQTT broker for IoT simulation
- IoT device simulator

### Known Issues (Addressed in v2.0.0)

- No real LLM integration (mock only)
- Metrics lost on pod restart
- No automated Kubernetes actions
- Limited documentation
- Manual deployment process

---

## Version Comparison

| Feature | Capstone I (v1.0) | Capstone II (v2.0) |
|---------|-------------------|-------------------|
| LLM Analysis | Mock/Placeholder | Real xAI/OpenAI |
| Auto Response | None | Isolate/Scale/Evict |
| Persistence | None | PostgreSQL |
| Metric Recovery | ❌ | ✅ |
| One-Click Deploy | ❌ | ✅ |
| Documentation | Basic | Comprehensive |
| Docker Images | None | Pre-built |

---

## Migration Notes

### From Capstone I to II

If upgrading from Capstone I:

1. **Backup existing data** (if any)
2. **Set environment variables:**
   ```bash
   export XAI_API_KEY="your-key"
   export OPENAI_API_KEY="your-key"  # optional
   ```
3. **Run fresh deployment:**
   ```bash
   ./deploy.sh --clean
   ```
4. **Import new dashboards:**
   ```bash
   ./scripts/load-dashboards.sh
   ```

---

## Roadmap

### Planned for Future Releases

- [ ] Multi-cluster support
- [ ] Custom rule definition UI
- [ ] Alert correlation engine
- [ ] ML-based anomaly detection (supplement to LLM)
- [ ] Slack/Teams notifications
- [ ] Compliance reporting (SOC 2, NIST)
- [ ] High availability configuration

---

*For detailed documentation, see [docs/](docs/)*
