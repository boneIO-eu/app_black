"""GpioEventButtonBeta to receive signals."""
from __future__ import annotations
import time
import logging
from functools import partial
from boneio.const import DOUBLE, LONG, SINGLE, ClickTypes, BOTH
from boneio.helper import GpioBaseClass, ClickTimer
from boneio.helper.gpio import add_event_callback, add_event_detect
from boneio.helper.timeperiod import TimePeriod
# TIMINGS FOR BUTTONS


DOUBLE_CLICK_TIME = 0.35  # Maximum time between two clicks for a double-click
LONG_CLICK_TIME = 0.6  # Minimum time for a long click
DEBOUNCE_TIME = 0.05
_LOGGER = logging.getLogger(__name__)


DOUBLE_CLICK_DURATION_MS = 300
LONG_PRESS_DURATION_MS = 600


class GpioEventButtonBeta(GpioBaseClass):
    """Represent Gpio input switch."""

    def __init__(self, **kwargs) -> None:
        """Setup GPIO Input Button"""
        super().__init__(**kwargs)
        self._state = self.is_pressed
        self.button_pressed_time = 0.0
        self.click_count = 0
        self.last_click_time = 0.0
        self._double_test = None
        self._long_test = None

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

        add_event_detect(pin=self._pin, edge=BOTH)
        add_event_callback(pin=self._pin, callback=self.check_state)
        _LOGGER.debug("Configured BETA listening for input pin %s", self._pin)

    def double_click_press_callback(self):
        self._is_waiting_for_second_click = False
        if not self._state and not self._timer_long.is_waiting():
            self.press_callback(click_type=SINGLE, duration=None)

    def check_state(self, channel) -> None:
        time_now = time.time()
        self._state = self.is_pressed
        if self._state:
            if time_now - self.button_pressed_time >= DEBOUNCE_TIME:
                self.button_pressed_time = time_now
                self.click_count += 1
                self._timer_long.start_timer()
                if self._timer_double.is_waiting():
                    self._timer_double.reset()
                    self._double_click_ran = True
                    self.press_callback(click_type=DOUBLE, duration=None)
                    return
                self._timer_double.start_timer()
                self._is_waiting_for_second_click = True

        else:
            if not self._is_waiting_for_second_click and not self._double_click_ran:
                if self._timer_long.is_waiting():
                    self.press_callback(click_type=SINGLE, duration=None)
            self._timer_long.reset()
            self._double_click_ran = False

    def press_callback(self, click_type: ClickTypes, duration: float | None = None):
        self.click_count = 0
        self._loop.call_soon_threadsafe(
            partial(self._press_callback, click_type, self._pin, duration)
        )
