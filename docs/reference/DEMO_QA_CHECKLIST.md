# Demo QA Checklist

Last updated: 2026-04-05

Related prep docs:
- `docs/reference/EXAMINER_QA_30.md` — concise, code-backed answers for common examiner questions
- `docs/reference/EXAMINER_IOT_QA_20.md` — IoT emulation/deployment/detection questions with live `kubectl` verification commands
- `docs/ARCHITECTURE.md` — full technical architecture reference

## Pre-Demo (Required)
- [ ] `bash scripts/readiness-check.sh` returns `DEMO STATUS: READY`
- [ ] Dashboard opens: `http://localhost:30800/ui`
- [ ] Login works: `admin / admin`
- [ ] Alerts tab loads
- [ ] Overview tab shows non-zero alerts
- [ ] IoT inventory is non-zero and explainable via `/api/iot/devices`
- [ ] If discussing live devices, distinguish `registered` logical rows from pod-backed or recently heartbeating rows

## Demo-Critical Runtime Checks (Recommended)
- [ ] `bash scripts/run-live-attacks.sh --duration 5 --show-alerts 2`
- [ ] Recent alerts appear in script sample output (source + severity + rule)
- [ ] If script reports alert delta `+0` but samples are fresh, verify with `/api/metrics` or dashboard (known delta-counter script bug)
- [ ] Recent alert sample prints (source + severity + rule)
- [ ] Dashboard shows new alerts after attack run

## Optional Technical Validation (If Time)
- [ ] `bash scripts/readiness-check.sh --quick`
- [ ] `bash scripts/e2e-verbose-test.sh --quick`
- [ ] `python scripts/e2e-pipeline.py --api-url http://localhost:30800 --duration 5 --skip-provider-tests`

## Acceptable Warnings (Do Not Block Demo)
- Prometheus/Grafana NodePort unreachable in `readiness-check.sh --quick`
- Prometheus scrape warnings in quick mode
- LLM provider quota/auth warnings for non-primary providers (if primary path still works)

## Blockers (Fix Before Examiner)
- [ ] Cannot login with `admin/admin`
- [ ] `/health` not healthy
- [ ] `/ui` not reachable
- [ ] `run-live-attacks.sh` completes but alert delta is `0`
- [ ] IDS API pod not running
- [ ] Suricata/Falco pods not running

## One-Line Fallback Plan (if UI glitches)
- Run `bash scripts/run-live-attacks.sh --duration 10 --show-alerts 3`
- Show `python scripts/e2e-pipeline.py --api-url http://localhost:30800 --duration 5 --skip-provider-tests`
- Explain end-to-end flow from terminal outputs and metrics
