"""Cover module."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

from boneio.components.output import MCPOutput
from boneio.const import (
    CLOSE,
    CLOSED,
    CLOSING,
    COVER,
    IDLE,
    OPEN,
    OPENING,
    STOP,
)
from boneio.core.events import EventBus
from boneio.core.utils import TimePeriod
from boneio.core.messaging import BasicMqtt
from boneio.models import CoverState
from boneio.models.events import CoverEvent

_LOGGER = logging.getLogger(__name__)
DEFAULT_RESTORED_STATE = {"position": 100}
COVER_COMMANDS = {
    OPEN: "open_cover",
    CLOSE: "close_cover",
    STOP: "stop",
    "toggle": "toggle",
    "toggle_open": "toggle_open",
}


class RelayHelper:
    """Relay helper for cover either open/close."""

    def __init__(self, relay: MCPOutput, time: TimePeriod) -> None:
        """Initialize helper."""
        self._relay = relay
        self._steps = 100 / time.total_seconds

    @property
    def relay(self) -> MCPOutput:
        """Get relay."""
        return self._relay

    @property
    def steps(self) -> int:
        """Get steps for each time."""
        return int(self._steps)


class PreviousCover(BasicMqtt):
    """Cover class of boneIO"""

    def __init__(
        self,
        id: str,
        open_relay: MCPOutput,
        close_relay: MCPOutput,
        state_save: Callable,
        open_time: TimePeriod,
        close_time: TimePeriod,
        event_bus: EventBus,
        restored_state: dict = DEFAULT_RESTORED_STATE,
        **kwargs,
    ) -> None:
        """Initialize cover class."""
        self._loop = asyncio.get_event_loop()
        self._id = id
        super().__init__(id=id, name=id, topic_type=COVER, **kwargs)
        self._lock = asyncio.Lock()
        self._state_save = state_save
        self._open = RelayHelper(relay=open_relay, time=open_time)
        self._close = RelayHelper(relay=close_relay, time=close_time)
        self._open_time = open_time
        self._close_time = close_time
        _LOGGER.debug(
            "Cover %s initialized: open_time=%s (%dms), close_time=%s (%dms), open_steps=%d/s, close_steps=%d/s",
            id, open_time, open_time.total_milliseconds, close_time, close_time.total_milliseconds,
            self._open.steps, self._close.steps
        )
        self._set_position = None
        self._current_operation = IDLE
        self._position = float(restored_state.get("position", DEFAULT_RESTORED_STATE["position"]))
        self._requested_closing = True
        self._event_bus = event_bus
        self._timer_handle = None
        self._last_timestamp = 0.0
        if self._position is None:
            self._closed = True
        else:
            self._closed = self._position <= 0
        self._event_bus.add_sigterm_listener(self.on_exit)
        self._loop.call_soon_threadsafe(
            self._loop.call_later,
            0.5,
            self.send_state,
        )

    async def run_cover(
        self,
        current_operation: str,
    ) -> None:
        """Run cover engine."""
        if self._current_operation != IDLE:
            self._stop_cover()
        self._current_operation = current_operation

        def get_relays():
            if current_operation == OPENING:
                return (self._open.relay, self._close.relay)
            else:
                return (self._close.relay, self._open.relay)

        (relay, inverted_relay) = get_relays()
        async with self._lock:
            if inverted_relay.is_active:
                inverted_relay.turn_off()
            self._timer_handle = self._event_bus.add_every_second_listener(
                f"{COVER}{self.id}", self.listen_cover
            )
            relay.turn_on()

    def on_exit(self) -> None:
        """Stop on exit."""
        self._stop_cover(on_exit=True)

    @property
    def state(self) -> str:
        """Current state of cover."""
        return CLOSED if self._closed else OPEN

    async def stop(self) -> None:
        """Public Stop cover graceful."""
        _LOGGER.info("Stopping cover %s.", self._id)
        if self._current_operation != IDLE:
            self._stop_cover(on_exit=False)
        await self.async_send_state()

    async def async_send_state(self) -> None:
        """Send state to Websocket on action asynchronously."""
        self._last_timestamp = time.time()
        event = CoverState(
            id=self.id,
            name=self.name,
            state=self.state,
            position=int(round(self._position, 0)),
            kind=self.kind,
            timestamp=self.last_timestamp,
            current_operation=self._current_operation,
        )
        self._event_bus.trigger_event(CoverEvent(entity_id=self.id, state=event))

    def send_state(self) -> None:
        """Send state of cover to mqtt."""
        self._message_bus.send_message(
            topic=f"{self._send_topic}/state", payload=self.state
        )
        pos = round(self._position, 0)
        self._message_bus.send_message(topic=f"{self._send_topic}/pos", payload={ "position": str(pos) })
        self._state_save(value={"position": pos})

    def _stop_cover(self, on_exit=False) -> None:
        """Stop cover."""
        self._open.relay.turn_off()
        self._close.relay.turn_off()
        if self._timer_handle is not None:
            self._event_bus.remove_every_second_listener(f"{COVER}{self.id}")
            self._timer_handle = None
            self._set_position = None
            if not on_exit:
                self.send_state()
        self._current_operation = IDLE

    @property
    def current_cover_position(self) -> int:
        """Return the current position of the cover."""
        return int(round(self._position, 0))

    def listen_cover(self, *args) -> None:
        """Listen for change in cover."""
        if self._current_operation == IDLE:
            return

        def get_step():
            """Get step for current operation."""
            if self._requested_closing:
                return -self._close.steps
            else:
                return self._open.steps

        step = get_step()
        self._position += step
        rounded_pos = round(self._position, 0)
        if self._set_position:
            # Set position is only working for every 10%, so round to nearest 10.
            # Except for start moving time
            if (
                self._requested_closing and rounded_pos < 95
            ) or rounded_pos > 5:
                rounded_pos = round(self._position, -1)
        else:
            if rounded_pos > 100:
                rounded_pos = 100
            elif rounded_pos < 0:
                rounded_pos = 0
        self._message_bus.send_message(topic=f"{self._send_topic}/pos", payload={"position": str(rounded_pos)})
        asyncio.create_task(self.async_send_state())
        if rounded_pos == self._set_position or (
            self._set_position is None
            and (rounded_pos >= 100 or rounded_pos <= 0)
        ):
            self._position = rounded_pos
            self._closed = self.current_cover_position <= 0
            self._stop_cover()
            return

        self._closed = self.current_cover_position <= 0

    async def close_cover(self) -> None:
        """Close cover."""
        if self._position == 0:
            return
        if self._position is None:
            self._closed = True
            return
        estimated_time_s = self._position / self._close.steps
        _LOGGER.info(
            "Closing cover %s from position %d%%. Estimated time: %.1fs (close_time=%dms, steps=%d/s)",
            self._id, self._position, estimated_time_s, self._close_time.total_milliseconds, self._close.steps
        )

        self._requested_closing = True
        self._message_bus.send_message(topic=f"{self._send_topic}/state", payload=CLOSING)
        await self.run_cover(
            current_operation=CLOSING,
        )

    async def open_cover(self) -> None:
        """Open cover."""
        if self._position == 100:
            return
        if self._position is None:
            self._closed = False
            return
        estimated_time_s = (100 - self._position) / self._open.steps
        _LOGGER.info(
            "Opening cover %s from position %d%%. Estimated time: %.1fs (open_time=%dms, steps=%d/s)",
            self._id, self._position, estimated_time_s, self._open_time.total_milliseconds, self._open.steps
        )

        self._requested_closing = False
        self._message_bus.send_message(topic=f"{self._send_topic}/state", payload=OPENING)
        await self.run_cover(
            current_operation=OPENING,
        )

    async def set_cover_position(self, position: int) -> None:
        """Move cover to a specific position."""
        set_position = round(position, -1)
        if self._position == position or set_position == self._set_position:
            return
        if self._set_position:
            self._stop_cover(on_exit=True)
        self._set_position = set_position

        self._requested_closing = set_position < self._position
        current_operation = CLOSING if self._requested_closing else OPENING
        
        # Calculate estimated time
        position_diff = abs(self._position - set_position)
        if self._requested_closing:
            steps = self._close.steps
            time_config = self._close_time
        else:
            steps = self._open.steps
            time_config = self._open_time
        estimated_time_s = position_diff / steps if steps > 0 else 0
        
        _LOGGER.info(
            "Setting cover %s position from %d%% to %d%% (%s). Estimated time: %.1fs (time_config=%dms, steps=%d/s)",
            self._id, self._position, set_position, current_operation, 
            estimated_time_s, time_config.total_milliseconds, steps
        )
        self._message_bus.send_message(
            topic=f"{self._send_topic}/state", payload=current_operation
        )
        await self.run_cover(
            current_operation=current_operation,
        )

    async def open(self) -> None:
        _LOGGER.debug("Opening cover %s.", self._id)
        await self.open_cover()

    async def close(self) -> None:
        _LOGGER.debug("Closing cover %s.", self._id)
        await self.close_cover()

    async def toggle(self) -> None:
        _LOGGER.debug("Toggle cover %s from input.", self._id)
        if self.state == CLOSED:
            await self.close()
        else:
            await self.open()

    async def toggle_open(self) -> None:
        _LOGGER.debug("Toggle open cover %s from input.", self._id)
        if self._current_operation != IDLE:
            await self.stop()
        else:
            await self.open()

    async def toggle_close(self) -> None:
        _LOGGER.debug("Toggle close cover %s from input.", self._id)
        if self._current_operation != IDLE:
            await self.stop()
        else:
            await self.close()

    @property
    def last_timestamp(self) -> float:
        return self._last_timestamp

    @property
    def position(self) -> int:
        return int(round(self._position, 0))

    @property
    def current_operation(self) -> str:
        return self._current_operation

    @property
    def kind(self) -> str:
        return "previous"
    
    def update_config_times(self, config: dict) -> None:
        """Update cover timing configuration.
        
        Args:
            config: Dictionary with timing values as TimePeriod objects.
                   Keys: open_time, close_time
        """
        if "open_time" in config:
            self._open_time = config["open_time"]
            self._open = RelayHelper(relay=self._open.relay, time=config["open_time"])
        if "close_time" in config:
            self._close_time = config["close_time"]
            self._close = RelayHelper(relay=self._close.relay, time=config["close_time"])