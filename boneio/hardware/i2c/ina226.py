"""INA226 power monitoring sensor driver.

This module provides support for INA226 current/voltage/power monitoring sensor.
The INA226 is a high-side/low-side current shunt and power monitor with I2C
interface, used on boneIO Black v1.0 boards (replacing INA219 from v0.8).

Key improvements over INA219:
- Bus voltage range: 0–36V (vs 0–26V)
- Bus voltage resolution: 1.25 mV (vs 4 mV)
- Internal power register (no need for V×I computation)
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime

from boneio.const import SENSOR, STATE
from boneio.core.messaging import BasicMqtt
from boneio.core.utils import AsyncUpdater, Filter
from boneio.exceptions import I2CError
from boneio.hardware.i2c.ina226_driver import INA226_I2C
from boneio.models import SensorState
from boneio.models.events import SensorEvent

_LOGGER = logging.getLogger(__name__)

# Unit conversion for different measurement types
UNIT_CONVERTER = {"current": "A", "power": "W", "voltage": "V"}


class INA226Sensor(BasicMqtt, Filter):
    """Single measurement from INA226 sensor.

    This class represents one measurement type (current, voltage, or power)
    from an INA226 sensor. Multiple INA226Sensor instances are typically
    managed by a single INA226 coordinator.

    Args:
        device_class: Type of measurement ('current', 'voltage', or 'power')
        filters: List of filter expressions to apply
        state: Initial state value
        **kwargs: Additional arguments (name, id, message_bus, etc.)
    """

    def __init__(
        self, device_class: str, filters: list, state: float | None, **kwargs
    ) -> None:
        """Initialize INA226 sensor."""
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


class INA226(AsyncUpdater):
    """INA226 power monitoring sensor coordinator.

    This class manages an INA226 sensor and its multiple measurement types
    (current, voltage, power). It periodically reads values from the sensor
    and updates individual INA226Sensor instances.

    Features:
    - High-side/low-side current sensing
    - 0–36V bus voltage measurement (1.25 mV resolution)
    - Internal power calculation (more accurate than V×I)
    - I2C interface (address: 0x40–0x4F)
    - 16-bit ADC with configurable averaging

    Args:
        address: I2C address of the sensor (default: 0x40)
        id: Sensor identifier
        sensors: List of sensor configurations (device_class, id, filters)
        r_shunt: Shunt resistor value in Ohms (default: 0.05 for boneIO v1.0)
        max_current: Maximum expected current in A (default: 1.5)
        **kwargs: Additional arguments (manager, update_interval, etc.)
    """

    def __init__(
        self,
        address: int,
        id: str,
        sensors: list[dict] | None = None,
        r_shunt: float = 0.05,
        max_current: float = 1.5,
        **kwargs,
    ) -> None:
        """Initialize INA226 sensor coordinator.

        Raises:
            I2CError: If sensor is not found or communication fails
        """
        if sensors is None:
            sensors = []
        self._loop = asyncio.get_event_loop()
        self._sensors: dict[str, INA226Sensor] = {}
        self._id = id

        # Initialize hardware sensor with error handling
        try:
            self._ina = INA226_I2C(
                address=address,
                r_shunt=r_shunt,
                max_current=max_current,
            )
        except OSError as err:
            raise I2CError(
                f"Failed to initialize INA226 at address 0x{address:02X}: {err}"
            ) from err

        # Create individual sensor instances for each measurement type
        for sensor in sensors:
            _name = sensor["id"]
            _id = f"{id}{_name.replace(' ', '')}"
            self._sensors[sensor["device_class"]] = INA226Sensor(
                device_class=sensor["device_class"],
                filters=sensor.get("filters", []),
                state=None,
                name=_name,
                id=_id,
                **kwargs,
            )

        AsyncUpdater.__init__(self, **kwargs)
        _LOGGER.info(
            "Configured INA226 on address 0x%02X with %d sensors "
            "(R_SHUNT=%.3fΩ, I_max=%.1fA)",
            address, len(self._sensors), r_shunt, max_current,
        )

    @property
    def id(self) -> str:
        """Get sensor coordinator ID.

        Returns:
            Coordinator identifier string
        """
        return self._id

    @property
    def sensors(self) -> dict[str, INA226Sensor]:
        """Get dictionary of managed sensors.

        Returns:
            Dictionary mapping device_class to INA226Sensor instances
        """
        return self._sensors

    async def async_update(self, timestamp: datetime) -> None:
        """Read sensor values and update all managed sensors.

        This method is called periodically by AsyncUpdater. It reads
        current, voltage, and power from the INA226 and updates the
        corresponding sensor instances.

        Args:
            timestamp: Current timestamp
        """
        for k, sensor in self._sensors.items():
            try:
                value = getattr(self._ina, k)
                _LOGGER.debug(
                    "Fetched INA226 value: %s = %s %s",
                    k, value, sensor.unit_of_measurement,
                )

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
                _LOGGER.error("Error reading INA226 %s: %s", k, err)
