"""Base temperature sensor class.

This module provides TempSensor, a specialized base class for temperature sensors.
It extends BaseSensor with temperature-specific functionality.
"""

from __future__ import annotations

import logging

from boneio.const import TEMPERATURE
from boneio.core.sensor import BaseSensor
from boneio.exceptions import I2CError

_LOGGER = logging.getLogger(__name__)


class TempSensor(BaseSensor):
    """Base class for temperature sensors.
    
    This class extends BaseSensor with temperature-specific functionality.
    It handles hardware sensor initialization and provides common temperature
    sensor patterns.
    
    Class Attributes:
        SensorClass: The hardware sensor driver class (e.g., PCT2075, MCP9808)
        DefaultName: Default sensor name (TEMPERATURE)
        
    Inheriting classes should:
    1. Set SensorClass to the appropriate hardware driver
    2. Implement any sensor-specific initialization
    3. Override async_update() if needed
    
    Args:
        i2c: I2C bus instance
        address: I2C address (int) or sensor ID (str for 1-Wire)
        id: Sensor identifier
        filters: List of filter expressions (default: ['round(x, 2)'])
        unit_of_measurement: Temperature unit (default: '°C')
        **kwargs: Additional arguments (manager, update_interval, etc.)
        
    Example:
        >>> class MyTempSensor(TempSensor):
        ...     SensorClass = PCT2075
        ...     
        ...     def __init__(self, i2c, address, **kwargs):
        ...         super().__init__(i2c=i2c, address=address, **kwargs)
    """
    
    SensorClass = None
    DefaultName = TEMPERATURE

    def __init__(
        self,
        i2c,
        address: int | str,
        id: str | None = None,
        filters: list | None = None,
        unit_of_measurement: str = "°C",
        **kwargs,
    ):
        """Initialize temperature sensor.
        
        Args:
            i2c: I2C bus instance or None for 1-Wire sensors
            address: I2C address (int) or sensor ID (str)
            id: Sensor identifier (defaults to DefaultName)
            filters: Filter expressions (defaults to ['round(x, 2)'])
            unit_of_measurement: Temperature unit
            **kwargs: Additional arguments
            
        Raises:
            I2CError: If sensor initialization fails
        """
        # Set defaults
        if id is None:
            id = self.DefaultName
        if filters is None:
            filters = [{"round": 2}]  # Default: round to 2 decimals
            
        # Initialize BaseSensor first
        super().__init__(
            id=id,
            filters=filters,
            unit_of_measurement=unit_of_measurement,
            **kwargs,
        )
        
        # Initialize hardware sensor
        self._pct = None
        if self.SensorClass:
            try:
                if isinstance(address, int):
                    # I2C sensor
                    self._pct = self.SensorClass(i2c_bus=i2c, address=address)
                else:
                    # Other sensors (e.g., 1-Wire with string address)
                    self._pct = self.SensorClass(address)
                _LOGGER.info(
                    "Initialized %s temperature sensor at address %s",
                    self.SensorClass.__name__,
                    address
                )
            except (ValueError, RuntimeError) as err:
                raise I2CError(
                    f"Failed to initialize {self.__class__.__name__} "
                    f"at address {address}: {err}"
                )

    @property
    def temperature(self) -> float | None:
        """Read temperature from hardware sensor.
        
        Returns:
            Temperature value or None if unavailable
        """
        if self._pct and hasattr(self._pct, 'temperature'):
            try:
                return self._pct.temperature
            except Exception as err:
                _LOGGER.error("Error reading temperature from %s: %s", self.id, err)
                return None
        return None

    async def async_update(self, timestamp: float) -> None:
        """Fetch temperature and publish to MQTT.
        
        This method reads the temperature from the hardware sensor,
        applies filters, and publishes the result.
        
        Args:
            timestamp: Current timestamp
        """
        try:
            _temp = self.temperature
            
            if _temp is None:
                _LOGGER.warning("Temperature reading returned None for sensor %s", self.id)
                return
                
            _LOGGER.debug(
                "Fetched temperature %s°C for sensor %s. Applying filters.",
                _temp,
                self.id
            )
            
            # Apply filters
            _temp = self._apply_filters(value=_temp)
            
            if _temp is None:
                _LOGGER.debug("Filtered temperature is None for sensor %s", self.id)
                return
                
            # Update state
            self._state = _temp
            
            # Publish to MQTT and EventBus
            self._publish_state(timestamp=timestamp)
            
        except RuntimeError as err:
            _LOGGER.error("Sensor error for %s: %s", self.id, err)
        except Exception as err:
            _LOGGER.error("Unexpected error updating %s: %s", self.id, err)

