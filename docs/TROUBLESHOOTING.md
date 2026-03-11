# Troubleshooting Guide

Use this guide for the current active deployment path.

## First commands to run

Start with:

```bash
bash scripts/pre-demo-check.sh
bash scripts/demo-readiness.sh --quick
bash scripts/llm-manager.sh check
```

These checks are more useful than older ad hoc shell fixes because they validate the current stack directly.

## Common issues

## 1. Dashboard or API not reachable

Check:

```bash
curl -s http://localhost:30800/health | jq .
```

If that fails, use forwarded access:

```bash
bash scripts/access-stack.sh start
bash scripts/access-stack.sh status
curl -s http://localhost:8000/health | jq .
```

## 2. K3s or cluster state looks broken

Recovery path:

```bash
sudo bash scripts/start-everything.sh
```

This is the current supported recovery/startup path.

## 3. Code changes are not visible

Run:

```bash
bash scripts/deploy-code.sh
```

This refreshes the running code and mounted static assets.

## 4. LLM providers show unverified, cooldown, or error

Run:

```bash
bash scripts/llm-manager.sh check
curl -s http://localhost:30800/api/llm/diagnostics | jq .
```

Interpretation:
- `unverified` = configured, but no successful live call yet in the current process
- `cooldown` = provider recently failed and is temporarily suppressed
- `auth_failed` = bad key or provider-side authentication problem
- `operational` = working now

## 5. Governance validation fails

Run:

```bash
bash scripts/test-governance-modes.sh
```

If it stops early, check LLM availability:

```bash
bash scripts/llm-manager.sh check
```

Governance validation requires at least one operational LLM provider.

## 6. Alert history looks noisy

Current known behavior:
- the dashboard groups repeated alerts into 5-minute incident buckets
- alert history can still be dominated by higher-volume detector traffic

Check detector mix:

```bash
curl -s 'http://localhost:30800/api/alerts?limit=120' | jq '.alerts | group_by(.source) | map({source: (.[0].source // "unknown"), count: length})'
```

## 7. Need live proof during a demo

Processed event feed:

```bash
bash scripts/live-pipeline-log.sh --attacks
```

Raw component logs:

```bash
SINCE=5m bash scripts/tail-pipeline-pods.sh
```

## 8. IoT device rows look stale or unclear

Use:

```bash
curl -s http://localhost:30800/api/iot/devices | jq '{total,logical_total,pod_backed_total,counting_mode,devices}'
```

Important:
- logical registry rows are inventory records
- they are not proof of live hardware unless there is recent heartbeat/telemetry

## 9. Provider usage table looks inconsistent

This is expected if you mix diagnostics and alert-analysis traffic.

Rules:
- DB-backed provider usage counts alert-analysis calls only
- manual probe/test actions update diagnostics but not usage totals
- a provider can be operational even if balance visibility is unavailable

## 10. If you are not sure what is wrong

Run this sequence:

```bash
bash scripts/pre-demo-check.sh
bash scripts/demo-readiness.sh --quick
bash scripts/llm-manager.sh check
bash scripts/comprehensive-test.sh
```

If those pass, the active runtime path is healthy.
