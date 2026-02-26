# Capstone Canonical Source Ledger

Date: 2026-02-20

Purpose: establish one authoritative source per claim category before drafting the capstone report.

## Canonical Rules

1. If values conflict across docs, prioritize the source listed in "Primary".
2. Record deltas in "Reconcile Notes" before drafting final text.
3. Never cite archived docs as canonical unless no active doc exists.

## Claim Authority Map

| Claim Category | Primary | Secondary | Reconcile Notes |
|---|---|---|---|
| System architecture and component boundaries | [ARCHITECTURE.md](ARCHITECTURE.md) | [HOW_IT_WORKS.md](HOW_IT_WORKS.md) | Use architecture naming from primary; use flow narrative from secondary. |
| API endpoint inventory and contracts | [API_REFERENCE.md](API_REFERENCE.md) | [HOW_IT_WORKS.md](HOW_IT_WORKS.md) | Endpoint count must match API reference, not older index summaries. |
| KPI definitions and formulas | [METRICS_SPEC.md](METRICS_SPEC.md) | [METRICS_AUDIT.md](METRICS_AUDIT.md) | Definitions from spec; realism commentary from audit. |
| KPI result values used in report tables | [PROJECT_METRICS.md](PROJECT_METRICS.md) | [DEMO_READINESS_REPORT.md](DEMO_READINESS_REPORT.md) | Keep one run window per table; label timeframe explicitly. |
| Security model and ATT&CK mapping | [SECURITY_MODEL.md](SECURITY_MODEL.md) | [DETECTION_TELEMETRY_ATTACK_QA.md](DETECTION_TELEMETRY_ATTACK_QA.md) | Use model for formal mapping; QA doc for deep explanations. |
| Governance/HITL behavior | [OPERATOR_INTERFACE.md](OPERATOR_INTERFACE.md) | [SUPERVISOR_GUIDE.md](SUPERVISOR_GUIDE.md) | Keep terminology consistent: autonomous/assisted/manual (legacy aliases may appear in historical docs). |
| LLM limitations and safe-mode behavior | [LLM_REALITY_CHECK.md](LLM_REALITY_CHECK.md) | [FORCED_ARCHITECTURE_50Q.md](FORCED_ARCHITECTURE_50Q.md) | Limit claims to demonstrated behavior and stated constraints. |
| Deployment and runtime ops | [DEPLOYMENT.md](DEPLOYMENT.md) | [OPERATIONS.md](OPERATIONS.md) | Deployment steps from primary; operational runbooks from secondary. |
| Validation protocol | [VALIDATION_CHECKLIST.md](VALIDATION_CHECKLIST.md) | [DEMO_READINESS_REPORT.md](DEMO_READINESS_REPORT.md) | Checklist is method; readiness report is evidence output. |
| Figure inventory and placements | [CAPSTONE_FIGURES.md](CAPSTONE_FIGURES.md) | [ARCHITECTURE.md](ARCHITECTURE.md) | Use figure IDs from capstone figures file for cross-references. |

## Drift Watchlist (Must Reconcile Before Final Draft)

- Endpoint totals across index/reference docs.
- Metrics cardinality counts (`38` vs `40+` style drifts).
- Pod/deployment totals and environment sizing references.
- Deduplication percentages quoted across multiple docs.

## Reconciliation Log Template

| Topic | Conflicting Sources | Chosen Value | Rationale | Date |
|---|---|---|---|---|
| Example: endpoint count | API_REFERENCE vs README | 43 | API reference is contract source | 2026-02-20 |
