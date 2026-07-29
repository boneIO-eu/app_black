"""OneWire hardware sensors.

The kernel ds2482/w1-therm modules handle hardware communication;
this package exposes only the DallasSensor wrapper.
"""

from boneio.hardware.onewire.dallas import DallasSensor

__all__ = [
    "DallasSensor",
]
