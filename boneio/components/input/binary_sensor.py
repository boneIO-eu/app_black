"""GpioInputBinarySensor to receive signals."""

from __future__ import annotations

import logging

from boneio.components.input.detectors import BinarySensorDetector
from boneio.const import BinaryStateTypes, PRESSED, RELEASED
from boneio.hardware.gpio.input import GpioBaseClass, get_gpio_manager

_LOGGER = logging.getLogger(__name__)


class GpioInputBinarySensor(GpioBaseClass):
    """Represent Gpio binary sensor on input boards."""

    def __init__(self, **kwargs) -> None:
        """Setup GPIO Binary Sensor with state detection."""
        super().__init__(**kwargs)
        
        # Determine if inverted
        inverted = kwargs.get("inverted", False)
        self._inverted = inverted
        
        # Set click types based on inversion
        self._click_type = (
            (RELEASED, PRESSED) if inverted else (PRESSED, RELEASED)
        )
        
        # Create binary sensor detector
        self._detector = BinarySensorDetector(
            loop=self._loop,
            callback=self._on_state_changed,
            debounce_ms=self._bounce_time * 1000,  # Convert to ms
            inverted=inverted,
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
        
        _LOGGER.debug("Configured binary sensor %s on pin %s (inverted=%s)", 
                     self._name, self._pin, inverted)
        
        # Send initial state if requested
        if kwargs.get("initial_send", False):
            self._loop.call_soon(self._send_initial_state)

    def _send_initial_state(self) -> None:
        """Send initial state after setup."""
        # Read current state from GPIO manager
        from boneio.hardware.gpio.input.base import read_input
        current_value = read_input(self._pin)
        
        # Determine state based on inversion
        is_pressed = not current_value if not self._inverted else current_value
        state_str = PRESSED if is_pressed else RELEASED
        
        _LOGGER.debug("Sending initial state for %s: %s", self._name, state_str)
        self.press_callback(
            click_type=state_str,
            duration=None,
            start_time=0.0,
        )

    def _on_state_changed(self, state: BinaryStateTypes, timestamp: float) -> None:
        """Called by BinarySensorDetector when state changes.
        
        Args:
            state: New state (PRESSED or RELEASED)
            timestamp: Timestamp of the change
        """
        _LOGGER.debug(
            "State changed for %s (%s): %s at %.3f",
            self._name,
            self._pin,
            state,
            timestamp,
        )
        
        # Update internal state
        self._state = (state == PRESSED)
        
        # Call the base class press_callback
        self.press_callback(
            click_type=state,
            duration=None,
            start_time=timestamp,
        )
