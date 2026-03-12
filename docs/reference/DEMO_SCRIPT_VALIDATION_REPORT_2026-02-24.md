# Demo Script Validation Report (2026-02-24)

> [!IMPORTANT]
> Historical / snapshot document. This file may contain time-bound results, legacy route names, or report-only summaries.
> Do not use it as the current API/runtime contract. Verify current behavior using `docs/INDEX.md`, `docs/API_REFERENCE.md`,
> and live checks (`/health`, `/api/alerts`, `/api/metrics`).


Scope: demo-critical scripts and auth path. This is not a full audit of all project files.

## Changes Applied

### Auth and demo account
- Enforced single demo login account:
  - `admin / admin`
- Updated demo scripts to use `admin/admin` instead of `operator/operator`

### Script reliability improvements
- `scripts/run-live-attacks.sh`
  - Added clearer non-technical narration
  - Added mode validation
  - Added recent alert sample output
  - Fixed sample alert rendering bug
- `scripts/readiness-check.sh`
  - Rewritten for:
    - API URL auto-detection (`localhost:8000`, `localhost:30800`, NodePort)
    - `admin/admin` login validation
    - protected endpoint validation with token
    - reliable dashboard UI check (no `pipefail` false negative)
- `scripts/readiness-check.sh`
  - `admin/admin` login
  - `--quick` mode now treats Prometheus/Grafana issues as warnings
  - Added curl timeouts to prevent hangs
- `scripts/e2e-verbose-test.sh`
  - API URL auto-detection
  - `admin/admin` auth support
  - fixed removed endpoint reference
  - fixed readonly color variable conflict
  - fixed dashboard UI false negative under `pipefail`
- `scripts/comprehensive-test.sh`
  - API URL auto-detection
  - `admin/admin` auth support
  - replaced removed LLM metrics endpoint check

### Python demo script improvements
- `scripts/eval-complete.py`
  - auto-login with `admin/admin` if no token provided
  - final summary no longer falsely claims LLM analysis succeeded when alert processing returns error
- `scripts/e2e-pipeline.py`
  - auto-login with `admin/admin`
  - new `--skip-provider-tests` flag for fast/reliable demo runs

### Runtime bug fix discovered during testing
- Fixed LLM manager failover bug in `services/ids-api/src/llm_providers/manager.py`
  - missing attribute: `rate_limit_cooldown_seconds`
  - unsafe exception branch referencing `result` when undefined

## Validation Executed

### Static validation
- `bash -n` on patched shell scripts: PASS
- `python -m py_compile` on patched Python scripts: PASS

### Real cluster validation (executed)
- `bash scripts/readiness-check.sh`
  - PASS
  - Result: `DEMO STATUS: READY`
- `bash scripts/run-live-attacks.sh --duration 5 --show-alerts 2`
  - PASS
  - Observed non-zero alert delta (`+62` in one run)
  - Recent alert sample printed
- `bash scripts/readiness-check.sh --quick`
  - PASS (with warnings)
  - Warnings were Prometheus/Grafana visibility only
- `bash scripts/e2e-verbose-test.sh --quick`
  - PASS
  - Dashboard, health, governance, pipeline checks succeeded
- `python scripts/e2e-pipeline.py --api-url http://localhost:30800 --duration 5 --skip-provider-tests`
  - PASS
  - Authenticated as admin
  - Submitted test alert
  - Received processed alert response (LLM engine `kimi`)

## Known Non-Blockers
- Prometheus/Grafana NodePorts may be unreachable on some setups even when the IDS demo itself is ready
- Some LLM providers may show auth/quota issues depending on keys/quotas; use primary path and `--skip-provider-tests`

## Recommended Demo Commands (Tomorrow)
```bash
bash scripts/readiness-check.sh
bash scripts/run-live-attacks.sh --duration 30 --show-alerts 3
python scripts/e2e-pipeline.py --api-url http://localhost:30800 --duration 5 --skip-provider-tests
```
