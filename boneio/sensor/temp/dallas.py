"""Dallas temp sensor."""

import asyncio
import logging

from w1thermsensor import (
    NoSensorFoundError,
    SensorNotReadyError,
    W1ThermSensorError,
    W1ThermSensor
)

from boneio.const import SENSOR, STATE, TEMPERATURE
from boneio.helper import AsyncUpdater, BasicMqtt
from boneio.helper.exceptions import OneWireError

from . import TempSensor

_LOGGER = logging.getLogger(__name__)


class DallasSensor(TempSensor, AsyncUpdater):
    """Unified Dallas temperature sensor class using w1thermsensor."""
    DefaultName = TEMPERATURE
    SensorClass = W1ThermSensor

    def __init__(
        self,
        address: str,  # Sensor ID as string
        id: str = DefaultName,
        filters: list = ["round(x, 2)"],
        **kwargs,
    ):
        """Initialize Dallas temperature sensor.
        
        Args:
            address: Sensor ID (e.g. '28-0000098c7df0')
            id: Sensor identifier for MQTT
            filters: List of filters to apply to readings
            **kwargs: Additional arguments passed to parent classes
        """
        self._loop = asyncio.get_event_loop()
        BasicMqtt.__init__(self, id=id, topic_type=SENSOR, **kwargs)
        self._filters = filters
        self._state = None
        try:
            self._pct = self.SensorClass(sensor_id=address)
            # Perform a first read to check if sensor is available
            self._pct.get_temperature()
        except (ValueError, W1ThermSensorError) as err:
            raise OneWireError(f"Error initializing sensor {address}: {err}")
        AsyncUpdater.__init__(self, **kwargs)



    async def async_update(self, timestamp: float) -> None:
        """Update sensor reading asynchronously.
        
        Args:
            timestamp: Current timestamp for the reading
        """
        try:
            # Run blocking get_temperature in executor to avoid blocking the event loop
            _temp = await self._loop.run_in_executor(None, self._pct.get_temperature)
            _LOGGER.debug("Fetched temperature %s for sensor %s. Applying filters.", _temp, self.id)
            _temp = self._apply_filters(value=_temp)
            if _temp is None:
                return
            self._state = _temp
            self._timestamp = timestamp
            self._message_bus.send_message(
                topic=self._send_topic,
                payload={STATE: self._state},
            )
        except (SensorNotReadyError, NoSensorFoundError, W1ThermSensorError) as err:
            _LOGGER.error("Failed to read sensor %s: %s", self.id, err)
