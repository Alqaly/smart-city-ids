#!/bin/bash

if [[ -z "$1" ]]; then
    echo "Usage: ./scale-iot.sh <number_of_devices>"
    echo "Example: ./scale-iot.sh 20"
    exit 1
fi

echo "Scaling IoT devices to $1..."
kubectl scale deployment iot-devices -n smart-city --replicas=$1

echo "Waiting for pods..."
sleep 10

echo "Current IoT devices:"
kubectl get pods -n smart-city -l app=iot-device
