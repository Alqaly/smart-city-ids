# 🚀 Quick Start Guide - 5 Minutes to Demo

## Installation (1 minute)

```bash
cd /root/smart-city-ids
./scripts/start-everything.sh
```

Wait for the output:
```
✅ Smart City IDS System is ready!
```

---

## Verify Services (1 minute)

In a **new terminal**:

```bash
kubectl get pods -n smart-city
```

You should see 6 pods running (all showing "Running")

---

## Test Services (1 minute)

In a **new terminal**, run:

```bash
# Port-forward traffic camera service
kubectl port-forward -n smart-city svc/traffic-camera-service 8001:80 &

# Test it
sleep 2
curl http://localhost:8001/health
```

Expected output:
```json
{"status": "healthy", "service": "traffic-camera", ...}
```

---

## Run Attack Demo (2 minutes)

```bash
# Still in same terminal
python3 attack-simulator/data_exfiltration.py http://localhost:8001
```

**You should see:**
- ✅ Camera data extracted
- ✅ Admin config modified
- ✅ Analytics data stolen

---

## Check IDS (1 minute)

```bash
# In another terminal
kubectl port-forward -n smart-city svc/ids-api-service 8004:5003 &

sleep 2

# Get dashboard
curl http://localhost:8004/api/dashboard
```

---

## Cleanup

```bash
./scripts/cleanup.sh
```

---

## Useful Commands

```bash
# Watch pods in real-time
kubectl get pods -n smart-city -w

# View pod logs
kubectl logs -f <pod-name> -n smart-city

# View all services
kubectl get svc -n smart-city

# Port forward any service
kubectl port-forward -n smart-city svc/<service-name> <local>:80 &

# Get pod resource usage
kubectl top pods -n smart-city

# Delete and restart a pod
kubectl delete pod <pod-name> -n smart-city
```

---

## Full Demo Workflow

```bash
# Terminal 1: Start system
cd /root/smart-city-ids
./scripts/start-everything.sh

# Wait for "✅ Smart City IDS System is ready!"

# Terminal 2: Watch pods
kubectl get pods -n smart-city -w

# Terminal 3: Test service
kubectl port-forward -n smart-city svc/traffic-camera-service 8001:80 &
sleep 2
curl http://localhost:8001/api/cameras

# Terminal 4: Run attack
python3 attack-simulator/data_exfiltration.py http://localhost:8001

# Terminal 5: Check IDS
kubectl port-forward -n smart-city svc/ids-api-service 8004:5003 &
sleep 2
curl http://localhost:8004/api/dashboard
```

---

## Common Issues

**K3s won't start:**
```bash
pkill -f "k3s server"
k3s server &
```

**Pods not running:**
```bash
kubectl describe pod <pod-name> -n smart-city
kubectl logs <pod-name> -n smart-city
```

**Service not accessible:**
```bash
kubectl port-forward -n smart-city svc/<service> 8000:80
curl http://localhost:8000/health
```

**Port already in use:**
```bash
pkill -f "kubectl port-forward"
```

---

That's it! You now have a working Smart City IDS demo. 🎉
