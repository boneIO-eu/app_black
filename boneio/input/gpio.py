"""GPIOInputButton to receive signals."""
from __future__ import annotations
import logging
import asyncio
from datetime import timedelta
from functools import partial
from boneio.const import DOUBLE, LONG, SINGLE, ClickTypes
from boneio.helper import GpioBaseClass, ClickTimer


# TIMINGS FOR BUTTONS

DEBOUNCE_DURATION = timedelta(microseconds=150000)
DOUBLE_CLICK_DURATION_MS = 350
LONG_PRESS_DURATION_MS = 700

_LOGGER = logging.getLogger(__name__)


class GpioInputButton(GpioBaseClass):
    """Represent Gpio input switch."""

    def __init__(self, **kwargs) -> None:
        """Setup GPIO Input Button"""
        super().__init__(**kwargs)
        self._state = self.is_pressed
        _LOGGER.debug("Configured listening for input pin %s", self._pin)
        self._timer_double = ClickTimer(
            delay=DOUBLE_CLICK_DURATION_MS,
            action=lambda x: self.double_click_press_callback(),
        )
        self._timer_long = ClickTimer(
            delay=LONG_PRESS_DURATION_MS,
            action=lambda x: self.press_callback(click_type=LONG),
        )
        self._double_click_ran = False
        self._is_waiting_for_second_click = False
        self._long_press_ran = False
        asyncio.create_task(self._run())

    def press_callback(self, click_type: ClickTypes):
        self._loop.call_soon_threadsafe(
            partial(self._press_callback, click_type, self._pin)
        )

    def double_click_press_callback(self):
        self._is_waiting_for_second_click = False
        if not self._state and not self._timer_long.is_waiting():
            self.press_callback(click_type=SINGLE)

    async def _run(self) -> None:
        while True:
            self.check_state(state=self.is_pressed)
            await asyncio.sleep(self._bounce_time.total_in_seconds)

    def check_state(self, state: bool) -> None:
        if state == self._state:
            return
        self._state = state
        if state:
            self._timer_long.start_timer()
            if self._timer_double.is_waiting():
                self._timer_double.reset()
                self._double_click_ran = True
                self.press_callback(click_type=DOUBLE)
            else:
                self._timer_double.start_timer()
                self._is_waiting_for_second_click = True

        else:
            if not self._is_waiting_for_second_click and not self._double_click_ran:
                if self._timer_long.is_waiting():
                    self.press_callback(click_type=SINGLE)
            self._timer_long.reset()
            self._double_click_ran = False
