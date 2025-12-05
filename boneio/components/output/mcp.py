"""MCP23017 Output module (formerly MCPRelay)."""

import logging
from typing import override
from boneio.hardware.gpio.expanders.mcp23017 import MCP23017

from boneio.const import COVER, MCP, OFF, ON, SWITCH
from boneio.components.output.basic import BasicOutput

_LOGGER = logging.getLogger(__name__)


class MCPOutput(BasicOutput):
    """Represents MCP23017 output (formerly MCPRelay)."""

    def __init__(
        self,
        pin: int,
        mcp: MCP23017,
        mcp_id: str,
        output_type: str = SWITCH,
        restored_state: bool = False,
        **kwargs
    ) -> None:
        """Initialize MCP relay."""
        self._mcp = mcp
        self._pin_id = pin
        if output_type == COVER:
            """Just in case to not restore state of covers etc."""
            restored_state = False
        super().__init__(
            **kwargs, output_type=output_type, restored_state=restored_state
        )
        self._expander_id = mcp_id

        self.init_with_check_if_can_restore_state(restored_state=restored_state)
        _LOGGER.debug("Setup MCP with pin %s", self._pin_id)

    def init_with_check_if_can_restore_state(self, restored_state: bool) -> None:
        if restored_state:
            if self._interlock_manager and self._interlock_groups:
                if not self._interlock_manager.can_turn_on(self, self._interlock_groups):
                    _LOGGER.warning(
                        f"Interlock active: cannot restore ON state for {self._pin_id} at startup"
                    )
                    restored_state = False
        self._mcp.configure_pin_as_output(self._pin_id, restored_state)


    @property
    def expander_type(self) -> str:
        """Check expander type."""
        return MCP

    @property
    @override
    def is_active(self) -> bool:
        """Is relay active."""
        return self._mcp.get_pin_value(self._pin_id)

    @override
    def turn_on(self, timestamp=None) -> None:
        """Call turn on action."""
        self._mcp.set_pin_value(self._pin_id, True)
        self._state = ON
        if not timestamp:
            self._execute_momentary_turn(momentary_type=ON)

    @override
    def turn_off(self, timestamp=None) -> None:
        """Call turn off action."""
        self._mcp.set_pin_value(self._pin_id, False)
        self._state = OFF
        if not timestamp:
            self._execute_momentary_turn(momentary_type=OFF)
