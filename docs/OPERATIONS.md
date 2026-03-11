# Smart City IDS Operations Guide

Day-to-day operating procedures for the active Smart City IDS research deployment.

---

## 1) Daily Health Checks

```bash
bash scripts/access-stack.sh start
bash scripts/access-stack.sh status

kubectl get pods -n smart-city
kubectl get pods -n monitoring
kubectl get pods -n falco-system
```

```bash
curl -s http://localhost:30800/health | jq '{status,storage_type,components}'
curl -s http://localhost:30800/api/metrics | jq '{total_alerts,iot_devices_active,llm_engines}'
```

If `localhost:30800` is not reachable in your environment:

```bash
bash scripts/access-stack.sh start
curl -s http://127.0.0.1:8000/health | jq .
```

---

## 2) Authentication and Governance Checks

```bash
TOKEN=$(curl -s -X POST http://localhost:30800/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"operator","password":"operator"}' | jq -r '.access_token')
```

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  http://localhost:30800/api/governance/status | jq '{mode,pending_count,metrics}'
curl -s -H "Authorization: Bearer $TOKEN" \
  http://localhost:30800/api/governance/pending | jq .
```

---

## 3) Alert Pipeline Monitoring

```bash
curl -s http://localhost:30800/api/alerts?limit=10 | jq '.alerts'
curl -s http://localhost:30800/api/rate-limiter/status | jq .
curl -s http://localhost:30800/api/circuit-breaker/status | jq .
```

Alert History semantics in the dashboard:

- The UI loads a wider recent alert window and groups repeated alerts into 5-minute incident buckets.
- Grouping key: detector, rule, severity, namespace/pod/container context, and threat signature.
- The detector summary above the table explains why a detector may be missing from view. If Suricata is not shown there, the loaded window is dominated by other detectors.

Audit a specific alert end-to-end:

```bash
ALERT_ID=123
curl -s http://localhost:30800/api/audit/trace/alert-${ALERT_ID} | jq .
```

---

## 4) LLM Operations

```bash
curl -s http://localhost:30800/api/llm/diagnostics | jq .
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:30800/api/llm/status | jq .
```

Dashboard usage semantics:

- `Provider Breakdown (today)` is DB-backed usage for real IDS alert-analysis calls.
- Manual `Test Key` / `Probe` actions affect provider diagnostics and runtime status only.
- A provider can recover from stale startup-failure state after a successful strict/manual test.
- `Hist` in the success column means historical DB usage exists, but runtime success counters were reset after restart.

Overview metric semantics:

- `Dedup + LLM Savings` is shown only after the deduplicator has processed real duplicate-capable security alerts in the current process.
- `Flood Suppression` reflects cumulative alert-rate throttling since the last rate-limiter reset/startup, not a rolling live-only UI window.

Strict provider diagnostic:

```bash
curl -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  "http://localhost:30800/api/llm/test/openai?strict=true" \
  -H "Content-Type: application/json" \
  -d '{"test_prompt":"strict provider diagnostic"}' | jq .
```

---

## 5) Attack-Chain Exercise Workflow

Current deployment path is CLI-driven via `scripts/run-live-attacks.sh`.

```bash
# Baseline preflight (script name retained for compatibility)
bash scripts/pre-demo-check.sh

# Dry-run exercise plan
bash scripts/run-live-attacks.sh --mode all --duration 20 --dry-run --verbose

# MQTT abuse chain
bash scripts/run-live-attacks.sh --mode mqtt --duration 30 --show-alerts 5 --verbose

# Full exercise
bash scripts/run-live-attacks.sh --mode all --duration 30 --show-alerts 3 --verbose
```

Governance mode validation:

```bash
bash scripts/test-governance-modes.sh
bash scripts/e2e-verbose-test.sh --quick
```

These checks require at least one operational LLM provider. With zero operational providers, they fail early with the live diagnostics summary instead of producing a misleading governance result.

---

## 6) Deployment and Update Workflow

```bash
# Build/import ids-api image, refresh static ConfigMaps, restart pods
bash scripts/deploy-code.sh
```

`deploy-code.sh` now refreshes:
- `ids-app-static`
- `ids-app-static-js`
- `ids-app-static-js-modules`

This is required because the deployment mounts `/app/static*` from ConfigMaps.

---

## 7) Incident Response Checks

When high-severity alerts occur:

```bash
curl -s http://localhost:30800/api/alerts?limit=20 | jq '.alerts[] | {id,rule,severity,threat_type,actions_taken}'
kubectl get networkpolicy -n smart-city
kubectl get deploy -n smart-city
```

---

## 8) Common Recovery Actions

```bash
kubectl logs -n smart-city -l app=ids-api --tail=200
kubectl rollout restart deployment/ids-api -n smart-city
kubectl rollout status deployment/ids-api -n smart-city
```

```bash
kubectl logs -n falco-system -l app=falco-forwarder --tail=100
kubectl logs -n monitoring -l app=suricata-forwarder --tail=100
```

If DB fallback is suspected:

```bash
curl -s http://localhost:30800/health | jq '{status,storage_type,components}'
```

---

## 9) Capacity Scaling

Use repeatable profiles instead of ad-hoc manual scaling:

```bash
bash scripts/scale-profile.sh status
bash scripts/scale-profile.sh small
bash scripts/scale-profile.sh medium
bash scripts/scale-profile.sh large
```

For advanced `ids-api` scaling:

```bash
IDS_API_REPLICAS=2 bash scripts/scale-profile.sh medium
```

Keep `ids-api` at one replica unless shared state for dedup/rate-limit is enabled.
