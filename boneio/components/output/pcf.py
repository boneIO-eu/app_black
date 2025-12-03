"""PCF8575 Output module (formerly PCFRelay)."""

import logging
from typing import final

from boneio.components.output.basic import BasicOutput
from boneio.const import NONE, OFF, ON, PCF, SWITCH
from boneio.hardware.gpio.expanders import PCF8575

_LOGGER = logging.getLogger(__name__)

@final
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
        self._expander = expander
        self._pin_id = pin
        if output_type == NONE:
            """Just in case to not restore state of covers etc."""
            restored_state = False
        self._expander.configure_pin_as_output(pin_number=pin, value=restored_state)
        super().__init__(
            **kwargs, output_type=output_type, restored_state=restored_state
        )
        self._expander_id = expander_id
        _LOGGER.debug("Setup PCF with pin %s", self._pin_id)

    @property
    def expander_type(self) -> str:
        """Check expander type."""
        return PCF


    @property
    def is_active(self) -> bool:
        """Is relay active."""
        return not self._expander.get_pin_value(self._pin_id)

    def turn_on(self, timestamp=None) -> None:
        """Call turn on action."""
        self._expander.set_pin_value(self._pin_id, False)
        if not timestamp:
            self._execute_momentary_turn(momentary_type=ON)

    def turn_off(self, timestamp=None) -> None:
        """Call turn off action."""
        self._expander.set_pin_value(self._pin_id, True)
        if not timestamp:
            self._execute_momentary_turn(momentary_type=OFF)
