"""Basic Relay module."""

import asyncio
import logging
from typing import Callable

from boneio.const import LIGHT, NONE, OFF, ON, RELAY, STATE, SWITCH
from boneio.helper import BasicMqtt

_LOGGER = logging.getLogger(__name__)


class BasicRelay(BasicMqtt):
    """Basic relay class."""

    def __init__(
        self,
        callback: Callable,
        id: str = None,
        output_type=SWITCH,
        restored_state: bool = False,
        **kwargs,
    ) -> None:
        """Initialize Basic relay."""
        self._momentary_turn_on = kwargs.pop("momentary_turn_on", None)
        self._momentary_turn_off = kwargs.pop("momentary_turn_off", None)
        super().__init__(id=id, name=id, topic_type=RELAY, **kwargs)
        self._output_type = output_type
        if output_type == NONE:
            self._momentary_turn_on = None
            self._momentary_turn_off = None
        self._state = restored_state
        self._callback = callback
        self._loop = asyncio.get_running_loop()

    @property
    def is_mcp_type(self) -> bool:
        """Check if relay is mcp type."""
        return False

    @property
    def output_type(self) -> str:
        """HA type."""
        return self._output_type

    @property
    def is_light(self) -> bool:
        """Check if HA type is light"""
        return self._output_type == LIGHT

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
        if self.output_type != NONE:
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
