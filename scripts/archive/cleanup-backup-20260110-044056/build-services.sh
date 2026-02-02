#!/bin/bash

echo "🏗️  Building Smart City Services..."

# Build Traffic Camera
echo "📹 Building Traffic Camera Service..."
cd smart-city-services/traffic-camera
docker build -t traffic-camera:latest .
cd ../..

# Build Healthcare API
echo "🏥 Building Healthcare API Service..."
cd smart-city-services/healthcare-api
docker build -t healthcare-api:latest .
cd ../..

# Build Parking System
echo "🚗 Building Parking System Service..."
cd smart-city-services/parking-system
docker build -t parking-system:latest .
cd ../..

echo "✅ All services built successfully!"
echo ""
echo "Verify images:"
docker images | grep -E "traffic-camera|healthcare-api|parking-system"
