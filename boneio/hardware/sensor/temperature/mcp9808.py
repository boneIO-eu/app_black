"""MCP9808 temperature sensor wrapper.

This module provides a sensor wrapper for the MCP9808 I2C temperature sensor.
It combines the low-level MCP9808 hardware driver with sensor functionality
(MQTT, async updates, filtering, etc.).
"""

from __future__ import annotations

import logging

from boneio.hardware.i2c.mcp9808 import MCP9808 as MCP9808Driver
from boneio.hardware.sensor.temperature.base import TempSensor

_LOGGER = logging.getLogger(__name__)


class MCP9808(TempSensor):
    """MCP9808 high-accuracy temperature sensor with MQTT and async update support.
    
    This class wraps the MCP9808 hardware driver with full sensor functionality:
    - Periodic async updates
    - MQTT publishing
    - EventBus integration
    - Value filtering
    - State management
    
    The MCP9808 is a high-accuracy digital temperature sensor with I2C interface.
    Features:
    - Temperature range: -40°C to +125°C
    - Accuracy: ±0.25°C (typical, 0°C to +65°C), ±0.5°C (-40°C to +125°C)
    - Resolution: 0.0625°C (12-bit)
    - I2C address: 0x18-0x1F (default: 0x18)
    
    Args:
        i2c: I2C bus instance
        address: I2C device address (0x18-0x1F)
        id: Sensor identifier
        filters: List of filter expressions
        unit_of_measurement: Temperature unit (default: '°C')
        **kwargs: Additional arguments (manager, update_interval, etc.)
        
    Example:
        >>> from boneio.hardware.i2c.bus import SMBus2I2C
        >>> i2c = SMBus2I2C(bus_num=1)
        >>> sensor = MCP9808(
        ...     i2c=i2c,
        ...     address=0x18,
        ...     id='precision_temp',
        ...     filters=[{'round': 3}],
        ...     manager=manager,
        ...     update_interval=TimePeriod(seconds=30)
        ... )
    """
    
    SensorClass = MCP9808Driver
    DefaultName = "MCP9808"

    def __init__(
        self,
        i2c,
        address: int = 0x18,
        id: str | None = None,
        **kwargs,
    ):
        """Initialize MCP9808 temperature sensor.
        
        Args:
            i2c: I2C bus instance
            address: I2C address (0x18-0x1F, default: 0x18)
            id: Sensor identifier (defaults to 'MCP9808')
            **kwargs: Additional arguments passed to TempSensor
        """
        if id is None:
            id = self.DefaultName
            
        super().__init__(
            i2c=i2c,
            address=address,
            id=id,
            **kwargs,
        )
        
        _LOGGER.info(
            "MCP9808 sensor '%s' initialized at address 0x%02X",
            self.id,
            address
        )

