"""Event detectors for GPIO inputs with debounce and multiclick support."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

import gpiod

from boneio.const import (
    BinaryStateTypes,
    ClickTypes,
    CLICK_SEQUENCES,
    DEFAULT_SEQUENCE_WINDOW_MS,
    DOUBLE,
    LONG,
    PRESSED,
    RELEASED,
    SINGLE,
    TRIPLE,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class ClickState:
    """State for tracking multi-click detection."""
    click_count: int = 0
    last_press_ts: float | None = None
    last_release_ts: float | None = None
    finalizer: asyncio.TimerHandle | None = None
    finalizer_scheduled_loop_ts: float | None = None
    long_press_timer: asyncio.TimerHandle | None = None
    long_press_scheduled_loop_ts: float | None = None
    # Sequence tracking
    last_click_type: str | None = None
    last_click_time: float | None = None


@dataclass
class BinarySensorState:
    """State for binary sensor detection."""
    last_press_ts: float | None = None
    last_state: bool = False
    current_state: bool = False


class MultiClickDetector:
    """Detects single, double, triple, long-press events and sequences with software debounce.
    
    Supports sequence detection like double_then_long, single_then_long, etc.
    Based on multiclick_detector.py from tests.
    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        callback: Callable[[ClickTypes, float | None], None],
        debounce_ms: float = 50.0,
        multiclick_window_ms: float = 220.0,
        hold_threshold_ms: float = 400.0,
        sequence_window_ms: float = DEFAULT_SEQUENCE_WINDOW_MS,
        name: str = "unknown",
        pin: str = "unknown",
    ):
        """Initialize multiclick detector.
        
        Args:
            loop: Asyncio event loop
            callback: Callback(click_type, duration) - called on detection
            debounce_ms: Debounce time in milliseconds
            multiclick_window_ms: Window for double-click detection
            hold_threshold_ms: Time threshold for long press
            sequence_window_ms: Window for sequence detection (e.g., double_then_long)
            name: Name of the input
            pin: Pin name for logging
        """
        self._loop = loop
        self._callback = callback
        self._debounce_seconds = debounce_ms / 1000.0
        self._multiclick_window = multiclick_window_ms / 1000.0
        self._hold_threshold = hold_threshold_ms / 1000.0
        self._sequence_window = sequence_window_ms / 1000.0
        self._name = name
        self._pin = pin
        self._state = ClickState()

    def _finalize_clicks(self) -> None:
        """Finalize a multi-click sequence."""
        count = self._state.click_count
        
        if count == 1:
            click_type = SINGLE
            _LOGGER.info("Detected SINGLE click on %s (%s)", self._name, self._pin)
        elif count == 2:
            click_type = DOUBLE
            _LOGGER.info("Detected DOUBLE click on %s (%s)", self._name, self._pin)
        elif count == 3:
            click_type = TRIPLE
            _LOGGER.info("Detected TRIPLE click on %s (%s)", self._name, self._pin)
        else:
            click_type = SINGLE  # Fallback for 4+ clicks
            _LOGGER.info("Detected %d clicks on %s (%s), treating as SINGLE", count, self._name, self._pin)
        
        self._state.click_count = 0
        self._state.finalizer = None
        self._state.finalizer_scheduled_loop_ts = None
        
        # Emit the click
        self._emit_click(click_type, None)

    def _emit_click(self, click_type: ClickTypes, duration: float | None) -> None:
        """Emit a click event, checking for sequences first.
        
        Args:
            click_type: The detected click type (single, double, triple, long)
            duration: Duration of the click (for long press)
        """
        current_time = self._loop.time()
        
        # Check if this click forms a sequence with the previous one
        sequence_type = self._check_sequence(click_type, current_time)
        if sequence_type:
            _LOGGER.info(
                "Detected sequence %s on %s (%s)",
                sequence_type.upper(), self._name, self._pin
            )
            try:
                self._callback(sequence_type, duration)
            except Exception as exc:
                _LOGGER.error("Error in sequence callback for %s: %s", self._name, exc, exc_info=True)
        
        # Always emit the basic click type
        try:
            self._callback(click_type, duration)
        except Exception as exc:
            _LOGGER.error("Error in click callback for %s: %s", self._name, exc, exc_info=True)
        
        # Remember this click for potential sequence detection
        self._state.last_click_type = click_type
        self._state.last_click_time = current_time

    def _check_sequence(self, current_click: ClickTypes, current_time: float) -> ClickTypes | None:
        """Check if current click forms a sequence with previous click.
        
        Args:
            current_click: Current click type
            current_time: Current timestamp
            
        Returns:
            Sequence type if detected, None otherwise
        """
        if not self._state.last_click_type or not self._state.last_click_time:
            return None
        
        elapsed = current_time - self._state.last_click_time
        if elapsed > self._sequence_window:
            # Too much time passed, no sequence - this is normal behavior
            return None
        
        # Look up sequence in mapping
        sequence_key = (self._state.last_click_type, current_click)
        sequence_type = CLICK_SEQUENCES.get(sequence_key)
        
        if sequence_type:
            # Clear sequence state to prevent chaining
            self._state.last_click_type = None
            self._state.last_click_time = None
            return cast(ClickTypes, sequence_type)
        
        return None

    def _detect_long_press(self) -> None:
        """Detect and report a long press."""
        duration = None
        if self._state.last_press_ts and self._state.last_release_ts:
            duration = self._state.last_release_ts - self._state.last_press_ts
        
        _LOGGER.info("Detected LONG press on %s (%s)", self._name, self._pin)
        
        self._state.click_count = 0  # Reset click counter
        self._state.long_press_timer = None
        self._state.long_press_scheduled_loop_ts = None
        
        # Emit the long press (may also trigger sequence)
        self._emit_click(LONG, duration)

    def handle_event(self, event: gpiod.EdgeEvent) -> None:
        """Process a GPIO edge event and update click state.
        
        Args:
            event: GPIO edge event from gpiod
        """
        timestamp_s = event.timestamp_ns / 1_000_000_000
        
        _LOGGER.debug(
            "handle_event called for %s with edge type: %s",
            self._name,
            "FALLING" if event.event_type is event.Type.FALLING_EDGE else "RISING",
        )

        if event.event_type is event.Type.FALLING_EDGE:
            # Button pressed (FALLING_EDGE on BeagleBone with pull-up)
            
            # Software debounce
            if self._state.last_press_ts and (timestamp_s - self._state.last_press_ts) < self._debounce_seconds:
                delta_ms = (timestamp_s - self._state.last_press_ts) * 1000
                _LOGGER.debug(
                    "Ignoring bounced press on %s (%.3f ms since last press, debounce %.3f ms)",
                    self._name,
                    delta_ms,
                    self._debounce_seconds * 1000,
                )
                return

            _LOGGER.debug("PRESSED: %s (%s)", self._name, self._pin)
            self._state.last_press_ts = timestamp_s

            # Cancel any pending finalizer for a multi-click sequence
            if self._state.finalizer:
                _LOGGER.debug("Cancelling pending finalize timer for %s", self._name)
                self._state.finalizer.cancel()
                self._state.finalizer = None
                self._state.finalizer_scheduled_loop_ts = None

            # Schedule a check for a long press
            scheduled_at = self._loop.time()
            self._state.long_press_scheduled_loop_ts = scheduled_at
            self._state.long_press_timer = self._loop.call_later(
                self._hold_threshold,
                self._detect_long_press,
            )
            _LOGGER.debug(
                "Scheduled long press timer for %s to fire in %.3fs",
                self._name,
                self._hold_threshold,
            )

        elif event.event_type is event.Type.RISING_EDGE:
            # Button released (RISING_EDGE on BeagleBone with pull-up)
            
            # Software debounce
            if self._state.last_release_ts and (timestamp_s - self._state.last_release_ts) < self._debounce_seconds:
                delta_ms = (timestamp_s - self._state.last_release_ts) * 1000
                _LOGGER.debug(
                    "Ignoring bounced release on %s (%.3f ms since last release)",
                    self._name,
                    delta_ms,
                )
                return

            _LOGGER.debug("RELEASED: %s (%s)", self._name, self._pin)
            self._state.last_release_ts = timestamp_s
            
            _LOGGER.debug(
                "long_press_timer state for %s: %s",
                self._name,
                "EXISTS" if self._state.long_press_timer else "None",
            )

            # If a long press timer exists, it means it hasn't fired yet.
            # This is a short click.
            if self._state.long_press_timer:
                _LOGGER.debug("Cancelling long press timer for %s", self._name)
                self._state.long_press_timer.cancel()
                self._state.long_press_timer = None
                self._state.long_press_scheduled_loop_ts = None

                # Increment click count
                self._state.click_count += 1
                _LOGGER.debug("Click count for %s: %d", self._name, self._state.click_count)

                # Schedule finalizer to conclude the multi-click sequence
                scheduled_at = self._loop.time()
                self._state.finalizer_scheduled_loop_ts = scheduled_at
                self._state.finalizer = self._loop.call_later(
                    self._multiclick_window,
                    self._finalize_clicks,
                )
            # If long_press_timer is None, it means it already fired and the long press action
            # was handled. We do nothing on release.
            else:
                _LOGGER.debug(
                    "Release on %s ignored for click detection because long press already handled",
                    self._name,
                )


class BinarySensorDetector:
    """Detects binary state changes (PRESSED/RELEASED) with software debounce."""

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        callback: Callable[[BinaryStateTypes, float], None],
        debounce_ms: float = 50.0,
        inverted: bool = False,
        name: str = "unknown",
        pin: str = "unknown",
    ):
        """Initialize binary sensor detector.
        
        Args:
            loop: Asyncio event loop
            callback: Callback(state, timestamp) - called on state change
            debounce_ms: Debounce time in milliseconds
            inverted: If True, invert the logic (PRESSED when high)
            name: Name of the sensor
            pin: Pin name for logging
        """
        self._loop = loop
        self._callback = callback
        self._debounce_seconds = debounce_ms / 1000.0
        self._inverted = inverted
        self._name = name
        self._pin = pin
        self._state = BinarySensorState()

    def handle_event(self, event: gpiod.EdgeEvent) -> None:
        """Process a GPIO edge event for binary sensor.
        
        Args:
            event: GPIO edge event from gpiod
        """
        timestamp_s = event.timestamp_ns / 1_000_000_000

        # Determine new state based on edge type
        # FALLING_EDGE = button pressed (with pull-up)
        # RISING_EDGE = button released (with pull-up)
        is_pressed = event.event_type is event.Type.FALLING_EDGE
        
        if self._inverted:
            is_pressed = not is_pressed

        # Software debounce
        if self._state.last_press_ts and (timestamp_s - self._state.last_press_ts) < self._debounce_seconds:
            delta_ms = (timestamp_s - self._state.last_press_ts) * 1000
            _LOGGER.debug(
                "Ignoring bounced event on %s (%.3f ms since last event, debounce %.3f ms)",
                self._name,
                delta_ms,
                self._debounce_seconds * 1000,
            )
            return

        # Check if state actually changed
        if self._state.current_state == is_pressed:
            _LOGGER.debug("State unchanged for %s, ignoring", self._name)
            return

        self._state.last_press_ts = timestamp_s
        self._state.current_state = is_pressed
        
        state_str = PRESSED if is_pressed else RELEASED
        _LOGGER.info("Binary sensor %s (%s): %s", self._name, self._pin, state_str)

        # Call the callback
        try:
            self._callback(state_str, timestamp_s)
        except Exception as exc:
            _LOGGER.error("Error in binary sensor callback for %s: %s", self._name, exc, exc_info=True)
