"""Remote device support for controlling external devices.

Supports multiple protocols:
- MQTT: Standard MQTT communication (boneIO Black, ESPHome, etc.)
- ESPHome API: Native ESPHome API via TCP/IP
- CAN: CAN bus communication (future)
- Loxone: Loxone Miniserver integration (future)
"""

from boneio.core.remote.base import RemoteDevice, RemoteDeviceProtocol
from boneio.core.remote.mqtt import MQTTRemoteDevice
from boneio.core.remote.esphome import (
    ESPHomeRemoteDevice,
    discover_esphome_entities,
    scan_esphome_devices,
    ESPHOME_API_AVAILABLE,
    ZEROCONF_AVAILABLE,
)

__all__ = [
    "RemoteDevice",
    "RemoteDeviceProtocol",
    "MQTTRemoteDevice",
    "ESPHomeRemoteDevice",
    "discover_esphome_entities",
    "scan_esphome_devices",
    "ESPHOME_API_AVAILABLE",
    "ZEROCONF_AVAILABLE",
]
