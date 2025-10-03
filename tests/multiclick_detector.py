#!/usr/bin/env python3
"""Monitor multi-click events on multiple BeagleBone Black GPIO inputs."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import gpiod

_LOGGER = logging.getLogger(__name__)


@dataclass
class ClickState:
    """Track click related state for a single GPIO line."""

    click_count: int = 0
    last_press_ts: Optional[float] = None
    last_release_ts: Optional[float] = None
    finalizer: Optional[asyncio.TimerHandle] = None
    finalizer_scheduled_loop_ts: Optional[float] = None
    long_press_timer: Optional[asyncio.TimerHandle] = None
    long_press_scheduled_loop_ts: Optional[float] = None


class MultiClickDetector:
    """Detect single, double and triple clicks on multiple GPIO inputs."""

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        line_aliases: Dict[Tuple[int, int], str],
        click_timeout: float,
        hold_threshold: float,
        debounce_ms: float = 0,
    ) -> None:
        self._loop = loop
        self._line_aliases = line_aliases
        self._click_timeout = click_timeout
        self._hold_threshold = hold_threshold
        self._debounce_seconds = debounce_ms / 1000.0
        self._states: Dict[Tuple[int, int], ClickState] = defaultdict(ClickState)

    def _long_press_detected(self, key: Tuple[int, int]) -> None:
        """Handle a long press event."""
        state = self._states[key]
        alias = self._line_aliases.get(key, f"chip{key[0]}-line{key[1]}")

        # Long press detected, log it and reset click count to prevent a single click on release
        _LOGGER.info(
            "Detected long press on %s (chip %s offset %s)",
            alias,
            key[0],
            key[1],
        )
        state.click_count = 0  # <--- KLUCZOWE: Resetuj licznik
        if state.long_press_scheduled_loop_ts is not None:
            fired_after = self._loop.time() - state.long_press_scheduled_loop_ts
            _LOGGER.debug(
                "Long press timer fired for %s after %.3fs (threshold %.3fs)",
                alias,
                fired_after,
                self._hold_threshold,
            )
        state.long_press_timer = None
        state.long_press_scheduled_loop_ts = None

    def handle_event(self, key: Tuple[int, int], event: gpiod.EdgeEvent) -> None:
        """Process a GPIO edge event and update click state."""
        alias = self._line_aliases.get(key, f"chip{key[0]}-line{key[1]}")
        state = self._states[key]
        timestamp_s = event.timestamp_ns / 1_000_000_000

        if event.event_type is event.Type.FALLING_EDGE:
            # Software debounce
            if state.last_press_ts and (timestamp_s - state.last_press_ts) < self._debounce_seconds:
                delta_ms = (timestamp_s - state.last_press_ts) * 1000
                _LOGGER.debug(
                    "Ignoring bounced press on %s (%.3f ms since last press, debounce %.3f ms)",
                    alias,
                    delta_ms,
                    self._debounce_seconds * 1000,
                )
                return

            _LOGGER.info("PRESSED: %s", alias)
            state.last_press_ts = timestamp_s

            # Cancel any pending finalizer for a multi-click sequence
            if state.finalizer:
                _LOGGER.debug("Cancelling pending finalize timer for %s", alias)
                state.finalizer.cancel()
                state.finalizer = None
                state.finalizer_scheduled_loop_ts = None

            # Schedule a check for a long press
            scheduled_at = self._loop.time()
            state.long_press_timer = self._loop.call_later(
                self._hold_threshold, self._long_press_detected, key
            )
            state.long_press_scheduled_loop_ts = scheduled_at
            _LOGGER.debug(
                "Scheduled long press timer for %s to fire in %.3fs", alias, self._hold_threshold
            )
            return

        if event.event_type is event.Type.RISING_EDGE:
            _LOGGER.info("RELEASED: %s", alias)

            # If a long press timer exists, it means it hasn't fired yet.
            # This is a short click.
            if state.long_press_timer:
                elapsed = 0.0
                if state.long_press_scheduled_loop_ts is not None:
                    elapsed = self._loop.time() - state.long_press_scheduled_loop_ts
                _LOGGER.debug(
                    "Cancelling long press timer for %s after %.3fs", alias, elapsed
                )
                state.long_press_timer.cancel()
                state.long_press_timer = None
                state.long_press_scheduled_loop_ts = None

                state.click_count += 1

                # Set a timer to finalize the click sequence (e.g., to detect single vs double)
                scheduled_at = self._loop.time()
                state.finalizer = self._loop.call_later(
                    self._click_timeout, self._finalize_sequence, key
                )
                state.finalizer_scheduled_loop_ts = scheduled_at
                state.last_release_ts = timestamp_s
                _LOGGER.debug(
                    "Scheduled finalize timer for %s to fire in %.3fs", alias, self._click_timeout
                )
            # If long_press_timer is None, it means it already fired and the long press action
            # was handled. We do nothing on release.
            else:
                _LOGGER.debug(
                    "Release on %s ignored for click detection because long press already handled",
                    alias,
                )
            return

    def _finalize_sequence(self, key: Tuple[int, int]) -> None:
        """Emit a log message summarising the detected click sequence."""
        state = self._states.get(key)
        if state is None or state.click_count <= 0:
            return

        alias = self._line_aliases.get(key, f"chip{key[0]}-line{key[1]}")
        click_count = state.click_count

        now_loop = self._loop.time()
        scheduled_delay = None
        actual_delay = None
        release_to_final = None
        if state.finalizer_scheduled_loop_ts is not None:
            scheduled_delay = self._click_timeout
            actual_delay = now_loop - state.finalizer_scheduled_loop_ts
        if state.last_release_ts is not None:
            release_to_final = now_loop - state.last_release_ts
        _LOGGER.debug(
            "Finalizing %s: scheduled_delay=%.3fs actual_delay=%.3fs release_to_final=%.3fs",
            alias,
            scheduled_delay if scheduled_delay is not None else -1.0,
            actual_delay if actual_delay is not None else -1.0,
            release_to_final if release_to_final is not None else -1.0,
        )

        label = {
            1: "single click",
            2: "double click",
            3: "triple click",
        }.get(click_count, f"{click_count} clicks")

        _LOGGER.info(
            "Detected %s on %s (chip %s offset %s)",
            label,
            alias,
            key[0],
            key[1],
        )

        # Reset state for the next sequence
        state.click_count = 0
        state.finalizer = None
        state.finalizer_scheduled_loop_ts = None