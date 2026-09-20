"""Remote input components — virtual inputs from external devices.

This package provides remote input classes that receive state changes from
external devices (ESPHome API, CAN bus, etc.) instead of local GPIO pins.
All remote inputs share a common base :class:`RemoteInputBase` and implement
the same duck-type interface as :class:`GpioBaseClass`.

Subpackages:
    base:    ``RemoteInputBase`` — shared logic (EventBus, actions, MultiClickDetector)
    esphome: ``ESPHomeBinarySensorInput`` — ESPHome native API
    mqtt:    ``MqttBinarySensorInput`` — any device that publishes a state on a
             topic, most usefully another boneIO
    # future:
    # can_esphome: CAN bus → ESPHome device
    # can_boneio:  CAN bus → another boneIO Black
"""

from boneio.components.input.remote.base import RemoteInputBase
from boneio.components.input.remote.esphome import ESPHomeBinarySensorInput
from boneio.components.input.remote.mqtt import MqttBinarySensorInput

__all__ = [
    "RemoteInputBase",
    "ESPHomeBinarySensorInput",
    "MqttBinarySensorInput",
]
