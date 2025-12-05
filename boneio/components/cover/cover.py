from __future__ import annotations

import asyncio
import logging
import json
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable

from boneio.const import (
    CLOSED,
    CLOSING,
    COVER,
    IDLE,
    OPEN,
    OPENING,
)
from boneio.core.events import EventBus, async_track_point_in_time, utcnow
from boneio.core.messaging import BasicMqtt
from boneio.core.utils import TimePeriod
from boneio.models import CoverState, PositionDict
from boneio.components.output import MCPOutput
from boneio.models.events import CoverEvent

_LOGGER = logging.getLogger(__name__)

class BaseCoverABC(ABC):
    """Base cover class."""

    @abstractmethod
    def __init__(self, id: str,
        open_relay: MCPOutput,
        close_relay: MCPOutput,
        state_save: Callable,
        open_time: TimePeriod,
        close_time: TimePeriod,
        event_bus: EventBus,
        position: int = 100,
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
    async def run_cover(self, current_operation: str, target_position: float | None = None,  target_tilt: float | None = None) -> None:
        """This function is called to run cover after calling open, close, toggle, toggle_open, toggle_close, set_cover_position"""
        pass

    @abstractmethod
    async def send_state(self, state: str, position: float) -> None:
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
    def __init__(self, id: str,
        open_relay: MCPOutput,
        close_relay: MCPOutput,
        state_save: Callable,
        open_time: TimePeriod,
        close_time: TimePeriod,
        event_bus: EventBus,
        position: int = 100,
        name: str | None = None,
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
        self._position = position
        self._initial_position = None
        self._current_operation = IDLE
        _LOGGER.debug(
            "BaseCover %s initialized: open_time=%dms, close_time=%dms, initial_position=%d%%",
            id, self._open_time, self._close_time, position
        )

        self._last_timestamp = time.monotonic()

        self._last_update_time = 0
        self._closed = position <= 0

        self._movement_thread = None
        self._stop_event = threading.Event()

        self._event_bus.add_sigterm_listener(self.on_exit)

        self._loop.call_soon_threadsafe(
            self._loop.call_later,
            0.5,
            self.send_state,
            self.state,
            self.json_position
        )

    async def on_exit(self) -> None:
        """Stop on exit."""
        await self.stop(on_exit=True)

    async def stop(self, on_exit=False) -> None:
        if self._movement_thread and self._movement_thread.is_alive():
            self._stop_event.set()
            self._movement_thread.join(timeout=0.5)
            self._open_relay.turn_off()
            self._close_relay.turn_off()
            self._current_operation = IDLE
            if not on_exit:
                self.send_state(self.state, self.json_position)

    async def open(self) -> None:
        if self._position >= 100:
            return
        estimated_time_s = (100 - self._position) / 100 * self._open_time / 1000
        _LOGGER.info(
            "Opening cover %s from position %d%%. Estimated time: %.1fs (open_time=%dms)",
            self._id, self._position, estimated_time_s, self._open_time
        )
        await self.run_cover(current_operation=OPENING)
        self._message_bus.send_message(topic=f"{self._send_topic}/state", payload=OPENING)

    async def close(self) -> None:
        if self._position <= 0:
            return
        estimated_time_s = self._position / 100 * self._close_time / 1000
        _LOGGER.info(
            "Closing cover %s from position %d%%. Estimated time: %.1fs (close_time=%dms)",
            self._id, self._position, estimated_time_s, self._close_time
        )
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
                self._id, self._position, position, estimated_time_s, self._open_time
            )
            await self.run_cover(current_operation=OPENING, target_position=position)
        elif position < self._position:
            estimated_time_s = position_diff / 100 * self._close_time / 1000
            _LOGGER.info(
                "Setting cover %s position from %d%% to %d%% (CLOSING). Estimated time: %.1fs (close_time=%dms)",
                self._id, self._position, position, estimated_time_s, self._close_time
            )
            await self.run_cover(current_operation=CLOSING, target_position=position)

    async def toggle(self) -> None:
        _LOGGER.debug("Toggle cover %s from input.", self._id)
        if self._position > 50:
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
    def state(self) -> str:
        if self._current_operation == OPENING:
            return OPENING
        elif self._current_operation == CLOSING:
            return CLOSING
        else:
            return CLOSED if self._position == 0 else OPEN

    @property
    def position(self) -> int:
        return round(self._position, 0)

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
            **json_position
        )
        self._event_bus.trigger_event(CoverEvent(
            entity_id=self.id,
            state=event
        ))
        self._message_bus.send_message(topic=f"{self._send_topic}/state", payload=state)
        self._message_bus.send_message(topic=f"{self._send_topic}/pos", payload=json.dumps(json_position))

    def send_state_and_save(self, json_position: PositionDict):
        self.send_state(self.state, json_position)
        self._state_save(json_position)