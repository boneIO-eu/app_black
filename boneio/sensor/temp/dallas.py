"""Dallas temp sensor."""

import asyncio
from datetime import timedelta

# from datetime import timedelta
from adafruit_ds18x20 import DS18X20
from adafruit_onewire.bus import OneWireAddress

from boneio.const import SENSOR, TEMPERATURE
from boneio.helper import BasicMqtt
from boneio.helper.events import utcnow
from boneio.helper.exceptions import OneWireError
from boneio.helper.timeperiod import TimePeriod

from . import TempSensor


class DallasSensor(TempSensor):
    DefaultName = TEMPERATURE
    SensorClass = DS18X20

    def __init__(
        self,
        bus,
        update_interval: TimePeriod,
        address: OneWireAddress,
        id: str = DefaultName,
        **kwargs
    ):
        """Initialize Temp class."""
        self._update_interval = update_interval or TimePeriod(seconds=60)
        self._loop = asyncio.get_event_loop()
        BasicMqtt.__init__(self, id=id, topic_type=SENSOR, **kwargs)
        try:
            self._pct = DS18X20(bus=bus, address=address)
            self._unsub_refresh = None
            self._schedule_refresh(utcnow() + timedelta(seconds=2))
        except ValueError as err:
            raise OneWireError(err)
