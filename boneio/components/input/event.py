"""GpioEventButton to receive signals."""

from __future__ import annotations

import logging
import time

from boneio.const import ClickTypes
from boneio.components.input.detectors import MultiClickDetector
from boneio.hardware.gpio.input import GpioBaseClass, get_gpio_manager

_LOGGER = logging.getLogger(__name__)

# TIMINGS FOR BUTTONS
DOUBLE_CLICK_DURATION_MS = 220
LONG_PRESS_DURATION_MS = 400


class GpioEventButton(GpioBaseClass):
    """Represent Gpio input switch with multiclick detection."""

    def __init__(self, **kwargs) -> None:
        """Setup GPIO Event Button with multiclick support."""
        super().__init__(**kwargs)
        
        # Create multiclick detector
        self._detector = MultiClickDetector(
            loop=self._loop,
            callback=self._on_click_detected,
            debounce_ms=self._bounce_time * 1000,  # Convert to ms
            multiclick_window_ms=DOUBLE_CLICK_DURATION_MS,
            hold_threshold_ms=LONG_PRESS_DURATION_MS,
            name=self._name,
            pin=self._pin,
        )
        
        # Register with GPIO manager
        gpio_manager = get_gpio_manager(loop=self._loop)
        gpio_manager.add_input(
            name=self._name,
            pin=self._pin,
            detector=self._detector,
            gpio_mode=kwargs.get("gpio_mode", "gpio"),
        )
        
        _LOGGER.debug("Configured event input %s on pin %s", self._name, self._pin)

    def _on_click_detected(self, click_type: ClickTypes, duration: float | None) -> None:
        """Called by MultiClickDetector when a click is detected.
        
        Args:
            click_type: Type of click (SINGLE, DOUBLE, LONG)
            duration: Duration of the press (for LONG press)
        """
        start_time = time.time()
        _LOGGER.debug(
            "Click detected on %s (%s): %s, duration=%s",
            self._name,
            self._pin,
            click_type,
            duration,
        )
        
        # Call the base class press_callback which handles manager callback and events
        self.press_callback(
            click_type=click_type,
            duration=duration,
            start_time=start_time,
        )