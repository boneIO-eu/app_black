"""GpioEventButtonNew to receive signals."""

from __future__ import annotations

import logging
import time

from boneio.const import BOTH, DOUBLE, LONG, SINGLE
from boneio.helper import ClickTimer, GpioBaseClass
from boneio.helper.gpio import add_event_callback, add_event_detect
from boneio.helper.timeperiod import TimePeriod

_LOGGER = logging.getLogger(__name__)

# TIMINGS FOR BUTTONS
DOUBLE_CLICK_DURATION_MS = 220
LONG_PRESS_DURATION_MS = 400


class GpioEventButtonNew(GpioBaseClass):
    """Represent Gpio input switch."""

    def __init__(self, **kwargs) -> None:
        """Setup GPIO Input Button"""
        super().__init__(**kwargs)
        self._state = self.is_pressed
        self.button_pressed_time = 0.0
        self.last_click_time = 0.0

        # Initialize timers
        self._timer_double = ClickTimer(
            delay=TimePeriod(milliseconds=DOUBLE_CLICK_DURATION_MS),
            action=lambda x: self.single_click_callback(),
        )
        self._timer_long = ClickTimer(
            delay=TimePeriod(milliseconds=LONG_PRESS_DURATION_MS),
            action=lambda x: self.long_click_callback(x),
        )
        
        # State tracking
        self._double_click_possible = False  # True after first click until window expires
        
        add_event_detect(pin=self._pin, edge=BOTH)
        add_event_callback(pin=self._pin, callback=self.check_state)
        _LOGGER.debug("Configured NEW listening for input pin %s", self._pin)

    def single_click_callback(self):
        """Called when double click window expires without second click."""
        if not self._state:  # Only trigger if button is released
            self.press_callback(click_type=SINGLE, duration=None, start_time=self.button_pressed_time)
        self._double_click_possible = False

    def double_click_callback(self):
        """Handle double click."""
        self.press_callback(click_type=DOUBLE, duration=None, start_time=self.button_pressed_time)
        self._double_click_possible = False
        self._timer_double.reset()  # Cancel pending single click

    def long_click_callback(self, duration: float):
        """Handle long press."""
        self._double_click_possible = False  # Cancel any pending clicks
        self._timer_double.reset()
        self.press_callback(click_type=LONG, duration=duration, start_time=self.button_pressed_time)

    def check_state(self, _) -> None:
        """Check state - called from GPIO interrupt (different thread)."""
        # Schedule the actual state handling in the main event loop
        self._loop.call_soon_threadsafe(self._handle_state_change)

    def _handle_state_change(self) -> None:
        """Handle state change in the main event loop thread."""
        time_now = time.time()
        self._state = self.is_pressed

        if self._state:  # Button pressed
            # Ignore bounces
            if time_now - self.button_pressed_time < self._bounce_time:
                return
                
            self.button_pressed_time = time_now
            
            if self._double_click_possible:
                # Second press within window - trigger double click
                self.double_click_callback()
            else:
                # First press - start timers
                self._timer_long.start_timer()
                self._timer_double.start_timer()
                self._double_click_possible = True

        else:  # Button released
            self._timer_long.reset()  # Cancel long press detection