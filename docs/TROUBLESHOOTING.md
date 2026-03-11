# Troubleshooting Guide

## Quick Fix Command

**After WiFi change or reboot, run this first:**
```bash
./scripts/check-setup.sh
```

This will:
- Fix K3s permissions
- Show current IP and all service URLs
- Verify cluster and pod status

---

## Quick Fix Checklist

- [ ] K3s permissions? `sudo chmod 644 /etc/rancher/k3s/k3s.yaml`
- [ ] KUBECONFIG set? `export KUBECONFIG=/etc/rancher/k3s/k3s.yaml`
- [ ] API key set? `echo $XAI_API_KEY`
- [ ] Pods running? `kubectl get pods -n smart-city`
- [ ] No errors? `kubectl logs -n smart-city -l app=ids-api --tail=50`
- [ ] Network working? `ping google.com`

---

## WiFi / IP Changed Issues

### Cannot Access Grafana/Prometheus After WiFi Change

**Error:** `Failed to connect to 172.x.x.x port 30300`

**Cause:** IP address changed when you connected to new WiFi

**Fix:**
```bash
# Run the check script to see new IP
./scripts/check-setup.sh

# Or manually get new IP
kubectl get nodes -o wide
# Look at INTERNAL-IP column
```

---

### K3s Permission Denied

**Error:** `error loading config file "/etc/rancher/k3s/k3s.yaml": permission denied`

**Fix:**
```bash
sudo chmod 644 /etc/rancher/k3s/k3s.yaml
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

# Make permanent (add to shell config)
echo 'export KUBECONFIG=/etc/rancher/k3s/k3s.yaml' >> ~/.bashrc
echo 'export KUBECONFIG=/etc/rancher/k3s/k3s.yaml' >> ~/.zshrc
source ~/.bashrc  # or source ~/.zshrc
```

---

### K3s Not Running After Reboot

**Error:** `The connection to the server localhost:6443 was refused`

**Fix:**
```bash
sudo systemctl restart k3s
sleep 15
sudo chmod 644 /etc/rancher/k3s/k3s.yaml
kubectl get nodes
```

---

## Raspberry Pi Issues

### Pi Cannot Connect to IDS API

**Error:** `Failed to connect to 172.x.x.x port 30800`

**Cause:** IP changed or Pi on different network

**Fix:**
1. On Kali, get current IP:
   ```bash
   ./scripts/check-setup.sh
   ```
2. On Pi, update and run:
   ```bash
   python3 motion_sensor.py --ids-url http://<NEW_IP>:30800
   ```

---

### Motion Sensor Always Shows "MOTION!" (Stuck)

**Cause:** Sensor damaged (likely connected to 5V instead of 3.3V)

**Fix:**
- AM312 sensor MUST use Pin 1 (3.3V), NOT Pin 2 (5V)
- If damaged, replace sensor (~$2)
- Temporary workaround: Add cooldown in code or use keyboard simulation

---

### GPIO Busy Error

**Error:** `lgpio.error: 'GPIO busy'`

**Cause:** Previous Python process still holding GPIO

**Fix:**
```bash
sudo killall python3
sleep 2
python3 motion_sensor.py --ids-url http://<IP>:30800
```

---

## Common Issues

### Alert History shows mostly Falco / governance rows and no Suricata

**Cause:** the visible recent window is dominated by higher-volume Falco or governance alerts. This does not necessarily mean Suricata is down.

**How to check:**
```bash
curl -s http://localhost:30800/api/alerts?limit=120 | jq '.alerts | group_by(.source) | map({source: (.[0].source // "unknown"), count: length})'
curl -s http://localhost:30800/health | jq '.components.suricata'
kubectl logs -n monitoring -l app=suricata-forwarder --tail=50
```

**Dashboard behavior:**
- Alert History groups repeated alerts into 5-minute incident buckets.
- The detector summary above the table shows the source mix in the loaded window.
- If Suricata is absent from that summary, it simply did not contribute alerts in the current loaded window.

### Deploy Script Fails

**Error:** `command not found: ./deploy.sh`

**Fix:**
```bash
chmod +x deploy.sh
./deploy.sh
```

---

### Pods Won't Start / CrashLoopBackOff

**Error:** Pod stuck in CrashLoopBackOff

**Check logs:**
```bash
kubectl logs -n smart-city <pod-name> --tail=100
kubectl describe pod -n smart-city <pod-name>
```

**Common causes:**
- Image not found → Run `docker build` and load into K3s
- Memory limit → Increase `resources.limits.memory` in manifest
- API key missing → Check `kubectl get secret -n smart-city ids-secrets`

---

### IDS API Returns 401 (Unauthorized)

**Common causes:**
- Missing/invalid JWT for protected endpoints (dashboard/API actions)
- Invalid LLM provider API key (401 from provider), which is a **different** issue

**Fix:**
```bash
# For IDS API JWT auth (dashboard/admin endpoints): login and use Bearer token
TOKEN=$(curl -s http://localhost:30800/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}' | jq -r .access_token)

# Example protected call
curl -s http://localhost:30800/api/governance/status \
  -H "Authorization: Bearer $TOKEN" | jq .
```

For LLM provider key issues (provider returns 401), verify and resync keys:

```bash
# Check .env keys
grep 'API_KEY' .env

# Sync .env -> K8s secret and restart ids-api
bash scripts/apply-llm-env-to-k8s-secret.sh
bash scripts/deploy-code.sh

# Reset provider latches/circuit state after fixing keys
curl -s -X POST http://localhost:30800/api/llm/retry-all \
  -H "Authorization: Bearer $TOKEN" | jq .

# Strict per-provider diagnostic (no fallback masking)
curl -s -X POST \
  "http://localhost:30800/api/llm/test/openai?strict=true" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"test_prompt":"strict provider diagnostic"}' | jq .
```

Provider panel note:
- `Provider Breakdown (today)` counts only DB-backed alert-analysis usage.
- Manual provider tests and probes update diagnostics/runtime status but do not increase those usage counters.
- `Hist` means historical DB usage exists, but the current runtime process has not accumulated enough success counters to compute a live percentage for that same window.

---

### IDS API Returns 429 (Rate Limited)

**Error:** `{"error": "Rate limited", "status": 429}`

**Cause:** Could be one of:
- Alert ingest rate limiter throttling (`/api/alerts`)
- Provider-side quota/rate limiting (LLM API)

**Fix (diagnose first):**
```bash
# Alert ingest rate limiter status
curl -s http://localhost:30800/api/rate-limiter/status | jq .

# LLM provider diagnostics (cooldown/quota/auth state)
curl -s http://localhost:30800/api/llm/diagnostics | jq .
```

Interpretation:
- `401` on a provider card usually means invalid or expired API key.
- `429` usually means quota exhaustion or provider-side rate limiting.
- A successful strict test can clear stale runtime provider-failure state, but it will not change DB-backed historical usage totals.

### Alert History has no search box / filtering is weak

The live inline dashboard now includes a search field in the `Alert History` tab.
It searches rule, detector, summary, threat type, namespace/pod/container, and LLM analysis text.

If search still does not appear:
```bash
bash scripts/deploy-code.sh
bash scripts/access-stack.sh restart
```

---

### Grafana Won't Load

**Error:** Cannot access `http://localhost:30300`

**Cause:** Grafana pod not running or port not exposed

**Fix:**
```bash
# Check Grafana pod
kubectl get pods -n monitoring

# Check NodePort
kubectl get svc -n monitoring grafana

# If port wrong, update it
# Or access from node IP: http://<node-ip>:30300
```

---

### PostgreSQL Connection Failed

**Error:** `FATAL: remaining connection slots are reserved`

**Cause:** Too many connections, DB limit reached

**Fix:**
```bash
# Restart postgres
kubectl rollout restart deployment postgres -n smart-city

# Wait 30 seconds for recovery
sleep 30
kubectl logs -n smart-city -l app=postgres --tail=20
```

If the dashboard suddenly appears to lose old alerts:
- Check `/health` for DB/storage status
- `ids-api` may be in memory fallback
- Current builds auto-retry PostgreSQL and recover without restarting `ids-api`

```bash
curl -s http://localhost:30800/health | jq '{status,storage_type,components}'
```

---

### Falco Not Detecting Alerts

**Error:** No alerts in dashboard

**Cause:** Falco pod not running or syscalls not being captured

**Fix:**
```bash
# Check Falco
kubectl get pods -n falco-system

# View Falco logs
kubectl logs -n falco-system -l app=falco --tail=50

# Trigger a test alert
kubectl exec -n smart-city <pod-name> -- touch /etc/shadow  # Should trigger Falco
```

---

### High Memory Usage

**Error:** Pod OOMKilled (Out of Memory)

**Cause:** Memory limit too low

**Fix:**
```yaml
# In manifest, increase limits:
resources:
  limits:
    memory: "4Gi"  # Increase from 2Gi
```

Then redeploy:
```bash
kubectl apply -f k8s-manifests/
```

---

### LLM Analysis Takes >10 Seconds

**Cause:** LLM API slow or network latency

**Fix:**
```bash
# Check LLM response time
kubectl logs -n smart-city ids-api | grep "LLM.*latency"

# If >5s consistently, check:
# 1. Is XAI API down? (https://status.x.ai)
# 2. Network latency? (ping api.x.ai)
# 3. Rate limit? (check response headers)
```

---

### "imagePullBackOff" Errors

**Error:** Pod stuck pulling image

**Cause:** Docker image not found in registry

---

### Dashboard/UI Looks Stale After Deploy

**Symptoms:**
- Backend behavior changed but dashboard still shows old UI/API client behavior
- Removed routes still appear in browser calls

**Cause:** `ids-api` deployment mounts static assets from ConfigMaps (`ids-app-static*`), so image rebuild alone is not enough.

**Fix:**
```bash
# Recommended: deploy script now refreshes all static ConfigMaps + restarts ids-api
bash scripts/deploy-code.sh

# Verify mounted ConfigMaps exist
kubectl -n smart-city get configmap ids-app-static ids-app-static-js ids-app-static-js-modules
```

---

### NodePort URL Not Reachable on localhost

**Symptoms:**
- `curl http://localhost:30800/health` fails
- Service exists as NodePort but localhost access is refused

**Cause:** NodePort is exposed on the Kubernetes node network, not guaranteed on localhost loopback.

**Fix (recommended):**
```bash
bash scripts/access-stack.sh start
bash scripts/access-stack.sh status
```

Then use stable local URLs:
- `http://localhost:8000` (IDS API/UI via `scripts/access-stack.sh start`)
- `http://localhost:3000` (Grafana)
- `http://localhost:9090` (Prometheus)

**Fix:**
```bash
# Rebuild and load images
./scripts/build-images.sh
k3s ctr image import <(docker save smart-city-ids/ids-api:latest)

# Verify
k3s ctr image ls | grep smart-city
```

---

## Get Help

1. Check this guide
2. Run `kubectl logs -n smart-city <pod-name>`
3. Check GitHub issues: https://github.com/Alqaly/smart-city-ids/issues
4. Ask team lead
