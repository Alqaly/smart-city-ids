# Documentation Claims Validation Report (2026-02-24)

> [!IMPORTANT]
> Historical / snapshot document. This file may contain time-bound results, legacy route names, or report-only summaries.
> Do not use it as the current API/runtime contract. Verify current behavior using `docs/INDEX.md`, `docs/API_REFERENCE.md`,
> and live checks (`/health`, `/api/alerts`, `/api/metrics`).


Scope validated:
- `docs/reference/EXAMINER_QA_30.md`
- `docs/ARCHITECTURE.md`
- `docs/reference/FORCED_ARCHITECTURE_50Q.md`
- `docs/reference/DEMO_QA_CHECKLIST.md`

Method:
- Live script execution (`readiness-check`, `readiness-check`, `e2e-verbose-test`, `e2e-pipeline`, `run-live-attacks`)
- Direct API calls to `http://localhost:30800`
- Kubernetes resource checks (`kubectl`)
- Config/manifests inspection (`rg`)

## Summary

- `EXAMINER_QA_30.md`: Mostly validated and safe for demo speaking prep
- `ARCHITECTURE.md`: Valid overall, but had stale details (replicas, governance mode naming) — corrected
- `FORCED_ARCHITECTURE_50Q.md`: Useful as deep backup/gap-analysis, but not a strict “current runtime truth” doc
- `DEMO_QA_CHECKLIST.md`: Valid, updated with live attack script delta caveat

## Validated Live (PASS)

- Cluster connectivity and core workloads present (`falco`, `suricata`, `forwarders`, `ids-api`, `postgres`, `grafana`, `prometheus`)
- IDS API health endpoint reachable and healthy (`/health`)
- Dashboard reachable (`/ui`)
- Login works with `admin/admin`
- Protected endpoint access works with token
- IoT device baseline reported as `13`
- SSE live stream endpoint works (`/api/alerts/live` returns `event: connected`)
- Governance mode switching works live:
  - `manual`
  - `assisted`
  - `autonomous`
- Dedup stats endpoint returns real values (`/api/deduplicator-stats`)
- Alert flood suppression/rate limiter endpoint returns real values (`/api/rate-limiter/status`)
- Suricata rule `SMARTCITY HTTP flood` (`sid:9000003`) exists in config
- Falco forwarder namespace allowlist includes `smart-city`, `monitoring`, `falco-system`
- End-to-end alert processing works (`e2e-pipeline.py` produced a processed alert with analysis/action)

## Runtime Caveats (PASS architecture, FAIL current provider health)

- LLM provider architecture exists and is configured (5 providers visible)
- Current runtime provider health is degraded in this environment (all providers were `error`/`circuit_open` during some checks)
- This is a runtime credentials/quota/provider-state issue, not a missing feature issue

## Known Script/Docs Mismatch Found

### `scripts/run-live-attacks.sh` metrics delta output
- Script can report `Alerts received (delta, approx): +0` while also printing fresh IDS alerts in the sample output
- Detector -> forwarder -> IDS -> dashboard path is still working
- Treat this as a script metrics-counter bug, not a detection pipeline failure
- `docs/reference/DEMO_QA_CHECKLIST.md` updated to reflect this caveat

## Docs Corrected During Validation

### `docs/ARCHITECTURE.md`
- Updated `ids-api` replica wording to current demo reality (`×1 pod demo-pinned`)
- Updated governance naming from `autopilot` to `autonomous` (legacy aliases normalized)
- Updated governance mode table terminology

### `docs/reference/FORCED_ARCHITECTURE_50Q.md`
- Added status note clarifying it is a broader historical snapshot + gap analysis
- Added pointers to `docs/reference/EXAMINER_QA_30.md` and `docs/ARCHITECTURE.md`
- Corrected stale references (governance mode naming, chat rate limiter status, local-LLM fallback assumptions)

## Commands Run (evidence)

- `bash scripts/readiness-check.sh`
- `bash scripts/run-live-attacks.sh --duration 5 --show-alerts 3`
- `bash scripts/readiness-check.sh --quick`
- `bash scripts/e2e-verbose-test.sh --quick`
- `python scripts/e2e-pipeline.py --api-url http://localhost:30800 --duration 5 --skip-provider-tests`
- `curl -s http://localhost:30800/health`
- `curl -s http://localhost:30800/api/deduplicator-stats`
- `curl -s http://localhost:30800/api/rate-limiter/status`
- `curl -sN http://localhost:30800/api/alerts/live --max-time 2`
- `kubectl get pods -A`
- `kubectl get deploy/hpa -n smart-city ids-api ...`
- `rg` checks against `k8s-manifests/suricata-fixed.yaml` and `k8s-manifests/falco-forwarder.yaml`

## Recommendation for Demo Use

- Use `docs/reference/EXAMINER_QA_30.md` as your main speaking prep
- Use `docs/ARCHITECTURE.md` for technical follow-up, but rely on the updated wording
- Use `docs/reference/FORCED_ARCHITECTURE_50Q.md` only as deep backup / improvement discussion
- If `run-live-attacks.sh` shows `delta +0`, immediately point to:
  - recent alert sample output in the script
  - dashboard Alerts tab
  - `/api/metrics` total alert count
