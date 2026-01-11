# 🛡️ Smart City IDS - WSL2 Setup Guide

## CRITICAL: WSL2 Systemd Issue

WSL2 environments sometimes have limited systemd support. This guide covers **all possible scenarios**.

---

## Prerequisites

### Windows Host
- **WSL2** installed (not WSL1)
- Ubuntu 20.04 LTS or newer distribution
- At least 8GB RAM allocated to WSL2
- 20GB free disk space

### Inside WSL2
```bash
# Check your WSL version
wsl --list --verbose

# Should show something like:
# NAME           STATE       VERSION
# Ubuntu-20.04   Running     2
```

---

## Part 1: WSL2 Configuration

### Step 1: Enable Systemd (Recommended)

If your WSL2 doesn't have systemd enabled, enable it:

```bash
# Edit WSL configuration
sudo nano /etc/wsl.conf
```

Add these lines:
```ini
[boot]
systemd=true

[interop]
enabled=true
appendWindowsPath=true
```

**Save and restart WSL:**
```bash
# In PowerShell on Windows (not in WSL)
wsl --terminate Ubuntu-20.04
# Then restart the Ubuntu terminal
```

### Step 2: Verify Systemd is Running

Back in WSL:
```bash
systemctl --version
systemctl status

# Should show:
# systemd 245 (245.4-4ubuntu3.2)
# ...
# System uptime: 2min 34s
```

If systemd is working, proceed to Part 2.

**If systemd is NOT available**, see **Alternate Setup** at the end of this guide.

---

## Part 2: Install K3s (With Systemd)

### Step 1: Update System

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y curl git nano
```

### Step 2: Install K3s

```bash
# Download and install K3s
curl -sfL https://get.k3s.io | sh -

# This installs K3s and registers it as a systemd service
# Installation takes 2-3 minutes
```

### Step 3: Verify K3s is Running

```bash
# Check K3s service status
sudo systemctl status k3s.service

# Should show:
# ● k3s.service - Lightweight Kubernetes
#    Loaded: loaded (/etc/systemd/system/k3s.service; enabled; preset: disabled)
#    Active: active (running) since ...
```

### Step 4: Setup kubectl Access

```bash
# Set correct permissions for kubectl config
sudo chmod 644 /etc/rancher/k3s/k3s.yaml

# Add to your ~/.bashrc
echo "export KUBECONFIG=/etc/rancher/k3s/k3s.yaml" >> ~/.bashrc
source ~/.bashrc

# Verify kubectl works
kubectl cluster-info
kubectl get nodes
```

---

## Part 3: Deploy Smart City IDS

### Step 1: Navigate to Project

```bash
cd ~/smart-city-ids
# Or wherever you cloned it
```

### Step 2: Create Namespace

```bash
kubectl apply -f k8s-manifests/namespace.yaml

# Verify
kubectl get namespaces | grep smart-city
```

### Step 3: Create ConfigMaps

```bash
# Traffic Camera
kubectl create configmap traffic-camera-code \
  --from-file=smart-city-services/traffic-camera/app.py \
  -n smart-city \
  --dry-run=client -o yaml | kubectl apply -f -

# Healthcare API
kubectl create configmap healthcare-api-code \
  --from-file=smart-city-services/healthcare-api/app.py \
  -n smart-city \
  --dry-run=client -o yaml | kubectl apply -f -

# Parking System
kubectl create configmap parking-system-code \
  --from-file=smart-city-services/parking-system/app.py \
  -n smart-city \
  --dry-run=client -o yaml | kubectl apply -f -
```

### Step 4: Deploy Services

```bash
kubectl apply -f k8s-manifests/services-no-build.yaml

# Wait a few seconds
sleep 10

# Check pod status
kubectl get pods -n smart-city

# Expected output (after 1-2 minutes):
# NAME                              READY   STATUS    RESTARTS   AGE
# traffic-camera-7d4f9c8b2-abc12    1/1     Running   0          45s
# traffic-camera-7d4f9c8b2-def45    1/1     Running   0          45s
# healthcare-api-5g6h7i8j9-klm23    1/1     Running   0          42s
# healthcare-api-5g6h7i8j9-nop45    1/1     Running   0          42s
# parking-system-2q3r4s5t6-uv789    1/1     Running   0          39s
# parking-system-2q3r4s5t6-wxy01    1/1     Running   0          39s
```

---

## Part 4: Testing the Setup

### Test 1: Check Cluster Health

```bash
kubectl cluster-info
kubectl get nodes
kubectl get pods -n smart-city
```

### Test 2: Port-Forward and Test Services

**In one terminal:**
```bash
# Port-forward traffic camera
kubectl port-forward -n smart-city svc/traffic-camera-service 8001:80
```

**In another terminal:**
```bash
# Test the service
curl http://localhost:8001/health
curl http://localhost:8001/api/cameras
curl http://localhost:8001/api/analytics
```

### Test 3: View Logs

```bash
# Get a pod name
kubectl get pods -n smart-city

# View its logs
kubectl logs <pod-name> -n smart-city

# Follow logs in real-time
kubectl logs -f <pod-name> -n smart-city
```

---

## Part 5: Running Attacks

### Attack 1: DDoS Simulation

```bash
# First, port-forward the service (in one terminal)
kubectl port-forward -n smart-city svc/traffic-camera-service 8001:80

# In another terminal, run the DDoS simulator
python attack-simulator/ddos_simulator.py http://localhost:8001/api/cameras 10 30

# Parameters:
# - URL: http://localhost:8001/api/cameras
# - Threads: 10
# - Duration: 30 seconds
```

### Attack 2: Data Exfiltration

```bash
# Port-forward a service
kubectl port-forward -n smart-city svc/healthcare-api-service 8002:80

# Extract data (in another terminal)
python attack-simulator/data_exfiltration.py http://localhost:8002

# This attempts to:
# - Extract patient data
# - Access admin configs
# - Steal payment records
# - Modify system settings
```

---

## Part 6: Common Issues and Solutions

### Issue 1: "K3s failed to start" or "systemctl not found"

**Symptom:**
```
Job for k3s.service failed because the control process exited with error code.
```

**Solution:**

Check if systemd is available:
```bash
systemctl --version
```

If not available, see **Alternate Setup (No Systemd)** below.

### Issue 2: "Kubernetes Service not responding"

**Symptom:**
```
Connection refused
```

**Solution:**

```bash
# 1. Check if services are running
kubectl get svc -n smart-city

# 2. Check if pods are ready
kubectl get pods -n smart-city

# 3. Check pod logs
kubectl describe pod <pod-name> -n smart-city

# 4. View container output
kubectl logs <pod-name> -n smart-city
```

### Issue 3: "Pod stuck in Pending"

**Symptom:**
```
NAME                    READY   STATUS    RESTARTS   AGE
traffic-camera-xxx      0/1     Pending   0          5m
```

**Solution:**

```bash
# Check what's wrong
kubectl describe pod <pod-name> -n smart-city

# Common causes:
# - Not enough resources
# - Image pull error
# - Node not ready

# Check node status
kubectl get nodes

# Check resource usage
kubectl top nodes
kubectl top pods -n smart-city
```

### Issue 4: "Cannot bind port 80"

**Solution:**

```bash
# Use a different local port
kubectl port-forward -n smart-city svc/traffic-camera-service 8001:80

# Or kill the process using port 80
sudo lsof -i :80
sudo kill -9 <PID>
```

### Issue 5: ConfigMap not found

**Solution:**

```bash
# Verify ConfigMap exists
kubectl get configmap -n smart-city

# If missing, recreate it
kubectl create configmap traffic-camera-code \
  --from-file=smart-city-services/traffic-camera/app.py \
  -n smart-city \
  --dry-run=client -o yaml | kubectl apply -f -

# View ConfigMap contents
kubectl describe configmap traffic-camera-code -n smart-city
```

---

## Alternate Setup (No Systemd)

If systemd is NOT available in your WSL2:

### Step 1: Install K3s (Direct Mode)

```bash
# Kill any existing K3s processes
sudo pkill -f "k3s server" 2>/dev/null || true

# Start K3s directly (not via systemd)
sudo k3s server \
    --write-kubeconfig-mode=644 \
    --write-kubeconfig=/etc/rancher/k3s/k3s.yaml \
    --disable=traefik \
    --disable=servicelb \
    &

# Setup kubectl
echo "export KUBECONFIG=/etc/rancher/k3s/k3s.yaml" >> ~/.bashrc
source ~/.bashrc

# Wait for K3s to be ready (2-3 minutes)
sleep 30
kubectl cluster-info
```

### Step 2: Create Namespace and Deploy

Same as Part 3 above.

### Step 3: Keep K3s Running

K3s is now running in the background. To keep it running:

```bash
# Option 1: Keep terminal open
# (K3s will stop if you close the terminal)

# Option 2: Run in tmux
sudo apt install tmux
tmux new-session -d -s k3s 'k3s server --write-kubeconfig-mode=644 --write-kubeconfig=/etc/rancher/k3s/k3s.yaml --disable=traefik --disable=servicelb'

# Option 3: Create a persistent script
cat > ~/.local/bin/start-k3s.sh << 'EOF'
#!/bin/bash
sudo k3s server \
    --write-kubeconfig-mode=644 \
    --write-kubeconfig=/etc/rancher/k3s/k3s.yaml \
    --disable=traefik \
    --disable=servicelb
EOF

chmod +x ~/.local/bin/start-k3s.sh
# Run: ~/.local/bin/start-k3s.sh
```

---

## Quick Reference Commands

### Cluster Management
```bash
# Start K3s
sudo systemctl start k3s.service

# Stop K3s
sudo systemctl stop k3s.service

# Check status
sudo systemctl status k3s.service

# View logs
sudo journalctl -xeu k3s.service
```

### Kubernetes Operations
```bash
# List pods
kubectl get pods -n smart-city

# List services
kubectl get svc -n smart-city

# View pod logs
kubectl logs <pod-name> -n smart-city

# Port-forward
kubectl port-forward -n smart-city svc/<service-name> <local-port>:80

# Execute command in pod
kubectl exec -it <pod-name> -n smart-city -- /bin/bash

# Delete a pod (will auto-restart)
kubectl delete pod <pod-name> -n smart-city

# Describe pod (detailed info)
kubectl describe pod <pod-name> -n smart-city
```

### Troubleshooting
```bash
# Check all resources in namespace
kubectl get all -n smart-city

# Watch pods in real-time
kubectl get pods -n smart-city -w

# Get pod events
kubectl get events -n smart-city

# Check resource usage
kubectl top nodes
kubectl top pods -n smart-city

# Export logs to file
kubectl logs <pod-name> -n smart-city > pod-logs.txt
```

---

## Performance Tips for WSL2

1. **Allocate Enough Resources**
   - Edit `.wslconfig` in Windows home folder:
   ```ini
   [wsl2]
   memory=8GB
   processors=4
   swap=4GB
   ```

2. **Mount Project on WSL Filesystem** (not /mnt/c)
   - Projects on `/mnt/c` (Windows) are slower
   - Clone to `~/smart-city-ids` instead

3. **Increase File Limits**
   ```bash
   sudo sysctl -w fs.inotify.max_user_watches=524288
   ```

4. **Monitor K3s Memory Usage**
   ```bash
   watch -n 1 'kubectl top nodes; kubectl top pods -n smart-city'
   ```

---

## Next Steps

1. ✅ Verify all services are running
2. 📊 Set up monitoring (Falco, Prometheus)
3. 🎯 Create and run attack scenarios
4. 📈 Collect metrics and analyze
5. 🚀 Deploy IDS application

See `/docs` folder for detailed guides.
