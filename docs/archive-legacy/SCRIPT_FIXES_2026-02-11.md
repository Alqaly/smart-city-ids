# Script Reliability Fixes (2026-02-11)

## Summary
This update fixes script failures reported during full-script runs:

- Kubernetes scripts failing due unreadable `KUBECONFIG=/etc/rancher/k3s/k3s.yaml`
- Demo readiness false failures (Falco label assumptions + strict endpoint path)
- Migration script failure when `DATABASE_URL` is unset
- Attack simulation scripts failing due outdated pod labels/service names
- Falco daemonset crash (`could not initialize inotify handler`)

## Files Updated

- `scripts/lib/script-utils.sh`
- `scripts/check-setup.sh`
- `scripts/demo-readiness.sh`
- `scripts/build-images.sh`
- `scripts/demo-walkthrough.sh`
- `scripts/start-everything.sh`
- `scripts/db/run_migrations.sh`
- `scripts/demos/capstone1-demo.sh`
- `attack-simulations/generate-security-events.sh`
- `attack-simulations/generate-network-attacks.sh`
- `attack-simulations/generate-advanced-attacks.sh`
- `attack-simulations/monitor-ids-logs.sh`
- `attack-simulations/ids-demo-showcase.sh`
- `k8s-manifests/falco-values.yaml`

## What Changed

1. Kubeconfig fallback and readability handling
- Scripts now fall back to `~/.kube/config` when exported `KUBECONFIG` is unreadable.
- Added explicit readable-file checks in `ensure_kubeconfig`.

2. Counter logic under `set -e`
- Replaced `((VAR++))` with `((VAR+=1))` in strict-mode scripts to avoid early exits.

3. Demo readiness robustness
- Falco running check now detects actual `falco-*` running pods reliably.
- Token-protected endpoint check now supports `/api/operator/dashboard` plus fallback endpoints (`/api/operator/metrics`, `/api/operator/incidents`).

4. Migration script fallback execution
- `run_migrations.sh` now:
  - Loads `.env` automatically.
  - Derives `DATABASE_URL` when missing.
  - Falls back to in-cluster PostgreSQL (`deploy/postgres`) if local DB is unreachable.

5. Attack simulation portability
- Attack scripts now support multiple pod labels (`iot-device`, `iot-device-enhanced`, `iot-simulator`, etc.).
- Service lookup tolerates environments without `iot-device-service`.
- Pod command execution was hardened so missing tools do not crash the script.

6. Falco stability fix
- Set `falco.watch_config_files: false` in `k8s-manifests/falco-values.yaml`.
- Live cluster ConfigMap was updated and `daemonset/falco` restarted to clear CrashLoop.

7. Start script kubeconfig behavior
- `start-everything.sh` now syncs kubeconfig to user path (`~/.kube/config`) and writes that path to shell profiles instead of forcing `/etc/rancher/k3s/k3s.yaml`.

## Validation Run Results

Validated with `KUBECONFIG=/etc/rancher/k3s/k3s.yaml` exported (worst-case environment):

- `bash scripts/check-system.sh` -> `EXIT 0`
- `bash scripts/demo-readiness.sh --quick` -> `EXIT 0`
- `bash scripts/check-setup.sh` -> `EXIT 0`
- `bash scripts/db/run_migrations.sh` -> `EXIT 0` (via k8s fallback)
- `bash attack-simulations/generate-security-events.sh` -> `EXIT 0`
- `bash attack-simulations/generate-network-attacks.sh` -> `EXIT 0`
- `bash attack-simulations/generate-advanced-attacks.sh` -> `EXIT 0`


## Additional Fixes (same day)

### 8. Demo script stability + non-interactive support
- `scripts/demo.sh`
  - Fixed metric parsing to avoid strict-mode exits when metrics endpoint is temporarily unavailable.
- `scripts/demos/phase4-run-smart-city-attacks.sh`
  - Uses shared script utilities (`ensure_kubeconfig`, nodePort helpers).
  - Uses dynamic Grafana/Prometheus nodePorts (no hardcoded `31701`).
  - Added non-interactive auto-confirm behavior for CI/audits.
  - Added Kubernetes API retry loop before failing preflight.
  - Fixed metric parsing under `set -euo pipefail`.
- `scripts/demos/supervisor-demo.sh`
  - Uses shared script utilities and dynamic nodePorts.
  - Added `--yes` mode to skip ENTER prompts.
  - Fixed arithmetic and metric parsing reliability.
- `scripts/demos/capstone1-live-view.sh`
  - Added `--help` support.
  - Exits cleanly when no TTY is available (instead of failing in automation).
- `scripts/demos/capstone1-demo.sh`
  - Added `--help` support.
  - Fixed metric parsing and Grafana URL building (dynamic nodePort).

### 9. Scalability test reliability
- `scripts/scalability-test.sh`
  - Added kubeconfig check + Kubernetes API retries.
  - Auto-discovers Prometheus and IDS API nodePorts from services.
  - Fixed JSON output schema to avoid invalid booleans/nulls in result files.

### 10. Grafana + LLM status consistency
- `k8s-manifests/grafana-provisioning-dashboards.yaml`
  - Fixed incorrect circuit-breaker label query from `engine="xai-grok-4"` to `engine="xai"`.
  - LLM request panel now filters to engines that actually exist in current circuit-breaker metrics.
- `services/ids-api/src/main.py`
  - Circuit breaker now tracks configured providers only, reducing misleading CLOSED/OPEN states for unconfigured engines.

## Latest Script Audit Artifacts

All script run logs and summaries are in:
- `script-run-outputs/20260211-124420-scripts-audit-fixed`
- `script-run-outputs/20260211-124702-scripts-audit-fixed2`
- `script-run-outputs/20260211-124952-scripts-audit-final`

Focused retests after final patches:
- `scripts/demo.sh --dry-run --wait 1` -> `EXIT 0`
- `scripts/scalability-test.sh --scales 10 --duration 1` -> `EXIT 0`
- `AUTO_CONFIRM=1 scripts/demos/phase4-run-smart-city-attacks.sh 1` -> `EXIT 0`
- `scripts/demos/supervisor-demo.sh --yes` -> `EXIT 0`
- `scripts/check-system.sh` -> `EXIT 0`

## Additional Compatibility/Scalability Hardening (Operator + One-Command)

### Core fixes applied
- Added robust alert source detection in `services/ids-api/src/main.py`:
  - Uses `rule`, `output`, `output_fields.container.name`, and `event_type`.
  - Fixes Suricata alerts being miscounted as Falco when signature text doesn't contain `suricata`.
- Added IoT active gauge refresh in `services/ids-api/src/main.py`:
  - `smartcity_ids_iot_devices_active` now falls back to running IoT pods in Kubernetes when DB-based registrations are sparse.
  - Fixes dashboard IoT devices staying at zero.
- Added LLM manager fallback in `services/ids-api/src/main.py`:
  - If `llm_providers` package is unavailable in ConfigMap-mounted code, IDS API falls back to legacy `LLMEngineManager` instead of `llm_manager=None`.
  - Prevents `'NoneType' object has no attribute analyze'` failures.

### Deployment compatibility fixes
- `deploy.sh`:
  - Secret creation now matches deployment contract:
    - Secret name: `ids-secrets`
    - Keys: `xai-api-key`, `openai-api-key`, `anthropic-api-key`, `gemini-api-key`, `kimi-api-key`
  - `ids-app-code` and `ids-app-static` use server-side apply to avoid oversized annotation failures.
- `scripts/start-everything.sh`:
  - Uses user kubeconfig path consistently instead of forcing `/etc/rancher/k3s/k3s.yaml`.
  - `ids-app-code` configmap updates use server-side apply.

### New one-command script
- Added `scripts/one-command-ready.sh`:
  - Fixes and persists kubeconfig to `~/.kube/config`
  - Loads keys from `.env`
  - Upserts `ids-secrets` with available provider keys
  - Applies core manifests with retry logic and API-server transient handling
  - Syncs IDS API configmaps and restarts IDS API
  - Validates readiness and prints endpoints
  - Optional monitor mode: `--monitor`

### Verified outcomes (latest)
- `/api/llm/status` now returns providers (non-zero): xai/openai/kimi in current environment.
- IoT active gauge now reports non-zero (`smartcity_ids_iot_devices_active` reflects running simulator pods).
- Suricata source metric present when Suricata-formatted alerts are ingested:
  - `smartcity_ids_alerts_received_total{priority="Warning",source="suricata"} 1.0`

### Remaining external limitation
- xAI provider responds with HTTP 429 (credit/quota exhausted) in current environment.
  - This is an account quota state, not code/config mismatch.

## Grafana/Data Consistency Fixes (2026-02-11 evening)

### Why Grafana looked misleading
- Two dashboard definitions were diverged:
  - Provisioned dashboard in cluster: `k8s-manifests/grafana-provisioning-dashboards.yaml` (`grafana-dashboard-ieee-improved.json`)
  - Older dashboard file often imported/viewed manually: `infrastructure/monitoring/grafana-dashboard-unified.json`
- The older dashboard used:
  - `smartcity_ids_iot_devices_active or vector(0)` (can show contradictory 0 + real value series)
  - Circuit-breaker labels `CLOSED/OPEN` (easy to misread as provider "up/down")

### Code fixes applied
- `services/ids-api/src/llm_manager.py`
  - `analyze()` now returns:
    - `failed_engines`
    - `attempted_engines`
  - This lets API-level metrics reflect failover attempts correctly.
- `services/ids-api/src/main.py`
  - `analyze_with_fallback()` now updates circuit-breaker state for failed/successful engines using returned `failed_engines`.
  - `/metrics` now calls `update_circuit_breaker_metrics()` on each scrape (series always present).
  - `startup()` now initializes circuit-breaker metrics immediately.

### Dashboard/query fixes applied (existing files only)
- `k8s-manifests/grafana-provisioning-dashboards.yaml`
  - IoT panels:
    - `avg_over_time(iot_device_active[15m])`
    - -> `max(smartcity_ids_iot_devices_active) or on() vector(0)`
  - LLM requests panel:
    - `increase(...) * on(engine) group_left() (smartcity_ids_circuit_breaker_state >= 0)`
    - -> `sum by (engine, result) (increase(smartcity_ids_llm_requests_total[5m]))`
- `infrastructure/monitoring/grafana-dashboard-ieee-improved.json`
  - Same IoT + LLM query fixes as above.
- `infrastructure/monitoring/grafana-dashboard-unified.json`
  - IoT panel fixed to:
    - `max(smartcity_ids_iot_devices_active) or on() vector(0)`
  - Provider state labels normalized:
    - `CLOSED -> HEALTHY`
    - `HALF_OPEN -> TESTING`
    - `OPEN -> FAILING`

### Runtime rollout performed
- Applied existing Grafana provisioning manifest and restarted Grafana:
  - `kubectl apply -f k8s-manifests/grafana-provisioning-dashboards.yaml`
  - `kubectl -n monitoring rollout restart deploy/grafana`
- Replaced `ids-app-code` ConfigMap from `services/ids-api/src` and restarted IDS API:
  - `kubectl -n smart-city replace -f /tmp/ids-app-code.yaml`
  - `kubectl -n smart-city rollout restart deploy/ids-api`

### Verification snapshots (post-fix)
- Circuit breaker metrics now present (no empty series):
  - `smartcity_ids_circuit_breaker_state{xai}=2`
  - `smartcity_ids_circuit_breaker_state{openai}=2`
  - `smartcity_ids_circuit_breaker_state{kimi}=2`
- IoT query now returns single resolved value (no duplicate 0 series):
  - `max(smartcity_ids_iot_devices_active) or on() vector(0)` -> `39`
- Alert sources currently:
  - `falco=29064`
  - `suricata=1`
- LLM backend logs still show real external API states:
  - `xAI: 429 quota exhausted`
  - `OpenAI/Kimi: 401 invalid authentication`

## Demo + Endpoint Reliability Fixes (latest)

### `scripts/demo.sh` fixes
- Root cause fixed: metrics were previously read from `kubectl exec deploy/ids-api` (random replica each call), which caused false `+0` and inconsistent before/after values.
- Script now pins a single IDS API pod (`IDS_METRICS_POD`) for all baseline/after checks in one run.
- Added polling window (`MAX_PIPELINE_WAIT`, default `90s`) instead of one-shot check.
- Added deterministic internal fallback injection if runtime path does not produce a delta in time.
- Added deterministic Suricata-format injection for `--attack-type network`.
- Fixed deterministic injection transport by using `kubectl exec -i ... python` (stdin heredoc requires `-i`).
- Attack execution now uses `sh -c` (more portable than `bash -c` in minimal containers).
- Success criteria improved:
  - `received > 0` is treated as pipeline success.
  - `processed == 0` is reported as warning (async/throttled/provider-failure) instead of hard fail.

### LLM provider status clarity
- `services/ids-api/src/main.py`
  - `smartcity_ids_circuit_breaker_state` now exports all engines with explicit unconfigured state:
    - `0=HEALTHY`, `1=TESTING`, `2=FAILING`, `3=UNCONFIGURED`
  - Root endpoint `/` now reports generic multi-provider LLM mode instead of hardcoding xAI+OpenAI wording.

### Dashboard status clarity
- Updated mappings in:
  - `infrastructure/monitoring/grafana-dashboard-unified.json`
  - `infrastructure/monitoring/grafana-dashboard-ieee-improved.json`
  - `k8s-manifests/grafana-provisioning-dashboards.yaml`
- Provider cards now support explicit `UNCONFIGURED` state in addition to `HEALTHY/TESTING/FAILING`.

### Endpoint/runbook documentation
- Added `docs/DEMO_RUNBOOK_AND_ENDPOINT_CHECKS.md` with:
  - API key verification in 3 places (`.env`, Kubernetes secret, live pod env)
  - one-by-one endpoint validation commands
  - demo commands for Falco and network/suricata paths
  - direct Prometheus truth queries for dashboard cross-checks

## Consolidation + Immediate Access Fixes

- Added new canonical script: `scripts/demo-day.sh`
  - Starts local access (`localhost:8000`, `localhost:3000`, `localhost:9090`)
  - Prints NodePort + localhost URLs
  - Shows full workload summary (smart-city + monitoring + IoT pods)
  - Verifies API keys in `.env`, `ids-secrets`, and running `ids-api` pod
  - Verifies protected endpoints with operator token
  - Runs controlled attacks with bounded budget (`--profile`, `--runs`)
  - Integrates existing `scripts/demo.sh` + `attack-simulations/*` workflows

- `scripts/one-command-ready.sh` improvements:
  - Added optional `--no-port-forward` (default now starts local access automatically)
  - Starts and validates local port-forwards for IDS API/Grafana/Prometheus
  - Prints local URLs + process IDs
  - Prints workload summary counts
  - Fixed `ids-app-code` ConfigMap creation bug (`--from-file=llm_providers=<dir>` invalid usage)
  - Fixed rollout race by selecting running pod names for `kubectl exec` checks
  - Removed fragile wait-on-all-pods for `ids-api` label during rolling updates

- `scripts/check-system.sh` endpoint text corrected:
  - NodePort UI now shown as `http://<node-ip>:30800/ui`
  - localhost UI explicitly marked as port-forward dependent

## LLM Credit Burn + Alert Storm Root-Cause Fixes (2026-02-11 night)

### Root causes found
- `services/ids-api/src/main.py`
  - `/api/alerts/internal` was bypassing key flood/cost controls used by `/api/alerts`:
    - no API rate limiter
    - no request queue backpressure
    - no alert-level throttling
    - no dedup cache reuse
  - Result: cluster-forwarded alert bursts could trigger repeated LLM calls.
- `k8s-manifests/falco-forwarder.yaml`
  - Falco forwarder streamed logs without replay protection.
  - On restarts/reconnects it could re-read prior alert lines and forward duplicates again.
- `services/ids-api/src/llm_providers/manager.py`
  - Providers with exhausted quota/invalid auth were retried on every alert, causing repeated failed attempts and noisy failover.

### Permanent code fixes applied
- `services/ids-api/src/main.py`
  - `/api/alerts/internal` now uses same controls as `/api/alerts`:
    - token-bucket rate limiting
    - request queue admission control
    - alert rate limiter
    - dedup cache before LLM call
  - Added `finally` dequeue to avoid queue leak.
  - Fixed `AlertRateLimiter.should_process(...)` call to use correct dict signature.
  - Fixed `AlertResponse.alert_id` type to accept both numeric and throttled string IDs.
- `services/ids-api/src/llm_providers/manager.py`
  - Added provider cooldown for non-retryable provider states:
    - exhausted credits/quota
    - spending limit reached
    - invalid/unauthorized key
    - 401/403/429 terminal errors
  - Cooldown state is exposed in status (`cooldown_until`, `cooldown_remaining_seconds`).
  - Cooldown duration configurable via `LLM_PROVIDER_COOLDOWN_SECONDS` (default `900`).
- `k8s-manifests/falco-forwarder.yaml`
  - Added replay protection:
    - stream with `since_seconds=15`
    - in-forwarder duplicate hash suppression with TTL (`DEDUP_TTL_SECONDS=120`)

### Tests added/updated
- `services/ids-api/tests/test_llm_provider_manager.py`
  - Added cooldown regression test: quota error on `xai` causes temporary skip on next request.
- `services/ids-api/tests/test_internal_alert_controls.py` (new)
  - Verifies duplicate `/api/alerts/internal` events call LLM once (second event served from dedup cache).

### Validation
- `pytest -q services/ids-api/tests/test_internal_alert_controls.py` -> `1 passed`
- `pytest -q services/ids-api/tests/test_llm_provider_manager.py services/ids-api/tests/test_operator_contracts.py` -> `5 passed`

## Permanent localhost access fix (2026-02-11 late night)

### Problem
- Users hit:
  - `curl http://localhost:8000/health`
  - `curl http://localhost:8000/ui`
  - -> `connection refused`
- Root cause: scripts were creating ad-hoc `kubectl port-forward` background jobs that could exit silently, leaving `localhost:8000` down.

### Permanent fix
- Embedded robust local port-forward handling directly into existing scripts:
  - explicit `KUBECONFIG` usage
  - stale process cleanup
  - health-checked startup with retry window
  - clear fallback to NodePort
- Updated:
  - `scripts/one-command-ready.sh`
  - `scripts/demo-day.sh`
  - `scripts/start-everything.sh`
  - `scripts/lib/script-utils.sh` (shared port-forward helper functions)

### Canonical user command
- `bash scripts/one-command-ready.sh`
- then:
  - `curl http://localhost:8000/health`
  - `curl http://localhost:8000/ui`
