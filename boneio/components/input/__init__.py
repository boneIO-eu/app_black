"""High-level input components.

This module provides high-level input components that combine
hardware GPIO drivers with business logic, MQTT, and Home Assistant integration.
"""

from boneio.components.input.binary_sensor import GpioInputBinarySensor
from boneio.components.input.event import GpioEventButton

__all__ = [
    "GpioInputBinarySensor",
    "GpioEventButton",
]
