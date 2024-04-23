"""GpioInputBinarySensorNew to receive signals."""
import logging
from boneio.const import PRESSED, RELEASED, BOTH
from boneio.helper import GpioBaseClass
from boneio.helper.gpio import add_event_callback, add_event_detect

_LOGGER = logging.getLogger(__name__)


class GpioInputBinarySensorNew(GpioBaseClass):
    """Represent Gpio sensor on input boards."""

    def __init__(self, **kwargs) -> None:
        """Setup GPIO Input Button"""
        super().__init__(**kwargs)
        self._state = self.is_pressed
        self._click_type = (
            (RELEASED, PRESSED)
            if kwargs.get("inverted", False)
            else (PRESSED, RELEASED)
        )
        _LOGGER.debug("Configured sensor pin %s", self._pin)
        add_event_detect(pin=self._pin, edge=BOTH)
        add_event_callback(pin=self._pin, callback=self.check_state)

    def check_state(self, _) -> None:
        state = self.is_pressed
        if state == self._state:
            return
        self._state = state
        click_type = self._click_type[0] if state else self._click_type[1]
        _LOGGER.debug("%s event on pin %s - %s", click_type, self._pin, self.name)
        self.press_callback(click_type=click_type, duration=None)
