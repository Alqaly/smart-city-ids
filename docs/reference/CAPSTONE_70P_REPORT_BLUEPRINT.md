# Capstone 70-Page Report Blueprint (IEEE Style)

> [!IMPORTANT]
> Historical / snapshot document. This file may contain time-bound results, legacy route names, or report-only summaries.
> Do not use it as the current API/runtime contract. Verify current behavior using `docs/INDEX.md`, `docs/API_REFERENCE.md`,
> and live checks (`/health`, `/api/alerts`, `/api/metrics`).


Date: 2026-02-20  
Target length: 70 pages (body + figures + references; appendices optional extra)

This is the implementation-ready writing blueprint for producing a full capstone report directly from `docs/` materials.

## 1) Page Budget by Chapter

| Chapter | Target Pages | Primary Sources |
|---|---:|---|
| Abstract + Keywords | 1 | [../../README.md](../../README.md), [ACADEMIC_CONTEXT.md](ACADEMIC_CONTEXT.md) |
| 1. Introduction | 6 | [ACADEMIC_CONTEXT.md](ACADEMIC_CONTEXT.md), [../SUPERVISOR_GUIDE.md](../SUPERVISOR_GUIDE.md), [../../README.md](../../README.md) |
| 2. Problem Statement & Objectives | 7 | [OPERATOR_INTERFACE.md](OPERATOR_INTERFACE.md), [LLM_REALITY_CHECK.md](LLM_REALITY_CHECK.md), [../HOW_IT_WORKS.md](../HOW_IT_WORKS.md) |
| 3. Related Context / Positioning | 6 | [ACADEMIC_CONTEXT.md](ACADEMIC_CONTEXT.md), [../SECURITY_MODEL.md](../SECURITY_MODEL.md), [EXAMINER_DEFENSE.md](EXAMINER_DEFENSE.md) |
| 4. System Architecture | 10 | [../ARCHITECTURE.md](../ARCHITECTURE.md), [../HOW_IT_WORKS.md](../HOW_IT_WORKS.md), [CAPSTONE_FIGURES.md](CAPSTONE_FIGURES.md) |
| 5. Implementation Details | 10 | [../DEVELOPMENT.md](../DEVELOPMENT.md), [../API_REFERENCE.md](../API_REFERENCE.md), [../IOT_EMULATION_REPORT.md](../IOT_EMULATION_REPORT.md) |
| 6. Evaluation Methodology | 7 | [../VALIDATION_CHECKLIST.md](../VALIDATION_CHECKLIST.md), [../SECURITY_MODEL.md](../SECURITY_MODEL.md), [DEMO_READINESS_REPORT.md](DEMO_READINESS_REPORT.md) |
| 7. Results & Analysis | 10 | [PROJECT_METRICS.md](PROJECT_METRICS.md), [../METRICS_SPEC.md](../METRICS_SPEC.md), [METRICS_AUDIT.md](METRICS_AUDIT.md) |
| 8. Discussion, Limits, Risks | 7 | [LLM_REALITY_CHECK.md](LLM_REALITY_CHECK.md), [DETECTION_TELEMETRY_ATTACK_QA.md](DETECTION_TELEMETRY_ATTACK_QA.md), [FORCED_ARCHITECTURE_50Q.md](FORCED_ARCHITECTURE_50Q.md) |
| 9. Conclusion & Future Work | 4 | [LLM_SECURITY_INTERFACE_IMPROVEMENT_PLAN.md](LLM_SECURITY_INTERFACE_IMPROVEMENT_PLAN.md), [FORCED_ARCHITECTURE_50Q.md](FORCED_ARCHITECTURE_50Q.md) |
| References | 2 | External IEEE references + internal docs |
| **Total** | **70** |  |

## 2) Minimum Figure/Table Targets

- Figures: 12–18 (architecture, pipeline, governance flow, metrics dashboards)
- Tables: 12–16 (threat mapping, endpoint summary, KPI outcomes, limitations)
- Use [CAPSTONE_FIGURES.md](CAPSTONE_FIGURES.md) as primary figure source.

## 3) Chapter Execution Order (Fastest Path)

1. Freeze metrics and endpoint counts using [CAPSTONE_CANONICAL_SOURCE_LEDGER.md](CAPSTONE_CANONICAL_SOURCE_LEDGER.md).
2. Draft Chapters 4 and 5 first (architecture + implementation).
3. Draft Chapters 6 and 7 (evaluation + results) with fixed KPIs.
4. Write Chapters 1 to 3 (intro/problem/positioning) to match what is actually implemented.
5. Finish Chapters 8 and 9 (limitations/future work), then references.

## 4) Non-Negotiable Writing Rules

- Do not mix conflicting values (pods, metrics count, endpoint count) across chapters.
- Every major claim must map to at least one file in [CAPSTONE_EVIDENCE_MATRIX.md](CAPSTONE_EVIDENCE_MATRIX.md).
- Use IEEE numeric citation style and keep claims falsifiable and reproducible.

## 5) Ready-to-Use Section Prompts

- Architecture section prompt: "Describe data flow from Falco/Suricata ingestion through LLM analysis, governance, actioning, and persistence, then map to implementation modules and API endpoints."
- Evaluation section prompt: "Define experiment setup, input scenarios, KPI definitions, run procedure, and measured outcomes with threats-to-validity."
- Discussion section prompt: "Compare achieved capabilities vs known limitations and justify safety controls and HITL governance under degraded LLM conditions."
