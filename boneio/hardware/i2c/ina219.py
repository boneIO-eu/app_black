"""INA219 power monitoring sensor driver.

This module provides support for INA219 current/voltage/power monitoring sensor.
The INA219 is a high-side current shunt and power monitor with I2C interface.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime

from boneio.const import SENSOR, STATE
from boneio.core.messaging import BasicMqtt
from boneio.core.utils import AsyncUpdater, Filter
from boneio.hardware.i2c.ina219_driver import INA219_I2C
from boneio.models import SensorState
from boneio.models.events import SensorEvent

_LOGGER = logging.getLogger(__name__)

# Unit conversion for different measurement types
UNIT_CONVERTER = {"current": "A", "power": "W", "voltage": "V"}


class INA219Sensor(BasicMqtt, Filter):
    """Single measurement from INA219 sensor.
    
    This class represents one measurement type (current, voltage, or power)
    from an INA219 sensor. Multiple INA219Sensor instances are typically
    managed by a single INA219 coordinator.
    
    Args:
        device_class: Type of measurement ('current', 'voltage', or 'power')
        filters: List of filter expressions to apply
        state: Initial state value
        **kwargs: Additional arguments (name, id, message_bus, etc.)
        
    Example:
        >>> sensor = INA219Sensor(
        ...     device_class='current',
        ...     filters=['round(x, 3)'],
        ...     state=None,
        ...     name='Battery Current',
        ...     id='battery_current',
        ...     message_bus=message_bus
        ... )
    """

    def __init__(
        self, device_class: str, filters: list, state: float | None, **kwargs
    ) -> None:
        """Initialize INA219 sensor."""
        super().__init__(topic_type=SENSOR, **kwargs)
        self._unit_of_measurement = UNIT_CONVERTER[device_class]
        self._device_class = device_class
        self._filters = filters
        self._raw_state = state
        self._timestamp = time.time()
        self._state = (
            self._apply_filters(value=self._raw_state) if self._raw_state else None
        )

    @property
    def raw_state(self) -> float | None:
        """Get raw unfiltered state value.
        
        Returns:
            Raw measurement value or None
        """
        return self._raw_state

    @raw_state.setter
    def raw_state(self, value: float) -> None:
        """Set raw state value.
        
        Args:
            value: New raw measurement value
        """
        self._raw_state = value

    @property
    def state(self) -> float | None:
        """Get filtered state value.
        
        Returns:
            Filtered measurement value or None
        """
        return self._state

    @property
    def device_class(self) -> str:
        """Get device class (measurement type).
        
        Returns:
            Device class string ('current', 'voltage', or 'power')
        """
        return self._device_class

    @property
    def unit_of_measurement(self) -> str:
        """Get unit of measurement.
        
        Returns:
            Unit string ('A', 'V', or 'W')
        """
        return self._unit_of_measurement

    @property
    def last_timestamp(self) -> float:
        """Get timestamp of last update.
        
        Returns:
            Unix timestamp
        """
        return self._timestamp

    def update(self, timestamp: float) -> None:
        """Update sensor state and publish to MQTT.
        
        Args:
            timestamp: Current timestamp
        """
        _state = self._apply_filters(value=self._raw_state) if self._raw_state else None
        if not _state:
            return
        self._state = _state
        self._timestamp = timestamp
        self._message_bus.send_message(
            topic=self._send_topic,
            payload={STATE: self.state},
        )


class INA219(AsyncUpdater):
    """INA219 power monitoring sensor coordinator.
    
    This class manages an INA219 sensor and its multiple measurement types
    (current, voltage, power). It periodically reads values from the sensor
    and updates individual INA219Sensor instances.
    
    Features:
    - High-side current sensing
    - 0-26V bus voltage measurement
    - Calculated power measurement
    - I2C interface (address: 0x40-0x4F)
    - 12-bit ADC resolution
    
    Args:
        address: I2C address of the sensor (default: 0x40)
        id: Sensor identifier
        sensors: List of sensor configurations (device_class, id, filters)
        **kwargs: Additional arguments (manager, update_interval, etc.)
        
    Example:
        >>> ina219 = INA219(
        ...     address=0x40,
        ...     id='battery',
        ...     sensors=[
        ...         {'device_class': 'current', 'id': 'Current', 'filters': ['round(x, 3)']},
        ...         {'device_class': 'voltage', 'id': 'Voltage', 'filters': ['round(x, 2)']},
        ...         {'device_class': 'power', 'id': 'Power', 'filters': ['round(x, 2)']},
        ...     ],
        ...     manager=manager,
        ...     update_interval=TimePeriod(seconds=10)
        ... )
    """

    def __init__(
        self, address: int, id: str, sensors: list[dict] = [], **kwargs
    ) -> None:
        """Initialize INA219 sensor coordinator."""
        self._loop = asyncio.get_event_loop()
        self._ina_219 = INA219_I2C(address=address)
        self._sensors = {}
        self._id = id
        
        # Create individual sensor instances for each measurement type
        for sensor in sensors:
            _name = sensor["id"]
            _id = f"{id}{_name.replace(' ', '')}"
            self._sensors[sensor["device_class"]] = INA219Sensor(
                device_class=sensor["device_class"],
                filters=sensor.get("filters", []),
                state=None,
                name=_name,
                id=_id,
                **kwargs,
            )
        
        AsyncUpdater.__init__(self, **kwargs)
        _LOGGER.info("Configured INA219 on address 0x%02X with %d sensors", address, len(self._sensors))

    @property
    def id(self) -> str:
        """Get sensor coordinator ID.
        
        Returns:
            Coordinator identifier string
        """
        return self._id

    @property
    def sensors(self) -> dict:
        """Get dictionary of managed sensors.
        
        Returns:
            Dictionary mapping device_class to INA219Sensor instances
        """
        return self._sensors

    async def async_update(self, timestamp: datetime) -> None:
        """Read sensor values and update all managed sensors.
        
        This method is called periodically by AsyncUpdater. It reads
        current, voltage, and power from the INA219 and updates the
        corresponding sensor instances.
        
        Args:
            timestamp: Current timestamp
        """
        for k, sensor in self._sensors.items():
            try:
                value = getattr(self._ina_219, k)
                _LOGGER.debug("Fetched INA219 value: %s = %s %s", k, value, sensor.unit_of_measurement)
                
                if sensor.raw_state != value:
                    sensor.raw_state = value
                    sensor.update(timestamp=timestamp)
                    
                    # Trigger event on EventBus
                    self.manager.event_bus.trigger_event(SensorEvent(
                        entity_id=sensor.id,
                        state=SensorState(
                            id=sensor.id,
                            name=sensor.name,
                            state=sensor.state,
                            unit=sensor.unit_of_measurement,
                            timestamp=sensor.last_timestamp,
                        ),
                    ))
            except Exception as err:
                _LOGGER.error("Error reading INA219 %s: %s", k, err)
