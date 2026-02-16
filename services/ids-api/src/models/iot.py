"""IoT sensor data Pydantic model.

Defines the JSON schema for telemetry ingested from Raspberry Pi
and other edge devices via ``POST /api/iot/sensor-data``.

Supported event types:
    * ``heartbeat``       — periodic liveness ping.
    * ``motion_detected`` — PIR sensor trigger.
    * ``anomaly``         — device-detected anomaly.
    * ``temperature``     — temperature reading.
    * ``humidity``        — humidity reading.
"""

from pydantic import BaseModel, Field
from typing import Any, Dict, Optional


class IoTSensorData(BaseModel):
    """Incoming IoT sensor telemetry from Raspberry Pi / edge devices.

    Example::

        {
            "device_id": "pi-cam-north-001",
            "device_type": "motion_sensor",
            "event_type": "motion_detected",
            "value": 1,
            "timestamp": "2025-01-15T12:34:56Z",
            "metadata": {"location": "north-entrance"}
        }
    """

    # Unique identifier for the physical device (e.g. "pi-cam-north-001").
    device_id: str = Field(
        ..., min_length=1, max_length=64, description="Unique device identifier"
    )
    # Category of the device (motion_sensor, temperature, camera, etc.).
    device_type: str = Field(
        ..., description="Type of device (motion_sensor, temperature, etc.)"
    )
    # What happened (heartbeat, motion_detected, anomaly, etc.).
    event_type: str = Field(
        ..., description="Event type (motion_detected, heartbeat, anomaly)"
    )
    # Sensor reading — type varies by device (int, float, bool, string).
    value: Optional[Any] = Field(None, description="Sensor value")
    # ISO 8601 timestamp from the device clock (may differ from server time).
    timestamp: Optional[str] = Field(None, description="ISO timestamp")
    # Arbitrary key-value pairs (location, firmware version, etc.).
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
