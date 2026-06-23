"""Regression tests for phantom press at boot.

At boot, GPIO pins with pull-up resistors may generate a FALLING_EDGE
when the button circuit pulls them LOW.  This phantom press was causing:
1. A long press action to fire 400ms after boot (phantom toggle)
2. The first real button press to be ignored (stale release)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from boneio.components.input.detectors import MultiClickDetector


# ── Helpers ──────────────────────────────────────────────────────────────────


@dataclass
class FakeEdgeEvent:
    """Minimal fake gpiod.EdgeEvent for testing."""

    class Type:
        FALLING_EDGE = "FALLING"
        RISING_EDGE = "RISING"

    event_type: str
    timestamp_ns: int
    line_offset: int = 0


def _make_detector(
    loop: asyncio.AbstractEventLoop,
    callback: MagicMock | None = None,
    **kwargs,
) -> MultiClickDetector:
    """Create a MultiClickDetector with sensible test defaults."""
    cb = callback or MagicMock()
    return MultiClickDetector(
        loop=loop,
        callback=cb,
        debounce_ms=kwargs.get("debounce_ms", 30.0),
        multiclick_window_ms=kwargs.get("multiclick_window_ms", 220.0),
        hold_threshold_ms=kwargs.get("hold_threshold_ms", 400.0),
        name=kwargs.get("name", "TestButton"),
        pin=kwargs.get("pin", "P8_34"),
        max_long_press_seconds=kwargs.get("max_long_press_seconds", 120.0),
    )


def _falling(timestamp_s: float) -> FakeEdgeEvent:
    """Create a FALLING_EDGE event (press) at the given kernel timestamp."""
    return FakeEdgeEvent(
        event_type=FakeEdgeEvent.Type.FALLING_EDGE,
        timestamp_ns=int(timestamp_s * 1_000_000_000),
    )


def _rising(timestamp_s: float) -> FakeEdgeEvent:
    """Create a RISING_EDGE event (release) at the given kernel timestamp."""
    return FakeEdgeEvent(
        event_type=FakeEdgeEvent.Type.RISING_EDGE,
        timestamp_ns=int(timestamp_s * 1_000_000_000),
    )


# ── Tests: Stale release guard ──────────────────────────────────────────────


class TestStaleReleaseGuard:
    """Test that RISING_EDGE with press duration > max_long_press_seconds resets state."""

    async def test_stale_release_resets_detector(self):
        """A release after 22h should reset state, not be treated as long press end."""
        loop = asyncio.get_event_loop()
        callback = MagicMock()
        det = _make_detector(loop, callback, max_long_press_seconds=120.0)

        # Simulate phantom FALLING at boot (kernel time ≈ 0.5s)
        det.handle_event(_falling(0.5))
        assert det._state.last_press_ts == 0.5

        # Cancel the long press timer manually (simulates safety timeout)
        if det._state.long_press_timer:
            det._state.long_press_timer.cancel()
            det._state.long_press_timer = None

        # 22.9h later: user presses → RISING_EDGE
        boot_plus_22h = 0.5 + 82362.0  # ~22.9 hours
        det.handle_event(_rising(boot_plus_22h))

        # State should be reset (stale guard triggered)
        assert det._state.last_press_ts is None
        assert det._state.last_press_loop_ts is None
        assert det._state.last_release_ts == boot_plus_22h

        # No callback should have been triggered by the stale release
        callback.assert_not_called()

    async def test_stale_release_followed_by_valid_press(self):
        """After stale release resets state, next FALLING should register normally."""
        loop = asyncio.get_event_loop()
        callback = MagicMock()
        det = _make_detector(loop, callback, max_long_press_seconds=120.0)

        # Phantom FALLING at boot
        det.handle_event(_falling(0.5))
        if det._state.long_press_timer:
            det._state.long_press_timer.cancel()
            det._state.long_press_timer = None

        # Stale RISING 22h later
        t_user_press = 82362.5
        det.handle_event(_rising(t_user_press))
        assert det._state.last_press_ts is None  # reset by guard

        # Real FALLING 50ms later (after debounce window)
        t_real_press = t_user_press + 0.050
        det.handle_event(_falling(t_real_press))

        # Should be registered as a valid press
        assert det._state.last_press_ts == t_real_press
        assert det._state.long_press_timer is not None

        # Clean up timer
        det._state.long_press_timer.cancel()

    async def test_normal_release_not_affected(self):
        """A normal release (< max_long_press_seconds) should work normally."""
        loop = asyncio.get_event_loop()
        callback = MagicMock()
        det = _make_detector(loop, callback, max_long_press_seconds=120.0)

        # Normal FALLING
        det.handle_event(_falling(1000.0))

        # Normal RISING 200ms later (short click)
        det.handle_event(_rising(1000.200))

        # Should have registered as a click (timer cancelled, count incremented)
        assert det._state.last_release_ts == 1000.200
        assert det._state.click_count == 1

        # Clean up finalizer
        if det._state.finalizer:
            det._state.finalizer.cancel()


# ── Tests: Boot press suppression ────────────────────────────────────────────


class TestBootPressSuppression:
    """Test that _boot_press_suppressed flag prevents phantom actions at boot."""

    async def test_boot_suppression_absorbs_phantom_falling(self):
        """With _boot_press_suppressed=True, FALLING records ts but doesn't schedule timer."""
        loop = asyncio.get_event_loop()
        callback = MagicMock()
        det = _make_detector(loop, callback)

        # GpioManager seeds the flag
        det._boot_press_suppressed = True

        # Phantom FALLING at boot
        det.handle_event(_falling(0.5))

        # Timestamp recorded for debounce
        assert det._state.last_press_ts == 0.5
        # But NO timer scheduled
        assert det._state.long_press_timer is None
        assert det._state.last_press_loop_ts is None
        # Flag consumed
        assert det._boot_press_suppressed is False
        # No callback
        callback.assert_not_called()

    async def test_boot_suppression_flag_only_affects_first_falling(self):
        """After suppression is consumed, second FALLING works normally."""
        loop = asyncio.get_event_loop()
        callback = MagicMock()
        det = _make_detector(loop, callback)

        det._boot_press_suppressed = True

        # First FALLING (suppressed)
        det.handle_event(_falling(0.5))
        assert det._state.long_press_timer is None

        # Stale RISING (handled by stale guard since last_press_ts is from boot)
        det.handle_event(_rising(82362.5))
        assert det._state.last_press_ts is None  # reset

        # Second FALLING (real user press, after debounce)
        det.handle_event(_falling(82362.6))
        assert det._state.last_press_ts == 82362.6
        assert det._state.long_press_timer is not None  # timer scheduled!

        # Clean up
        det._state.long_press_timer.cancel()

    async def test_without_suppression_falling_schedules_timer(self):
        """Without the flag, FALLING_EDGE schedules long press timer normally."""
        loop = asyncio.get_event_loop()
        callback = MagicMock()
        det = _make_detector(loop, callback)

        assert det._boot_press_suppressed is False

        det.handle_event(_falling(1000.0))

        assert det._state.long_press_timer is not None
        assert det._state.last_press_ts == 1000.0

        # Clean up
        det._state.long_press_timer.cancel()

    async def test_full_boot_scenario(self):
        """Full scenario: boot phantom → user press → single click detected."""
        loop = asyncio.get_event_loop()
        callback = MagicMock()
        det = _make_detector(loop, callback)
        det._boot_press_suppressed = True

        # 1. Phantom FALLING at boot (kernel ts ≈ 0.5s)
        det.handle_event(_falling(0.5))
        assert det._state.long_press_timer is None  # suppressed
        callback.assert_not_called()

        # 2. Bounce FALLING ignored (press-vs-press debounce)
        det.handle_event(_falling(0.501))
        callback.assert_not_called()

        # 3. User presses 22h later → RISING (stale release)
        det.handle_event(_rising(82362.5))
        assert det._state.last_press_ts is None  # stale guard reset
        callback.assert_not_called()

        # 4. Bounce FALLING (cross-debounce, too close to release)
        det.handle_event(_falling(82362.501))
        callback.assert_not_called()

        # 5. Real FALLING 50ms later
        det.handle_event(_falling(82362.550))
        assert det._state.last_press_ts == 82362.550
        assert det._state.long_press_timer is not None

        # 6. Real RISING 200ms later (short click)
        det.handle_event(_rising(82362.750))
        assert det._state.click_count == 1

        # 7. Finalizer fires → SINGLE click
        if det._state.finalizer:
            det._state.finalizer.cancel()
            det._finalize_clicks()

        callback.assert_called_once_with("single", None)
