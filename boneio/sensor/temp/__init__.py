"""Manage BoneIO onboard temp sensors."""

import asyncio
from adafruit_pct2075 import PCT2075
from adafruit_mcp9808 import MCP9808
from boneio.const import STATE, SENSOR, LM75, MCP_TEMP_9808, TEMPERATURE

from boneio.helper.exceptions import I2CError
from boneio.helper import BasicMqtt


class TempSensor(BasicMqtt):
    """Represent Temp sensor in BoneIO."""

    SensorClass = None
    DefaultName = TEMPERATURE

    def __init__(self, i2c, address, id: str = DefaultName, **kwargs):
        """Initialize Temp class."""
        super().__init__(id=id, topic_type=SENSOR, **kwargs)
        try:
            self._pct = self.SensorClass(i2c_bus=i2c, address=address)
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


class LM75Sensor(TempSensor):
    """Represent LM75 sensor in BoneIO."""

    SensorClass = PCT2075
    DefaultName = LM75


class MCP9808Sensor(TempSensor):
    """Represent MCP9808 sensor in BoneIO."""

    SensorClass = MCP9808
    DefaultName = MCP_TEMP_9808
