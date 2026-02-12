# Documentation Index — Smart City IDS

Technical documentation for the LLM-driven Intrusion Detection System.

---

## Core Documentation

| Document | Description |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | System design: namespace layout, pod inventory, alert pipeline, source structure, LLM provider architecture, database schema, network topology, Prometheus metrics |
| [API_REFERENCE.md](API_REFERENCE.md) | All 37 API endpoints, request/response models, authentication, configuration variables, error codes |
| [HOW_IT_WORKS.md](HOW_IT_WORKS.md) | End-to-end walkthrough: detection → intake → LLM analysis → automated response → governance → persistence |
| [DEVELOPMENT.md](DEVELOPMENT.md) | Local setup, K3s deployment, code architecture, testing, debugging, scripts reference |

## Supplemental Documentation

| Document | Description |
|---|---|
| [SETUP.md](SETUP.md) | Installation prerequisites and initial cluster setup |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Deployment procedures and manifest details |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Common issues, recovery procedures, K3s fixes |
| [LLM_CONFIGURATION.md](LLM_CONFIGURATION.md) | LLM provider setup, key management, model selection |
| [SECURITY_MODEL.md](SECURITY_MODEL.md) | Security architecture, threat model, JWT auth |
| [OPERATOR_INTERFACE.md](OPERATOR_INTERFACE.md) | Dashboard usage, SOC workflow, HITL operations |
| [SUPERVISOR_GUIDE.md](SUPERVISOR_GUIDE.md) | Governance modes, approval workflow, audit trail |
| [METRICS_SPEC.md](METRICS_SPEC.md) | Prometheus metrics specification |
| [LOG_FORMAT_GUIDE.md](LOG_FORMAT_GUIDE.md) | Log format and structured logging reference |
| [COMMANDS_REFERENCE.md](COMMANDS_REFERENCE.md) | kubectl and admin command reference |

## Academic Context

| Document | Description |
|---|---|
| [ACADEMIC_CONTEXT.md](ACADEMIC_CONTEXT.md) | Research context and academic positioning |
| [EXAMINER_DEFENSE.md](EXAMINER_DEFENSE.md) | Defense preparation and examiner Q&A |

## Quick Links

- **Dashboard**: `http://localhost:30800/ui`
- **Health check**: `curl http://localhost:30800/health`
- **Prometheus**: `http://localhost:31106`
- **Grafana**: `http://localhost:30300`
- **Demo credentials**: `operator` / `operator`
