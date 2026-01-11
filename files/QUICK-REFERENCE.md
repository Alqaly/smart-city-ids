# 🛡️ Smart City IDS - Quick Reference Card

## 🚀 One-Line Startup

```bash
# Full WSL2 setup (do this ONCE)
sudo nano /etc/wsl.conf  # Add: [boot] systemd=true
# Restart WSL, then:
curl -sfL https://get.k3s.io | sh - && \
echo "export KUBECONFIG=/etc/rancher/k3s/k3s.yaml" >> ~/.bashrc && \
source ~/.bashrc

# Deploy the system (do this each time)
cd ~/smart-city-ids && \
kubectl apply -f k8s-manifests/namespace.yaml && \
kubectl create configmap traffic-camera-code --from-file=smart-city-services/traffic-camera/app.py -n smart-city --dry-run=client -o yaml | kubectl apply -f - && \
kubectl create configmap healthcare-api-code --from-file=smart-city-services/healthcare-api/app.py -n smart-city --dry-run=client -o yaml | kubectl apply -f - && \
kubectl create configmap parking-system-code --from-file=smart-city-services/parking-system/app.py -n smart-city --dry-run=client -o yaml | kubectl apply -f - && \
kubectl apply -f k8s-manifests/services-no-build.yaml && \
kubectl get pods -n smart-city -w
```

---

## 📊 Essential Commands

### Cluster Status
```bash
# Overall cluster health
kubectl cluster-info

# All nodes
kubectl get nodes

# All pods in smart-city
kubectl get pods -n smart-city

# Watch pods in real-time
kubectl get pods -n smart-city -w

# All services
kubectl get svc -n smart-city

# All events
kubectl get events -n smart-city
```

### Debugging Pods
```bash
# Detailed pod info
kubectl describe pod <POD-NAME> -n smart-city

# View logs
kubectl logs <POD-NAME> -n smart-city

# Follow logs (tail -f)
kubectl logs -f <POD-NAME> -n smart-city

# Last 100 lines
kubectl logs <POD-NAME> -n smart-city --tail=100

# Previous pod (if crashed)
kubectl logs <POD-NAME> -n smart-city --previous
```

### Pod Management
```bash
# Delete a pod (will auto-restart)
kubectl delete pod <POD-NAME> -n smart-city

# Execute command in pod
kubectl exec -it <POD-NAME> -n smart-city -- /bin/bash

# Copy file from pod
kubectl cp smart-city/<POD-NAME>:/path/to/file ./local-file

# Scale a deployment
kubectl scale deployment traffic-camera --replicas=5 -n smart-city
```

### Port Forwarding
```bash
# Traffic Camera (port 8001)
kubectl port-forward -n smart-city svc/traffic-camera-service 8001:80

# Healthcare API (port 8002)
kubectl port-forward -n smart-city svc/healthcare-api-service 8002:80

# Parking System (port 8003)
kubectl port-forward -n smart-city svc/parking-system-service 8003:80

# All in background
kubectl port-forward -n smart-city svc/traffic-camera-service 8001:80 &
kubectl port-forward -n smart-city svc/healthcare-api-service 8002:80 &
kubectl port-forward -n smart-city svc/parking-system-service 8003:80 &
```

### Resource Monitoring
```bash
# CPU and memory usage
kubectl top nodes
kubectl top pods -n smart-city

# Pod resource requests/limits
kubectl describe nodes

# Check cluster capacity
kubectl describe node <NODE-NAME>
```

### Troubleshooting K3s
```bash
# K3s service status
sudo systemctl status k3s.service

# K3s logs
sudo journalctl -xeu k3s.service | tail -50

# K3s direct logs
tail -50 /tmp/k3s.log

# Restart K3s
sudo systemctl restart k3s.service

# Stop K3s
sudo systemctl stop k3s.service

# Start K3s
sudo systemctl start k3s.service
```

---

## 🎯 Testing the Services

### Test Traffic Camera
```bash
# Port-forward first (terminal 1)
kubectl port-forward -n smart-city svc/traffic-camera-service 8001:80

# Test endpoints (terminal 2)
curl http://localhost:8001/health
curl http://localhost:8001/api/cameras
curl http://localhost:8001/api/analytics
curl http://localhost:8001/admin/config

# Extract data
curl http://localhost:8001/admin/config | jq .
```

### Test Healthcare API
```bash
# Port-forward
kubectl port-forward -n smart-city svc/healthcare-api-service 8002:80

# Extract patient data
curl http://localhost:8002/api/patients | jq .

# Get specific patient
curl http://localhost:8002/api/patient/P001 | jq .

# Add prescription (no validation!)
curl -X POST http://localhost:8002/api/prescriptions/P001 \
  -H "Content-Type: application/json" \
  -d '{"drug":"Aspirin","dosage":"500mg","duration":7}' | jq .
```

### Test Parking System
```bash
# Port-forward
kubectl port-forward -n smart-city svc/parking-system-service 8003:80

# Get parking lots
curl http://localhost:8003/api/lots | jq .

# Process payment (logs in plain text!)
curl -X POST http://localhost:8003/api/payment \
  -H "Content-Type: application/json" \
  -d '{"card_number":"4111111111111111","cvv":"123","amount":10}' | jq .

# View all transactions
curl http://localhost:8003/api/transactions | jq .
```

---

## 🎯 Running Attacks

### DDoS Attack
```bash
# 10 threads, 30 seconds
python attack-simulator/ddos_simulator.py http://localhost:8001/api/cameras 10 30

# 20 threads, 60 seconds
python attack-simulator/ddos_simulator.py http://localhost:8001/api/cameras 20 60

# Extreme (15 threads)
python attack-simulator/ddos_simulator.py http://localhost:8001/api/cameras 15 45
```

### Data Exfiltration
```bash
# Extract from traffic camera
python attack-simulator/data_exfiltration.py http://localhost:8001

# Extract from healthcare
python attack-simulator/data_exfiltration.py http://localhost:8002

# Extract from parking
python attack-simulator/data_exfiltration.py http://localhost:8003
```

---

## 📊 Kubernetes Manifest Commands

### View manifests
```bash
# View namespace config
cat k8s-manifests/namespace.yaml

# View deployments
cat k8s-manifests/services-no-build.yaml | grep -A 30 "kind: Deployment"

# View services
cat k8s-manifests/services-no-build.yaml | grep -A 20 "kind: Service"
```

### Apply changes
```bash
# Apply a single file
kubectl apply -f k8s-manifests/namespace.yaml

# Apply entire directory
kubectl apply -f k8s-manifests/

# Dry-run (simulate)
kubectl apply -f k8s-manifests/namespace.yaml --dry-run=client

# Show what will change
kubectl apply -f k8s-manifests/namespace.yaml --dry-run=server
```

### Delete resources
```bash
# Delete entire namespace (removes all pods/services)
kubectl delete namespace smart-city

# Delete specific deployment
kubectl delete deployment traffic-camera -n smart-city

# Delete specific service
kubectl delete svc traffic-camera-service -n smart-city

# Delete all in namespace
kubectl delete all -n smart-city
```

---

## 🔧 ConfigMap Commands

### Create ConfigMaps
```bash
# Traffic Camera
kubectl create configmap traffic-camera-code \
  --from-file=smart-city-services/traffic-camera/app.py \
  -n smart-city --dry-run=client -o yaml | kubectl apply -f -

# Healthcare API
kubectl create configmap healthcare-api-code \
  --from-file=smart-city-services/healthcare-api/app.py \
  -n smart-city --dry-run=client -o yaml | kubectl apply -f -

# Parking System
kubectl create configmap parking-system-code \
  --from-file=smart-city-services/parking-system/app.py \
  -n smart-city --dry-run=client -o yaml | kubectl apply -f -
```

### View ConfigMaps
```bash
# List all ConfigMaps
kubectl get configmap -n smart-city

# View ConfigMap contents
kubectl get configmap traffic-camera-code -n smart-city -o yaml

# Describe ConfigMap
kubectl describe configmap traffic-camera-code -n smart-city

# View file content
kubectl get configmap traffic-camera-code -n smart-city -o jsonpath='{.data.app\.py}' | less
```

### Update ConfigMaps
```bash
# Delete and recreate
kubectl delete configmap traffic-camera-code -n smart-city
kubectl create configmap traffic-camera-code \
  --from-file=smart-city-services/traffic-camera/app.py \
  -n smart-city

# Rollout restart deployments to pick up new config
kubectl rollout restart deployment traffic-camera -n smart-city
```

---

## 🐛 Common Error Solutions

| Error | Solution |
|-------|----------|
| `Pod in Pending` | Wait 2-3 min or check: `kubectl describe pod <pod> -n smart-city` |
| `CrashLoopBackOff` | Check logs: `kubectl logs <pod> -n smart-city` |
| `ImagePullBackOff` | Network issue, wait and retry |
| `Connection refused` | Port-forward not running: `kubectl port-forward ...` |
| `No resources available` | Increase WSL2 RAM or delete other pods |
| `ConfigMap not found` | Recreate with ConfigMap commands above |
| `systemctl not found` | Enable systemd: edit `/etc/wsl.conf` and restart WSL |
| `Port already in use` | Use different port or kill process: `sudo lsof -i :<port>` |

---

## 📈 Performance Monitoring

### Real-time monitoring
```bash
# Watch everything
watch -n 1 'kubectl get all -n smart-city; echo "---"; kubectl top pods -n smart-city'

# Just pods
watch -n 2 'kubectl get pods -n smart-city'

# Just nodes
watch -n 2 'kubectl top nodes'
```

### Collect metrics
```bash
# Export pod descriptions
kubectl describe pods -n smart-city > pod-descriptions.txt

# Export logs
kubectl logs -l app=traffic-camera -n smart-city > traffic-camera.log

# Export events
kubectl get events -n smart-city > events.txt

# Export all resources
kubectl get all -n smart-city -o yaml > all-resources.yaml
```

---

## 🛠️ Useful Aliases

Add to ~/.bashrc:
```bash
alias k='kubectl'
alias kn='kubectl -n smart-city'
alias kpg='kubectl get pods -n smart-city'
alias kpw='kubectl get pods -n smart-city -w'
alias kl='kubectl logs -f'
alias kd='kubectl describe'
alias ke='kubectl get events -n smart-city'
alias kt='kubectl top pods -n smart-city'
```

Then use:
```bash
kpg           # Get pods
kpw           # Watch pods
kl pod-name   # View logs
kd pod pod-name  # Describe pod
```

---

## 📞 Quick Help

| Command | Purpose |
|---------|---------|
| `kubectl --help` | Full kubectl help |
| `kubectl api-resources` | All resource types |
| `kubectl explain pod` | Pod structure docs |
| `kubectl explain deployment` | Deployment structure docs |
| `kubectl cluster-info dump` | Full cluster dump |

---

## 🎯 Step-by-Step Workflow

```bash
# 1. Start everything
sudo systemctl start k3s.service
sleep 5

# 2. Check cluster
kubectl cluster-info
kubectl get nodes

# 3. Deploy services
kubectl apply -f k8s-manifests/namespace.yaml
kubectl create configmap traffic-camera-code --from-file=smart-city-services/traffic-camera/app.py -n smart-city --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f k8s-manifests/services-no-build.yaml

# 4. Wait for pods
kubectl get pods -n smart-city -w
# (Press Ctrl+C when all show Running)

# 5. Test services
kubectl port-forward -n smart-city svc/traffic-camera-service 8001:80 &
curl http://localhost:8001/health

# 6. Run attacks
python attack-simulator/ddos_simulator.py http://localhost:8001/api/cameras 10 30

# 7. Monitor
kubectl logs -f traffic-camera-xxx -n smart-city

# 8. Cleanup
pkill kubectl  # Kill port-forwards
sudo systemctl stop k3s.service
```

---

**Print this card and keep it handy! 🚀**

Last Updated: November 2025
