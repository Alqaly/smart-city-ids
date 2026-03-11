# Demo Runbook and Endpoint Checks (2026-02-11)

## 1) One-time environment check

```bash
export KUBECONFIG="$HOME/.kube/config"
scripts/check-system.sh
scripts/demo-readiness.sh --quick
```

## 2) Verify API keys in 3 places

```bash
# (A) Local .env
grep -E '^(XAI_API_KEY|OPENAI_API_KEY|ANTHROPIC_API_KEY|GEMINI_API_KEY|KIMI_API_KEY)=' .env

# (B) Kubernetes secret
kubectl -n smart-city get secret ids-secrets -o json | jq -r '
  .data
  | to_entries[]
  | "\(.key)=len:\((.value|@base64d|length))"'

# (C) Running ids-api pod env vars
POD=$(kubectl -n smart-city get pod -l app=ids-api -o jsonpath='{.items[0].metadata.name}')
kubectl -n smart-city exec "$POD" -- sh -lc '
  for k in XAI_API_KEY OPENAI_API_KEY ANTHROPIC_API_KEY GEMINI_API_KEY KIMI_API_KEY; do
    v=$(printenv "$k" || true); echo "$k len:${#v}";
  done'
```

## 3) Verify endpoints one-by-one

```bash
kubectl -n smart-city port-forward svc/ids-api-service 38000:8000
```

In another shell:

```bash
# Public endpoints
curl -s http://127.0.0.1:38000/ | jq .
curl -s http://127.0.0.1:38000/health | jq .
curl -s http://127.0.0.1:38000/api/metrics | jq .
curl -s http://127.0.0.1:38000/api/alerts?limit=5 | jq .
curl -s http://127.0.0.1:38000/metrics | head -n 30

# Auth and protected endpoints
TOKEN=$(curl -s -X POST http://127.0.0.1:38000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"operator","password":"operator"}' | jq -r '.access_token')

curl -s http://127.0.0.1:38000/api/llm/status -H "Authorization: Bearer $TOKEN" | jq .
curl -s http://127.0.0.1:38000/api/operator/dashboard -H "Authorization: Bearer $TOKEN" | jq .
curl -s 'http://127.0.0.1:38000/api/operator/search?query=suricata&limit=5' -H "Authorization: Bearer $TOKEN" | jq .
curl -s http://127.0.0.1:38000/api/governance/status -H "Authorization: Bearer $TOKEN" | jq .
```

## 4) Reliable demo command

```bash
# Falco runtime path
scripts/demo.sh --wait 5

# Network path (includes deterministic Suricata-format validation injection)
scripts/demo.sh --attack-type network --wait 5
```

## 5) Prometheus truth checks for dashboard numbers

```bash
PROM=$(kubectl -n monitoring get pod -l app=prometheus -o jsonpath='{.items[0].metadata.name}')

kubectl -n monitoring exec "$PROM" -- wget -qO- \
  'http://localhost:9090/api/v1/query?query=sum(smartcity_ids_alerts_received_total)' \
  | jq -r '.data.result[0].value[1]'

kubectl -n monitoring exec "$PROM" -- wget -qO- \
  'http://localhost:9090/api/v1/query?query=sum(smartcity_ids_alerts_processed_total{result="success"})' \
  | jq -r '.data.result[0].value[1]'

kubectl -n monitoring exec "$PROM" -- wget -qO- \
  'http://localhost:9090/api/v1/query?query=sum%20by(source)(smartcity_ids_alerts_received_total)' \
  | jq -r '.data.result[] | [.metric.source,.value[1]] | @tsv'

kubectl -n monitoring exec "$PROM" -- wget -qO- \
  'http://localhost:9090/api/v1/query?query=smartcity_ids_circuit_breaker_state' \
  | jq -r '.data.result[] | [.metric.engine,.value[1]] | @tsv'
```

## Notes

- `smartcity_ids_circuit_breaker_state` values:
  - `0=HEALTHY`
  - `1=TESTING`
  - `2=FAILING`
  - `3=UNCONFIGURED`
- If xAI key exists but still fails, check quota/billing; `429` means key is present but credits/limit is exhausted.
