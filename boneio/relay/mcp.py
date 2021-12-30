"""MCP23017 Relay module."""

import logging

from adafruit_mcp230xx.mcp23017 import MCP23017

from boneio.relay.basic import BasicRelay

_LOGGER = logging.getLogger(__name__)


class MCPRelay(BasicRelay):
    """Represents MCP Relay output"""

    def __init__(self, pin: int, mcp: MCP23017, mcp_id: str, **kwargs) -> None:
        """Initialize MCP relay."""
        super().__init__(**kwargs)
        self._pin_id = pin
        self._pin = mcp.get_pin(pin)
        self._pin.switch_to_output(value=True)
        self._mcp_id = mcp_id
        self._pin.value = False
        _LOGGER.debug("Setup MCP with pin %s", self._pin_id)

    @property
    def is_mcp_type(self) -> bool:
        """Check if relay is mcp type."""
        return True

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

    @property
    def ha_type(self) -> str:
        """HA type."""
        return self._ha_type

    def turn_on(self) -> None:
        """Call turn on action."""
        self.pin.value = True
        self._loop.call_soon_threadsafe(self.send_state)

    def turn_off(self) -> None:
        """Call turn off action."""
        self.pin.value = False
        self._loop.call_soon_threadsafe(self.send_state)
