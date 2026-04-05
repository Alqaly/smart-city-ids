# Operations Guide

Day-to-day operating procedures for the Smart City IDS deployment.

## Daily checks

Use:

```bash
bash scripts/readiness-check.sh
bash scripts/readiness-check.sh --quick
```

These are the fastest current checks for:
- cluster reachability
- core pods
- API health
- dashboard availability
- detector visibility
- login and protected endpoint access

## Access

Direct local path:
- `http://localhost:30800/ui`

Stable forwarded path:

```bash
bash scripts/access-stack.sh start
bash scripts/access-stack.sh status
```

Use the forwarded path if local NodePort access is inconvenient.

## Authentication

Default local credentials are environment-dependent. The common local default is:
- `admin / admin`

Example login:

```bash
TOKEN=$(curl -s -X POST http://localhost:30800/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}' | jq -r '.access_token')
```

## Health and metrics

```bash
curl -s http://localhost:30800/health | jq '{status,storage_type,components}'
curl -s http://localhost:30800/api/metrics | jq '{total_alerts,iot_devices_active,llm_engines}'
curl -s http://localhost:30800/api/iot/devices | jq '{total,logical_total,pod_backed_total,counting_mode}'
```

## Governance and automation

Read status:

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  http://localhost:30800/api/governance/status | jq '{mode,pending_count,metrics}'
```

Run real governance validation:

```bash
bash scripts/test-governance-modes.sh
bash scripts/readiness-check.sh
```

These require at least one operational LLM provider.

## LLM operations

Fast check:

```bash
bash scripts/llm-manager.sh check
```

Direct diagnostics:

```bash
curl -s http://localhost:30800/api/llm/diagnostics | jq .
```

Important meanings:
- provider usage tables count real alert-analysis calls only
- manual tests update diagnostics, not DB-backed usage totals
- `unverified` means configured but not yet proven by a successful live call in the current process

## Live attack flow

Run a live protocol/runtime exercise:

```bash
bash scripts/run-live-attacks.sh --mode protocol --duration 30 --show-alerts 5 --verbose
```

Use two terminals during live exercises:

```bash
# Processed IDS events
bash scripts/live-pipeline-log.sh --attacks

# Raw component logs
SINCE=5m bash scripts/tail-pipeline-pods.sh
```

## Code updates

After code changes:

```bash
bash scripts/deploy-code.sh
```

For full cluster bring-up or recovery:

```bash
sudo bash scripts/start-everything.sh
```

## Scaling

Preferred path:

```bash
bash scripts/scale-profile.sh status
bash scripts/scale-profile.sh small
bash scripts/scale-profile.sh medium
bash scripts/scale-profile.sh large
```

Quick manual replica changes:

```bash
bash scripts/scale-iot.sh
```

## Log access

API logs:

```bash
kubectl logs -n smart-city -l app=ids-api --tail=200
```

Forwarder logs:

```bash
kubectl logs -n falco-system -l app=falco-forwarder --tail=100
kubectl logs -n monitoring -l app=suricata-forwarder --tail=100
```
