"""GpioInputBinarySensor to receive signals."""
import logging
import asyncio
from boneio.const import PRESSED, RELEASED
from boneio.helper import GpioBaseClass

_LOGGER = logging.getLogger(__name__)


class GpioInputBinarySensor(GpioBaseClass):
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
        asyncio.create_task(self._run())

    async def _run(self) -> None:
        while True:
            self.check_state(state=self.is_pressed)
            await asyncio.sleep(self._bounce_time)

    def check_state(self, state: bool) -> None:
        if state == self._state:
            return
        self._state = state
        click_type = self._click_type[0] if state else self._click_type[1]
        _LOGGER.debug("%s event on pin %s", click_type, self._pin)
        self.press_callback(click_type=click_type, duration=None)
