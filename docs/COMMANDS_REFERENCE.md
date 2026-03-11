# Smart City IDS Command Reference

Operational command reference for the current research deployment.

---

## 1) Connectivity and Access

```bash
# Recommended: stable localhost endpoints regardless of node IP/Wi-Fi changes
bash scripts/access-stack.sh start
bash scripts/access-stack.sh status

# NodePort access (if bound locally in your setup)
curl -s -o /dev/null -w "HEALTH:%{http_code}\n" http://localhost:30800/health
curl -s -o /dev/null -w "UI:%{http_code}\n" http://localhost:30800/ui

# If localhost:30800 is not reachable, use port-forward
kubectl -n smart-city port-forward svc/ids-api-service 8000:8000
curl -s http://127.0.0.1:8000/health | jq .
```

---

## 2) Authentication Helpers

```bash
# Default local credentials are environment-dependent; adjust as needed
TOKEN=$(curl -s -X POST http://localhost:30800/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"operator","password":"operator"}' | jq -r '.access_token')

test -n "$TOKEN" && test "$TOKEN" != "null" || {
  echo "Login failed"; exit 1;
}
```

---

## 3) Core Health and Runtime State

```bash
curl -s http://localhost:30800/health | jq '{status,storage_type,components}'
curl -s http://localhost:30800/api/metrics | jq '{total_alerts,iot_devices_active,llm_engines}'
curl -s http://localhost:30800/api/rate-limiter/status | jq .
curl -s http://localhost:30800/api/alerts?limit=5 | jq '.alerts'
```

---

## 4) Governance and Automation Controls

```bash
# Read governance status
curl -s -H "Authorization: Bearer $TOKEN" \
  http://localhost:30800/api/governance/status | jq '{mode,pending_count,metrics}'

# Set mode (manual|assisted|autonomous)
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  "http://localhost:30800/api/governance/mode?mode=assisted" | jq .

# Enable full autonomous force profile (optional)
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  "http://localhost:30800/api/governance/autonomy/force?enabled=true" | jq .

# View pending actions
curl -s -H "Authorization: Bearer $TOKEN" \
  http://localhost:30800/api/governance/pending | jq .
```

### End-to-end governance mode validation

```bash
bash scripts/test-governance-modes.sh
bash scripts/e2e-verbose-test.sh --quick
```

These governance/E2E checks require at least one operational LLM provider.

---

## 5) LLM Diagnostics and Strict Provider Tests

```bash
# Status and diagnostics
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:30800/api/llm/status | jq .
curl -s http://localhost:30800/api/llm/diagnostics | jq .

# Strict provider diagnostic (disables fallback for this test only)
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  "http://localhost:30800/api/llm/test/openai?strict=true" \
  -H "Content-Type: application/json" \
  -d '{"test_prompt":"provider strict diagnostic"}' | jq .

# Provider comparison/cost usage
curl -s http://localhost:30800/api/llm/providers/comparison | jq .
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:30800/api/metrics/llm-usage?window=today" | jq .
```

---

## 6) Live Attack Execution (Current Path)

```bash
# Dry run first
bash scripts/run-live-attacks.sh --mode all --duration 20 --dry-run --verbose

# Full multi-mode run
bash scripts/run-live-attacks.sh --mode all --duration 30 --show-alerts 3 --verbose

# MQTT abuse mode
bash scripts/run-live-attacks.sh --mode mqtt --duration 30 --show-alerts 5 --verbose
```

Notes:
- Current deployment uses CLI-driven attack execution (`scripts/run-live-attacks.sh`).
- Legacy `/api/attacks/*` routes are removed and should not be used.

---

## 7) Deployment and Static Asset Refresh

```bash
# Build, import image, refresh static ConfigMaps, restart ids-api
bash scripts/deploy-code.sh

# Verify deployment
kubectl -n smart-city get pods -l app=ids-api -o wide
kubectl -n smart-city get configmap ids-app-static ids-app-static-js ids-app-static-js-modules
```

---

## 8) Scaling Profiles

```bash
# Show current scale state
bash scripts/scale-profile.sh status

# Apply repeatable profiles
bash scripts/scale-profile.sh small
bash scripts/scale-profile.sh medium
bash scripts/scale-profile.sh large

# Optional (advanced): ids-api replicas >1
IDS_API_REPLICAS=2 bash scripts/scale-profile.sh medium
```

---

## 9) Troubleshooting

```bash
# API logs
kubectl logs -n smart-city -l app=ids-api --tail=200

# Forwarder logs
kubectl logs -n falco-system -l app=falco-forwarder --tail=100
kubectl logs -n monitoring -l app=suricata-forwarder --tail=100

# Restart ids-api
kubectl rollout restart deployment/ids-api -n smart-city
kubectl rollout status deployment/ids-api -n smart-city
```


## Live Demo Logs

```bash
# Processed IDS event feed
bash scripts/live-pipeline-log.sh --attacks

# Raw pod logs across the pipeline
SINCE=5m bash scripts/tail-pipeline-pods.sh
```

`live-pipeline-log.sh` is the processed event viewer. `tail-pipeline-pods.sh` is the raw multi-component log tailer.
