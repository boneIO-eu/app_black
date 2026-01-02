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
    # Exclusive mode: pending click waiting for sequence window
    pending_click_type: str | None = None
    pending_click_duration: float | None = None
    pending_click_timer: asyncio.TimerHandle | None = None


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
        sequence_mode: str = "immediate",
        enabled_sequences: set[str] | None = None,
        enable_triple_click: bool = False,
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
            sequence_mode: 'immediate' (default) or 'exclusive'
            enabled_sequences: Set of enabled sequence types (e.g., {'double_then_long'})
            enable_triple_click: Enable triple click detection (default: False)
            name: Name of the input
            pin: Pin name for logging
        """
        self._loop = loop
        self._callback = callback
        self._debounce_seconds = debounce_ms / 1000.0
        self._multiclick_window = multiclick_window_ms / 1000.0
        self._hold_threshold = hold_threshold_ms / 1000.0
        self._sequence_window = sequence_window_ms / 1000.0
        self._sequence_mode = sequence_mode
        self._enabled_sequences = enabled_sequences or set()
        self._enable_triple_click = enable_triple_click
        self._name = name
        self._pin = pin
        self._state = ClickState()
        
        # Pre-compute which click types should be delayed in exclusive mode
        # based on enabled sequences
        self._delay_click_types: set[str] = set()
        if sequence_mode == "exclusive" and self._enabled_sequences:
            for seq in self._enabled_sequences:
                # Find which click type starts this sequence
                for (first, _second), seq_name in CLICK_SEQUENCES.items():
                    if seq_name == seq:
                        self._delay_click_types.add(first)
                        break

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
            if self._enable_triple_click:
                click_type = TRIPLE
                _LOGGER.info("Detected TRIPLE click on %s (%s)", self._name, self._pin)
            else:
                # Triple click disabled - emit double + single instead
                _LOGGER.info("Triple click disabled on %s (%s), emitting DOUBLE + SINGLE", self._name, self._pin)
                self._state.click_count = 0
                self._state.finalizer = None
                self._state.finalizer_scheduled_loop_ts = None
                self._emit_click(DOUBLE, None)
                self._emit_click(SINGLE, None)
                return
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
        
        In 'immediate' mode: emit events immediately, sequences are additional.
        In 'exclusive' mode: delay single/double, if sequence detected only emit sequence.
        
        Args:
            click_type: The detected click type (single, double, triple, long)
            duration: Duration of the click (for long press)
        """
        current_time = self._loop.time()
        
        if self._sequence_mode == "exclusive":
            self._emit_click_exclusive(click_type, duration, current_time)
        else:
            self._emit_click_immediate(click_type, duration, current_time)

    def _emit_click_immediate(self, click_type: ClickTypes, duration: float | None, current_time: float) -> None:
        """Immediate mode: emit events immediately, sequences are additional."""
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

    def _emit_click_exclusive(self, click_type: ClickTypes, duration: float | None, current_time: float) -> None:
        """Exclusive mode: delay single/double, if sequence detected only emit sequence.
        
        Logic:
        - For single/double: store as pending, start timer for sequence_window
        - For long/single: check if pending exists, if so check for sequence
        - Timer expiry: emit the pending click
        
        Supported sequences:
        - double_then_long: double (pending) + long
        - single_then_long: single (pending) + long
        - double_then_single: double (pending) + single
        """
        # Check if there's a pending click and this could form a sequence
        if self._state.pending_click_type:
            # Check if we can form a sequence with current click
            sequence_key = (self._state.pending_click_type, click_type)
            sequence_type = CLICK_SEQUENCES.get(sequence_key)
            
            # Only detect sequences that are actually enabled
            if sequence_type and sequence_type in self._enabled_sequences:
                # Cancel pending timer
                if self._state.pending_click_timer:
                    self._state.pending_click_timer.cancel()
                    self._state.pending_click_timer = None
                
                _LOGGER.info(
                    "Detected sequence %s on %s (%s) [exclusive mode]",
                    sequence_type.upper(), self._name, self._pin
                )
                
                # Clear pending state
                self._state.pending_click_type = None
                self._state.pending_click_duration = None
                
                # Emit only the sequence, not the base events
                try:
                    self._callback(cast(ClickTypes, sequence_type), duration)
                except Exception as exc:
                    _LOGGER.error("Error in sequence callback for %s: %s", self._name, exc, exc_info=True)
                
                # Clear sequence tracking
                self._state.last_click_type = None
                self._state.last_click_time = None
                return
            else:
                # Sequence not enabled - emit the pending click now and continue
                # Cancel pending timer
                if self._state.pending_click_timer:
                    self._state.pending_click_timer.cancel()
                    self._state.pending_click_timer = None
                
                pending_type = self._state.pending_click_type
                pending_duration = self._state.pending_click_duration
                
                _LOGGER.debug(
                    "Sequence %s not enabled, emitting pending click %s on %s",
                    sequence_type, pending_type, self._name
                )
                
                # Clear pending state
                self._state.pending_click_type = None
                self._state.pending_click_duration = None
                
                # Emit the pending click
                try:
                    self._callback(cast(ClickTypes, pending_type), pending_duration)
                except Exception as exc:
                    _LOGGER.error("Error in click callback for %s: %s", self._name, exc, exc_info=True)
                
                # Continue to process current click below (don't return)
        
        # Only delay click types that can start a configured sequence
        # e.g., if only double_then_long is enabled, only delay 'double', not 'single'
        if click_type in self._delay_click_types:
            # Cancel any existing pending timer
            if self._state.pending_click_timer:
                self._state.pending_click_timer.cancel()
            
            # Store pending click
            self._state.pending_click_type = click_type
            self._state.pending_click_duration = duration
            
            # Start timer to emit after sequence window
            self._state.pending_click_timer = self._loop.call_later(
                self._sequence_window,
                self._emit_pending_click
            )
            _LOGGER.debug(
                "Pending click %s on %s, waiting %.0fms for sequence",
                click_type, self._name, self._sequence_window * 1000
            )
            return
        
        # For long (without pending) or other types: emit immediately
        try:
            self._callback(click_type, duration)
        except Exception as exc:
            _LOGGER.error("Error in click callback for %s: %s", self._name, exc, exc_info=True)
        
        # Remember for sequence detection
        self._state.last_click_type = click_type
        self._state.last_click_time = current_time

    def _emit_pending_click(self) -> None:
        """Emit the pending click after sequence window expired (exclusive mode)."""
        if not self._state.pending_click_type:
            return
        
        click_type = cast(ClickTypes, self._state.pending_click_type)
        duration = self._state.pending_click_duration
        
        _LOGGER.debug(
            "Sequence window expired, emitting pending click %s on %s",
            click_type, self._name
        )
        
        # Clear pending state
        self._state.pending_click_type = None
        self._state.pending_click_duration = None
        self._state.pending_click_timer = None
        
        # Emit the click
        try:
            self._callback(click_type, duration)
        except Exception as exc:
            _LOGGER.error("Error in pending click callback for %s: %s", self._name, exc, exc_info=True)
        
        # Remember for sequence detection (in case of chained sequences)
        self._state.last_click_type = click_type
        self._state.last_click_time = self._loop.time()

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
        
        # Only detect sequences that are actually enabled
        if sequence_type and sequence_type in self._enabled_sequences:
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

            # In exclusive mode: if there's a pending click waiting for sequence,
            # cancel its timer - user is continuing the sequence with this press
            if self._sequence_mode == "exclusive" and self._state.pending_click_timer:
                _LOGGER.debug(
                    "Cancelling pending click timer for %s - user continuing sequence",
                    self._name
                )
                self._state.pending_click_timer.cancel()
                self._state.pending_click_timer = None

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
