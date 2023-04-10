from __future__ import annotations
import asyncio
from boneio.helper.events import async_call_later_miliseconds


class ClickTimer:
    """Represent async call later function with variable to check if timing is ON."""

    def __init__(self, delay: float, action) -> None:
        """Initialize Click timer."""
        self._loop = asyncio.get_running_loop()
        self._remove_listener = None
        self._delay = delay
        self._action = action

    def is_waiting(self) -> bool:
        """If variable is set then timer is ON, if None is Off."""
        return self._remove_listener is not None

    def action(self, x: float) -> None:
        """Reset Call later variable and call action."""
        self.reset()
        self._action(x)

    def reset(self) -> None:
        """Uninitialize variable remove_listener."""
        if self._remove_listener:
            self._remove_listener()
            self._remove_listener = None

    def start_timer(self) -> None:
        """Start timer."""
        self._remove_listener = async_call_later_miliseconds(
            loop=self._loop,
            action=self.action,
            delay=self._delay,
        )
