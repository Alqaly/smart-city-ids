"""IoT sensor data model."""

from pydantic import BaseModel, Field
from typing import Any, Dict, Optional


class IoTSensorData(BaseModel):
    """Incoming IoT sensor telemetry from Raspberry Pi / edge devices."""

    device_id: str = Field(
        ..., min_length=1, max_length=64, description="Unique device identifier"
    )
    device_type: str = Field(
        ..., description="Type of device (motion_sensor, temperature, etc.)"
    )
    event_type: str = Field(
        ..., description="Event type (motion_detected, heartbeat, anomaly)"
    )
    value: Optional[Any] = Field(None, description="Sensor value")
    timestamp: Optional[str] = Field(None, description="ISO timestamp")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
