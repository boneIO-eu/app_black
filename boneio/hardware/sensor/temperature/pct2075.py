"""PCT2075 temperature sensor wrapper.

This module provides a sensor wrapper for the PCT2075/LM75 I2C temperature sensor.
It combines the low-level PCT2075 hardware driver with sensor functionality
(MQTT, async updates, filtering, etc.).
"""

from __future__ import annotations

import logging

from boneio.hardware.i2c.pct2075 import PCT2075 as PCT2075Driver
from boneio.hardware.sensor.temperature.base import TempSensor

_LOGGER = logging.getLogger(__name__)


class PCT2075(TempSensor):
    """PCT2075/LM75 temperature sensor with MQTT and async update support.
    
    This class wraps the PCT2075 hardware driver with full sensor functionality:
    - Periodic async updates
    - MQTT publishing
    - EventBus integration
    - Value filtering
    - State management
    
    The PCT2075 is a digital temperature sensor with I2C interface, compatible
    with LM75 and similar sensors. Features:
    - Temperature range: -55°C to +125°C
    - Accuracy: ±2°C (typical)
    - Resolution: 0.125°C
    - I2C address: 0x48-0x4F (default: 0x48)
    
    Args:
        i2c: I2C bus instance
        address: I2C device address (0x48-0x4F)
        id: Sensor identifier
        filters: List of filter expressions
        unit_of_measurement: Temperature unit (default: '°C')
        **kwargs: Additional arguments (manager, update_interval, etc.)
        
    Example:
        >>> from boneio.hardware.i2c.bus import SMBus2I2C
        >>> i2c = SMBus2I2C(bus_num=1)
        >>> sensor = PCT2075(
        ...     i2c=i2c,
        ...     address=0x48,
        ...     id='room_temperature',
        ...     filters=[{'round': 2}],
        ...     manager=manager,
        ...     update_interval=TimePeriod(seconds=60)
        ... )
    """
    
    SensorClass = PCT2075Driver
    DefaultName = "PCT2075"

    def __init__(
        self,
        i2c,
        address: int = 0x48,
        id: str | None = None,
        **kwargs,
    ):
        """Initialize PCT2075 temperature sensor.
        
        Args:
            i2c: I2C bus instance
            address: I2C address (0x48-0x4F, default: 0x48)
            id: Sensor identifier (defaults to 'PCT2075')
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
            "PCT2075 sensor '%s' initialized at address 0x%02X",
            self.id,
            address
        )

