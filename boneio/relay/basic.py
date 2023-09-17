"""Basic Relay module."""

import asyncio
import logging
from typing import Callable
from boneio.helper.util import callback
from boneio.const import COVER, LIGHT, NONE, OFF, ON, RELAY, STATE, SWITCH
from boneio.helper import BasicMqtt
from boneio.helper.events import EventBus

_LOGGER = logging.getLogger(__name__)


class BasicRelay(BasicMqtt):
    """Basic relay class."""

    def __init__(
        self,
        callback: Callable,
        id: str,
        event_bus: EventBus,
        output_type=SWITCH,
        restored_state: bool = False,
        topic_type: str = RELAY,
        **kwargs,
    ) -> None:
        """Initialize Basic relay."""
        self._momentary_turn_on = kwargs.pop("momentary_turn_on", None)
        self._momentary_turn_off = kwargs.pop("momentary_turn_off", None)
        super().__init__(id=id, name=id, topic_type=topic_type, **kwargs)
        self._output_type = output_type
        self._event_bus = event_bus
        if output_type == COVER:
            self._momentary_turn_on = None
            self._momentary_turn_off = None
        self._state = ON if restored_state else OFF
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
    def id(self) -> str:
        """Id of the relay.
        Has to be trimmed out of spaces because of MQTT handling in HA."""
        return self._id or self._pin

    @property
    def name(self) -> str:
        """Not trimmed id."""
        return self._name or self._pin

    @property
    def state(self) -> str:
        """Is relay active."""
        return self._state
    
    def payload(self) -> dict:
        return {STATE: self.state}

    def send_state(self) -> None:
        """Send state to Mqtt on action."""
        state = ON if self.is_active else OFF
        self._state = state
        if self.output_type not in (NONE, COVER):
            self._send_message(
                topic=self._send_topic, payload=self.payload(), retain=True
            )
        self._event_bus.trigger_output_event(self.id)
        self._loop.call_soon_threadsafe(self._callback)

    def toggle(self) -> None:
        """Toggle relay."""
        _LOGGER.debug("Toggle relay.")
        if self.is_active:
            self.turn_off()
        else:
            self.turn_on()

    @callback
    def _momentary_callback(self, time, action):
        _LOGGER.info("Momentary callback at %s", time)
        action()

    @property
    def is_active(self) -> bool:
        """Is active check."""
        raise NotImplementedError
    
    async def async_turn_on(self) -> None:
        self._loop.call_soon(self.turn_on)

    async def async_turn_off(self) -> None:
        self._loop.call_soon(self.turn_off)

    def turn_on(self) -> None:
        """Call turn on action."""
        raise NotImplementedError

    def turn_off(self) -> None:
        """Call turn off action."""
        raise NotImplementedError
