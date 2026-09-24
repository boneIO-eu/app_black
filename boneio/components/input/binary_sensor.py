"""GpioInputBinarySensor to receive signals."""

from __future__ import annotations

import logging
import time
from typing import cast

from boneio.components.input.detectors import BinarySensorDetector
from boneio.const import PRESSED, RELEASED, BinaryStateTypes, ClickTypes
from boneio.core.utils.timeperiod import parse_time_to_ms
from boneio.hardware.gpio.input import GpioBaseClass, get_gpio_manager
from boneio.models import InputState
from boneio.models.events import InputEvent

_LOGGER = logging.getLogger(__name__)

# Matches the binary_sensor bounce_time default in schema.yaml. Needed on the
# hot-reload path, which reads the YAML without running Cerberus, so an
# omitted bounce_time arrives as None rather than as the schema default.
DEFAULT_BOUNCE_TIME_MS = 120


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
        )
        
        _LOGGER.debug("Configured binary sensor %s on pin %s (inverted=%s)", 
                     self._name, self._pin, inverted)
        
        # Send initial state if requested - register callback to run after GPIO manager starts
        if kwargs.get("initial_send", False):
            gpio_manager.register_on_start_callback(self._send_initial_state)

    def update_inverted(self, inverted: bool) -> bool:
        """Apply a new ``inverted`` setting to a running sensor.

        Polarity is decided in ``__init__`` and baked into the detector, so a
        config reload alone used to leave the running sensor on the old
        polarity until the application was restarted.

        Args:
            inverted: New inverted flag from the reloaded config.

        Returns:
            True if the polarity actually changed (caller should re-publish
            the state), False if it was already set that way.
        """
        inverted = bool(inverted)
        if inverted == self._inverted:
            return False

        self._inverted = inverted
        self._click_type = (RELEASED, PRESSED) if inverted else (PRESSED, RELEASED)

        # Re-read the pin and re-anchor the detector with the new polarity.
        gpio_manager = get_gpio_manager(loop=self._loop)
        current_value = gpio_manager.read_value(self._pin)
        is_pressed = current_value if inverted else not current_value
        self._detector.resync(inverted=inverted, current_state=is_pressed)

        _LOGGER.info(
            "Binary sensor %s (%s): inverted changed to %s without restart",
            self._name,
            self._pin,
            inverted,
        )
        return True

    def update_bounce_time(self, bounce_time) -> bool:
        """Apply a new debounce window to a running sensor.

        Like ``inverted``, ``bounce_time`` is read in ``__init__`` and handed to
        the detector, so a config reload used to leave the old window in place
        until the application was restarted.

        Args:
            bounce_time: Value straight from the reloaded config — a TimePeriod
                at startup, but a bare number of milliseconds (WebUI) or a string
                such as "120ms" (hand-written YAML) on the hot-reload path, which
                skips Cerberus coercion. ``None`` means the schema default.

        Returns:
            True if the window actually changed.
        """
        seconds = parse_time_to_ms(bounce_time, DEFAULT_BOUNCE_TIME_MS) / 1000.0
        if seconds == self._bounce_time:
            return False

        self._bounce_time = seconds
        self._detector.set_debounce(seconds)
        _LOGGER.info(
            "Binary sensor %s (%s): bounce_time changed to %.0fms without restart",
            self._name,
            self._pin,
            seconds * 1000,
        )
        return True

    def _send_initial_state(self) -> None:
        """Send initial state after setup."""
        self.send_current_state()

    def send_current_state(self) -> None:
        """Send current state to MQTT without triggering actions.
        
        This can be called on startup (if initial_send=True) or after config reload.
        Only publishes state to MQTT broker, does not execute any configured actions.
        """
        # Read current state from GPIO manager
        gpio_manager = get_gpio_manager(loop=self._loop)
        current_value = gpio_manager.read_value(self._pin)
        
        # Determine state based on inversion
        is_pressed = not current_value if not self._inverted else current_value
        state_str = PRESSED if is_pressed else RELEASED
        
        # Update internal state (for UI display via WebSocket)
        self._state = is_pressed
        self._last_state = state_str
        
        _LOGGER.debug("Publishing current state for %s: %s (publish_only)", self._name, state_str)
        
        # Use publish_only=True to send to MQTT without executing actions
        self._publish_state_only(state_str)

    def _publish_state_only(self, state_str: str) -> None:
        """Publish state to MQTT without triggering actions.
        
        Creates an InputEvent with publish_only=True flag, which tells
        the InputManager to only publish to MQTT without executing actions.
        
        Args:
            state_str: State string (PRESSED or RELEASED)
        """
        timestamp = time.time()
        
        # Create event state
        event_state = InputState(
            name=self.name,
            pin=self._pin,
            state=state_str,
            type=self.input_type,
            timestamp=timestamp,
            boneio_input=self.boneio_input,
            area=self.area,
        )
        
        # Trigger event with publish_only=True
        self._event_bus.trigger_event(InputEvent(
            entity_id=self.id,
            click_type=cast(ClickTypes, state_str),
            duration=None,
            state=event_state,
            publish_only=True,
        ))

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
