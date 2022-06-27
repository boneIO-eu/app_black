"""GPIOInputButton to receive signals."""
import logging
from datetime import datetime, timedelta
from functools import partial

from boneio.const import DOUBLE, LONG, SINGLE
from boneio.helper import GpioBaseClass, edge_detect

# TIMINGS FOR BUTTONS
DEBOUNCE_DURATION = timedelta(microseconds=150000)
LONG_PRESS_DURATION = timedelta(microseconds=700000)
DELAY_DURATION = 0.08
SECOND_DELAY_DURATION = 0.14

_LOGGER = logging.getLogger(__name__)


class GpioInputButton(GpioBaseClass):
    """Represent Gpio input switch."""

    def __init__(self, **kwargs) -> None:
        """Setup GPIO Input Button"""
        super().__init__(**kwargs)
        edge_detect(
            self._pin,
            callback=self._handle_press,
            bounce=self._bounce_time.total_milliseconds,
        )
        self._first_press_timestamp = None
        self._is_long_press = False
        self._second_press_timestamp = None
        self._second_check = False
        _LOGGER.debug("Configured listening for input pin %s", self._pin)

    def _handle_press(self, pin: str) -> None:
        """Handle the button press callback"""
        # Ignore if we are in a long press
        if self._is_long_press:
            return
        now = datetime.now()

        # Debounce button
        if (
            self._first_press_timestamp is not None
            and now - self._first_press_timestamp < DEBOUNCE_DURATION
        ):
            return

        # Second click debounce. Just in case.
        if (
            self._second_press_timestamp is not None
            and now - self._second_press_timestamp < DEBOUNCE_DURATION
        ):
            return
        if not self._first_press_timestamp:
            self._first_press_timestamp = now
        elif not self._second_press_timestamp:
            self._second_press_timestamp = now

        self._loop.call_soon_threadsafe(
            self._loop.call_later,
            DELAY_DURATION,
            self.check_press_length,
        )

    def check_press_length(self) -> None:
        """Check if it's a single, double or long press"""
        # Check if button is still pressed
        if self.is_pressed:
            # Schedule a new check
            self._loop.call_soon_threadsafe(
                self._loop.call_later,
                DELAY_DURATION,
                self.check_press_length,
            )

            # Handle edge case due to multiple clicks
            if self._first_press_timestamp is None:
                return

            # Check if we reached a long press
            diff = datetime.now() - self._first_press_timestamp
            if not self._is_long_press and diff > LONG_PRESS_DURATION:
                self._is_long_press = True
                _LOGGER.debug("Long button press on pin %s, call callback", self._pin)
                self._loop.call_soon_threadsafe(
                    partial(self._press_callback, LONG, self._pin)
                )
            return

        # Handle short press
        if not self._is_long_press:
            if not self._second_press_timestamp and not self._second_check:
                # let's try to check if second click will atempt
                self._second_check = True
                self._loop.call_soon_threadsafe(
                    self._loop.call_later,
                    SECOND_DELAY_DURATION,
                    self.check_press_length,
                )
                return
            if self._second_check:
                if self._second_press_timestamp:
                    _LOGGER.debug(
                        "Double click event on pin %s, diff %s",
                        self._pin,
                        self._second_press_timestamp - self._first_press_timestamp,
                    )
                    self._loop.call_soon_threadsafe(
                        partial(self._press_callback, DOUBLE, self._pin)
                    )

                elif self._first_press_timestamp:
                    _LOGGER.debug("One click event on pin %s, call callback", self._pin)
                    self._loop.call_soon_threadsafe(
                        partial(self._press_callback, SINGLE, self._pin)
                    )

        # Clean state on button released
        self._first_press_timestamp = None
        self._second_press_timestamp = None
        self._second_check = False
        self._is_long_press = False
