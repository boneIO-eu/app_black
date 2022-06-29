"""GPIO Relay module.
!!Not used in BoneIO.
Created just in case.
"""

import logging

from boneio.const import HIGH, LOW
from boneio.helper import read_input, setup_output, write_output
from boneio.relay.basic import BasicRelay

_LOGGER = logging.getLogger(__name__)


class GpioRelay(BasicRelay):
    """Represents GPIO Relay output"""

    def __init__(self, pin: str, **kwargs) -> None:
        """Initialize Gpio relay."""
        super().__init(**kwargs)
        self._pin = pin
        setup_output(self._pin)
        write_output(self.pin, LOW)
        _LOGGER.debug("Setup relay with pin %s", self._pin)

    @property
    def is_active(self) -> bool:
        """Is relay active."""
        return read_input(self.pin, on_state=HIGH)

    @property
    def pin(self) -> str:
        """PIN of the relay"""
        return self._pin

    def turn_on(self) -> None:
        """Call turn on action."""
        write_output(self.pin, HIGH)
        self._loop.call_soon_threadsafe(self.send_state)

    def turn_off(self) -> None:
        """Call turn off action."""
        write_output(self.pin, LOW)
        self._loop.call_soon_threadsafe(self.send_state)
