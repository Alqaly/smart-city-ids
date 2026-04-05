# Forced Architecture Documentation (50 Questions)

Date: 2026-02-20 | Last reviewed: 2026-04-05
Scope reviewed: IDS API routers/state/config, LLM provider manager stack, Falco/Suricata forwarders, Kubernetes operator CRD, K8s manifests, dashboard UI.

This document answers each required question from code reality, then adds improvement guidance where gaps exist.

## Status Note (2026-02-24)

This file is a broad architecture review snapshot and includes some historical references
from earlier dashboard/governance iterations. For examiner prep, prefer:

- `docs/reference/EXAMINER_QA_30.md` (clean, current, concise answers)
- `docs/ARCHITECTURE.md` (full technical reference)

Current-state corrections (important):
- Governance mode names in the live UI/API are `autonomous`, `assisted`, `manual` (with legacy aliases normalized).
- Dashboard behavior now includes explicit dedup/flood-suppression visibility and clearer platform-noise labeling.
- Alert flood handling now suppresses throttled duplicates before DB/SSE dashboard broadcast.

## ✅ P0 Implementation Update (2026-02-20)

The three P0 backlog items are now implemented in runtime code:

1. **Provider-failure resilience + notify-only guard path**
   - Added deterministic fallback handling in analysis flow when provider calls fail.
   - Added action guard so destructive actions are blocked in notify-only mode when enabled.
   - Key files: `services/ids-api/src/api/_state.py`, `services/ids-api/src/api/alerts.py`, `services/ids-api/src/config.py`.

2. **Per-user chat rate limiting**
   - Added per-user/session token bucket limiter for `/api/analyst/chat`.
   - Tunables: `ANALYST_CHAT_RATE_LIMIT_PER_MINUTE`, `ANALYST_CHAT_RATE_LIMIT_BURST`.
   - Key file: `services/ids-api/src/api/analyst.py`.

3. **IDS API → ThreatResponse CRD wiring**
   - Added CRD creation path in Kubernetes automation client.
   - Added automatic ThreatResponse emission for executed destructive actions in alert pipeline.
   - Tunable: `K8S_USE_THREATRESPONSE_CRD`.
   - Key files: `services/ids-api/src/k8s_automation.py`, `services/ids-api/src/api/alerts.py`, `services/ids-api/src/config.py`.

---

## 🔥 CORE ARCHITECTURE (1-10)

1) What defines an alert in this IDS?
- Canonical IDS alert contract is: output, rule, priority, time, output_fields.
- Alert model is consumed by POST /api/alerts and /api/alerts/internal.
- Improvement: publish this schema as OpenAPI examples in docs/API_REFERENCE.md with one Falco and one Suricata payload.

2) Falco → Suricata → LLM pipeline end-to-end?
- Falco and Suricata are parallel sources, not serial stages; both forward alerts into IDS API.
- IDS flow: rate limit → queue → alert-throttle → dedup → LLM analyze_with_fallback → governance check → optional K8s actions → DB/audit/SSE.
- Improvement: add a sequence diagram image in docs/ARCHITECTURE.md showing parallel source ingestion.

3) What data formats do Falco/Suricata alerts use?
- Falco forwarders send Falco JSON fields directly (rule/output/output_fields/priority/time).
- Suricata forwarder converts Eve JSON into IDS alert format with mapped priority and output_fields (src_ip, dest_ip, signature, proto).
- Improvement: add a JSON transformation table from Eve JSON keys to IDS keys in docs/LOG_FORMAT_GUIDE.md.

4) How are duplicate alerts deduplicated?
- Two dedup layers exist: forwarder-level hash TTL filtering and API-side AlertDeduplicator fingerprint cache.
- API dedup uses rule + container + proc fields fingerprint, with severity-aware TTL.
- Improvement: expose dedup fingerprint examples and per-severity TTL in dashboard tooltip.

5) What happens when all 5 cloud LLMs fail simultaneously?
- LLM manager returns status=error after trying configured providers in priority order (skipping cooldown providers).
- analyze_with_fallback raises exception; alert endpoint returns degraded error response while still persisting raw alert record path.
- Improvement: add explicit emergency local heuristic analyzer fallback mode to keep deterministic scoring during total cloud outage.

6) Exact routing logic for LLM providers?
- Order source: forced provider override first, else routing mode (priority/cost_optimized/ab_test/severity_adaptive).
- cost_optimized chooses cheapest within ceiling if possible; severity_adaptive uses premium providers for high severity.
- Improvement: surface per-alert routing decision reason directly in Alert detail UI.

7) How does ThreatResponse CRD work in Kubernetes?
- CRD exists under ids.smartcity.local/v1alpha1 with spec.alertId/severity/actions and status.phase/appliedActions.
- Kopf operator watches create events, checks severity>=6, labels pod, and creates deny-all NetworkPolicy.
- Improvement: wire IDS API automation output to create ThreatResponse resources (currently not integrated in IDS API path).

8) What are the 5 pipeline stages and SLAs?
- Stage strip exists: Falco Alerts, Suricata Alerts, IDS Ingest+Dedup, LLM Analysis, Governance+K8s Actions.
- Current code computes rates and p95 for LLM stage; explicit numeric SLA thresholds are not codified.
- Improvement: define hard SLOs (example: ingest p95<200ms, LLM p95<3s, mitigation p95<60s) and enforce with alerting rules.

9) How is alert severity calculated (rules vs LLM)?
- Input rules/priority are context only; final severity used for automation/governance comes from LLM analysis severity field.
- Critical/high thresholds are then applied (>=8 isolate, >=6 scale).
- Improvement: add secondary deterministic severity floor from source priority when LLM confidence is low.

10) What metrics track false positive rate?
- false_positives_filtered metric is defined in Prometheus metrics module.
- In current refactored path, concrete increments are mostly in forwarder-side filtering counters, not fully unified into IDS API false-positive metric updates.
- Improvement: add explicit operator feedback labeling (true/false positive) pipeline and aggregate precision/recall dashboard.

---

## 🧠 LLM SYSTEM (11-20)

11) List all 5 cloud providers and configs?
- xai (XAI_API_KEY, grok-4-latest), anthropic (ANTHROPIC_API_KEY, claude-3-5-sonnet), openai (OPENAI_API_KEY), gemini (GEMINI_API_KEY), kimi (KIMI_API_KEY).
- Priority from LLM_PRIORITY env.
- Improvement: add startup config sanity endpoint that redacts keys but validates model/provider compatibility.

12) Provider failover exact algorithm?
- Iterate providers in runtime order; if preferred set, move it first.
- Skip providers in cooldown; attempt analyze; on success return immediately; otherwise collect errors and continue.
- Improvement: add weighted retry budget per provider and global attempt cap telemetry.

13) Prometheus metrics for LLM performance?
- smartcity_ids_llm_requests_total, smartcity_ids_llm_latency_seconds, smartcity_ids_llm_cost_usd_total, smartcity_ids_llm_tokens_total, cache metrics, failover counters.
- Comparison endpoints also expose p50/p95/p99 and success-rate views.
- Improvement: add per-model label (not only engine) for clearer model migration tracking.

14) How is LLM cost calculated per provider?
- Token-based estimate using per-1k token table when usage present or fallback token estimation.
- Aggregated in memory stats and exposed via /api/llm-stats/export and provider comparison APIs.
- Improvement: split prompt/completion rates where providers bill asymmetrically.

15) What happens if no LLM is healthy?
- Manager returns error after attempts; alert processing captures error path and does not execute analysis-derived automation.
- Governance and logging still retain event traceability.
- Improvement: add explicit policy mode NO_LLM_SAFE_MODE to auto-disable destructive actions and enforce notify-only behavior.

16) How to test specific provider manually?
- LLM control endpoints support provider-specific test via POST /api/llm/test/{provider} and control test endpoint.
- UI supports per-provider probe and test actions.
- Improvement: add server-side synthetic test corpus for repeatable benchmark scenarios.

17) Explain token input/output tracking?
- Providers normalize usage into prompt_tokens/completion_tokens/total_tokens when available.
- record_llm_tokens updates Prometheus and in-memory provider stats; fallback uses chars/4 estimate.
- Improvement: persist per-alert token usage in DB for long-range cost analytics.

18) Circuit breaker thresholds that disable providers?
- CircuitBreaker failure_threshold defaults to 5 and recovery_timeout default 30s for breaker state.
- Provider manager also has cooldown_seconds (default 900s) for non-retryable errors (quota/auth/429).
- Improvement: unify breaker and cooldown policy into one operator-tunable config section.

19) How does LLM Control Center tab work?
- Pulls control status, provider comparison, health summary, routing strategy, predictive risk.
- Supports force provider, priority update, probe, test console, fallback visualization, and provider cards.
- Improvement: add explicit stale-data badges and last-refresh timestamps per card.

20) What A/B testing exists between providers?
- A/B mode exists in routing config: deterministic bucket hash over alert signature and configurable split_percent_a.
- provider_a/provider_b selection is deterministic per alert fingerprint.
- Improvement: record A/B experiment id and outcome metrics to compare quality/cost statistically.

---

## 🐳 KUBERNETES (21-30)

21) How does dynamic IoT discovery find new devices?
- /api/iot/discover derives from live K8s pod listing filtered by IoT prefixes and enriches with restart/risk flags.
- /api/iot/devices merges in-memory registrations with pod details.
- Improvement: move from name-prefix matching to label selectors for resilient discovery.

22) What labels identify IoT workloads?
- Current runtime discovery mostly relies on pod name prefixes, not strict labels.
- Some metrics scraping relies on service DNS and deployment conventions.
- Improvement: standardize labels: app.kubernetes.io/component=iot and protocol/type labels across manifests.

23) Explain NetworkPolicy pod isolation process?
- K8sAutomation isolate_pod creates deny-all ingress+egress policy targeting pod-name label.
- ThreatResponse operator path labels pod with ids.smartcity.local/isolate=true then applies deny-all policy on that selector.
- Improvement: enforce a guaranteed selector strategy (pod UID label) to avoid mismatch with mutable pod names.

24) How does operator reconcile ThreatResponse?
- Kopf on-create handler validates spec, checks severity threshold, verifies target pod, labels pod, creates isolation NetworkPolicy, writes status.
- Returns phase Executed/Failed/Pending with appliedActions.
- Improvement: add update/delete handlers and retries with idempotent checks.

25) What RBAC roles exist (Observer/Analyst/etc)?
- API auth currently provides demo users (analyst/operator/admin) without endpoint-level RBAC authorization matrix.
- K8s RBAC exists for operator, Prometheus, forwarders (service account + cluster role bindings).
- Improvement: implement role claims in JWT and enforce per-route authorization middleware.

26) How are services discovered (mqtt-broker etc)?
- Service DNS names are hardcoded for IoT telemetry fan-out and manifests expose stable service endpoints.
- Forwarders use service DNS to reach IDS API.
- Improvement: add service registry endpoint that validates expected service DNS and readiness.

27) What pod health colors mean?
- UI convention: green healthy/running, yellow warning/degraded/cooldown, red error/disconnected.
- LLM and system cards use this mapping consistently after latest control updates.
- Improvement: publish legend component globally so all tabs use exactly identical semantics.

28) How to scale IoT replicas during DDoS?
- Automation path can call scale_deployment/scale_up on severity >=6 or recommended actions.
- Manual path via governance approval endpoints also supports scaling actions.
- Improvement: add predefined response playbook button: Scale IoT critical services to N replicas in one approval.

29) Explain falco-system namespace components?
- Core Falco pod, falco-forwarder deployment/serviceaccount/rbac, and optional metacollector components in deployment ecosystem.
- Forwarder tails Falco logs and posts normalized alerts to IDS internal endpoint.
- Improvement: add namespace health endpoint aggregating Falco pod + forwarder + ruleset status.

30) What monitoring stack exists?
- Prometheus deployment + configmap scrape jobs + PVC + serviceaccount/clusterrole.
- Grafana deployment + datasources + dashboards provisioning + PVC + NodePort service.
- Improvement: add alertmanager and SLO alert rules for pipeline/LLM/governance failure states.

---

## 📊 DASHBOARD & UX (31-40)

31) How does end-to-end trace modal work?
- Audit timeline rows contain trace_id buttons that call /api/audit/trace/{trace_id} and render ordered steps inline.
- Shows event_type/status/timestamps and raw payload blocks.
- Improvement: convert to true modal with stage badges and elapsed step timings.

32) What are the navigation tabs and purpose?
- The required baseline and the current UI can differ by branch/revision; verify against the live dashboard build used for the demo.
- This review snapshot observed fewer than 12 tabs in that branch and flagged the mismatch as a documentation/requirements issue.
- Improvement: keep a versioned UI inventory table in docs tied to release date/commit.

33) Explain hotkeys (Ctrl+1, Ctrl+A, etc)?
- Global hotkeys are not implemented in current index.html (only Enter handlers in inputs).
- Improvement: add keydown handler map for tab switching and quick actions with tooltip legend.

34) How does mobile hamburger menu work?
- Mobile hamburger navigation is not implemented; nav is horizontal scroll tab bar.
- Improvement: add responsive collapsed menu for <=768px with tab list drawer.

35) What MITRE ATT&CK heatmap shows?
- Dedicated heatmap panel is not implemented.
- MITRE technique IDs are shown in attack simulation cards/scenarios.
- Improvement: add matrix heatmap view from recent alerts grouped by mapped technique.

36) How to approve pending governance actions?
- UI uses chat action panel approve/reject buttons calling /api/analyst/action/pending-decision.
- Governance API also exposes /api/governance/approve/{id} and reject paths.
- Improvement: add dedicated Pending Actions queue tab with bulk actions and comment requirements.

37) Explain live SSE pipeline feed format?
- Frontend listens EventSource /api/alerts/live and handles connected/alert/message/data events.
- Render line includes time, severity short, score, threat type, rule, engine.
- Improvement: version event schema and include event_id for client-side replay dedup.

38) What SOC KPIs are displayed (MTTR/MTTD)?
- Displayed KPIs include total alerts, critical alerts, dedup savings, uptime, provider stats, rates.
- MTTR/MTTD labels are not explicit as dedicated dashboard KPIs currently.
- Improvement: compute and display MTTD/MTTR from audit trace deltas.

39) How does analyst chat agent select actions?
- Intent classifier + _extract_action_selector uses analysis automated_actions, target fields, and prompt cues.
- Suggested actions are deduped and surfaced with execute/approve/reject flow.
- Improvement: add confidence and estimated blast-radius per suggested action.

40) What rate limits protect chat interface?
- A dedicated per-user/session token-bucket limiter exists in `services/ids-api/src/api/analyst.py`.
- Tunables: `ANALYST_CHAT_RATE_LIMIT_PER_MINUTE` and `ANALYST_CHAT_RATE_LIMIT_BURST`.
- Improvement: add explicit max-concurrent chat request caps and surface limiter status in diagnostics.

---

## 🛡️ SECURITY & OPERATIONS (41-50)

41) How does HITL work for critical actions?
- Governance modes are `autonomous` / `assisted` / `manual` (legacy names may be normalized internally).
- Assisted mode uses confidence thresholds to require approvals for medium-confidence actions; manual requires operator approval for all actions.
- Analyst submit endpoint enforces confirmation_required then governance pending/decision path.
- Improvement: enforce dual-approval for severity >=9 actions.

42) What audit trail correlates alert → LLM → action?
- In-memory audit events include ALERT_RECEIVED, DEDUP_CHECK, LLM_ANALYSIS_START/END, GOVERNANCE_DECISION, ACTION_EXECUTED, ALERT_PROCESSED plus chat/HITL events.
- Trace IDs propagate through alert and chat workflows.
- Improvement: persist all audit events to durable store with retention policies.

43) Explain smoke test script and validation scope?
- scripts/readiness-check.sh validates cluster reachability, namespaces, core workloads, API health/auth, alerts presence, IoT pods, and demo command smoke checks.
- quick mode skips heavier checks.
- Improvement: add explicit LLM endpoint and governance pending-queue checks.

44) How are false positives from smart-city namespace suppressed?
- Falco forwarder has suppression filters for known benign rules/process/container patterns and namespace allowlist logic.
- Duplicate replay suppression also reduces noisy repeats.
- Improvement: move suppressions to managed configmap with versioned rules and audit counters.

45) What MITRE techniques are mapped to alerts?
- Attack simulation scenarios encode ICS technique IDs (for example T0866, T0814, T0807, T0836, T0879, T0831, T0867, T0890, T0843, T0846, T0552).
- These IDs are shown in UI scenario cards and injected payload metadata.
- Improvement: add automatic MITRE mapping table for live alerts beyond simulator.

46) How does semantic caching reduce LLM costs?
- True semantic embedding cache is not implemented in current active pipeline.
- Active cost reduction uses fingerprint dedup plus response cache and provider token-cost controls.
- Improvement: add embedding similarity cache for near-duplicate alerts with threshold tuning.

47) Explain per-user chat rate limiting?
- Implemented: `services/ids-api/src/api/analyst.py` includes a per-user/session token bucket (`PerUserTokenBucket`).
- Requests are keyed by normalized user/session identity and consume tokens with refill over time.
- Improvement: add websocket message-rate limits and admin-observable limiter metrics.

48) What happens on DDoS attack simulation?
- Attack simulation injects synthetic alert payload via /api/alerts/internal.
- Pipeline processes severity, may trigger scale_up/isolate actions according to thresholds/governance.
- Improvement: add automatic before/after service performance snapshots to prove mitigation effect.

49) How to generate PDF incident reports?
- PDF report generation endpoint is not implemented in current IDS API.
- Existing exports are JSON/CSV for audit logs.
- Improvement: add /api/reports/incident/{id}.pdf using templated HTML to PDF renderer.

50) What backup LLM routing for low-severity alerts?
- severity_adaptive mode routes high severity to premium providers and low severity to cheapest available provider.
- cost_optimized mode also enforces low-cost preference by ceiling.
- Improvement: add explicit low-severity static fallback chain (for example gemini→kimi) with canary monitoring.

---

## ⚙️ ADDITIONAL OPERABILITY Q&A

1) How does the system behave when all external dependencies (K8s, DB, all 5 LLM providers) fail simultaneously? Does it queue alerts, drop them, or crash?
- System is designed to degrade rather than hard-crash: DB can fall back to in-memory storage, and detector/API admission control still applies.
- Current branch should not assume a local-LLM fallback path; if all providers fail, analysis degrades and automation is constrained by governance/error handling.
- Bounded queue + rate limits + alert throttling can reject or suppress alerts under sustained overload (429/503/throttled), which is intentional backpressure.

2) Can an attacker bypass LLM analysis by crafting specific alert payloads? Is there input validation or prompt injection detection?
- Input validation exists via Pydantic schema (field lengths, allowed priority values, ISO timestamp, output_fields count cap).
- LLM response schema is validated/normalized before use.
- Dedicated prompt-injection detection/sanitization for alert text is not implemented; this remains a hardening gap.

3) How long does it take an operator to go from "alert fired" to "root cause identified"? Is there a one-click investigate feature?
- Operator APIs support one-click drilldown paths: incident detail, evidence, reasoning, and trace timeline endpoints.
- Current runtime does not enforce a measured SLA for “root cause identified”; timing is observable but not codified as a strict KPI.

4) Can you prove automated actions didn't make things worse? Is there before/after metrics and impact assessment?
- You have action/audit traceability (what ran, when, by whom/which mode), including action history and mitigation timing metrics.
- Automated before/after impact assessment snapshots are not implemented; proving non-regression still requires manual comparative analysis.

5) What prevents a compromised analyst account from mass-destroying infrastructure? Are there approval velocity limits and dual-approval for critical actions?
- Governance modes and approval queues exist (`autonomous`/`assisted`/`manual`), with protected-service blocking and audit trail.
- Dual-approval and approval velocity/rate limits are not implemented in current governance endpoints.
- Authentication is explicitly demo-grade and should be upgraded for production RBAC/identity assurance.

6) How do you detect if an LLM provider is giving consistently wrong severity scores? Is there accuracy tracking and auto-fallback?
- Operator feedback endpoints exist and compute running accuracy stats.
- Automatic provider fallback is based on operational failures (cooldown/circuit breaker), not semantic quality drift.
- No auto-demotion of providers based on low accuracy feedback is currently implemented.

7) What happens to the pipeline during a 10,000 alert/second flood? Does it backpressure, drop alerts, or crash?
- Backpressure + shedding: request queue caps in-flight processing; excess gets 503.
- API token bucket returns 429 when exhausted; per-rule/source/global alert throttling further suppresses noisy streams.
- Expected behavior is controlled dropping/rejection, not process crash.

8) How much does it cost to process 1 million alerts? Is there cost-aware routing and semantic caching?
- Cost-aware routing exists (priority/cost_optimized/ab_test/severity_adaptive) with token/cost observability.
- Fingerprint dedup and response caching reduce calls, but semantic embedding cache is not implemented.
- Exact 1M-alert cost depends on dedup hit rate, provider mix, and routing mode; code provides estimations, not a fixed constant.

9) How long does it take to add a new IoT device type or LLM provider? Is there a plugin architecture with hot-reload?
- LLM layer is modular/provider-managed, but adding a provider still requires code + deployment restart.
- Adding a new IoT device type requires emulator/API/manifests updates and redeploy.
- Hot-reload plugin architecture is not present in the current runtime path.

10) Can you replay yesterday's exact alert stream for testing? Is there event sourcing and time-travel debugging?
- Audit/trace export exists (events list, per-trace timeline, CSV/JSON export).
- Full event-sourcing replay/time-travel execution is not implemented.
- You can inspect and export historical traces, but deterministic pipeline replay is currently a gap.

---

## Priority Improvement Backlog (Immediate)

P0 (Reliability + Safety)
1. Implement explicit no-LLM-safe fallback analyzer and disable destructive actions when all providers fail.
2. Add per-user chat rate limiting and abuse protection.
3. Wire IDS API automated actions to ThreatResponse CRD creation for operator-native reconcile path.

P1 (Operator Trust)
4. Add explicit MTTD/MTTR KPIs and trace elapsed timings.
5. Persist audit timeline to database for durable incident forensics.
6. Add MITRE heatmap tab backed by live mapped alerts.

P2 (UX and Governance)
7. Add hotkeys and mobile hamburger navigation.
8. Add dedicated pending-actions queue tab with bulk approval workflows.
9. Add PDF incident export endpoint.

P3 (Cost and Analytics)
10. Add semantic near-duplicate cache (embedding similarity) and experiment metrics.
11. Split prompt/completion billing rates per provider.
12. Add A/B experiment outcome analytics view (quality, latency, cost).
