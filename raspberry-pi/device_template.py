#!/usr/bin/env python3
"""
Smart City IDS — IoT Device Client Template
============================================
Copy this file to create a client for any IoT sensor or device.

Subclass SmartCityDevice, override read_sensor() and is_anomaly(),
then run it on your hardware (Raspberry Pi, Arduino bridge, etc.).

Usage:
    python3 device_template.py --ids-url http://192.168.1.100:30800

See docs/IOT_INTEGRATION_SDK.md for full documentation.
"""

import argparse
import requests
import time
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


class SmartCityDevice:
    """Base class for any IoT device connecting to Smart City IDS.

    Override:
        read_sensor()  → returns dict of current readings
        is_anomaly()   → returns True if the reading is suspicious
    """

    def __init__(
        self,
        ids_url: str,
        device_id: str,
        device_type: str,
        threshold: int = 5,
        window_sec: int = 60,
        heartbeat_sec: int = 60,
    ):
        self.ids_url = ids_url.rstrip("/")
        self.device_id = device_id
        self.device_type = device_type
        self.threshold = threshold
        self.window_sec = window_sec
        self.heartbeat_sec = heartbeat_sec
        self.event_times: list[float] = []
        self.total_alerts = 0
        self.last_heartbeat = 0.0

    # ── Override these ───────────────────────────────────────────
    def read_sensor(self) -> dict:
        """Return a dict of current sensor readings."""
        raise NotImplementedError("Subclass must implement read_sensor()")

    def is_anomaly(self, reading: dict) -> bool:
        """Return True if this reading should trigger an alert."""
        return False

    # ── Telemetry ────────────────────────────────────────────────
    def send_telemetry(self, reading: dict, event_type: str = "telemetry"):
        payload = {
            "device_id": self.device_id,
            "device_type": self.device_type,
            "event_type": event_type,
            "value": reading,
            "timestamp": datetime.now().isoformat(),
        }
        try:
            r = requests.post(
                f"{self.ids_url}/api/iot/sensor", json=payload, timeout=10
            )
            if r.status_code == 200:
                logger.info("Telemetry sent: %s", event_type)
                return r.json()
        except requests.exceptions.ConnectionError:
            logger.error("Cannot connect to %s", self.ids_url)
        except Exception as e:
            logger.error("Send error: %s", e)
        return None

    # ── Alert ────────────────────────────────────────────────────
    def send_alert(self, reading: dict, rule_name: str = "Device Anomaly"):
        self.total_alerts += 1
        payload = {
            "output": f"{rule_name}: {self.device_id} reported anomalous reading",
            "priority": "Warning",
            "rule": rule_name,
            "time": datetime.now().isoformat(),
            "output_fields": {
                "container.name": self.device_type,
                "device.id": self.device_id,
                "alert.signature": rule_name,
                "threat.type": "Sensor Anomaly",
            },
        }
        try:
            r = requests.post(
                f"{self.ids_url}/api/alerts/internal", json=payload, timeout=10
            )
            if r.status_code == 200:
                data = r.json()
                logger.warning(
                    "ALERT #%d sent! Severity: %s/10",
                    self.total_alerts,
                    data.get("severity", "?"),
                )
                return data
        except Exception as e:
            logger.error("Alert error: %s", e)
        return None

    # ── Heartbeat ────────────────────────────────────────────────
    def send_heartbeat(self):
        self.send_telemetry(
            {"status": "alive", "uptime_alerts": self.total_alerts},
            event_type="heartbeat",
        )
        self.last_heartbeat = time.time()

    # ── Main Loop ────────────────────────────────────────────────
    def run(self, interval_sec: float = 1.0):
        logger.info("Starting %s [%s]", self.device_type, self.device_id)
        logger.info("IDS API: %s", self.ids_url)
        logger.info(
            "Anomaly threshold: %d events in %ds", self.threshold, self.window_sec
        )

        while True:
            try:
                reading = self.read_sensor()

                if self.is_anomaly(reading):
                    now = time.time()
                    self.event_times.append(now)
                    self.event_times = [
                        t for t in self.event_times if now - t < self.window_sec
                    ]
                    if len(self.event_times) >= self.threshold:
                        self.send_alert(reading)
                        self.event_times = []
                    else:
                        self.send_telemetry(reading, "anomaly")
                else:
                    self.send_telemetry(reading)

                if time.time() - self.last_heartbeat > self.heartbeat_sec:
                    self.send_heartbeat()

            except Exception as e:
                logger.error("Loop error: %s", e)

            time.sleep(interval_sec)


# ═════════════════════════════════════════════════════════════════
# EXAMPLE: Temperature + Humidity Sensor
# Replace this with your actual hardware logic.
# ═════════════════════════════════════════════════════════════════
class TemperatureSensor(SmartCityDevice):
    """Example: alerts when temperature exceeds a threshold."""

    def __init__(self, ids_url: str, max_temp: float = 60.0, **kwargs):
        super().__init__(
            ids_url=ids_url,
            device_id="temp-sensor-01",
            device_type="temperature_sensor",
            **kwargs,
        )
        self.max_temp = max_temp

    def read_sensor(self) -> dict:
        # TODO: Replace with real hardware read
        # e.g., DS18B20 via w1-gpio, or DHT22 via adafruit-circuitpython
        import random

        return {
            "temperature_c": round(20 + random.random() * 50, 1),
            "humidity_pct": round(30 + random.random() * 40, 1),
        }

    def is_anomaly(self, reading: dict) -> bool:
        return reading["temperature_c"] > self.max_temp


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Smart City IDS — IoT Device Client Template"
    )
    parser.add_argument(
        "--ids-url",
        required=True,
        help="IDS API URL (e.g., http://192.168.1.100:30800)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=5.0,
        help="Seconds between sensor reads (default: 5)",
    )
    args = parser.parse_args()

    sensor = TemperatureSensor(ids_url=args.ids_url)
    sensor.run(interval_sec=args.interval)
