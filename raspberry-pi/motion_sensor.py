#!/usr/bin/env python3
"""
Raspberry Pi 5 Motion Sensor for Smart City IDS
================================================

This script runs on the Raspberry Pi and sends motion sensor data
to the IDS API for monitoring and analysis.

Hardware:
- Raspberry Pi 5
- PIR Motion Sensor (HC-SR501 or similar)
  - VCC → Pin 2 (5V)
  - GND → Pin 6 (Ground)  
  - OUT → Pin 11 (GPIO 17)

Installation on Pi:
    sudo apt update
    sudo apt install python3-pip python3-gpiozero
    pip3 install requests

Usage:
    python3 motion_sensor.py --ids-url http://192.168.153.129:30800
    
    Or with simulated mode (no real sensor):
    python3 motion_sensor.py --ids-url http://192.168.153.129:30800 --simulate
"""

import argparse
import requests
import time
import random
import logging
import socket
from datetime import datetime
from typing import Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Try to import GPIO (will fail if not on Pi or no sensor)
try:
    from gpiozero import MotionSensor
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    logger.warning("gpiozero not available - running in simulation mode")


class SmartCityMotionSensor:
    """Motion sensor client for Smart City IDS"""
    
    def __init__(self, ids_url: str, device_id: str = None, gpio_pin: int = 17, simulate: bool = False):
        self.ids_url = ids_url.rstrip('/')
        self.device_id = device_id or f"rpi5-motion-{socket.gethostname()}"
        self.gpio_pin = gpio_pin
        self.simulate = simulate or not GPIO_AVAILABLE
        
        # Initialize sensor
        if not self.simulate:
            self.sensor = MotionSensor(gpio_pin)
            logger.info(f"PIR sensor initialized on GPIO {gpio_pin}")
        else:
            self.sensor = None
            logger.info("Running in SIMULATION mode (no real sensor)")
        
        # Stats
        self.motion_count = 0
        self.last_motion_time = None
        self.rapid_motion_threshold = 5  # motions in 10 seconds = anomaly
        self.recent_motions = []
        
    def send_event(self, event_type: str, value: any = None, metadata: dict = None) -> bool:
        """Send event to IDS API"""
        payload = {
            "device_id": self.device_id,
            "device_type": "motion_sensor",
            "event_type": event_type,
            "value": value,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        }
        
        try:
            response = requests.post(
                f"{self.ids_url}/api/iot/sensor",
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"✅ Event sent: {event_type} → {result.get('status')}")
                
                # Check if it triggered a security alert
                if result.get("alert_id"):
                    logger.warning(f"🚨 Security alert generated: ID={result['alert_id']}")
                    if result.get("analysis"):
                        severity = result["analysis"].get("severity", "?")
                        logger.warning(f"   LLM Severity: {severity}/10")
                
                return True
            else:
                logger.error(f"❌ API error: {response.status_code} - {response.text}")
                return False
                
        except requests.exceptions.ConnectionError:
            logger.error(f"❌ Cannot connect to IDS API at {self.ids_url}")
            return False
        except Exception as e:
            logger.error(f"❌ Error sending event: {e}")
            return False
    
    def on_motion_detected(self):
        """Handle motion detection"""
        now = time.time()
        self.motion_count += 1
        self.last_motion_time = now
        
        logger.info(f"🔴 MOTION DETECTED (count: {self.motion_count})")
        
        # Track recent motions for anomaly detection
        self.recent_motions.append(now)
        # Keep only last 10 seconds of motions
        self.recent_motions = [t for t in self.recent_motions if now - t < 10]
        
        # Check for rapid motion (potential intrusion)
        if len(self.recent_motions) >= self.rapid_motion_threshold:
            logger.warning(f"⚠️ RAPID MOTION DETECTED ({len(self.recent_motions)} in 10s)")
            self.send_event(
                event_type="rapid_motion",
                value=len(self.recent_motions),
                metadata={
                    "threshold": self.rapid_motion_threshold,
                    "window_seconds": 10,
                    "description": "Rapid repeated motion may indicate intrusion attempt"
                }
            )
            self.recent_motions = []  # Reset after alert
        else:
            # Normal motion event
            self.send_event(
                event_type="motion_detected",
                value=1,
                metadata={
                    "total_count": self.motion_count
                }
            )
    
    def on_no_motion(self):
        """Handle motion stopped (optional)"""
        logger.debug("Motion stopped")
    
    def send_heartbeat(self):
        """Send periodic heartbeat to IDS"""
        self.send_event(
            event_type="heartbeat",
            value=None,
            metadata={
                "uptime_seconds": int(time.time() - self.start_time),
                "motion_count": self.motion_count,
                "mode": "simulation" if self.simulate else "live"
            }
        )
    
    def simulate_motion(self):
        """Simulate motion events for testing"""
        # Random chance of motion
        if random.random() < 0.3:  # 30% chance every check
            self.on_motion_detected()
        
        # Rare chance of rapid motion (intrusion simulation)
        if random.random() < 0.02:  # 2% chance
            logger.info("🎭 Simulating intrusion (rapid motion)...")
            for _ in range(6):
                self.on_motion_detected()
                time.sleep(0.5)
    
    def run(self, heartbeat_interval: int = 60):
        """Main loop"""
        logger.info(f"🚀 Starting Smart City Motion Sensor")
        logger.info(f"   Device ID: {self.device_id}")
        logger.info(f"   IDS URL: {self.ids_url}")
        logger.info(f"   Mode: {'SIMULATION' if self.simulate else 'LIVE SENSOR'}")
        
        self.start_time = time.time()
        last_heartbeat = 0
        
        # Send initial registration
        self.send_event("device_online", metadata={"startup": True})
        
        if not self.simulate:
            # Real sensor mode - use callbacks
            self.sensor.when_motion = self.on_motion_detected
            self.sensor.when_no_motion = self.on_no_motion
            
            logger.info("Waiting for motion... (Ctrl+C to stop)")
            
            try:
                while True:
                    # Send periodic heartbeat
                    if time.time() - last_heartbeat > heartbeat_interval:
                        self.send_heartbeat()
                        last_heartbeat = time.time()
                    time.sleep(1)
            except KeyboardInterrupt:
                logger.info("Shutting down...")
                self.send_event("device_offline")
        else:
            # Simulation mode
            logger.info("Simulation running... (Ctrl+C to stop)")
            
            try:
                while True:
                    self.simulate_motion()
                    
                    # Heartbeat
                    if time.time() - last_heartbeat > heartbeat_interval:
                        self.send_heartbeat()
                        last_heartbeat = time.time()
                    
                    time.sleep(2)  # Check every 2 seconds
            except KeyboardInterrupt:
                logger.info("Shutting down...")
                self.send_event("device_offline")


def main():
    parser = argparse.ArgumentParser(description="Raspberry Pi Motion Sensor for Smart City IDS")
    parser.add_argument(
        "--ids-url",
        required=True,
        help="URL of the IDS API (e.g., http://192.168.153.129:30800)"
    )
    parser.add_argument(
        "--device-id",
        default=None,
        help="Unique device identifier (default: auto-generated)"
    )
    parser.add_argument(
        "--gpio-pin",
        type=int,
        default=17,
        help="GPIO pin for PIR sensor (default: 17)"
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Run in simulation mode (no real sensor needed)"
    )
    parser.add_argument(
        "--heartbeat",
        type=int,
        default=60,
        help="Heartbeat interval in seconds (default: 60)"
    )
    
    args = parser.parse_args()
    
    sensor = SmartCityMotionSensor(
        ids_url=args.ids_url,
        device_id=args.device_id,
        gpio_pin=args.gpio_pin,
        simulate=args.simulate
    )
    
    sensor.run(heartbeat_interval=args.heartbeat)


if __name__ == "__main__":
    main()
