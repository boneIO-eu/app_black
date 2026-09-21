"""Regression tests for orphaned long-hold timer chains.

A long press runs a self-rescheduling 200ms timer chain, and the detector
keeps only the *latest* handle in ``_state.long_hold_periodic_timer``. That is
fine while every press is followed by its release. It stops being fine when a
release goes missing — the edge is lost while the event loop is blocked, or it
is swallowed by the bounce guard — because the next press then starts a second
chain while the first is still running, and the first becomes unreachable:
nothing holds its handle any more, so nothing can cancel it, and its safety
timeout measures against the *new* press and therefore never trips.

The visible result on a controller is an input that "hangs": LONG events keep
firing five times a second from a button nobody is touching.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from unittest.mock import MagicMock

from boneio.components.input.detectors import MultiClickDetector


@dataclass
class FakeEdgeEvent:
    """Minimal fake gpiod.EdgeEvent for testing."""

    class Type:
        FALLING_EDGE = "FALLING"
        RISING_EDGE = "RISING"

    event_type: str
    timestamp_ns: int
    line_offset: int = 0


def _make_detector(loop, callback=None, **kwargs) -> MultiClickDetector:
    """Create a MultiClickDetector with sensible test defaults."""
    return MultiClickDetector(
        loop=loop,
        callback=callback or MagicMock(),
        debounce_ms=kwargs.get("debounce_ms", 30.0),
        multiclick_window_ms=kwargs.get("multiclick_window_ms", 220.0),
        hold_threshold_ms=kwargs.get("hold_threshold_ms", 400.0),
        name="TestButton",
        pin="P8_34",
        max_long_press_seconds=kwargs.get("max_long_press_seconds", 30.0),
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


class TestOrphanedLongHoldChain:
    """A press must never leave a previous long-hold chain running."""

    async def test_new_press_cancels_running_chain(self):
        """Press, lose the release, press again: the first chain is ended."""
        loop = asyncio.get_event_loop()
        det = _make_detector(loop)

        det.handle_event(_falling(1.0))
        # Long press fires; this starts the periodic chain.
        det._detect_long_press()
        first_chain = det._state.long_hold_periodic_timer
        assert first_chain is not None

        # The release never arrives. The user presses again.
        det.handle_event(_falling(5.0))

        assert first_chain.cancelled(), "the orphaned chain was left running"
        assert det._state.long_hold_periodic_timer is None

    async def test_orphaned_chain_does_not_survive_as_second_timer(self):
        """Two presses without releases must not leave two live chains."""
        loop = asyncio.get_event_loop()
        det = _make_detector(loop)

        chains = []
        for press_ts in (1.0, 5.0, 9.0):
            det.handle_event(_falling(press_ts))
            det._detect_long_press()
            chains.append(det._state.long_hold_periodic_timer)

        # Every chain but the last must have been cancelled on the next press.
        assert all(c.cancelled() for c in chains[:-1])
        assert not chains[-1].cancelled()

    async def test_long_press_state_is_reset_for_the_new_press(self):
        """The new press starts with a clean long-action ledger."""
        loop = asyncio.get_event_loop()
        det = _make_detector(loop)

        det.handle_event(_falling(1.0))
        det._detect_long_press()
        det._state.executed_long_actions = {0, 1}
        det._state.last_repeat_times = {0: 1234.0}

        det.handle_event(_falling(5.0))

        assert det._state.executed_long_actions == set()
        assert det._state.last_repeat_times == {}


class TestStalePeriodicHandle:
    """The periodic chain must drop its handle when it stops on its own."""

    async def test_early_return_clears_the_handle(self):
        """Released mid-chain: the handle must not outlive the chain."""
        loop = asyncio.get_event_loop()
        det = _make_detector(loop)

        det.handle_event(_falling(1.0))
        det._detect_long_press()
        assert det._state.long_hold_periodic_timer is not None

        # A release lands, so the next tick of the chain bails out.
        det._state.last_release_ts = 1.5
        det._send_periodic_long_event()

        assert det._state.long_hold_periodic_timer is None

    async def test_no_phantom_long_on_the_next_click(self):
        """A stale handle used to emit a LONG on an ordinary short click."""
        loop = asyncio.get_event_loop()
        callback = MagicMock()
        det = _make_detector(loop, callback)

        det.handle_event(_falling(1.0))
        det._detect_long_press()
        det._state.last_release_ts = 1.5
        det._send_periodic_long_event()
        callback.reset_mock()

        # An ordinary short click well after the bounce window.
        det.handle_event(_falling(10.0))
        det.handle_event(_rising(10.1))

        emitted = [c.args[0] for c in callback.call_args_list]
        assert "long" not in emitted, f"phantom long press emitted: {emitted}"
