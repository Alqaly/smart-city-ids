# Examiner Q&A (30 Questions) — Smart City IDS

Last updated: 2026-02-24

This is a cleaned, demo-ready Q&A based on the current implementation (code + manifests + dashboard behavior), not a generic template.

Scope used:
- `docs/ARCHITECTURE.md`
- `docs/reference/FORCED_ARCHITECTURE_50Q.md`
- `k8s-manifests/*` (Falco/Suricata/forwarders)
- `services/ids-api/src/api/*`, `services/ids-api/src/governance.py`
- current dashboard (`services/ids-api/static/index.html`)

## QA Master Guide

Use this file as the **primary examiner Q&A script** (architecture, pipeline, LLM, dashboard, governance).

Specialist deep dives (keep separate for speed during rehearsal):
- `docs/reference/EXAMINER_IOT_QA_20.md` — IoT emulation, deployments, endpoints, MQTT noise, `kubectl`-verified answers
- `docs/DETECTION_TELEMETRY_ATTACK_QA.md` — detection/attack mechanics deep-dive questions
- `docs/SCENARIOS/MQTT_FLOOD_LATERAL_IMPACT.md` — staged scenario spec (MITRE ATT&CK-ICS-style framing, expected telemetry, success criteria)

Recommended usage:
- Start in this file for most questions.
- Switch to `docs/reference/EXAMINER_IOT_QA_20.md` when the examiner focuses on IoT emulation realism, device modeling, or Kubernetes IoT deployment details.

## 1) What is the overall architecture of the Smart City IDS?
- It is a Kubernetes-native IDS stack on K3s with four major layers:
- Detection: Falco (runtime/syscall) and Suricata (network signatures)
- Ingestion + Correlation: IDS API (FastAPI) receives alerts from both forwarders
- Analysis + Response: LLM provider manager + governance + K8s automation actions
- Observability + UX: PostgreSQL (or memory fallback), Prometheus/Grafana, dashboard UI
- Falco and Suricata are parallel detectors, not sequential stages.

## 2) How does an alert flow end-to-end through the system?
- IoT service traffic/runtime behavior triggers Falco or Suricata.
- Forwarder normalizes detector output and POSTs to IDS API (`/api/alerts/internal`).
- IDS API pipeline: queue/rate-limit -> alert-level throttle -> dedup cache -> LLM analysis -> governance check -> optional K8s action -> DB/audit -> SSE to dashboard.
- Dashboard consumes stored metrics via REST and live events via SSE (`/api/alerts/live`).

## 3) Why Kubernetes, and how does it help scalability/resilience?
- Kubernetes lets the project model many services and detectors in one consistent environment.
- It provides service discovery (`*.svc.cluster.local`), restart/self-healing, and horizontal scaling for app components.
- It also makes defensive actions realistic (e.g., applying NetworkPolicy isolation or scaling a deployment).
- In this demo, K8s is also the control plane the IDS acts on.

## 4) How are the 13 IoT devices modeled in the cluster?
- Current device inventory is hybrid: logical registry rows plus pod-backed emulator rows exposed by `/api/iot/devices`.
- It corresponds to the expected active set: `2 traffic-camera + 2 healthcare-api + 2 parking-system + 3 env-sensor + 3 street-lighting + 1 mqtt-broker`.
- Separately, there are additional MQTT emulators (enhanced/high/medium/burst) that generate traffic and load.
- IoT APIs and telemetry aggregation are implemented in `services/ids-api/src/api/iot.py`.

## 5) What are the main failure points, and how does the system handle them?
- Detector failure (Falco/Suricata/forwarders): alerts from that source stop, but the other source and dashboard stay up.
- LLM provider failure: provider manager uses failover/circuit-breaker/cooldown and tries the next provider.
- DB outage: IDS API continues in memory fallback mode (dashboard now labels this clearly as demo fallback).
- Dashboard offline: backend still processes alerts; SSE/REST consumers can reconnect later.

## 6) What is the role of Suricata, and what attacks does it detect here?
- Suricata detects network-level attacks via signatures/rules (HTTP, DNS, protocol abuse patterns).
- In this project, custom rules include SQLi patterns, HTTP flood, auth brute force, and DNS tunneling-style behavior.
- These are defined in `k8s-manifests/suricata.yaml`.

## 7) What is the role of Falco, and what runtime behaviors do your custom rules focus on?
- Falco detects suspicious runtime/syscall behavior inside containers.
- Custom rules focus on patterns like shell in container, sensitive file reads, package manager execution, crypto-mining behavior, and unexpected DB access.
- Rule customizations are in `k8s-manifests/falco-values.yaml`.

## 8) How did you reduce false positives in Falco, especially “Sensitive File Read”?
- Reduction is a combination of rule tuning + forwarder filtering + UI labeling.
- The dashboard now marks many monitoring-stack sensitive-file reads (Grafana/Prometheus/certs) as likely platform noise instead of presenting them as unexplained threats.
- Important: monitoring namespace alerts are still forwarded intentionally for visibility (`falco-forwarder` allows `monitoring` and `falco-system`).

## 9) How is alert flooding handled when Suricata generates hundreds/minute?
- There are two controls:
- Deduplication (cache/fingerprint) reduces repeated LLM calls and cost.
- Alert-level rate limiter/throttler suppresses repeated duplicates before DB + SSE broadcast.
- Recent fix: throttled duplicates are stored in `throttled_alerts` and not sent to the live dashboard stream, which prevents UI flood.

## 10) Explain one custom Suricata rule and one custom Falco rule in detail.
- Suricata example: `SMARTCITY HTTP flood` (`sid:9000003`, `k8s-manifests/suricata.yaml`)
  - Uses `detection_filter: track by_src, count 300, seconds 10`
  - Meaning: if one source sends >300 matching HTTP requests in 10s, trigger attempted-DoS alert.
- Falco example: “Sensitive File Read” (custom rule set in `falco-values`)
  - Detects reads of sensitive paths from containers.
  - In smart-city context, this matters for secrets/certs/config theft, but needs namespace/context tuning to avoid platform noise (e.g., Grafana certificate reads).

## 11) What does the IDS API do, and how does it sit between detectors and LLMs?
- It is the control and correlation layer.
- It receives normalized alerts, applies backpressure/throttling/dedup, calls LLM analysis, enforces governance policy, triggers K8s actions, persists/audits outcomes, and exposes dashboard APIs.
- It decouples raw detector noise from analyst-facing decisions.

## 12) How does deduplication logic work?
- Alerts are fingerprinted using stable fields (rule/source/key runtime/network fields) and cached with TTL.
- If a duplicate arrives within TTL, the system can reuse prior analysis instead of calling an LLM again.
- Dedup stats are exposed by `/api/deduplicator-stats` (hit rate, hits/misses, estimated cost saved).
- The dashboard now surfaces this as `Dedup + LLM Savings`.

## 13) What is the “Governance + K8s Actions” stage, and what actions can it take?
- It is the policy gate between “analysis suggests action” and “cluster changes happen.”
- Typical actions include pod isolation (NetworkPolicy), scale up/down deployment, and related containment/mitigation actions depending on severity and policy.
- It also records pending approvals/history for auditability.

## 14) What is the difference between autonomous, assisted, and manual modes?
- `autonomous`: high-confidence actions can execute automatically.
- `assisted`: medium-confidence actions require analyst approval (1-click gate).
- `manual`: no automatic execution; analyst approves/builds the response.
- Legacy names are normalized (`live` -> `autonomous`, `active` -> `assisted`, `dry-run` -> `manual`).
- UI intentionally does not expose a full bypass/unsafe override mode.

## 15) How do you prevent dangerous or noisy automated actions from causing harm?
- Governance thresholds use severity + confidence.
- Human approval is required in assisted/manual paths.
- Flood suppression limits repeated noisy alerts from repeatedly triggering automation.
- K8s actions are scoped (targeted pod/deployment), and the system keeps audit trails of actions taken.

## 16) Why are there 5 LLM providers, and how do you choose one per alert?
- Multiple providers improve resilience (quota/auth failures, outages, latency spikes).
- Provider manager supports priority/failover and other routing behaviors.
- The active provider can change based on configured order, health, cooldown state, and routing strategy.

## 17) How does the LLM Provider Control Center work under the hood?
- UI calls IDS API LLM endpoints for diagnostics, routing strategy, usage/cost summaries, health, and provider operations.
- The backend aggregates runtime status (circuit breaker/cooldown/errors) and usage metrics (tokens, calls, cost estimates).
- The page shows both provider health and DB-backed usage windows when available.

## 18) How do you calculate/store Total Cost Today, Total Tokens, and 7-day API calls?
- Backend aggregates token usage and estimated cost per provider, then exposes it via LLM usage/diagnostics endpoints.
- Cost is estimated from provider cost tables and token counts (or token estimates when a provider does not return usage).
- The dashboard’s LLM usage panel reads these API responses (DB-backed window summaries where supported).

## 19) What prompts do you send to the LLMs, and what structured output do you expect?
- Prompts contain normalized alert context (source/rule/summary/runtime/network fields) and ask for security analysis.
- Expected structured fields include severity, threat type, confidence, reasoning, business impact, recommendations, and automated actions.
- Response validation/sanitization is enforced in the LLM response schema layer before automation decisions use it.

## 20) How does failover work if an active provider becomes slow/unreachable mid-attack?
- Provider manager checks health/cooldown/circuit-breaker state and tries providers in order.
- Failed providers are marked with error/cooldown state and skipped temporarily.
- Circuit breaker and cooldown mechanisms prevent repeatedly hammering a known-bad provider during floods.

## 21) What do the main dashboard metrics mean, and how are they computed?
- `Total Alerts`: processed alerts tracked by IDS metrics/DB.
- `Critical Alerts`: alerts with final severity in the high/critical band (typically severity >= 8).
- Pipeline rates (`alerts/min`, `p95 latency`): computed in `/api/pipeline-overview`.
- IoT devices: active logical device count from IoT registry/K8s-enriched state.
- Dedup/flood suppression: from `/api/deduplicator-stats` and `/api/rate-limiter/status`.

## 22) How does the Live Pipeline Feed work technically?
- It uses Server-Sent Events (SSE), not WebSockets.
- Endpoint: `GET /api/alerts/live` (`text/event-stream`) in `services/ids-api/src/api/alerts.py`.
- Each connected dashboard client gets its own async queue; processed alerts are broadcast to all queues.
- Recent fix: throttled duplicates are not broadcast, preventing live-feed storms.

## 23) Why did the top banner show “LLM 0/5” while providers were Ready/Active before, and how was it fixed?
- The inconsistency came from mixing “configured provider count” vs “currently usable/healthy provider count” and stale frontend logic.
- UI logic was updated to use provider diagnostics summary more consistently and to distinguish configured vs operational providers.
- Result: the banner now reflects usable providers and health issues more accurately.

## 24) How do you ensure the dashboard is showing real data, not mock/demo values?
- Dashboard metrics come from live API endpoints (`/health`, `/api/metrics`, `/api/pipeline-overview`, `/api/alerts`, `/api/deduplicator-stats`, `/api/rate-limiter/status`, etc.).
- Recent fixes removed/avoided misleading placeholders and made fallback states explicit (e.g., DB memory fallback label).
- The live feed is event-driven (SSE), not pre-baked static content.

## 25) If you had to add one more key metric, what would it be?
- I would add `MTTR (Mean Time to Response)` split by governance mode (`autonomous`, `assisted`, `manual`).
- It directly shows the operational value of automation and is easy for examiners to interpret.

## 26) How does the system behave under high load (SQLi + HTTP flood)?
- Suricata may generate many repeated detections quickly.
- IDS API now suppresses duplicate floods via alert-level throttling + dedup, so LLM calls and UI updates do not scale linearly with raw detector noise.
- In demo mode, `ids-api` is pinned to 1 replica to keep in-memory dedup/throttle state consistent (important for clean suppression behavior).

## 27) What smoke tests / E2E tests do you run before demo or deploy?
- `bash scripts/readiness-check.sh` (login, UI/API reachability, auth)
- `bash scripts/run-live-attacks.sh --duration ...` (end-to-end detector -> IDS -> dashboard path)
- `bash scripts/readiness-check.sh --quick`
- `bash scripts/e2e-verbose-test.sh --quick`
- `python scripts/e2e-pipeline.py --api-url http://localhost:30800 --duration 5 --skip-provider-tests`

## 28) How do you debug issues like “LLM usage panel shows 0 but calls are happening”?
- Check API endpoints directly first:
- `/api/llm/diagnostics`
- LLM usage/cost summary endpoints used by the UI
- `/api/alerts` (look for `analysis_present` / `llm_engine`)
- Then check `ids-api` logs and provider manager state (cooldowns, auth errors, quota failures).
- Also check frontend auth/caching issues (stale token or old cached JS can make panels look broken).

## 29) What are the main security considerations for the IDS itself?
- LLM API keys/credentials must be kept in environment/K8s secrets, not hardcoded.
- Dashboard/API auth must protect governance/automation endpoints (login token required).
- Automation actions must be gated by governance mode and audit-logged.
- Rate limiting and dedup are also security controls for the IDS itself (preventing self-DoS via alert floods).

## 29b) If you need to add/replace an LLM API key quickly, what do you do?
- Update the key in the project `.env` (canonical source).
- Sync the Kubernetes secret used by `ids-api` and redeploy the API pod.
- Reset provider states (`/api/llm/retry-all`) so circuit breaker/cooldown latches do not hide the new key.
- Run `/api/llm/test/{provider}` and verify `/api/llm/diagnostics` shows the provider as healthy.
- Hard refresh the dashboard so the LLM Control tab re-renders current provider health/usage.

## 30) If you had more time, what would you improve next?
- Persist dedup/throttle state in Redis (or shared store) so scaling `ids-api` >1 replica stays consistent.
- Stronger RBAC for dashboard users (route-level role enforcement, not demo-only auth).
- Better detector noise suppression (namespace/profile-specific Falco exceptions, default UI filters for platform alerts).
- MTTR/MTTD trend dashboards and post-action verification/rollback metrics.

---

## Research Limitations + Roadmap (say this clearly in viva)

Use this section when an examiner pushes from "working demo" to "research-grade production design".

### Current implementation (defensible today)
- Real Falco + Suricata detections feed a live IDS API pipeline (rate-limit, dedup, LLM, governance, K8s actions).
- IoT emulation is realistic enough for protocol/API demonstrations (camera/FHIR/parking/MQTT/Modbus/OPC UA/TALQ), but not a full fleet management platform.
- LLM provider failover/circuit-breaker/cooldown behavior is implemented and observable in the dashboard.

### Known limitations (acknowledge directly)
- Dashboard fleet view is now hybrid. A row alone does not prove live hardware; use `source`, `last_seen`, heartbeat/telemetry, and IP context.
- Deduplication and alert throttling state are in-memory, so `ids-api` horizontal scaling requires a shared store for consistency.
- Scenario definitions are implemented as attack scripts + rules, but not yet fully formalized as ATT&CK-ICS stage-by-stage scenario specs across the whole catalog.
- Device onboarding path supports telemetry ingestion, but not per-device auth + schema-versioned fleet registry as a production IoT platform would require.

### Roadmap (research-grounded next steps)
- Formalize scenarios as staged ATT&CK-ICS mappings with expected Falco/Suricata/IDS telemetry and impact criteria.
- Continue improving logical-device persistence and richer liveness validation for external devices.
- Move dedup/throttle shared state to Redis (or equivalent) so multi-replica IDS API remains correct.
- Add device profiles and schema versioning (expected ranges/protocol capabilities/location metadata).
- Add per-device auth for telemetry ingress (API key or signed token), with mTLS gateway option for larger deployments.

### Standards framing (what to cite verbally)
- Threat modeling / scenario staging: MITRE ATT&CK for ICS (ATT&CK-ICS).
- IoT device capability/security baseline framing: NISTIR 8259 / 8259A.
- Detection engineering: Suricata thresholding + Falco custom rulesets and tuning.

---

## Demo Notes (what to say clearly)

- If the dashboard shows `Database: In-memory fallback (demo mode)`, say:
  - "The IDS API is still functioning; persistence degraded from PostgreSQL to in-memory fallback, which is an explicit resilience mode."
- If you see many `SMARTCITY HTTP flood` alerts:
  - "That is one Suricata flood signature repeating. The IDS now throttles duplicates before LLM calls and before the live feed to prevent alert storms."
- If you see Grafana/Falco sensitive-file alerts:
  - "Those are often platform-noise alerts from the monitoring namespace; the dashboard now marks them as likely noise and shows where they came from."
