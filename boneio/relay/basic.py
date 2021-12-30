"""Basic Relay module."""

import asyncio
import logging
from typing import Callable

from boneio.const import OFF, ON, RELAY, STATE, SWITCH
from boneio.helper import BasicMqtt

_LOGGER = logging.getLogger(__name__)


class BasicRelay(BasicMqtt):
    """Basic relay class."""

    def __init__(
        self, callback: Callable, id: str = None, ha_type=SWITCH, **kwargs
    ) -> None:
        """Initialize Basic relay."""
        super().__init__(id=id, name=id, topic_type=RELAY, **kwargs)
        self._ha_type = ha_type
        self._state = False
        self._callback = callback
        self._loop = asyncio.get_running_loop()

    @property
    def is_mcp_type(self) -> bool:
        """Check if relay is mcp type."""
        return False

    @property
    def id(self) -> bool:
        """Id of the relay.
        Has to be trimmed out of spaces because of MQTT handling in HA."""
        return self._id or self._pin

    @property
    def name(self) -> bool:
        """Not trimmed id."""
        return self._name or self._pin

    @property
    def state(self) -> bool:
        """Is relay active."""
        return self._state

    def send_state(self) -> None:
        """Send state to Mqtt on action."""
        state = ON if self.is_active else OFF
        self._state = state
        self._send_message(
            topic=self._send_topic,
            payload={STATE: state},
        )
        self._loop.call_soon_threadsafe(self._callback)

    def toggle(self) -> None:
        """Toggle relay."""
        _LOGGER.debug("Toggle relay.")
        if self.is_active:
            self.turn_off()
        else:
            self.turn_on()

    @property
    def is_active(self) -> bool:
        """Is active check."""
        raise NotImplementedError

    def turn_on(self) -> None:
        """Call turn on action."""
        raise NotImplementedError

    def turn_off(self) -> None:
        """Call turn off action."""
        raise NotImplementedError
