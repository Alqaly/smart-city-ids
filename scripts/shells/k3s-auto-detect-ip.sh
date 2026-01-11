 Stop K3s
sudo systemctl stop k3s

# Remove the old K3s config that might have wrong IP
sudo rm -rf /var/lib/rancher/k3s/server/db
sudo rm -rf /var/lib/rancher/k3s/agent

# Start K3s fresh (it will auto-detect network)
sudo systemctl start k3s

# Wait for it to initialize
sleep 45

# Check status
sudo systemctl status k3s
