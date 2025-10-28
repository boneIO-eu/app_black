"""I2C hardware drivers and sensors.

This module provides I2C bus support and I2C-based sensors:
- SMBus2I2C wrapper for I2C communication
- Temperature sensors (PCT2075/LM75, MCP9808)
- Power monitoring (INA219)
"""

from boneio.hardware.i2c.bus import SMBus2I2C
from boneio.hardware.i2c.ina219 import INA219, INA219Sensor
from boneio.hardware.i2c.mcp9808 import MCP9808
from boneio.hardware.i2c.pct2075 import PCT2075

__all__ = [
    # Bus
    "SMBus2I2C",
    # Temperature sensors
    "PCT2075",
    "MCP9808",
    # Power monitoring
    "INA219",
    "INA219Sensor",
]
