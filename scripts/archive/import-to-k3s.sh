#!/bin/bash

echo "📦 Importing images to K3s..."

# Save images to tar files
docker save traffic-camera:latest -o /tmp/traffic-camera.tar
docker save healthcare-api:latest -o /tmp/healthcare-api.tar
docker save parking-system:latest -o /tmp/parking-system.tar

# Import to K3s
sudo k3s ctr images import /tmp/traffic-camera.tar
sudo k3s ctr images import /tmp/healthcare-api.tar
sudo k3s ctr images import /tmp/parking-system.tar

# Cleanup
rm /tmp/traffic-camera.tar /tmp/healthcare-api.tar /tmp/parking-system.tar

echo "✅ Images imported to K3s!"
echo ""
echo "Verify in K3s:"
sudo k3s crictl images | grep -E "traffic-camera|healthcare-api|parking-system"
