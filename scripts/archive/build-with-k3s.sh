#!/bin/bash

echo "🏗️  Building images directly with K3s..."

# Build Traffic Camera
echo "📹 Building Traffic Camera..."
cd smart-city-services/traffic-camera
sudo k3s ctr images import --base-name traffic-camera:latest <(tar -czf - Dockerfile app.py | sudo k3s ctr images import -)
cd ../..

# Actually, let's use buildah or podman instead
echo "We need a container builder. Let me install buildah..."

