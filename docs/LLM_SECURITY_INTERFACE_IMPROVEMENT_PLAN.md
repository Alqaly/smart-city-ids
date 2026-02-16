# LLM Security Interface Improvement Plan (Presentation + Stakeholder Edition)

Date: 2026-02-16
Owner: Smart City IDS Team
Scope: Dashboard UX + governance workflow + LLM explainability surfaces used in demos and stakeholder reviews.

---

## 1) Current State (What Exists Today)

This plan is based on a direct review of:
- `services/ids-api/static/index.html` (single-page dashboard UI with 7 tabs)
- `services/ids-api/src/main.py` (IDS API + orchestration endpoints)
- `services/ids-api/src/governance.py` (HITL state machine and approval queue)
- `services/ids-api/src/operator_interface.py` (operator-centric incident formatting)
- `services/ids-api/src/llm_manager.py` (multi-provider LLM failover and parsing)
- supporting docs in `docs/`

### Existing strengths
- 7-tab operator dashboard with live feed, governance controls, IoT telemetry, and attack reproduction.
- Multi-provider LLM failover with circuit-breaker behavior and provider diagnostics.
- Assisted/manual/autopilot governance controls with pending approvals and history.
- Attack reproduction tab tied to MITRE ATT&CK for ICS scenarios.
- Pipeline observability endpoints and token/cost visibility.

### Stakeholder-facing gaps to close
- Governance decisions are visible but not yet packaged as an "executive confidence" story (risk + rationale + impact in one place).
- Approval workflow lacks structured decision reasons beyond basic comments.
- LLM reasoning is present, but confidence explanation needs stronger consistency for non-technical audiences.
- Security posture cues are spread across tabs; no single "presentation mode" summary card.
- Demo readiness checks are mostly manual and not shown as a pre-flight checklist in UI.

---

## 2) Improvement Goals (Presentation Outcome)

By presentation day, stakeholders should be able to answer in under 60 seconds:
1. **Is the platform secure and controllable?**
2. **Why should we trust the LLM recommendation?**
3. **Who remains accountable for critical actions?**
4. **What measurable value did this interface add?**

---

## 3) Phased Roadmap

## Phase A — Interface Trust Layer (Highest Priority)

### A1. Governance Decision Card
- Add a compact "Why this action?" panel in Governance tab:
  - severity
  - confidence
  - top 3 indicators
  - business impact
  - required approval reason
- Source fields already exist in operator incident + governance payloads.

### A2. Approval Decision Quality
- Require structured analyst decision reason on approve/reject:
  - `Policy`
  - `False Positive`
  - `Needs More Evidence`
  - `Operational Risk`
- Keep free-text comment optional for narrative context.

### A3. Mode Guardrails
- Add explicit warning banner when switching to `autopilot`.
- Add mode transition audit note in UI feed immediately after change.

Acceptance criteria:
- Every approved/rejected critical action includes a structured reason.
- Autopilot mode changes are visually high-friction and auditable.

---

## Phase B — Explainability for Stakeholders

### B1. Confidence Breakdown Panel
- Show confidence as components (signal quality, source corroboration, pattern match).
- Keep current confidence score, but add plain-language explanation for each band.

### B2. Action Impact Preview
- Before approve, show expected impact snapshot:
  - target service
  - blast radius estimate
  - reversibility
  - rollback path

### B3. Evidence Lens Toggle
- Toggle between:
  - "Executive view" (plain language)
  - "Analyst view" (rule/process/container detail)

Acceptance criteria:
- Non-technical stakeholder can explain *why* action was proposed using only UI text.
- Analysts still retain deep technical details without navigation overhead.

---

## Phase C — Demo Reliability + Storytelling

### C1. Presentation Mode Header
- Add top-level "Presentation Snapshot" card:
  - providers healthy / degraded
  - pending critical approvals
  - current governance mode
  - 24h critical incidents
  - average response latency

### C2. One-Click Demo Scenario Packs
- Group attack scenarios by stakeholder stories:
  - Public Safety
  - Healthcare Integrity
  - Critical Infrastructure Availability

### C3. Pre-flight Check Widget
- UI checks before demo starts:
  - K8s connectivity
  - at least one LLM provider operational
  - SSE stream active
  - governance mode expected

Acceptance criteria:
- Demo operator can verify readiness in <20 seconds.
- Stakeholders see business narrative, not only technical events.

---

## 4) Security + Governance Enhancements

- Enforce comment/justification requirement for severity >= 8 approvals.
- Add dual-confirmation option for destructive actions in Manual mode (config-driven).
- Add immutable audit attributes to approval records:
  - actor
  - timestamp
  - mode at decision time
  - reason code
  - optional note

---

## 5) Measurement Plan (KPIs to Report)

Primary KPIs:
- Mean time to decision (critical approvals)
- Approval quality completeness (% with reason code)
- False-positive reversal rate
- Stakeholder trust score (post-demo survey)
- Analyst cognitive load proxy (clicks/time per incident)

Operational KPIs:
- LLM provider availability and failover success rate
- Circuit breaker open duration per provider
- Dedup reduction % and estimated cost savings

---

## 6) Implementation Map (Code Touchpoints)

Frontend:
- `services/ids-api/static/index.html`
  - governance tab rendering
  - approval action handlers
  - topbar/status cards
  - attack scenario grouping

Backend:
- `services/ids-api/src/governance.py`
  - approval payload validation
  - reason-code support
  - audit record enrichment
- `services/ids-api/src/main.py`
  - API contracts and response shaping for new UI fields
- `services/ids-api/src/operator_interface.py`
  - confidence/explainability field standardization

Tests:
- `services/ids-api/tests/test_operator_contracts.py`
- `services/ids-api/tests/test_approve_comment.py`
- `services/ids-api/tests/test_internal_alert_controls.py`

Docs:
- `docs/OPERATOR_INTERFACE.md`
- `docs/HITL_UI_CHANGES.md`

---

## 7) Execution Plan (Next Sprint)

Sprint 1 (2–3 days):
- Implement A1 + A2 + A3
- Add/adjust tests for approval reason code and mode switching behavior

Sprint 2 (2–3 days):
- Implement B1 + B2
- Add executive/analyst evidence toggle

Sprint 3 (1–2 days):
- Implement C1 + C3
- Final demo script and stakeholder walkthrough

---

## 8) Risks and Mitigations

- Risk: Added UI complexity harms analyst speed.
  - Mitigation: keep executive layer collapsible; analyst defaults unchanged.
- Risk: Inconsistent LLM explanation quality across providers.
  - Mitigation: normalize response schema and confidence wording in one adapter path.
- Risk: Demo-time provider degradation.
  - Mitigation: enforce pre-flight checks and local fallback messaging.

---

## 9) Stakeholder Narrative (What We Will Say)

- The interface is not just a dashboard; it is a **controlled decision system**.
- AI makes fast recommendations, but **humans remain accountable** for critical actions.
- Every action is explainable, auditable, and reversible when possible.
- The platform reduces alert fatigue while increasing transparency and governance quality.

---

## 10) Definition of Done for Presentation-Ready Interface

Done means:
- Critical actions always show clear reason + impact + approval logic.
- Governance mode changes are explicit and auditable in the UI.
- A stakeholder can understand system status from one snapshot card.
- Demo can be started with a visible readiness check and consistent storyline.
