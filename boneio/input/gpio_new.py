"""GpioEventButtonNew to receive signals."""
from __future__ import annotations
import time
import logging
from boneio.const import DOUBLE, LONG, SINGLE, BOTH
from boneio.helper import GpioBaseClass, ClickTimer
from boneio.helper.gpio import edge_detect
from boneio.helper.timeperiod import TimePeriod
_LOGGER = logging.getLogger(__name__)

# TIMINGS FOR BUTTONS
DOUBLE_CLICK_DURATION_MS = 180
LONG_PRESS_DURATION_MS = 600


class GpioEventButtonNew(GpioBaseClass):
    """Represent Gpio input switch."""

    def __init__(self, **kwargs) -> None:
        """Setup GPIO Input Button"""
        super().__init__(**kwargs)
        self._state = self.is_pressed
        self.button_pressed_time = 0.0
        self.last_click_time = 0.0
        self._double_test = None
        self._long_test = None

        self._timer_double = ClickTimer(
            delay=TimePeriod(milliseconds=DOUBLE_CLICK_DURATION_MS),
            action=lambda x: self.single_click_callback(),
        )
        self._timer_long = ClickTimer(
            delay=TimePeriod(milliseconds=LONG_PRESS_DURATION_MS),
            action=lambda x: self.long_click_callback(x),
        )
        self._double_click_ran = False
        self._long_press_ran = False
        edge_detect(pin=self._pin, callback=self.check_state, bounce=0, edge=BOTH)
        _LOGGER.debug("Configured NEW listening for input pin %s", self._pin)

    def single_click_callback(self):
        """This is invoked by double timer if time is up for double timer."""
        if not self._state and not self._timer_long.is_waiting():
            self.press_callback(click_type=SINGLE, duration=None)

    def double_click_callback(self):
        """This is double click callback."""
        self.press_callback(click_type=DOUBLE, duration=None)

    def long_click_callback(self, duration: float):
        """This is long click callback."""
        self.press_callback(click_type=LONG, duration=duration)

    def check_state(self, _) -> None:
        time_now = time.time()
        self._state = self.is_pressed
        if self._state:
            if time_now - self.button_pressed_time >= self._bounce_time:
                self.button_pressed_time = time_now
                self._timer_long.start_timer()
                if self._timer_double.is_waiting():
                    self._timer_double.reset()
                    self._double_click_ran = True
                    self.double_click_callback()
                    return
                self._timer_double.start_timer()

        else:
            if not self._timer_double.is_waiting() and not self._double_click_ran:
                if self._timer_long.is_waiting():
                    self.press_callback(click_type=SINGLE, duration=None)
            self._timer_long.reset()
            self._double_click_ran = False

