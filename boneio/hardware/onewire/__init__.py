"""OneWire hardware drivers and sensors.

This module provides 1-Wire protocol support and sensors:
- OneWire bus protocol implementation
- DS2482 I2C-to-1Wire bridge
- Dallas temperature sensors (DS18B20, etc.)
"""

from boneio.hardware.onewire.bus import OneWire, OneWireBus, OneWireAddress
from boneio.hardware.onewire.dallas import DallasSensor
from boneio.hardware.onewire.ds2482 import DS2482, DS2482_ADDRESS

__all__ = [
    # Bus and protocol
    "OneWire",
    "OneWireBus",
    "OneWireAddress",
    # I2C-to-1Wire bridge
    "DS2482",
    "DS2482_ADDRESS",
    # Sensors
    "DallasSensor",
]
