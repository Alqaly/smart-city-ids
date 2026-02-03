# Troubleshooting Guide

## Quick Fix Checklist

- [ ] API key set? `echo $XAI_API_KEY`
- [ ] Pods running? `kubectl get pods -n smart-city`
- [ ] No errors? `kubectl logs -n smart-city ids-api`
- [ ] Network working? `ping google.com`

---

## Common Issues

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

**Error:** `{"error": "Unauthorized", "status": 401}`

**Cause:** Invalid or missing API key

**Fix:**
```bash
# Check .env file
cat .env | grep API_KEY

# Verify secret is set
kubectl get secret -n smart-city ids-secrets -o jsonpath='{.data.xai-api-key}' | base64 -d

# If wrong, update and redeploy
nano .env
./deploy.sh
```

---

### IDS API Returns 429 (Rate Limited)

**Error:** `{"error": "Rate limited", "status": 429}`

**Cause:** Too many requests to LLM API

**Fix:** Wait 1 minute, then retry. Or increase `LLM_TIMEOUT` in config.

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
kubectl logs -n smart-city postgres --tail=20
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
