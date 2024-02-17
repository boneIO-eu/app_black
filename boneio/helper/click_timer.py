from __future__ import annotations
import logging
import asyncio
from boneio.helper.timeperiod import TimePeriod
import time

_LOGGER = logging.getLogger(__name__)


class ClickTimer:
    """Represent async call later function with variable to check if timing is ON."""

    def __init__(self, delay: TimePeriod, action) -> None:
        """Initialize Click timer."""
        self._loop = asyncio.get_running_loop()
        self._remove_listener = None
        self._delay: float = delay.total_in_seconds
        self._action = action

    def is_waiting(self) -> bool:
        """If variable is set then timer is ON, if None is Off."""
        return self._remove_listener is not None
    
    @property
    def delay(self) -> float:
        return self._delay

    def reset(self) -> None:
        """Uninitialize variable remove_listener."""
        if self._remove_listener:
            self._remove_listener.cancel()
            self._remove_listener = None

    async def _start_async_timer(self) -> None:
        start = time.time()
        await asyncio.sleep(self._delay)
        self._remove_listener = None
        self._action(round(time.time() - start, 2))

    def start_timer(self) -> None:
        """Start timer."""
        self._remove_listener = self._loop.create_task(self._start_async_timer())
