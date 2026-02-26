# Smart City IDS Documentation Index

This index is the authoritative entry point for technical documentation in `docs/`.

## Read This First (External Reviewers / Experts)

1. [../README.md](../README.md) — project overview, current scope, quick start
2. [ARCHITECTURE.md](ARCHITECTURE.md) — system design and component boundaries
3. [HOW_IT_WORKS.md](HOW_IT_WORKS.md) — end-to-end alert pipeline behavior
4. [API_REFERENCE.md](API_REFERENCE.md) — API contracts and endpoint behavior
5. [OPERATIONS.md](OPERATIONS.md) + [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — runtime operations and recovery

## Documentation Trust Model (Important)

Use this to avoid stale/misleading claims when sharing the repo externally.

- `Current / operational`: architecture, API, setup, deployment, operations, troubleshooting, security model, LLM configuration
- `Demo / examiner prep`: demo runbooks, Q&A, readiness reports (useful, but context-specific)
- `Academic / report support`: capstone blueprints, evidence matrices, defense notes
- `Historical / archived`: `docs/_archive/` and `docs/archive/` (not current system truth)
- `Generated artifacts`: coverage matrices and reports may reflect a specific date/run

When in doubt, validate runtime claims against:
- `GET /health`
- `GET /api/alerts`
- `GET /api/metrics`
- Kubernetes live state (`kubectl get pods -A`, `kubectl get svc -n smart-city`)

## Canonical Technical Docs (Current)

| Document | Purpose |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | System architecture, components, data flow, current-vs-target notes |
| [HOW_IT_WORKS.md](HOW_IT_WORKS.md) | End-to-end processing path (Falco/Suricata -> IDS API -> LLM -> governance -> actions) |
| [API_REFERENCE.md](API_REFERENCE.md) | API endpoints, auth, request/response contracts |
| [SETUP.md](SETUP.md) | Initial setup prerequisites and environment prep |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Deployment procedures and manifest-level deployment notes |
| [OPERATIONS.md](OPERATIONS.md) | Day-2 operations, checks, service management |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Recovery procedures and common failure modes |
| [SECURITY_MODEL.md](SECURITY_MODEL.md) | Security boundaries, threat model, auth, governance context |
| [LLM_CONFIGURATION.md](LLM_CONFIGURATION.md) | LLM provider configuration, key handling, routing basics |
| [LLM_CONTROL_AND_TROUBLESHOOTING.md](LLM_CONTROL_AND_TROUBLESHOOTING.md) | Operator-facing LLM diagnostics and recovery actions |
| [IOT_INTEGRATION_SDK.md](IOT_INTEGRATION_SDK.md) | External device onboarding, telemetry path, logical device registry path |

## Demo / Validation / Examiner Docs (Context-Specific)

| Document | Purpose |
|---|---|
| [DEMO_DAY_RUNBOOK.md](DEMO_DAY_RUNBOOK.md) | Practical demo-day execution sequence |
| [DEMO_QA_CHECKLIST.md](DEMO_QA_CHECKLIST.md) | Final checks and links to Q&A prep docs |
| [DEMO_CHEAT_SHEET.md](DEMO_CHEAT_SHEET.md) | Fast command reference during demo |
| [DEMO_READINESS_REPORT.md](DEMO_READINESS_REPORT.md) | Snapshot readiness report (time-bound) |
| [DOC_CLAIMS_VALIDATION_2026-02-24.md](DOC_CLAIMS_VALIDATION_2026-02-24.md) | Claim validation snapshot (time-bound) |
| [EXAMINER_QA_30.md](EXAMINER_QA_30.md) | Main examiner Q&A prep |
| [EXAMINER_IOT_QA_20.md](EXAMINER_IOT_QA_20.md) | IoT specialist Q&A (deep dive) |
| [FORCED_ARCHITECTURE_50Q.md](FORCED_ARCHITECTURE_50Q.md) | Deep backup / gap-analysis style Q&A (contains historical references) |

## Academic / Report Support Docs

| Document | Purpose |
|---|---|
| [ACADEMIC_CONTEXT.md](ACADEMIC_CONTEXT.md) | Research positioning and methodology framing |
| [CAPSTONE_EVIDENCE_MATRIX.md](CAPSTONE_EVIDENCE_MATRIX.md) | Evidence traceability for report claims |
| [CAPSTONE_CANONICAL_SOURCE_LEDGER.md](CAPSTONE_CANONICAL_SOURCE_LEDGER.md) | Canonical source mapping to reduce claim drift |
| [CAPSTONE_70P_REPORT_BLUEPRINT.md](CAPSTONE_70P_REPORT_BLUEPRINT.md) | Long-form report structure blueprint |
| [SCENARIOS/README.md](SCENARIOS/README.md) | Scenario documentation template |
| [SCENARIOS/MQTT_FLOOD_LATERAL_IMPACT.md](SCENARIOS/MQTT_FLOOD_LATERAL_IMPACT.md) | Research-style staged scenario spec |
| [SCENARIOS/FHIR_TAMPER_CLINICAL_IMPACT.md](SCENARIOS/FHIR_TAMPER_CLINICAL_IMPACT.md) | Research-style staged scenario spec |

## Reference / Supporting Docs

| Document | Purpose |
|---|---|
| [COMMANDS_REFERENCE.md](COMMANDS_REFERENCE.md) | Admin and kubectl command reference |
| [LOG_FORMAT_GUIDE.md](LOG_FORMAT_GUIDE.md) | Alert/log schemas and examples |
| [METRICS_SPEC.md](METRICS_SPEC.md) | Metric names and semantics |
| [METRICS_AUDIT.md](METRICS_AUDIT.md) | Metrics realism and audit notes |
| [ATTACK_SIMULATION_GUIDE.md](ATTACK_SIMULATION_GUIDE.md) | Attack simulation usage and constraints |
| [ATTACK_COVERAGE_MATRIX.csv](ATTACK_COVERAGE_MATRIX.csv) | Coverage artifact (generated / export) |
| [ATTACK_COVERAGE_MATRIX.json](ATTACK_COVERAGE_MATRIX.json) | Coverage artifact (generated / export) |

## Archive (Not Current System Truth)

- [ARCHIVE_INDEX.md](ARCHIVE_INDEX.md)
- [`docs/_archive/`](./_archive/)
- [`docs/archive/`](./archive/)

Use archives for historical context only. Do not cite archived files as current runtime behavior without re-validation.

## Quick Runtime Verification (Before Sharing)

```bash
bash scripts/pre-demo-check.sh
curl -s http://localhost:30800/health | jq
curl -s http://localhost:30800/api/metrics | jq '{total_alerts,iot_devices_active}'
```

