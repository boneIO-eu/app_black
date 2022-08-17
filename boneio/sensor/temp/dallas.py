"""Dallas temp sensor."""

import asyncio
from datetime import datetime

from adafruit_ds18x20 import DS18X20

from boneio.const import SENSOR, STATE, TEMPERATURE
from boneio.helper import BasicMqtt, PeriodicUpdater
from boneio.helper.exceptions import OneWireError
from boneio.helper.onewire import OneWireBus, AsyncBoneIOW1ThermSensor, OneWireAddress

from . import TempSensor


class DallasSensorDS2482(TempSensor, PeriodicUpdater):
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
        PeriodicUpdater.__init__(self, **kwargs)


class DallasSensorW1(TempSensor, PeriodicUpdater):
    DefaultName = TEMPERATURE
    SensorClass = AsyncBoneIOW1ThermSensor

    def __init__(
        self,
        address: OneWireAddress,
        id: str = DefaultName,
        **kwargs,
    ):
        """Initialize Temp class."""
        self._loop = asyncio.get_event_loop()
        BasicMqtt.__init__(self, id=id, topic_type=SENSOR, **kwargs)
        try:
            self._pct = AsyncBoneIOW1ThermSensor(sensor_id=address)
        except ValueError as err:
            raise OneWireError(err)
        PeriodicUpdater.__init__(self, **kwargs)

    async def async_update(self, time: datetime):
        self._state = await self._pct.get_temperature()
        self._send_message(
            topic=self._send_topic,
            payload={STATE: self._state},
        )
