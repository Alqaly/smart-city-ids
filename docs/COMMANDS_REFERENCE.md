# Command Reference

Current command reference for the active Smart City IDS runtime path.

## Start and update

```bash
# Full startup or recovery
sudo bash scripts/start-everything.sh

# Apply code changes to a running cluster
bash scripts/deploy-code.sh
```

## Readiness checks

```bash
bash scripts/pre-demo-check.sh
bash scripts/demo-readiness.sh --quick
bash scripts/llm-manager.sh check
```

## Access

```bash
# Direct local path
curl -s http://localhost:30800/health | jq .

# Stable forwarded access
bash scripts/access-stack.sh start
bash scripts/access-stack.sh status
curl -s http://localhost:8000/health | jq .
```

## Authentication

```bash
TOKEN=$(curl -s -X POST http://localhost:30800/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}' | jq -r '.access_token')
```

## Governance

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  http://localhost:30800/api/governance/status | jq .

curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  "http://localhost:30800/api/governance/mode?mode=assisted" | jq .

curl -s -H "Authorization: Bearer $TOKEN" \
  http://localhost:30800/api/governance/pending | jq .
```

## LLM diagnostics

```bash
curl -s http://localhost:30800/api/llm/diagnostics | jq .

curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  "http://localhost:30800/api/llm/test/openai?strict=true" \
  -H "Content-Type: application/json" \
  -d '{"test_prompt":"provider strict diagnostic"}' | jq .
```

## Alerts and metrics

```bash
curl -s http://localhost:30800/health | jq '{status,storage_type,components}'
curl -s http://localhost:30800/api/metrics | jq '{total_alerts,iot_devices_active,llm_engines}'
curl -s http://localhost:30800/api/alerts?limit=10 | jq '.alerts'
curl -s http://localhost:30800/api/iot/devices | jq '{total,logical_total,pod_backed_total,counting_mode}'
```

## Live attacks and demo logs

```bash
bash scripts/run-live-attacks.sh --mode protocol --duration 30 --show-alerts 5 --verbose

# Processed IDS events
bash scripts/live-pipeline-log.sh --attacks

# Raw pipeline logs
SINCE=5m bash scripts/tail-pipeline-pods.sh
```

## End-to-end validation

```bash
bash scripts/test-governance-modes.sh
bash scripts/e2e-verbose-test.sh --quick
bash scripts/comprehensive-test.sh
```

## Scaling

```bash
bash scripts/scale-profile.sh status
bash scripts/scale-profile.sh small
bash scripts/scale-profile.sh medium
bash scripts/scale-profile.sh large
```
