"""MCP23017 Relay module."""

import logging
from adafruit_mcp230xx.mcp23017 import MCP23017
from boneio.relay.basic import BasicRelay
from boneio.const import SWITCH, NONE

_LOGGER = logging.getLogger(__name__)


class MCPRelay(BasicRelay):
    """Represents MCP Relay output"""

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
        self._pin = mcp.get_pin(pin)
        self._pin.switch_to_output(value=True)
        if output_type == NONE:
            """Just in case to not restore state of covers etc."""
            restored_state = False
        self._pin.value = restored_state
        super().__init__(
            **kwargs, output_type=output_type, restored_state=restored_state
        )
        self._pin_id = pin
        self._mcp_id = mcp_id
        _LOGGER.debug("Setup MCP with pin %s", self._pin_id)

    @property
    def is_mcp_type(self) -> bool:
        """Check if relay is mcp type."""
        return True

    @property
    def pin_id(self) -> str:
        """Return PIN id."""
        return self._pin_id

    @property
    def mcp_id(self) -> str:
        """Retrieve parent MCP ID."""
        return self._mcp_id

    @property
    def is_active(self) -> bool:
        """Is relay active."""
        return self.pin.value

    @property
    def pin(self) -> str:
        """PIN of the relay"""
        return self._pin

    def turn_on(self) -> None:
        """Call turn on action."""
        self.pin.value = True
        self._loop.call_soon_threadsafe(self.send_state)

    def turn_off(self) -> None:
        """Call turn off action."""
        self.pin.value = False
        self._loop.call_soon_threadsafe(self.send_state)
