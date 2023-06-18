"""GPIOInputButton to receive signals."""
from __future__ import annotations
import time
import logging
from functools import partial
from boneio.const import DOUBLE, LONG, SINGLE, ClickTypes, BOTH
from boneio.helper import GpioBaseClass, ClickTimer
from boneio.helper.gpio import add_event_callback, add_event_detect
from boneio.helper.timeperiod import TimePeriod
# TIMINGS FOR BUTTONS


_LOGGER = logging.getLogger(__name__)

DOUBLE_CLICK_DURATION_MS = 250
LONG_PRESS_DURATION_MS = 500

class GpioInputButton(GpioBaseClass):
    """Represent Gpio input switch."""

    def __init__(self, **kwargs) -> None:
        """Setup GPIO Input Button"""
        super().__init__(**kwargs)
        self._state = self.is_pressed
        self.button_pressed_time = 0.0
        self._debounce_time: float = self._bounce_time.total_in_seconds
        self._period_to_wait_for_2nd_click: float = self._debounce_time

        self._timer_single = ClickTimer(
            delay=TimePeriod(milliseconds=self._period_to_wait_for_2nd_click),
            action=lambda x: self.press_callback(click_type=SINGLE),
        )

        self._timer_double = ClickTimer(
            delay=TimePeriod(milliseconds=DOUBLE_CLICK_DURATION_MS),
            action=lambda x: None,
        )
        self._timer_long = ClickTimer(
            delay=TimePeriod(milliseconds=LONG_PRESS_DURATION_MS),
            action=lambda x: self.press_callback(click_type=LONG),
        )
        self._double_click_ran = False
        self._is_waiting_for_second_click = False
        self._long_press_ran = False

        add_event_detect(pin=self._pin, edge=BOTH)
        add_event_callback(pin=self._pin, callback=self.check_state)
        _LOGGER.debug("Configured listening for input pin %s", self._pin)


    def check_state(self, channel) -> None:
        self._state = self.is_pressed
        time_now = time.time()
        if self._state:
            if time_now - self.button_pressed_time >= self._debounce_time:
                self.button_pressed_time = time_now
                self._timer_long.start_timer()
                self._timer_single.reset()
                if self._timer_double.is_waiting():
                    self._double_click_ran = True
                    self.press_callback(click_type=DOUBLE)
                    return
                else:
                    self._timer_double.start_timer()
                    self._is_waiting_for_second_click = True

        else:
            if not self._is_waiting_for_second_click and not self._double_click_ran:
                if self._timer_long.is_waiting():
                    self.press_callback(click_type=SINGLE)
            elif self._is_waiting_for_second_click:
                self._timer_single.start_timer()
            self._timer_long.reset()
            self._double_click_ran = False

    def reset_all_timers(self) -> None:
        self._is_waiting_for_second_click = False
        self._timer_single.reset()
        self._timer_double.reset()
        self._timer_long.reset()

    def press_callback(self, click_type: ClickTypes):
        _LOGGER.debug("Detected press %s", click_type)
        self.reset_all_timers()
        self._loop.call_soon_threadsafe(
            partial(self._press_callback, click_type, self._pin)
        )
