"""PCF8575 Output module (formerly PCFRelay)."""

import logging

from boneio.const import NONE, OFF, ON, PCF, SWITCH
from boneio.hardware.gpio.expanders import PCF8575
from boneio.hardware.gpio.expanders.pcf8575 import PCF8575DigitalInOut
from boneio.components.output.basic import BasicOutput

_LOGGER = logging.getLogger(__name__)


class PCFOutput(BasicOutput):
    """Represents PCF8575 output (formerly PCFRelay)."""

    def __init__(
        self,
        pin: int,
        expander: PCF8575,
        expander_id: str,
        output_type: str = SWITCH,
        restored_state: bool = False,
        **kwargs,
    ) -> None:
        """Initialize PCF relay."""
        self._pin: PCF8575DigitalInOut = expander.get_pin(pin)
        if output_type == NONE:
            """Just in case to not restore state of covers etc."""
            restored_state = False
        self._pin.switch_to_output(value=restored_state)
        super().__init__(
            **kwargs, output_type=output_type, restored_state=restored_state
        )
        self._pin_id = pin
        self._expander_id = expander_id
        self._active_state = False
        _LOGGER.debug("Setup PCF with pin %s", self._pin_id)

    @property
    def expander_type(self) -> str:
        """Check expander type."""
        return PCF

    @property
    def pin_id(self) -> int:
        """Return PIN id."""
        return self._pin_id

    @property
    def is_active(self) -> bool:
        """Is relay active."""
        return self.pin.value == self._active_state

    @property
    def pin(self) -> str:
        """PIN of the relay"""
        return self._pin

    def turn_on(self) -> None:
        """Call turn on action."""
        self.pin.value = self._active_state
        self._execute_momentary_turn(momentary_type=ON)
        self._loop.call_soon_threadsafe(self.send_state)
        self._loop.call_soon_threadsafe(self._callback)

    def turn_off(self) -> None:
        """Call turn off action."""
        self.pin.value = not self._active_state
        self._execute_momentary_turn(momentary_type=OFF)
        self._loop.call_soon_threadsafe(self.send_state)
        self._loop.call_soon_threadsafe(self._callback)
