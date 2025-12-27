"""Remote device support for controlling external devices.

Supports multiple protocols:
- MQTT: Standard MQTT communication (boneIO Black, ESPHome, etc.)
- CAN: CAN bus communication (future)
- Loxone: Loxone Miniserver integration (future)
- ESPHome API: Native ESPHome API (future)
"""

from boneio.core.remote.base import RemoteDevice, RemoteDeviceProtocol
from boneio.core.remote.mqtt import MQTTRemoteDevice

__all__ = [
    "RemoteDevice",
    "RemoteDeviceProtocol",
    "MQTTRemoteDevice",
]
