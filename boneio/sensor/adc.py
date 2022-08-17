"""ADC GPIO BBB sensor."""
import logging

from boneio.const import SENSOR
from boneio.helper import BasicMqtt, AsyncUpdater

try:
    import Adafruit_BBIO.ADC as ADC
except ModuleNotFoundError:

    class ADC:
        def __init__(self):
            pass

    pass

_LOGGER = logging.getLogger(__name__)


def initialize_adc():
    ADC.setup()


class GpioADCSensor(BasicMqtt, AsyncUpdater):
    """Represent Gpio ADC sensor."""

    def __init__(self, pin: str, **kwargs) -> None:
        """Setup GPIO ADC Sensor"""
        super().__init__(topic_type=SENSOR, **kwargs)
        self._pin = pin
        AsyncUpdater.__init__(self, **kwargs)
        _LOGGER.debug("Configured sensor pin %s", self._pin)

    @property
    def state(self):
        """Give rounded value of temperature."""
        return round(ADC.read(self._pin) * 1.8, 2)

    def update(self):
        """Fetch temperature periodically and send to MQTT."""
        self._send_message(
            topic=self._send_topic,
            payload=self.state,
        )
