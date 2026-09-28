from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from contextlib import suppress

from boneio.components.cover.cover import BaseCover
from boneio.components.output import BasicOutput
from boneio.const import CLOSE, CLOSING, IDLE, OPEN, OPENING, STOP
from boneio.core.events import EventBus
from boneio.core.utils import TimePeriod

_LOGGER = logging.getLogger(__name__)
DEFAULT_RESTORED_STATE = {"position": 100}


class TimeBasedCover(BaseCover):
    """Time-based cover algorithm similar to ESPHome."""

    def __init__(
        self,
        open_relay: BasicOutput,
        close_relay: BasicOutput,
        state_save: Callable,
        open_time: TimePeriod,
        close_time: TimePeriod,
        event_bus: EventBus,
        restored_state: dict = DEFAULT_RESTORED_STATE,
        **kwargs,
    ) -> None:
        position = float(restored_state.get("position", DEFAULT_RESTORED_STATE["position"]))
        super().__init__(
            open_relay=open_relay,
            close_relay=close_relay,
            state_save=state_save,
            open_time=open_time,
            close_time=close_time,
            event_bus=event_bus,
            position=position,
            **kwargs,
        )

    def _move_cover(self, direction: str, duration: float, target_position: int | None = None):
        """Run in sepearate thread.

        Args:
            direction: Direction of movement (OPEN or CLOSE)
            duration: Full time for 0-100% movement in milliseconds
            target_position: Optional target position (0-100)
        """
        if direction == OPEN:
            relay = self._open_relay
            total_steps = 100 - self._position
        elif direction == CLOSE:
            relay = self._close_relay
            total_steps = self._position
        else:
            return

        if duration == 0:
            # A zero open_time/close_time makes movement impossible: the guard
            # below returns before relay.turn_on(), so the relay is never
            # energised and the motor never gets voltage — while the cover still
            # reports IDLE and publishes state, so the UI looks like it worked.
            # This is always a misconfiguration, never a normal outcome.
            _LOGGER.error(
                "Cover %s cannot move %s: %s_time is 0. The relay will NOT be "
                "switched. Set a non-zero time in the cover configuration.",
                self._id,
                direction,
                "open" if direction == OPEN else "close",
            )

        if total_steps == 0 or duration == 0:
            self._current_operation = IDLE
            with suppress(RuntimeError):
                self._loop.call_soon_threadsafe(lambda: self.send_state(self.state, self.json_position))
            return

        # duration is full time for 100% movement, scale it by actual distance to travel
        end_position = target_position if target_position is not None else (100 if direction == OPEN else 0)
        travel_ms = duration * abs(end_position - self._initial_position) / 100.0
        travel_ms += self._endstop_overrun_ms(duration, self._initial_position, end_position)
        sign = 1 if direction == OPEN else -1

        def apply_movement(moving_ms: float) -> None:
            moved = moving_ms / duration * 100.0
            self._position = min(100.0, max(0.0, self._initial_position + sign * moved))

        self._drive_relay(relay, travel_ms, apply_movement)
        self._current_operation = IDLE
        with suppress(RuntimeError):
            self._loop.call_soon_threadsafe(lambda: self.send_state_and_save(self.json_position))
        self._last_update_time = time.monotonic()  # Upewnij się, że aktualizacja jest wysłana na końcu ruchu

    async def run_cover(self, current_operation: str, target_position: int | None = None, **kwargs) -> None:
        if self._movement_thread and self._movement_thread.is_alive():
            _LOGGER.warning("Cover movement already in progress. Stopping first.")
            await self.stop()

        # If STOP was requested, don't start new movement
        if current_operation == STOP:
            await self.stop()
            return

        self._current_operation = current_operation
        self._initial_position = self._position
        self._stop_event.clear()
        self._last_update_time = time.monotonic() - 1  # Inicjalizacja czasu ostatniej aktualizacji

        if current_operation == OPENING:
            self._movement_thread = threading.Thread(
                target=self._move_cover, args=("open", self._open_time, target_position)
            )
            self._movement_thread.start()
        elif current_operation == CLOSING:
            self._movement_thread = threading.Thread(
                target=self._move_cover, args=("close", self._close_time, target_position)
            )
            self._movement_thread.start()

    @property
    def kind(self) -> str:
        return "time"
