# 🚀 Quick Start Guide - 5 Minutes to Demo

## Installation (1 minute)

```bash
cd /root/smart-city-ids

./scripts/start-everything.sh
```bash

```bash
```bash

## Verify Services (1 minute)

In a **new terminal**:

```bash
```bash

---

## Test Services (1 minute)

In a **new terminal**, run:

```bash

kubectl port-forward -n smart-city svc/traffic-camera-service 8001:80 &

# Test it

sleep 2
curl <http://localhost:8001/health>
```bash

```json
```bash

## Run Attack Demo (2 minutes)

```bash

python3 attack-simulator/data_exfiltration.py <http://localhost:8001>
```bash

- ✅ Camera data extracted
- ✅ Admin config modified
- ✅ Analytics data stolen

---

## Check IDS (1 minute)

```bash

kubectl port-forward -n smart-city svc/ids-api-service 8004:5003 &

sleep 2

# Get dashboard

curl <http://localhost:8004/api/dashboard>
```bash

## Cleanup

```bash
```bash

## Useful Commands

```bash

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
```bash

## Full Demo Workflow

```bash

cd /root/smart-city-ids
./scripts/start-everything.sh

# Wait for "✅ Smart City IDS System is ready!"

# Terminal 2: Watch pods

kubectl get pods -n smart-city -w

# Terminal 3: Test service

kubectl port-forward -n smart-city svc/traffic-camera-service 8001:80 &
sleep 2
curl <http://localhost:8001/api/cameras>

# Terminal 4: Run attack

python3 attack-simulator/data_exfiltration.py <http://localhost:8001>

# Terminal 5: Check IDS

kubectl port-forward -n smart-city svc/ids-api-service 8004:5003 &
sleep 2
curl <http://localhost:8004/api/dashboard>
```bash

## Common Issues

### K3s won't start

```bash
pkill -f "k3s server"

k3s server &
```bash

```bash
kubectl describe pod <pod-name> -n smart-city

kubectl logs <pod-name> -n smart-city
```bash

```bash
kubectl port-forward -n smart-city svc/<service> 8000:80

curl <http://localhost:8000/health>
```bash

```bash
```bash

That's it! You now have a working Smart City IDS demo. 🎉
