"""ADC GPIO BBB sensor."""
import logging
import asyncio

from boneio.const import SENSOR
from boneio.helper import BasicMqtt
import Adafruit_BBIO.ADC as ADC

_LOGGER = logging.getLogger(__name__)


def initialize_adc():
    ADC.setup()


class GpioADCSensor(BasicMqtt):
    """Represent Gpio ADC sensor."""

    def __init__(self, pin: str, update_interval: int = 60, **kwargs) -> None:
        """Setup GPIO ADC Sensor"""
        super().__init__(topic_type=SENSOR, **kwargs)
        self._pin = pin
        self._update_interval = update_interval
        _LOGGER.debug("Configured sensor pin %s", self._pin)

    @property
    def state(self):
        """Give rounded value of temperature."""
        return round(ADC.read(self._pin) * 1.8, 2)

    async def send_state(self):
        """Fetch temperature periodically and send to MQTT."""
        while True:
            self._send_message(
                topic=self._send_topic,
                payload=self.state,
            )
            await asyncio.sleep(self._update_interval)
