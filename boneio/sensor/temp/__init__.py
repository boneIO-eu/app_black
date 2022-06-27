"""Manage BoneIO onboard temp sensors."""

import asyncio
from datetime import datetime, timedelta
from typing import Optional

from boneio.const import SENSOR, STATE, TEMPERATURE
from boneio.helper import BasicMqtt
from boneio.helper.events import async_track_point_in_time, utcnow
from boneio.helper.exceptions import I2CError
from boneio.helper.timeperiod import TimePeriod
from boneio.helper.util import callback


class TempSensor(BasicMqtt):
    """Represent Temp sensor in BoneIO."""

    SensorClass = None
    DefaultName = TEMPERATURE

    def __init__(
        self,
        i2c,
        address: str,
        id: str = DefaultName,
        update_interval: TimePeriod = TimePeriod(seconds=60),
        **kwargs
    ):
        """Initialize Temp class."""
        super().__init__(id=id, topic_type=SENSOR, **kwargs)
        self._update_interval = update_interval
        self._loop = asyncio.get_event_loop()
        try:
            self._pct = self.SensorClass(i2c_bus=i2c, address=address)
            self._unsub_refresh = None
            self._schedule_refresh(utcnow() + timedelta(seconds=2))
        except ValueError as err:
            raise I2CError(err)

    @property
    def state(self):
        """Give rounded value of temperature."""
        return round(self._pct.temperature, 2)

    def _schedule_refresh(self, update_time: Optional[datetime] = None):
        if self._unsub_refresh:
            self._unsub_refresh()
            self._unsub_refresh = None
        if not update_time:
            update_time = utcnow() + self._update_interval.as_timedelta
        self._unsub_refresh = async_track_point_in_time(
            loop=self._loop,
            action=self._refresh,
            point_in_time=update_time,
        )

    @callback
    def _refresh(self, time: datetime):
        if self._unsub_refresh:
            self._unsub_refresh()
            self._unsub_refresh = None

        self.send_state()
        self._schedule_refresh()

    def send_state(self):
        """Fetch temperature periodically and send to MQTT."""
        self._send_message(
            topic=self._send_topic,
            payload={STATE: self.state},
        )
