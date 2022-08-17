"""Manage BoneIO onboard temp sensors."""

import asyncio

from boneio.const import SENSOR, STATE, TEMPERATURE
from boneio.helper import BasicMqtt, AsyncUpdater
from boneio.helper.exceptions import I2CError


class TempSensor(BasicMqtt, AsyncUpdater):
    """Represent Temp sensor in BoneIO."""

    SensorClass = None
    DefaultName = TEMPERATURE

    def __init__(self, i2c, address: str, id: str = DefaultName, **kwargs):
        """Initialize Temp class."""
        super().__init__(id=id, topic_type=SENSOR, **kwargs)
        self._loop = asyncio.get_event_loop()
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

    def update(self):
        """Fetch temperature periodically and send to MQTT."""
        self._state = round(self._pct.temperature, 2)
        self._send_message(
            topic=self._send_topic,
            payload={STATE: self._state},
        )
