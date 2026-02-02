# Changelog

All notable changes to the Smart City IDS project.

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
