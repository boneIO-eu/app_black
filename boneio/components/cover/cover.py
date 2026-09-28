from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from contextlib import suppress

from boneio.components.output import BasicOutput
from boneio.const import (
    CLOSED,
    CLOSING,
    COVER,
    IDLE,
    OPEN,
    OPENING,
)
from boneio.core.events import EventBus
from boneio.core.messaging import BasicMqtt
from boneio.core.utils import TimePeriod
from boneio.core.utils.timeperiod import ensure_time_period
from boneio.models import CoverState, PositionDict, SavedPositionDict
from boneio.models.events import CoverEvent

_LOGGER = logging.getLogger(__name__)
# How often a moving cover recomputes its position. The relay is not switched
# off on this grid — the last wait is cut short to end exactly at the target.
MOVE_POLL_INTERVAL = 0.05  # s


class BaseCoverABC(ABC):
    """Base cover class."""

    @abstractmethod
    def __init__(
        self,
        id: str,
        open_relay: BasicOutput,
        close_relay: BasicOutput,
        state_save: Callable,
        open_time: TimePeriod,
        close_time: TimePeriod,
        event_bus: EventBus,
        position: float = 100.0,
        **kwargs,
    ) -> None:
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop cover."""
        pass

    @abstractmethod
    async def open(self) -> None:
        """Open cover."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close cover."""
        pass

    @abstractmethod
    async def toggle(self) -> None:
        """Toggle cover to open or close."""
        pass

    @abstractmethod
    async def toggle_open(self) -> None:
        """Toggle cover to open or stop."""
        pass

    @abstractmethod
    async def toggle_close(self) -> None:
        """Toggle cover to close or stop."""
        pass

    @abstractmethod
    async def set_cover_position(self, position: int) -> None:
        """Set cover position."""
        pass

    @property
    @abstractmethod
    def state(self) -> str:
        pass

    @property
    @abstractmethod
    def position(self) -> int:
        pass

    @property
    @abstractmethod
    def current_operation(self) -> str:
        pass

    @property
    @abstractmethod
    def last_timestamp(self) -> float:
        pass

    @property
    @abstractmethod
    def kind(self) -> str:
        pass

    @abstractmethod
    async def run_cover(self, current_operation: str, target_position: int | None = None, **kwargs) -> None:
        """This function is called to run cover after calling open, close, toggle, toggle_open, toggle_close, set_cover_position"""
        pass

    @abstractmethod
    def send_state(self, state: str, json_position: PositionDict) -> None:
        pass


class BaseVenetianCoverABC:
    @property
    @abstractmethod
    def tilt_position(self) -> int:
        pass

    @property
    @abstractmethod
    def tilt_current_operation(self) -> str:
        pass

    @property
    @abstractmethod
    def last_tilt_timestamp(self) -> float:
        pass

    @abstractmethod
    async def set_cover_tilt_position(self, position: int) -> None:
        """Set cover tilt position."""
        pass

    @abstractmethod
    async def tilt_open(self) -> None:
        """Open cover tilt."""
        pass

    @abstractmethod
    async def tilt_close(self) -> None:
        """Close cover tilt."""
        pass


class BaseCover(BaseCoverABC, BasicMqtt):
    def __init__(
        self,
        id: str,
        open_relay: BasicOutput,
        close_relay: BasicOutput,
        state_save: Callable,
        open_time: TimePeriod,
        close_time: TimePeriod,
        event_bus: EventBus,
        position: float = 100.0,
        name: str | None = None,
        actuator_activation_duration: TimePeriod | None = None,
        **kwargs,
    ) -> None:
        # Use provided name or fall back to id
        display_name = name if name else id
        BasicMqtt.__init__(self, id=id, name=display_name, topic_type=COVER, **kwargs)
        self._loop = asyncio.get_event_loop()
        self._id = id
        self._open_relay = open_relay
        self._close_relay = close_relay
        self._state_save = state_save
        self._event_bus = event_bus
        self._open_time = open_time.total_milliseconds
        self._close_time = close_time.total_milliseconds
        # Time from energising the relay until the motor actually moves. Some
        # drives (Somfy J4 WT) ignore orders shorter than ~200ms, so a short
        # tilt step would never happen without it.
        self._actuator_activation_ms = (
            actuator_activation_duration.total_milliseconds if actuator_activation_duration is not None else 0.0
        )
        self._position = position
        self._initial_position: float = position
        self._current_operation = IDLE
        self._last_operation = CLOSING
        _LOGGER.debug(
            "BaseCover %s initialized: open_time=%dms, close_time=%dms, initial_position=%d%%",
            id,
            self._open_time,
            self._close_time,
            position,
        )

        self._last_timestamp = time.time()

        self._last_update_time = 0.0
        self._closed = position <= 0

        self._movement_thread = None
        self._stop_event = threading.Event()

        # Flag set by action executor to signal this call originates from a button action.
        # Used by VenetianCover to conditionally skip tilt restore.
        self._from_action: bool = False
        # When True, tilt restore is explicitly requested by the action definition.
        self._action_tilt_restore: bool = False

        self._event_bus.add_sigterm_listener(self.on_exit)

        with suppress(RuntimeError):
            self._loop.call_soon_threadsafe(self._loop.call_later, 0.5, self.send_state, self.state, self.json_position)

    def _drive_relay(self, relay: BasicOutput, travel_ms: float, apply_movement: Callable[[float], None]) -> None:
        """Hold ``relay`` on until the cover has travelled ``travel_ms``, or until stopped.

        Runs in the movement thread. The motor is assumed to stand still for
        the first ``actuator_activation_duration`` after the relay closes, so
        the relay stays on for that long *plus* ``travel_ms``.

        ``apply_movement`` gets how long the motor has really been moving (ms)
        and updates the position from it. It is called on every poll and once
        more after the relay has dropped, timed at the turn-off — so a stop
        between polls, or the I2C write itself, is not lost from the position.

        Args:
            relay: The open or close relay to drive.
            travel_ms: Motor movement time needed to reach the target.
            apply_movement: Callback converting moving time to position.
        """
        activation_ms = self._actuator_activation_ms
        deadline_ms = activation_ms + travel_ms

        relay.turn_on()
        # Send relay state to WebSocket (not MQTT - that's handled by output_type check)
        with suppress(RuntimeError):
            self._loop.call_soon_threadsafe(lambda r=relay: asyncio.ensure_future(r.async_send_state()))
        # Both timestamps are taken after the relay write returns, so the I2C
        # latency of turn_on and turn_off cancels out.
        start_time = time.monotonic()

        while True:
            current_time = time.monotonic()
            elapsed_ms = (current_time - start_time) * 1000
            if elapsed_ms >= deadline_ms:
                break
            apply_movement(max(0.0, elapsed_ms - activation_ms))
            self._last_timestamp = time.time()  # Wall clock for display
            if current_time - self._last_update_time >= 1:
                with suppress(RuntimeError):
                    self._loop.call_soon_threadsafe(lambda: self.send_state(self.state, self.json_position))
                self._last_update_time = current_time
            # Waiting on the event instead of sleeping lets stop() cut in at once.
            if self._stop_event.wait(min(deadline_ms - elapsed_ms, MOVE_POLL_INTERVAL * 1000) / 1000):
                break

        relay.turn_off()
        elapsed_ms = (time.monotonic() - start_time) * 1000
        apply_movement(max(0.0, elapsed_ms - activation_ms))
        self._last_timestamp = time.time()
        with suppress(RuntimeError):
            self._loop.call_soon_threadsafe(lambda r=relay: asyncio.ensure_future(r.async_send_state()))

    def update_config_times(self, config: dict) -> None:
        """Update timing shared by all cover platforms.

        Args:
            config: Cover configuration; time values as TimePeriod or strings.
        """
        if "open_time" in config:
            self._open_time = ensure_time_period(config["open_time"]).total_milliseconds
        if "close_time" in config:
            self._close_time = ensure_time_period(config["close_time"]).total_milliseconds
        # Optional field: a removed value means "no activation delay" again.
        activation = config.get("actuator_activation_duration")
        self._actuator_activation_ms = ensure_time_period(activation).total_milliseconds if activation else 0.0

    async def on_exit(self) -> None:
        """Stop on exit."""
        await self.stop(on_exit=True)

    async def stop(self, on_exit=False) -> None:
        if self._movement_thread and self._movement_thread.is_alive():
            self._stop_event.set()

            # Halting is three blocking operations: waiting for the movement
            # thread to notice the stop event, and two relay writes that go out
            # over I2C behind a bus lock shared with every other device. Run
            # inline they were the *event loop's* wait — up to half a second of
            # frozen loop on every cover stop, and a cover stop is the first
            # thing `toggle`, `toggle_open` and `toggle_close` do, so an
            # ordinary button press paid it. Nothing reads GPIO while the loop
            # is stopped. Order is unchanged: join first, then de-energise.
            thread = self._movement_thread

            def _halt() -> None:
                thread.join(timeout=0.5)
                self._open_relay.turn_off()
                self._close_relay.turn_off()

            await asyncio.get_running_loop().run_in_executor(None, _halt)
            # Send relay states to WebSocket (not MQTT - that's handled by output_type check)
            with suppress(RuntimeError):
                asyncio.create_task(self._open_relay.async_send_state())
                asyncio.create_task(self._close_relay.async_send_state())
            if self._current_operation in (OPENING, CLOSING):
                self._last_operation = self._current_operation
            self._current_operation = IDLE
            if not on_exit:
                self.send_state(self.state, self.json_position)

    async def open(self) -> None:
        if self._position >= 100:
            return
        estimated_time_s = (100 - self._position) / 100 * self._open_time / 1000
        _LOGGER.info(
            "Opening cover %s from position %d%%. Estimated time: %.1fs (open_time=%dms)",
            self._id,
            self._position,
            estimated_time_s,
            self._open_time,
        )
        self._last_operation = OPENING
        await self.run_cover(current_operation=OPENING)
        self._message_bus.send_message(topic=f"{self._send_topic}/state", payload=OPENING)

    async def close(self) -> None:
        if self._position <= 0:
            return
        estimated_time_s = self._position / 100 * self._close_time / 1000
        _LOGGER.info(
            "Closing cover %s from position %d%%. Estimated time: %.1fs (close_time=%dms)",
            self._id,
            self._position,
            estimated_time_s,
            self._close_time,
        )
        self._last_operation = CLOSING
        await self.run_cover(current_operation=CLOSING)
        self._message_bus.send_message(topic=f"{self._send_topic}/state", payload=CLOSING)

    async def set_cover_position(self, position: int) -> None:
        if not 0 <= position <= 100:
            raise ValueError("Pozycja musi być w zakresie od 0 do 100.")

        if abs(self._position - position) < 1:
            return

        position_diff = abs(self._position - position)
        if position > self._position:
            estimated_time_s = position_diff / 100 * self._open_time / 1000
            _LOGGER.info(
                "Setting cover %s position from %d%% to %d%% (OPENING). Estimated time: %.1fs (open_time=%dms)",
                self._id,
                self._position,
                position,
                estimated_time_s,
                self._open_time,
            )
            await self.run_cover(current_operation=OPENING, target_position=position)
        elif position < self._position:
            estimated_time_s = position_diff / 100 * self._close_time / 1000
            _LOGGER.info(
                "Setting cover %s position from %d%% to %d%% (CLOSING). Estimated time: %.1fs (close_time=%dms)",
                self._id,
                self._position,
                position,
                estimated_time_s,
                self._close_time,
            )
            await self.run_cover(current_operation=CLOSING, target_position=position)

    async def toggle(self) -> None:
        _LOGGER.debug("Toggle cover %s from input.", self._id)
        if self._current_operation != IDLE:
            await self.stop()
        elif self._position >= 100:
            await self.close()
        elif self._position <= 0 or self._last_operation == CLOSING:
            await self.open()
        else:
            await self.close()

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

    async def smart_toggle(self, always_open_till: int = 50) -> None:
        """Smart toggle with position threshold.

        If cover is moving → stop.
        If position <= always_open_till → open (to 100%).
        If position > always_open_till → normal toggle (based on last_operation).

        Args:
            always_open_till: Position threshold (0-100%). Below or equal this
                value the cover will always open. Above it, normal toggle applies.
        """
        _LOGGER.debug(
            "Smart toggle cover %s (position=%d%%, threshold=%d%%)",
            self._id,
            self._position,
            always_open_till,
        )
        if self._current_operation != IDLE:
            await self.stop()
        elif self._position <= always_open_till:
            await self.open()
        elif self._position >= 100:
            await self.close()
        elif self._position <= 0 or self._last_operation == CLOSING:
            await self.open()
        else:
            await self.close()

    @property
    def state(self) -> str:
        if self._current_operation == OPENING:
            return OPENING
        elif self._current_operation == CLOSING:
            return CLOSING
        else:
            return CLOSED if self._position == 0 else OPEN

    @property
    def is_open(self) -> bool:
        """Whether the cover is currently open (position > 0).

        Used by the action conditions system to evaluate ``is_open`` / ``is_closed``
        checks for covers.

        Returns:
            True if the cover is not fully closed.
        """
        return self._position > 0

    @property
    def position(self) -> int:
        """Return current cover position as integer (0-100)."""
        return round(self._position)

    @property
    def json_position(self) -> PositionDict:
        return {"position": self.position}

    @property
    def current_operation(self) -> str:
        return self._current_operation

    @property
    def last_timestamp(self) -> float:
        return self._last_timestamp

    def send_state(self, state: str, json_position: PositionDict) -> None:
        event = CoverState(
            id=self.id,
            name=self.name,
            state=state,
            kind=self.kind,
            timestamp=self._last_timestamp,
            current_operation=self._current_operation,
            **json_position,
        )
        self._event_bus.trigger_event(CoverEvent(entity_id=self.id, state=event))
        self._message_bus.send_message(topic=f"{self._send_topic}/state", payload=state, retain=True)
        self._message_bus.send_message(topic=f"{self._send_topic}/pos", payload=json.dumps(json_position), retain=True)

    @property
    def saved_position(self) -> SavedPositionDict:
        """Raw float position for disk persistence."""
        return {"position": self._position}

    def send_state_and_save(self, json_position: PositionDict):
        """Send state to MQTT/WebSocket and save raw float position to disk."""
        self.send_state(self.state, json_position)
        self._state_save(self.saved_position)
