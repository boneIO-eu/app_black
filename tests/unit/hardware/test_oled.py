"""Tests for OLED display sleep/wake and button handling logic.

These tests verify:
- Sleep timer scheduling after wake-up (the single-click screensaver bug)
- Sleep callback behaviour
- render_display timer management
- Shutdown state machine transitions
"""

from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Module-level mocks — must be installed BEFORE importing Oled
# ---------------------------------------------------------------------------

# Create mock modules for hardware dependencies not available in test env
_mock_modules = {
    "luma": MagicMock(),
    "luma.core": MagicMock(),
    "luma.core.error": MagicMock(),
    "luma.core.interface": MagicMock(),
    "luma.core.interface.serial": MagicMock(),
    "luma.core.render": MagicMock(),
    "luma.oled": MagicMock(),
    "luma.oled.device": MagicMock(),
    "qrcode": MagicMock(),
    "PIL": MagicMock(),
    "PIL.ImageDraw": MagicMock(),
    "smbus2": MagicMock(),
}

# Install mocks for missing modules (don't overwrite real ones)
for mod_name, mock_mod in _mock_modules.items():
    if mod_name not in sys.modules:
        sys.modules[mod_name] = mock_mod

from boneio.core.utils.timeperiod import TimePeriod

# ---------------------------------------------------------------------------
# Helpers – lightweight fakes that avoid real I2C / PIL dependencies
# ---------------------------------------------------------------------------


class FakeDevice:
    """Minimal stand-in for luma.oled sh1106 device."""

    bounding_box = (0, 0, 127, 63)

    def display(self, image):
        """No-op display."""
        pass


class FakeCanvas:
    """Context-manager that yields a no-op draw surface."""

    def __init__(self, device):
        self._device = device

    def __enter__(self):
        return MagicMock()  # acts as PIL ImageDraw

    def __exit__(self, *args):
        pass


class FakeEventBus:
    """Minimal EventBus substitute with a real asyncio loop."""

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop
        self._listeners: dict = {}

    def add_event_listener(self, *, event_type, entity_id, listener_id, target):
        """Register a listener."""
        self._listeners[listener_id] = target

    def remove_event_listener(self, *, listener_id, **_kw):
        """Remove a listener."""
        self._listeners.pop(listener_id, None)


def _make_oled(loop: asyncio.AbstractEventLoop, sleep_seconds: float = 60):
    """Create an Oled instance with all hardware mocked out.

    Args:
        loop: Running asyncio event loop.
        sleep_seconds: Screensaver timeout in seconds.

    Returns:
        Tuple of (Oled instance, FakeEventBus).
    """
    event_bus = FakeEventBus(loop)
    sleep_timeout = TimePeriod(seconds=sleep_seconds)

    host_data = MagicMock()
    # Return some dummy data so render_display draws _something_
    host_data.get.return_value = {"uptime": "1h 23m", "cpu": "12%"}

    with patch("boneio.hardware.display.oled.canvas", FakeCanvas):
        from boneio.hardware.display.oled import Oled

        oled = Oled(
            host_data=host_data,
            grouped_outputs_by_expander=[],
            sleep_timeout=sleep_timeout,
            screen_order=["uptime"],
            input_groups=[],
            event_bus=event_bus,  # type: ignore[arg-type]  # duck-typed test double
            device=FakeDevice(),  # type: ignore[arg-type]  # duck-typed test double
        )

    return oled, event_bus


# ---------------------------------------------------------------------------
# Tests – Sleep / Wake cycle
# ---------------------------------------------------------------------------


class TestOledSleepWake:
    """Tests for OLED sleep timer and wake-up behaviour."""

    @pytest.fixture(autouse=True)
    def _patch_canvas(self):
        """Patch canvas for all tests in this class."""
        with patch("boneio.hardware.display.oled.canvas", FakeCanvas):
            yield

    # -- wake_up must schedule sleep timer --

    @pytest.mark.asyncio
    async def test_wake_up_starts_sleep_timer(self):
        """After wake_up, the sleep timer must be scheduled.

        This was the root-cause of the screensaver bug: wake_up() used to
        call _update_display() which never starts the timer.
        """
        loop = asyncio.get_running_loop()
        oled, _ = _make_oled(loop, sleep_seconds=30)

        # Put OLED to sleep manually
        oled._sleep = True
        oled._cancel_sleep_handle = None

        oled.wake_up()

        assert not oled._sleep, "OLED should be awake after wake_up()"
        assert oled._cancel_sleep_handle is not None, "Sleep timer must be scheduled after wake_up()"

    @pytest.mark.asyncio
    async def test_wake_up_via_single_click_starts_timer(self):
        """Simulates a single click while asleep — mirrors the user bug report.

        Expected: OLED wakes, sleep timer is rescheduled, screen will
        auto-sleep again after the timeout.
        """
        loop = asyncio.get_running_loop()
        oled, _ = _make_oled(loop, sleep_seconds=30)

        # Simulate sleeping OLED
        oled._sleep = True
        oled._cancel_sleep_handle = None

        # Simulate single click event
        event = SimpleNamespace(click_type="single", duration=0.0)
        await oled._handle_button_press(event)

        assert not oled._sleep
        assert oled._cancel_sleep_handle is not None, "Single-click wake must schedule sleep timer"

    @pytest.mark.asyncio
    async def test_second_click_after_wake_reschedules_timer(self):
        """Two clicks: first wakes, second switches screen — both must keep timer."""
        loop = asyncio.get_running_loop()
        oled, _ = _make_oled(loop, sleep_seconds=30)

        # Put to sleep
        oled._sleep = True
        oled._cancel_sleep_handle = None

        # First click — wake up
        event = SimpleNamespace(click_type="single", duration=0.0)
        await oled._handle_button_press(event)
        first_handle = oled._cancel_sleep_handle
        assert first_handle is not None

        # Second click — next screen
        await oled._handle_button_press(event)
        second_handle = oled._cancel_sleep_handle
        assert second_handle is not None

    # -- sleep callback behaviour --

    @pytest.mark.asyncio
    async def test_sleep_callback_sets_sleep_flag(self):
        """_sleep_callback must set _sleep=True and clear the timer handle."""
        loop = asyncio.get_running_loop()
        oled, _ = _make_oled(loop, sleep_seconds=1)

        oled._sleep = False
        oled._cancel_sleep_handle = MagicMock()  # pretend timer is active

        await oled._sleep_callback(None)

        assert oled._sleep
        assert oled._cancel_sleep_handle is None

    # -- render_display starts timer only when not already running --

    @pytest.mark.asyncio
    async def test_render_display_starts_timer_when_none(self):
        """render_display should start sleep timer if none is active."""
        loop = asyncio.get_running_loop()
        oled, _ = _make_oled(loop, sleep_seconds=30)

        oled._cancel_sleep_handle = None
        oled.render_display()

        assert oled._cancel_sleep_handle is not None

    @pytest.mark.asyncio
    async def test_render_display_restarts_timer_on_each_call(self):
        """Each render_display should restart the sleep timer (count from last interaction)."""
        loop = asyncio.get_running_loop()
        oled, _ = _make_oled(loop, sleep_seconds=30)

        oled.render_display()
        first_handle = oled._cancel_sleep_handle

        oled.render_display()
        second_handle = oled._cancel_sleep_handle

        # Timer should be restarted — new handle each time
        assert first_handle is not second_handle, "render_display must restart sleep timer"

    # -- wake_up cancels old timer before render_display re-creates one --

    @pytest.mark.asyncio
    async def test_wake_up_cancels_stale_timer(self):
        """If a sleep timer was somehow still pending, wake_up must cancel it."""
        loop = asyncio.get_running_loop()
        oled, _ = _make_oled(loop, sleep_seconds=30)

        # Simulate: timer is pending but OLED went to sleep already
        old_cancel = MagicMock()
        oled._sleep = True
        oled._cancel_sleep_handle = old_cancel

        oled.wake_up()

        old_cancel.assert_called_once()  # old timer was cancelled
        assert oled._cancel_sleep_handle is not None  # new timer created

    # -- sleep_timeout of 0 disables screensaver --

    @pytest.mark.asyncio
    async def test_zero_timeout_disables_sleep_timer(self):
        """With sleep_timeout=0, no timer should ever be started."""
        loop = asyncio.get_running_loop()
        oled, _ = _make_oled(loop, sleep_seconds=0)

        oled.render_display()

        assert oled._cancel_sleep_handle is None, "Zero sleep timeout must not schedule a timer"


# ---------------------------------------------------------------------------
# Tests – Shutdown state machine
# ---------------------------------------------------------------------------


class TestOledShutdownFlow:
    """Basic tests for the shutdown state machine."""

    @pytest.fixture(autouse=True)
    def _patch_canvas(self):
        with patch("boneio.hardware.display.oled.canvas", FakeCanvas):
            yield

    @pytest.mark.asyncio
    async def test_long_press_enters_wait_release(self):
        """A 2s+ long press in normal mode should enter 'wait_release' state."""
        loop = asyncio.get_running_loop()
        oled, _ = _make_oled(loop, sleep_seconds=30)

        # Simulate long press with duration >= threshold (2s)
        event = SimpleNamespace(click_type="long", duration=2.5)
        await oled._handle_button_press(event)

        assert oled._shutdown_state == "wait_release"

    @pytest.mark.asyncio
    async def test_single_click_cancels_shutdown(self):
        """During 'confirm' state, a single click must cancel shutdown."""
        loop = asyncio.get_running_loop()
        oled, _ = _make_oled(loop, sleep_seconds=30)

        # Force into confirm state
        oled._shutdown_state = "confirm"

        event = SimpleNamespace(click_type="single", duration=0.0)
        await oled._handle_button_press(event)

        assert not oled._shutdown_state, "Single click during confirm must cancel shutdown"

    @pytest.mark.asyncio
    async def test_long_press_during_sleep_wakes_only(self):
        """Long press while asleep should wake up, NOT start shutdown flow."""
        loop = asyncio.get_running_loop()
        oled, _ = _make_oled(loop, sleep_seconds=30)

        oled._sleep = True
        oled._cancel_sleep_handle = None

        # Long press while sleeping
        event = SimpleNamespace(click_type="long", duration=3.0)
        await oled._handle_button_press(event)

        # Should wake, not enter shutdown
        assert not oled._sleep
        assert oled._shutdown_state is None

    @pytest.mark.asyncio
    async def test_single_click_while_awake_does_not_start_shutdown(self):
        """A single click in normal mode must NOT enter shutdown state."""
        loop = asyncio.get_running_loop()
        oled, _ = _make_oled(loop, sleep_seconds=30)

        oled._sleep = False

        event = SimpleNamespace(click_type="single", duration=0.0)
        await oled._handle_button_press(event)

        assert oled._shutdown_state is None
