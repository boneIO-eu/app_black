"""GPIO expanders (I2C-based)."""

from boneio.hardware.gpio.expanders.mcp23017 import MCP23017
from boneio.hardware.gpio.expanders.pca9685 import PCA9685
from boneio.hardware.gpio.expanders.pcf8575 import PCF8575

__all__ = ["MCP23017", "PCA9685", "PCF8575"]
