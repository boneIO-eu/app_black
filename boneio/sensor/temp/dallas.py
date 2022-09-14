"""Dallas temp sensor."""

import asyncio
import logging
from datetime import datetime

from adafruit_ds18x20 import DS18X20
from w1thermsensor import SensorNotReadyError

from boneio.const import SENSOR, STATE, TEMPERATURE
from boneio.helper import AsyncUpdater, BasicMqtt
from boneio.helper.exceptions import OneWireError
from boneio.helper.onewire import AsyncBoneIOW1ThermSensor, OneWireAddress, OneWireBus

from . import TempSensor

_LOGGER = logging.getLogger(__name__)


class DallasSensorDS2482(TempSensor, AsyncUpdater):
    DefaultName = TEMPERATURE
    SensorClass = DS18X20

    def __init__(
        self,
        bus: OneWireBus,
        address: OneWireAddress,
        id: str = DefaultName,
        **kwargs,
    ):
        """Initialize Temp class."""
        self._loop = asyncio.get_event_loop()
        BasicMqtt.__init__(self, id=id, topic_type=SENSOR, **kwargs)
        try:
            self._pct = DS18X20(bus=bus, address=address)
            self._state = None
        except ValueError as err:
            raise OneWireError(err)
        AsyncUpdater.__init__(self, **kwargs)


class DallasSensorW1(TempSensor, AsyncUpdater):
    DefaultName = TEMPERATURE
    SensorClass = AsyncBoneIOW1ThermSensor

    def __init__(
        self,
        address: OneWireAddress,
        id: str = DefaultName,
        filters: list = ["round(x, 2)"],
        **kwargs,
    ):
        """Initialize Temp class."""
        self._loop = asyncio.get_event_loop()
        BasicMqtt.__init__(self, id=id, topic_type=SENSOR, **kwargs)
        self._filters = filters
        try:
            self._pct = AsyncBoneIOW1ThermSensor(sensor_id=address)
        except ValueError as err:
            raise OneWireError(err)
        AsyncUpdater.__init__(self, **kwargs)

    async def async_update(self, time: datetime) -> None:
        try:
            _temp = await self._pct.get_temperature()
            _LOGGER.debug("Fetched temperature %s. Applying filters.", _temp)
            _temp = self._apply_filters(value=_temp)
            if _temp is None:
                return
            self._state = _temp
            self._send_message(
                topic=self._send_topic,
                payload={STATE: self._state},
            )
        except SensorNotReadyError as err:
            _LOGGER.error("Sensor not ready, can't update %s", err)
