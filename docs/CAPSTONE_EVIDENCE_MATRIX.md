# Capstone Evidence Matrix (Chapter-to-Source Mapping)

Date: 2026-02-20

Use this matrix while drafting to guarantee traceability and reduce examiner challenges.

## Evidence Matrix

| Chapter | Must-Prove Outcome | Required Evidence Files |
|---|---|---|
| Ch1 Introduction | Problem relevance and project motivation | [ACADEMIC_CONTEXT.md](ACADEMIC_CONTEXT.md), [README.md](README.md), [SUPERVISOR_GUIDE.md](SUPERVISOR_GUIDE.md) |
| Ch2 Problem & Objectives | Clear threat model + operational pain points | [SECURITY_MODEL.md](SECURITY_MODEL.md), [OPERATOR_INTERFACE.md](OPERATOR_INTERFACE.md), [LLM_REALITY_CHECK.md](LLM_REALITY_CHECK.md) |
| Ch3 Positioning | Why this approach vs alternatives | [ACADEMIC_CONTEXT.md](ACADEMIC_CONTEXT.md), [EXAMINER_DEFENSE.md](EXAMINER_DEFENSE.md) |
| Ch4 Architecture | End-to-end pipeline and component decomposition | [ARCHITECTURE.md](ARCHITECTURE.md), [HOW_IT_WORKS.md](HOW_IT_WORKS.md), [CAPSTONE_FIGURES.md](CAPSTONE_FIGURES.md) |
| Ch5 Implementation | Concrete modules, APIs, deployment mechanics | [DEVELOPMENT.md](DEVELOPMENT.md), [API_REFERENCE.md](API_REFERENCE.md), [DEPLOYMENT.md](DEPLOYMENT.md), [IOT_EMULATION_REPORT.md](IOT_EMULATION_REPORT.md) |
| Ch6 Evaluation Method | Reproducible test protocol and scenarios | [VALIDATION_CHECKLIST.md](VALIDATION_CHECKLIST.md), [DEMO_READINESS_REPORT.md](DEMO_READINESS_REPORT.md), [SECURITY_MODEL.md](SECURITY_MODEL.md) |
| Ch7 Results | Quantified outcomes and KPI interpretation | [PROJECT_METRICS.md](PROJECT_METRICS.md), [METRICS_SPEC.md](METRICS_SPEC.md), [METRICS_AUDIT.md](METRICS_AUDIT.md) |
| Ch8 Discussion & Limits | Honest limitations, risks, trade-offs | [LLM_REALITY_CHECK.md](LLM_REALITY_CHECK.md), [DETECTION_TELEMETRY_ATTACK_QA.md](DETECTION_TELEMETRY_ATTACK_QA.md), [FORCED_ARCHITECTURE_50Q.md](FORCED_ARCHITECTURE_50Q.md) |
| Ch9 Conclusion & Future Work | Defensible contribution + roadmap | [LLM_SECURITY_INTERFACE_IMPROVEMENT_PLAN.md](LLM_SECURITY_INTERFACE_IMPROVEMENT_PLAN.md), [FORCED_ARCHITECTURE_50Q.md](FORCED_ARCHITECTURE_50Q.md), [CODE_QUALITY_REPORT.md](CODE_QUALITY_REPORT.md) |

## Evidence Quality Checklist

- Source is active (not archived) unless explicitly marked historical.
- Claim has one primary and one supporting reference.
- Quantitative claims include units, timeframe, and method.
- Safety/security claims include constraints and failure modes.

## Appendix Material Sources

- API schemas: [API_REFERENCE.md](API_REFERENCE.md), [LOG_FORMAT_GUIDE.md](LOG_FORMAT_GUIDE.md)
- Ops runbooks: [OPERATIONS.md](OPERATIONS.md), [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- Deployment manifests/process: [DEPLOYMENT.md](DEPLOYMENT.md), [SETUP.md](SETUP.md)
- Validation scripts and checks: [VALIDATION_CHECKLIST.md](VALIDATION_CHECKLIST.md), [COMMANDS_REFERENCE.md](COMMANDS_REFERENCE.md)
