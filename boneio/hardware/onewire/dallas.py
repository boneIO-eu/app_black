"""Dallas 1-Wire temperature sensor driver.

This module provides support for Dallas/Maxim 1-Wire temperature sensors
like DS18B20, DS18S20, DS1822, etc. using the w1thermsensor library.
"""

from __future__ import annotations

import logging

from boneio.const import TEMPERATURE
from boneio.exceptions import OneWireError
from boneio.hardware.sensor.temperature.base import TempSensor

_LOGGER = logging.getLogger(__name__)


class DallasSensor(TempSensor):
    """Dallas 1-Wire temperature sensor.
    
    This class provides support for Dallas/Maxim 1-Wire temperature sensors:
    - DS18B20 (most common)
    - DS18S20
    - DS1822
    - DS28EA00
    - MAX31850K
    
    The sensor uses the Linux kernel w1-gpio and w1-therm modules for communication.
    w1thermsensor library is imported lazily to avoid kernel module loading at import time.
    
    Args:
        address: Sensor ID as string (e.g., '28-0000098c7df0')
        id: Sensor identifier for MQTT
        filters: List of filter expressions to apply to readings
        **kwargs: Additional arguments (manager, update_interval, etc.)
        
    Example:
        >>> sensor = DallasSensor(
        ...     address='28-0000098c7df0',
        ...     id='living_room_temp',
        ...     filters=[{'round': 2}],
        ...     manager=manager,
        ...     update_interval=TimePeriod(seconds=60)
        ... )
    """
    
    DefaultName = TEMPERATURE

    def __init__(
        self,
        address: str,
        id: str | None = None,
        filters: list | None = None,
        **kwargs,
    ):
        """Initialize Dallas temperature sensor.
        
        Args:
            address: Sensor ID (e.g. '28-0000098c7df0')
            id: Sensor identifier for MQTT
            filters: List of filters to apply to readings
            **kwargs: Additional arguments passed to parent classes
            
        Raises:
            OneWireError: If sensor cannot be initialized or is not found
        """
        # Import w1thermsensor locally to avoid kernel module loading at import time
        from w1thermsensor import W1ThermSensor, W1ThermSensorError
        
        # Set default filters
        if filters is None:
            filters = [{"round": 2}]
        
        # Initialize TempSensor (which doesn't use i2c parameter for Dallas)
        # We pass None as i2c since Dallas uses 1-Wire
        try:
            super().__init__(
                i2c=None,
                address=address,
                id=id or self.DefaultName,
                filters=filters,
                **kwargs,
            )
        except Exception:
            # TempSensor will try to initialize with SensorClass if set
            # We need to handle Dallas specially since it uses different API
            pass
        
        # Store address for later reference
        self._address = address
        
        # Initialize Dallas sensor manually
        try:
            self._pct = W1ThermSensor(sensor_id=address)
            # Perform a first read to check if sensor is available
            self._pct.get_temperature()
            _LOGGER.info("Dallas sensor %s initialized successfully", address)
        except (ValueError, W1ThermSensorError) as err:
            raise OneWireError(f"Error initializing sensor {address}: {err}")

    @property
    def address(self) -> str:
        """Get sensor address.
        
        Returns:
            Sensor address string (e.g., '28-0000098c7df0')
        """
        return self._address

    @property
    def temperature(self) -> float | None:
        """Read temperature from Dallas sensor.
        
        This overrides the TempSensor.temperature property to handle
        Dallas-specific temperature reading with executor to avoid blocking.
        
        Returns:
            Temperature value or None if unavailable
        """
        if self._pct:
            try:
                # Note: get_temperature() is blocking, but we're in a property
                # The async_update method will handle this properly
                return self._pct.get_temperature()
            except Exception as err:
                _LOGGER.error("Error reading temperature from %s: %s", self.id, err)
                return None
        return None

    async def async_update(self, timestamp: float) -> None:
        """Update sensor reading asynchronously.
        
        This method reads the temperature from the Dallas sensor and publishes
        it to MQTT. The blocking get_temperature() call is run in an executor
        to avoid blocking the event loop.
        
        Args:
            timestamp: Current timestamp for the reading
        """
        try:
            # Run blocking get_temperature in executor to avoid blocking the event loop
            _temp = await self._loop.run_in_executor(None, self._pct.get_temperature)
            _LOGGER.debug("Fetched temperature %s°C for sensor %s. Applying filters.", _temp, self.id)
            
            if _temp is None:
                _LOGGER.warning("Temperature reading returned None for sensor %s", self.id)
                return
            
            # Apply filters
            _temp = self._apply_filters(value=_temp)
            if _temp is None:
                _LOGGER.debug("Filtered temperature is None for sensor %s", self.id)
                return
            
            # Update state
            self._state = _temp
            
            # Publish to MQTT and EventBus
            self._publish_state(timestamp=timestamp)
            
        except Exception as err:
            # Import exceptions locally to avoid kernel module loading at import time
            from w1thermsensor import (
                NoSensorFoundError,
                SensorNotReadyError,
                W1ThermSensorError,
            )
            
            if isinstance(err, (SensorNotReadyError, NoSensorFoundError, W1ThermSensorError)):
                _LOGGER.error("Failed to read sensor %s: %s", self.id, err)
            else:
                _LOGGER.error("Unexpected error reading sensor %s: %s", self.id, err)
