"""Manage LM75 sensor."""

import asyncio
from adafruit_pct2075 import PCT2075
from boneio.const import STATE, SENSOR, LM75

from boneio.helper.exceptions import I2CError
from boneio.helper import BasicMqtt


class LM75Sensor(BasicMqtt):
    """Represent LM75 sensor in BoneIO."""

    def __init__(self, i2c, address, id: str = LM75, **kwargs):
        """Initialize LM75 class."""
        super().__init__(id=id, topic_type=SENSOR, **kwargs)
        try:
            self._pct = PCT2075(i2c_bus=i2c, address=address)
        except ValueError as err:
            raise I2CError(err)

    @property
    def state(self):
        """Give rounded value of temperature."""
        return round(self._pct.temperature, 2)

    async def send_state(self):
        """Fetch temperature periodically and send to MQTT."""
        while True:
            self._send_message(
                topic=self._send_topic,
                payload={STATE: self.state},
            )
            await asyncio.sleep(60)
