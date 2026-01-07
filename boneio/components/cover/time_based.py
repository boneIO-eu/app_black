from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections.abc import Callable

from boneio.const import CLOSE, CLOSING, IDLE, OPEN, OPENING, STOP
from boneio.components.cover.cover import BaseCover
from boneio.core.events import EventBus
from boneio.core.utils import TimePeriod
from boneio.components.output import MCPOutput

_LOGGER = logging.getLogger(__name__)
DEFAULT_RESTORED_STATE = {"position": 100}

class TimeBasedCover(BaseCover):
    """Time-based cover algorithm similar to ESPHome."""
    def __init__(
        self,
        open_relay: MCPOutput,
        close_relay: MCPOutput,
        state_save: Callable,
        open_time: TimePeriod,
        close_time: TimePeriod,
        event_bus: EventBus,
        restored_state: dict = DEFAULT_RESTORED_STATE,
        **kwargs,
    ) -> None:
        position = int(restored_state.get("position", DEFAULT_RESTORED_STATE["position"]))
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

        if total_steps == 0 or duration == 0:
            self._current_operation = IDLE
            self._loop.call_soon_threadsafe(lambda: self.send_state(self.state, self.json_position))
            return

        # Calculate actual duration based on remaining distance
        # duration is full time for 100% movement, scale it by actual distance to travel
        actual_duration = duration * (total_steps / 100.0)

        relay.turn_on()
        # Send relay state to WebSocket (not MQTT - that's handled by output_type check)
        self._loop.call_soon_threadsafe(lambda r=relay: asyncio.ensure_future(r.async_send_state()))
        start_time = time.monotonic()

        while not self._stop_event.is_set():
            current_time = time.monotonic()  # Pobierz aktualny czas tylko raz na iterację
            elapsed_time = (current_time - start_time) * 1000  # Konwersja na milisekundy
            progress = elapsed_time / actual_duration if actual_duration > 0 else 1.0

            if direction == OPEN:
                self._position = min(100.0, self._initial_position + progress * total_steps)
            elif direction == CLOSE:
                self._position = max(0.0, self._initial_position - progress * total_steps)

            self._last_timestamp = current_time # Użyj pobranego czasu
            if current_time - self._last_update_time >= 1:
                self._loop.call_soon_threadsafe(lambda: self.send_state(self.state, self.json_position))
                self._last_update_time = current_time

            if target_position is not None:
                if (direction == OPEN and self._position >= target_position) or \
                   (direction == CLOSE and self._position <= target_position):
                    break

            if progress >= 1.0:
                break

            time.sleep(0.05)  # Małe opóźnienie, aby nie blokować CPU
        relay.turn_off()
        # Send relay state to WebSocket (not MQTT - that's handled by output_type check)
        self._loop.call_soon_threadsafe(lambda r=relay: asyncio.ensure_future(r.async_send_state()))
        self._current_operation = IDLE
        self._loop.call_soon_threadsafe(lambda: self.send_state_and_save(self.json_position))
        self._last_update_time = time.monotonic() # Upewnij się, że aktualizacja jest wysłana na końcu ruchu

    async def run_cover(self, current_operation: str, target_position: int | None = None) -> None:
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
        self._last_update_time = time.monotonic() - 1 # Inicjalizacja czasu ostatniej aktualizacji

        if current_operation == OPENING:
            self._movement_thread = threading.Thread(target=self._move_cover, args=("open", self._open_time, target_position))
            self._movement_thread.start()
        elif current_operation == CLOSING:
            self._movement_thread = threading.Thread(target=self._move_cover, args=("close", self._close_time, target_position))
            self._movement_thread.start()


    @property
    def kind(self) -> str:
        return "time"

    def update_config_times(self, config: dict) -> None:
        """Update cover timing configuration.
        
        Args:
            config: Dictionary with timing values as TimePeriod objects.
                   Keys: open_time, close_time
        """
        if "open_time" in config:
            self._open_time = config["open_time"].total_milliseconds
        if "close_time" in config:
            self._close_time = config["close_time"].total_milliseconds
    