"""Manage BoneIO onboard temp sensors."""

import asyncio
import logging
from datetime import datetime

from boneio.const import SENSOR, STATE, TEMPERATURE
from boneio.helper import BasicMqtt, AsyncUpdater
from boneio.helper.exceptions import I2CError
from boneio.helper.filter import Filter

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
        **kwargs
    ):
        """Initialize Temp class."""
        super().__init__(id=id, topic_type=SENSOR, **kwargs)
        self._loop = asyncio.get_event_loop()
        self._filters = filters
        try:
            self._pct = self.SensorClass(i2c_bus=i2c, address=address)
            self._state: float | None = None
        except ValueError as err:
            raise I2CError(err)
        AsyncUpdater.__init__(self, **kwargs)

    @property
    def state(self) -> float:
        """Give rounded value of temperature."""
        return self._state

    def update(self, time: datetime) -> None:
        """Fetch temperature periodically and send to MQTT."""
        _temp = self._pct.temperature
        _LOGGER.debug("Fetched temperature %s. Applying filters.", _temp)
        _temp = self._apply_filters(value=self._pct.temperature)
        if _temp is None:
            return
        self._state = _temp
        self._send_message(
            topic=self._send_topic,
            payload={STATE: self._state},
        )
