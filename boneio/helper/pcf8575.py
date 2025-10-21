from __future__ import annotations

from adafruit_pcf8575 import PCF8575 as AdafruitPCF8575

# Use smbus2 wrapper for Python 3.13+ on Debian 13
from boneio.helper.i2c_wrapper import SMBus2I2CWrapper as I2C


class PCF8575(AdafruitPCF8575):
    """PCF8575 I2C GPIO expander wrapper for smbus2."""

    def __init__(self, i2c: I2C, address: int, reset: bool) -> None:
        """Initialize PCF8575.
        
        Args:
            i2c: I2C bus instance (SMBus2I2CWrapper)
            address: I2C address of the device
            reset: Reset flag (unused, for API compatibility)
        """
        super().__init__(i2c_bus=i2c, address=address)
