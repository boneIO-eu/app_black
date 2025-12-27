"""GpioEventButton to receive signals."""

from __future__ import annotations

import logging
import time

from boneio.const import ClickTypes
from boneio.components.input.detectors import MultiClickDetector
from boneio.hardware.gpio.input import GpioBaseClass, get_gpio_manager
from boneio.core.utils import TimePeriod

_LOGGER = logging.getLogger(__name__)

# DEFAULT TIMINGS FOR BUTTONS (can be overridden in config)
DEFAULT_DOUBLE_CLICK_DURATION_MS = 220
DEFAULT_LONG_PRESS_DURATION_MS = 400
DEFAULT_SEQUENCE_WINDOW_MS = 500


def _to_milliseconds(value, default_ms: int) -> int:
    """Convert a value to milliseconds.
    
    Args:
        value: Can be int, float, TimePeriod, or None
        default_ms: Default value in milliseconds if value is None
        
    Returns:
        Value in milliseconds as integer
    """
    if value is None:
        return default_ms
    if isinstance(value, TimePeriod):
        return int(value.total_milliseconds)
    if isinstance(value, (int, float)):
        return int(value)
    return default_ms


class GpioEventButton(GpioBaseClass):
    """Represent Gpio input switch with multiclick detection."""

    def __init__(self, **kwargs) -> None:
        """Setup GPIO Event Button with multiclick support.
        
        Args:
            double_click_duration: Time window in ms to detect double click (default: 220ms)
            long_press_duration: Time in ms to detect long press (default: 400ms)
            sequence_window_duration: Time window in ms to detect sequences (default: 500ms)
            **kwargs: Additional arguments passed to GpioBaseClass
        """
        super().__init__(**kwargs)
        
        # Get timing values from config or use defaults, converting TimePeriod to ms
        double_click_duration = _to_milliseconds(
            kwargs.get('double_click_duration'),
            DEFAULT_DOUBLE_CLICK_DURATION_MS
        )
        long_press_duration = _to_milliseconds(
            kwargs.get('long_press_duration'),
            DEFAULT_LONG_PRESS_DURATION_MS
        )
        sequence_window_duration = _to_milliseconds(
            kwargs.get('sequence_window_duration'),
            DEFAULT_SEQUENCE_WINDOW_MS
        )
        
        # Create multiclick detector
        self._detector = MultiClickDetector(
            loop=self._loop,
            callback=self._on_click_detected,
            debounce_ms=self._bounce_time * 1000,  # Convert to ms
            multiclick_window_ms=double_click_duration,
            hold_threshold_ms=long_press_duration,
            sequence_window_ms=sequence_window_duration,
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

    def update_timings(
        self,
        double_click_duration: int | float | None = None,
        long_press_duration: int | float | None = None,
        sequence_window_duration: int | float | None = None,
    ) -> None:
        """Update timing parameters for click detection.
        
        This method allows updating timing parameters at runtime without
        recreating the detector. Useful for config reload.
        
        Args:
            double_click_duration: Time window in ms to detect double click
            long_press_duration: Time in ms to detect long press
            sequence_window_duration: Time window in ms to detect sequences
        """
        if double_click_duration is not None:
            value_ms = _to_milliseconds(double_click_duration, DEFAULT_DOUBLE_CLICK_DURATION_MS)
            self._detector._multiclick_window = value_ms / 1000.0
            _LOGGER.debug("Updated double_click_duration to %dms for %s", value_ms, self._name)
        
        if long_press_duration is not None:
            value_ms = _to_milliseconds(long_press_duration, DEFAULT_LONG_PRESS_DURATION_MS)
            self._detector._hold_threshold = value_ms / 1000.0
            _LOGGER.debug("Updated long_press_duration to %dms for %s", value_ms, self._name)
        
        if sequence_window_duration is not None:
            value_ms = _to_milliseconds(sequence_window_duration, DEFAULT_SEQUENCE_WINDOW_MS)
            self._detector._sequence_window = value_ms / 1000.0
            _LOGGER.debug("Updated sequence_window_duration to %dms for %s", value_ms, self._name)