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
        
        # Determine which sequences are enabled based on configured actions OR mqtt_sequences
        # A sequence is enabled if it has actions defined OR is set to publish to MQTT
        enabled_sequences: set[str] = set()
        sequence_types = {'double_then_long', 'single_then_long', 'double_then_single'}
        
        # Check actions
        actions = kwargs.get('actions', {})
        if isinstance(actions, dict):
            for seq_type in sequence_types:
                if seq_type in actions and actions[seq_type]:
                    enabled_sequences.add(seq_type)
        
        # Check mqtt_sequences
        mqtt_sequences = kwargs.get('mqtt_sequences', {})
        if isinstance(mqtt_sequences, dict):
            for seq_type in sequence_types:
                if mqtt_sequences.get(seq_type):
                    enabled_sequences.add(seq_type)
        
        _LOGGER.debug("Enabled sequences for %s: %s", self._name, enabled_sequences)
        
        # Get enable_triple_click setting (default: False)
        enable_triple_click = kwargs.get('enable_triple_click', False)
        
        # Create multiclick detector
        self._detector = MultiClickDetector(
            loop=self._loop,
            callback=self._on_click_detected,
            debounce_ms=self._bounce_time * 1000,  # Convert to ms
            multiclick_window_ms=double_click_duration,
            hold_threshold_ms=long_press_duration,
            sequence_window_ms=sequence_window_duration,
            sequence_mode=self._sequence_mode,
            enabled_sequences=enabled_sequences,
            enable_triple_click=enable_triple_click,
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
        sequence_mode: str | None = None,
        actions: dict | None = None,
        mqtt_sequences: dict | None = None,
        enable_triple_click: bool | None = None,
    ) -> None:
        """Update timing parameters for click detection.
        
        This method allows updating timing parameters at runtime without
        recreating the detector. Useful for config reload.
        
        Args:
            double_click_duration: Time window in ms to detect double click
            long_press_duration: Time in ms to detect long press
            sequence_window_duration: Time window in ms to detect sequences
            sequence_mode: 'immediate' or 'exclusive'
            actions: Actions dict to determine enabled sequences
            mqtt_sequences: MQTT sequences dict to determine enabled sequences
            enable_triple_click: Enable triple click detection
        """
        from boneio.const import CLICK_SEQUENCES
        
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
        
        if sequence_mode is not None:
            self._sequence_mode = sequence_mode
            self._detector._sequence_mode = sequence_mode
            _LOGGER.debug("Updated sequence_mode to %s for %s", sequence_mode, self._name)
        
        if enable_triple_click is not None:
            self._detector._enable_triple_click = enable_triple_click
            _LOGGER.debug("Updated enable_triple_click to %s for %s", enable_triple_click, self._name)
        
        # Update enabled sequences based on actions and mqtt_sequences
        sequence_types = {'double_then_long', 'single_then_long', 'double_then_single'}
        enabled_sequences: set[str] = set()
        
        if actions is not None and isinstance(actions, dict):
            for seq_type in sequence_types:
                if seq_type in actions and actions[seq_type]:
                    enabled_sequences.add(seq_type)
        
        if mqtt_sequences is not None and isinstance(mqtt_sequences, dict):
            for seq_type in sequence_types:
                if mqtt_sequences.get(seq_type):
                    enabled_sequences.add(seq_type)
        
        if actions is not None or mqtt_sequences is not None:
            self._detector._enabled_sequences = enabled_sequences
            
            # Recompute delay_click_types
            self._detector._delay_click_types = set()
            if self._detector._sequence_mode == "exclusive" and enabled_sequences:
                for seq in enabled_sequences:
                    for (first, _second), seq_name in CLICK_SEQUENCES.items():
                        if seq_name == seq:
                            self._detector._delay_click_types.add(first)
                            break
            _LOGGER.debug("Updated enabled_sequences to %s for %s", enabled_sequences, self._name)