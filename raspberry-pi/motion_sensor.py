#!/usr/bin/env python3
"""
Raspberry Pi Motion Sensor for Smart City IDS
==============================================

Sends motion alerts to IDS API after threshold is reached.

Hardware:
- Raspberry Pi 5 (or 4)
- AM312 PIR Motion Sensor (3.3V) - RECOMMENDED
  - VCC → Pin 1  (3.3V)  ⚠️ NOT Pin 2 (5V)!
  - OUT → Pin 11 (GPIO 17)
  - GND → Pin 6  (Ground)

Installation on Pi:
    sudo apt update
    sudo apt install python3-pip python3-gpiozero -y
    pip3 install requests --break-system-packages

Usage:
    python3 motion_sensor.py --ids-url http://<KALI_IP>:30800
    
    # Get Kali IP by running on Kali:
    hostname -I
"""

import argparse
import requests
import time
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

try:
    from gpiozero import MotionSensor
except ImportError:
    logger.error("❌ gpiozero not found!")
    logger.error("   Install: sudo apt install python3-gpiozero")
    exit(1)


class SmartCityMotionSensor:
    def __init__(self, ids_url, gpio_pin=17, threshold=5, window=60):
        self.ids_url = ids_url.rstrip('/')
        self.device_id = "rpi5-motion-sensor"
        self.threshold = threshold
        self.window = window
        self.sensor = MotionSensor(gpio_pin)
        self.motion_times = []
        self.was_off = True
        self.total_alerts = 0
        logger.info(f"Sensor initialized on GPIO {gpio_pin}")
    
    def send_alert(self, count):
        """Send alert to IDS API"""
        self.total_alerts += 1
        payload = {
            "device_id": self.device_id,
            "device_type": "motion_sensor",
            "event_type": "rapid_motion",
            "value": {"count": count, "threshold": self.threshold, "window": self.window},
            "timestamp": datetime.now().isoformat(),
        }
        try:
            r = requests.post(f"{self.ids_url}/api/iot/sensor", json=payload, timeout=10)
            if r.status_code == 200:
                result = r.json()
                logger.warning(f"🚨 ALERT SENT! (Total: {self.total_alerts})")
                if result.get("alert_id"):
                    logger.warning(f"   Alert ID: {result['alert_id']}")
                return True
        except requests.exceptions.ConnectionError:
            logger.error(f"❌ Cannot connect to {self.ids_url}")
        except Exception as e:
            logger.error(f"❌ Error: {e}")
        return False
    
    def run(self):
        """Main loop"""
        logger.info(f"🚀 Starting motion sensor")
        logger.info(f"📡 IDS URL: {self.ids_url}")
        logger.info(f"⚙️  Alert after {self.threshold} motions in {self.window}s")
        logger.info(f"👋 Wave your hand to trigger motion...")
        
        while True:
            current = self.sensor.motion_detected
            now = time.time()
            
            if not current:
                self.was_off = True
            elif current and self.was_off:
                self.was_off = False
                self.motion_times.append(now)
                self.motion_times = [t for t in self.motion_times if now - t < self.window]
                count = len(self.motion_times)
                logger.info(f"🔴 Motion! ({count}/{self.threshold} in last {self.window}s)")
                
                if count >= self.threshold:
                    logger.warning(f"🚨 THRESHOLD REACHED!")
                    self.send_alert(count)
                    self.motion_times = []
            
            time.sleep(0.1)


def main():
    parser = argparse.ArgumentParser(description="Raspberry Pi Motion Sensor for Smart City IDS")
    parser.add_argument("--ids-url", required=True, help="IDS API URL (e.g., http://192.168.1.187:30800)")
    parser.add_argument("--gpio-pin", type=int, default=17, help="GPIO pin (default: 17)")
    parser.add_argument("--threshold", type=int, default=5, help="Motions to trigger alert (default: 5)")
    parser.add_argument("--window", type=int, default=60, help="Time window in seconds (default: 60)")
    args = parser.parse_args()
    
    try:
        sensor = SmartCityMotionSensor(
            ids_url=args.ids_url,
            gpio_pin=args.gpio_pin,
            threshold=args.threshold,
            window=args.window
        )
        sensor.run()
    except KeyboardInterrupt:
        logger.info("Shutting down...")


if __name__ == "__main__":
    main()
