# Current Docs (Live-Verified)

This file lists the documents and runtime checks that were verified against the current deployed Smart City IDS instance.

## What this is

- A reviewer-facing pointer to the current, trustworthy docs
- A record of live endpoint checks performed against the running system
- A guardrail against relying on historical/snapshot reports as runtime truth

## Verify First (current deployment)

Use these before trusting any report/snapshot claim:

```bash
curl -s http://localhost:30800/health | jq '{status,storage_type,db:.components.database}'
curl -s http://localhost:30800/api/alerts?limit=3 | jq '.alerts | length'
curl -s http://localhost:30800/api/metrics | jq '{total_alerts,iot_devices_active}'
```

Auth-required checks:

```bash
TOKEN=$(curl -s -X POST http://localhost:30800/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin"}' | jq -r '.access_token')

curl -s -H "Authorization: Bearer $TOKEN" \
  http://localhost:30800/api/governance/status | jq '{mode,metrics}'
```

## Live-Verified Docs (current truth)

- `README.md` (project scope + entry points)
- `docs/INDEX.md` (documentation trust model)
- `docs/API_REFERENCE.md` (current route contract; use this over report docs)
- `docs/ARCHITECTURE.md`
- `docs/HOW_IT_WORKS.md`
- `docs/OPERATIONS.md`
- `docs/TROUBLESHOOTING.md`
- `docs/SECURITY_MODEL.md`
- `docs/ATTACK_SIMULATION_GUIDE.md` (updated to reflect CLI-only attack execution path)

## Live-Verified Runtime Facts (checked)

- Removed attack UI backend routes are not active:
  - `GET /api/attacks/registry` -> `404`
  - `GET /api/demo/chaos/status` -> `404`
- Dashboard source indicates attack UI is removed (`Attack Simulation removed: live attacks only`)
- `GET /health` returns healthy status and connected PostgreSQL persistence
- `GET /api/rate-limiter/status` returns valid status/config payload
- `GET /api/governance/status` (with auth) returns mode + metrics payload
- `scripts/run-live-attacks.sh --dry-run --verbose` runs and prints phased scenario execution plan

## What is not a live contract

The following are still useful, but should be treated as context/snapshot material, not authoritative runtime truth:

- Time-bound validation reports (for example `*_2026-*.md`)
- Metrics/reporting snapshots (for example `docs/PROJECT_METRICS.md`, `docs/IOT_EMULATION_REPORT.md`)
- Historical changelog entries describing removed/optional features
- Anything under `docs/archive/` or `docs/_archive/`

## Review policy (recommended)

1. Start with `README.md` and `docs/INDEX.md`.
2. Confirm runtime with `/health`, `/api/alerts`, `/api/metrics`.
3. Use `docs/API_REFERENCE.md` for current endpoints.
4. Treat report/snapshot docs as supporting evidence only.
