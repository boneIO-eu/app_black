from __future__ import annotations

import logging
import threading
import time

from boneio.const import CLOSE, CLOSING, IDLE, OPEN, OPENING
from boneio.components.cover.cover import BaseCover, BaseVenetianCoverABC
from boneio.core.utils import TimePeriod
from boneio.models import PositionDict

_LOGGER = logging.getLogger(__name__)
COVER_MOVE_UPDATE_INTERVAL = 50  # ms
TILT_MOVE_UPDATE_INTERVAL = 10  # ms
DEFAULT_RESTORED_STATE = {"position": 100, "tilt": 100}


class VenetianCover(BaseCover, BaseVenetianCoverABC):
    """Time-based cover algorithm similar to ESPHome, with tilt support.
    Uses a dedicated thread for precise timing control of cover movement."""

    def __init__(
        self,
        tilt_duration: TimePeriod,  # ms
        actuator_activation_duration: TimePeriod,  # ms
        restored_state: dict = DEFAULT_RESTORED_STATE,
        **kwargs,
    ) -> None:
        self._tilt_duration = (
            tilt_duration.total_milliseconds
        )  # Czas trwania ruchu lameli
        self._initial_tilt_position = int(
            restored_state.get("tilt", DEFAULT_RESTORED_STATE["tilt"])
        )

        position = int(
            restored_state.get("position", DEFAULT_RESTORED_STATE["position"])
        )
        # --- TILT ---
        self._tilt_position = int(
            restored_state.get("tilt", DEFAULT_RESTORED_STATE["tilt"])
        )

        # self._actuator_activation_duration = (
        #     actuator_activation_duration.total_milliseconds
        # )  # ms
        self._last_tilt_update = 0.0

        super().__init__(
            position=position,
            **kwargs,
        )
        _LOGGER.debug(
            "VenetianCover %s initialized: open_time=%dms, close_time=%dms, tilt_duration=%dms, position=%d%%, tilt=%d%%",
            self._id, self._open_time, self._close_time, self._tilt_duration, position, self._tilt_position
        )

    def _move_cover(
        self,
        direction: str,
        duration: float,
        tilt_duration: float,
        target_position: int | None = None,
        target_tilt_position: int | None = None,
    ):
        """Moving cover in separate thread."""
        tilt_delta = abs(self._initial_tilt_position - target_tilt_position) if target_tilt_position is not None else 0
        if direction == OPEN:
            relay = self._open_relay
            total_steps = 100 - self._position
            total_tilt_step = (
                tilt_delta
                if target_tilt_position is not None
                else 100 - self._initial_tilt_position
            )

        elif direction == CLOSE:
            relay = self._close_relay
            total_steps = self._position
            total_tilt_step = (
                tilt_delta
                if target_tilt_position is not None
                else self._initial_tilt_position
            )
        else:
            return
        if target_tilt_position is not None:
            if tilt_delta < 1:
                total_steps = 0
            else:
                total_steps = 1

        if total_steps == 0 or duration == 0:
            self._current_operation = IDLE
            self._loop.call_soon_threadsafe(
                self.send_state, self.state, self.json_position
            )
            return

        relay.turn_on()
        start_time = time.monotonic()
        progress = 0.0
        tilt_progress = 0.0
        needed_tilt_duration = tilt_duration * (total_tilt_step / 100)
        if target_tilt_position is None:
            tilt_delta = 1.0
            

        while not self._stop_event.is_set():
            current_time = (
                time.monotonic()
            )  # Pobierz aktualny czas tylko raz na iterację
            elapsed_time = (
                current_time - start_time
            ) * 1000  # Konwersja na milisekundy

           
            if elapsed_time < needed_tilt_duration:
                tilt_progress = elapsed_time / needed_tilt_duration
                progress = 0.0
            else:
                tilt_progress = 1.0
                progress = (elapsed_time - needed_tilt_duration) / duration

            if direction == OPEN:
                # Obliczanie _position dla kierunku OPEN
                self._position = min(100.0, self._initial_position + progress * 100)

                # Obliczanie _tilt_position dla kierunku OPEN
                if target_tilt_position is not None:
                    self._tilt_position = min(target_tilt_position, self._initial_tilt_position + tilt_progress * tilt_delta)
                else: # Fallback jeśli nie ma target_tilt_position
                    self._tilt_position = min(
                        100.0, self._initial_tilt_position + tilt_progress * (100 - self._initial_tilt_position)
                    )
            elif direction == CLOSE:
                # Obliczanie _position dla kierunku CLOSE
                self._position = max(0.0, self._initial_position - progress * 100)

                # Obliczanie _tilt_position dla kierunku CLOSE
                if target_tilt_position is not None:
                    self._tilt_position = max(target_tilt_position, self._initial_tilt_position - tilt_progress * tilt_delta)
                else: # Fallback jeśli nie ma target_tilt_position
                    self._tilt_position = max(
                        0.0, self._initial_tilt_position - tilt_progress * self._initial_tilt_position
                    )

            self._last_timestamp = current_time  # Użyj pobranego czasu
            if current_time - self._last_update_time >= 1:
                self._loop.call_soon_threadsafe(
                    self.send_state, self.state, self.json_position
                )
                self._last_update_time = current_time

            if target_tilt_position is not None:
                if (
                    direction == OPEN and self._tilt_position >= target_tilt_position
                ) or (
                    direction == CLOSE and self._tilt_position <= target_tilt_position
                ):
                    break

            if target_position is not None:
                if (direction == OPEN and self._position >= target_position) or (
                    direction == CLOSE and self._position <= target_position
                ):
                    break

            if progress >= 1.0 or (target_tilt_position and tilt_progress >= 1.0):
                break

            if target_tilt_position is not None and abs(self._tilt_position - target_tilt_position) < 5:
                time.sleep(0.01)
            else:
                time.sleep(0.05)
        relay.turn_off()
        self._current_operation = IDLE
        self._loop.call_soon_threadsafe(
            self.send_state_and_save, self.json_position
        )
        self._last_update_time = (
            time.monotonic()
        )  # Upewnij się, że aktualizacja jest wysłana na końcu ruchu

    async def set_tilt(self, tilt_position: int) -> None:
        """Setting tilt position."""
        if not 0 <= tilt_position <= 100:
            raise ValueError("Tilt position must be in range from 0 to 100.")

        if abs(self._tilt_position - tilt_position) < 1:
            return

        tilt_diff = abs(self._tilt_position - tilt_position)
        estimated_time_s = tilt_diff / 100 * self._tilt_duration / 1000
        
        if tilt_position > self._tilt_position:
            _LOGGER.info(
                "Setting tilt %s from %d%% to %d%% (OPENING). Estimated time: %.2fs (tilt_duration=%dms)",
                self._id, self._tilt_position, tilt_position, estimated_time_s, self._tilt_duration
            )
            await self.run_cover(
                current_operation=OPENING, target_tilt_position=tilt_position
            )
        elif tilt_position < self._tilt_position:
            _LOGGER.info(
                "Setting tilt %s from %d%% to %d%% (CLOSING). Estimated time: %.2fs (tilt_duration=%dms)",
                self._id, self._tilt_position, tilt_position, estimated_time_s, self._tilt_duration
            )
            await self.run_cover(
                current_operation=CLOSING, target_tilt_position=tilt_position
            )

    @property
    def json_position(self) -> PositionDict:
        return {"position": round(self.position, 0), "tilt": self.tilt}

    @property
    def tilt(self) -> int:
        return int(round(self._tilt_position, 0))

    @property
    def tilt_position(self) -> int:
        """Return tilt position (required by BaseVenetianCoverABC)."""
        return self.tilt

    @property
    def tilt_current_operation(self) -> str:
        """Return current tilt operation (required by BaseVenetianCoverABC)."""
        return self._current_operation

    @property
    def last_tilt_timestamp(self) -> float:
        """Return last tilt timestamp (required by BaseVenetianCoverABC)."""
        return self._last_tilt_update

    @property
    def kind(self) -> str:
        return "venetian"

    async def set_cover_tilt_position(self, position: int) -> None:
        """Set cover tilt position (required by BaseVenetianCoverABC)."""
        await self.set_tilt(position)

    async def tilt_open(self) -> None:
        """Opening only tilt cover."""
        estimated_time_s = (100 - self._tilt_position) / 100 * self._tilt_duration / 1000
        _LOGGER.info(
            "Opening tilt cover %s from %d%%. Estimated time: %.2fs (tilt_duration=%dms)",
            self._id, self._tilt_position, estimated_time_s, self._tilt_duration
        )
        await self.set_tilt(tilt_position=100)

    async def tilt_close(self) -> None:
        """Closing only tilt cover."""
        estimated_time_s = self._tilt_position / 100 * self._tilt_duration / 1000
        _LOGGER.info(
            "Closing tilt cover %s from %d%%. Estimated time: %.2fs (tilt_duration=%dms)",
            self._id, self._tilt_position, estimated_time_s, self._tilt_duration
        )
        await self.set_tilt(tilt_position=0)

    def update_config_times(self, config: dict) -> None:
        """Update cover timing configuration.
        
        Args:
            config: Dictionary with timing values as TimePeriod objects.
                   Keys: open_time, close_time, tilt_duration
        """
        if "open_time" in config:
            self._open_time = config["open_time"].total_milliseconds
        if "close_time" in config:
            self._close_time = config["close_time"].total_milliseconds
        if "tilt_duration" in config and config["tilt_duration"]:
            self._tilt_duration = config["tilt_duration"].total_milliseconds

    async def run_cover(
        self,
        current_operation: str,
        target_position: int | None = None,
        target_tilt_position: int | None = None,
    ) -> None:
        if self._movement_thread and self._movement_thread.is_alive():
            _LOGGER.warning("Cover movement is already in progress. Stopping first.")
            await self.stop()

        self._current_operation = current_operation
        self._initial_position = self._position
        self._initial_tilt_position = self._tilt_position
        self._stop_event.clear()
        self._last_update_time = (
            time.monotonic()
        )  # Inicjalizacja czasu ostatniej aktualizacji

        if current_operation == OPENING:
            self._movement_thread = threading.Thread(
                target=self._move_cover,
                args=(
                    "open",
                    self._open_time,
                    self._tilt_duration,
                    target_position,
                    target_tilt_position,
                ),
            )
            self._movement_thread.start()
        elif current_operation == CLOSING:
            self._movement_thread = threading.Thread(
                target=self._move_cover,
                args=(
                    "close",
                    self._close_time,
                    self._tilt_duration,
                    target_position,
                    target_tilt_position,
                ),
            )
            self._movement_thread.start()
