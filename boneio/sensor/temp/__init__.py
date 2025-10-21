"""Manage BoneIO onboard temp sensors."""

from __future__ import annotations

import asyncio
import logging

from boneio.const import SENSOR, STATE, TEMPERATURE
from boneio.helper import AsyncUpdater, BasicMqtt
from boneio.helper.exceptions import I2CError
from boneio.core.utils import Filter
from boneio.models import SensorState

_LOGGER = logging.getLogger(__name__)


class TempSensor(BasicMqtt, AsyncUpdater, Filter):
    """Represent Temp sensor in BoneIO."""

    SensorClass = None
    DefaultName = TEMPERATURE

    def __init__(
        self,
        i2c,
        address: str,
        id: str = DefaultName,
        filters: list = ["round(x, 2)"],
        unit_of_measurement: str = "°C",
        **kwargs,
    ):
        """Initialize Temp class."""
        self._loop = asyncio.get_event_loop()
        
        # Debug log the kwargs
        _LOGGER.debug("TempSensor initialization kwargs: %s", kwargs)
        
        # Initialize BasicMqtt first
        BasicMqtt.__init__(self, id=id, topic_type=SENSOR, **kwargs)
        
        # Get required parameters for AsyncUpdater
        manager = kwargs.get('manager')
        update_interval = kwargs.get('update_interval')
        _LOGGER.debug("Initializing AsyncUpdater with manager: %s, update_interval: %s", manager, update_interval)
        
        # Initialize AsyncUpdater next
        AsyncUpdater.__init__(self, manager=manager, update_interval=update_interval)
        
        # Initialize Filter
        Filter.__init__(self)
        
        self._filters = filters
        self._unit_of_measurement = unit_of_measurement
        self._state: float | None = None
        try:
            if self.SensorClass:
                self._pct = self.SensorClass(i2c_bus=i2c, address=address)
        except ValueError as err:
            raise I2CError(err)

    @property
    def state(self) -> float:
        """Give rounded value of temperature."""
        return self._state if self._state is not None else -1

    @property
    def unit_of_measurement(self) -> str:
        return self._unit_of_measurement

    async def async_update(self, timestamp: float) -> None:
        """Fetch temperature periodically and send to MQTT."""
        try:
            _temp = self._pct.temperature
            _LOGGER.debug("Fetched temperature %s. Applying filters.", _temp)
            _temp = self._apply_filters(value=self._pct.temperature)
        except RuntimeError as err:
            _temp = None
            _LOGGER.error("Sensor error: %s %s", err, self.id)
        if _temp is None:
            return
        self._state = _temp
        self._timestamp = timestamp
        self.manager.event_bus.trigger_event({
            "event_type": "sensor",
            "entity_id": self.id,
            "event_state": SensorState(
                id=self.id,
                name=self.name,
                state=self.state,
                unit=self.unit_of_measurement,
                timestamp=self.last_timestamp,
            ),
        })
        self._message_bus.send_message(
            topic=self._send_topic,
            payload={STATE: self._state},
        )
