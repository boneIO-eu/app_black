"""High-level input components.

This module provides high-level input components that combine
hardware GPIO drivers with business logic, MQTT, and Home Assistant integration.

Sub-packages:
    remote: Virtual inputs from remote devices (ESPHome API, CAN bus, …)
"""

from boneio.components.input.binary_sensor import GpioInputBinarySensor
from boneio.components.input.event import GpioEventButton
from boneio.components.input.remote import ESPHomeBinarySensorInput, RemoteInputBase

__all__ = [
    "GpioInputBinarySensor",
    "GpioEventButton",
    "ESPHomeBinarySensorInput",
    "RemoteInputBase",
]
