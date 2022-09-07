"""ADC GPIO BBB sensor."""
from datetime import datetime
import logging

from boneio.const import SENSOR
from boneio.helper import BasicMqtt, AsyncUpdater
from boneio.helper.filter import Filter

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


class GpioADCSensor(BasicMqtt, AsyncUpdater, Filter):
    """Represent Gpio ADC sensor."""

    def __init__(self, pin: str, **kwargs) -> None:
        """Setup GPIO ADC Sensor"""
        super().__init__(topic_type=SENSOR, **kwargs)
        self._pin = pin
        self._state = None
        AsyncUpdater.__init__(self, **kwargs)
        _LOGGER.debug("Configured sensor pin %s", self._pin)

    @property
    def state(self) -> float:
        """Give rounded value of temperature."""
        return self._state

    def update(self, time: datetime) -> None:
        """Fetch temperature periodically and send to MQTT."""
        _state = self._apply_filters(value=ADC.read(self._pin))
        if not _state:
            return
        self._state = _state
        self._send_message(
            topic=self._send_topic,
            payload=self.state,
        )
