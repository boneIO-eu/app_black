"""GpioEventButton to receive signals."""
from __future__ import annotations
import logging
import asyncio
from boneio.const import DOUBLE, LONG, SINGLE
from boneio.helper import GpioBaseClass, ClickTimer, TimePeriod


# TIMINGS FOR BUTTONS

DOUBLE_CLICK_DURATION_MS = 350
LONG_PRESS_DURATION_MS = 600

_LOGGER = logging.getLogger(__name__)


class GpioEventButton(GpioBaseClass):
    """Represent Gpio input switch."""

    def __init__(self, **kwargs) -> None:
        """Setup GPIO Input Button"""
        super().__init__(**kwargs)
        self._state = self.is_pressed
        _LOGGER.debug("Configured stable listening for input pin %s", self._pin)
        self._timer_double = ClickTimer(
            delay=TimePeriod(milliseconds=DOUBLE_CLICK_DURATION_MS),
            action=lambda x: self.double_click_press_callback(),
        )
        self._timer_long = ClickTimer(
            delay=TimePeriod(milliseconds=LONG_PRESS_DURATION_MS),
            action=lambda x: self.press_callback(click_type=LONG, duration=x),
        )
        self._double_click_ran = False
        self._is_waiting_for_second_click = False
        self._long_press_ran = False
        asyncio.create_task(self._run())

    def double_click_press_callback(self):
        self._is_waiting_for_second_click = False
        if not self._state and not self._timer_long.is_waiting():
            self.press_callback(click_type=SINGLE, duration=None)

    async def _run(self) -> None:
        while True:
            self.check_state(state=self.is_pressed)
            await asyncio.sleep(self._bounce_time)

    def check_state(self, state: bool) -> None:
        if state == self._state:
            return
        self._state = state
        if state: #is pressed?
            self._timer_long.start_timer()
            if self._timer_double.is_waiting():
                self._timer_double.reset()
                self._double_click_ran = True
                self.press_callback(click_type=DOUBLE, duration=None)
            else:
                self._timer_double.start_timer()
                self._is_waiting_for_second_click = True

        else: #is released?
            if not self._is_waiting_for_second_click and not self._double_click_ran:
                if self._timer_long.is_waiting():
                    self.press_callback(click_type=SINGLE, duration=None)
            self._timer_long.reset()
            self._double_click_ran = False
