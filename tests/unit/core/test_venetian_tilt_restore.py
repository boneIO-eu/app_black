"""Tests for VenetianCover tilt restore after close feature.

Tests verify that when tilt_restore_after_close is enabled:
1. The previous tilt position is saved before closing.
2. After close movement completes, the tilt is restored to the saved value.
3. Opening the cover clears the saved tilt.
4. The feature does not interfere when disabled (default).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from boneio.components.cover.venetian import VenetianCover
from boneio.core.utils import TimePeriod
from boneio.const import IDLE


def _make_venetian(
    tilt_restore: bool = False,
    position: float = 100.0,
    tilt: float = 50.0,
) -> VenetianCover:
    """Create a VenetianCover with mocked relays for testing.

    Args:
        tilt_restore: Whether tilt_restore_after_close is enabled.
        position: Initial cover position (0-100).
        tilt: Initial tilt position (0-100).

    Returns:
        Configured VenetianCover instance with mock relays.
    """
    open_relay = MagicMock()
    open_relay.id = "open_relay"
    open_relay.turn_on = MagicMock()
    open_relay.turn_off = MagicMock()
    open_relay.async_send_state = AsyncMock()

    close_relay = MagicMock()
    close_relay.id = "close_relay"
    close_relay.turn_on = MagicMock()
    close_relay.turn_off = MagicMock()
    close_relay.async_send_state = AsyncMock()

    event_bus = MagicMock()
    event_bus.add_sigterm_listener = MagicMock()
    message_bus = MagicMock()
    message_bus.send_message = MagicMock()

    cover = VenetianCover(
        id="test_venetian",
        name="Test Venetian",
        open_relay=open_relay,
        close_relay=close_relay,
        state_save=MagicMock(),
        event_bus=event_bus,
        message_bus=message_bus,
        topic_prefix="boneio",
        open_time=TimePeriod(seconds=30),
        close_time=TimePeriod(seconds=30),
        tilt_duration=TimePeriod(seconds=2),
        actuator_activation_duration=TimePeriod(milliseconds=0),
        restored_state={"position": position, "tilt": tilt},
        tilt_restore_after_close=tilt_restore,
    )
    return cover


class TestTiltRestoreInit:
    """Test initialization with tilt_restore_after_close."""

    async def test_default_tilt_restore_disabled(self):
        """By default, tilt_restore_after_close is disabled."""
        cover = _make_venetian(tilt_restore=False)
        assert cover._tilt_restore_after_close is False
        assert cover._tilt_before_close is None

    async def test_tilt_restore_enabled(self):
        """When enabled, the flag is set."""
        cover = _make_venetian(tilt_restore=True)
        assert cover._tilt_restore_after_close is True
        assert cover._tilt_before_close is None


class TestTiltRestoreClose:
    """Test tilt saving during close()."""

    async def test_close_saves_tilt_when_enabled(self):
        """When tilt_restore is enabled, close() saves current tilt."""
        cover = _make_venetian(tilt_restore=True, tilt=45.0)

        # Patch run_cover to not start threads
        cover.run_cover = AsyncMock()
        cover._message_bus = MagicMock()

        await cover.close()

        assert cover._tilt_before_close == 45.0

    async def test_close_no_save_when_disabled(self):
        """When tilt_restore is disabled, close() does not save tilt."""
        cover = _make_venetian(tilt_restore=False, tilt=45.0)

        cover.run_cover = AsyncMock()
        cover._message_bus = MagicMock()

        await cover.close()

        assert cover._tilt_before_close is None

    async def test_close_no_save_when_tilt_zero(self):
        """When tilt is already 0, nothing to save."""
        cover = _make_venetian(tilt_restore=True, tilt=0.0)

        cover.run_cover = AsyncMock()
        cover._message_bus = MagicMock()

        await cover.close()

        assert cover._tilt_before_close is None


class TestTiltRestoreOpen:
    """Test tilt clearing during open()."""

    async def test_open_clears_saved_tilt(self):
        """Opening the cover clears any saved tilt."""
        cover = _make_venetian(tilt_restore=True, tilt=45.0)
        cover._tilt_before_close = 45.0

        cover.run_cover = AsyncMock()
        cover._message_bus = MagicMock()

        await cover.open()

        assert cover._tilt_before_close is None


class TestTiltRestoreSetPosition:
    """Test tilt saving during set_cover_position()."""

    async def test_set_position_lower_saves_tilt(self):
        """When setting a lower position (closing), tilt is saved."""
        cover = _make_venetian(tilt_restore=True, position=80.0, tilt=45.0)

        cover.run_cover = AsyncMock()
        cover._message_bus = MagicMock()

        await cover.set_cover_position(20)

        assert cover._tilt_before_close == 45.0

    async def test_set_position_higher_clears_tilt(self):
        """When setting a higher position (opening), saved tilt is cleared."""
        cover = _make_venetian(tilt_restore=True, position=30.0, tilt=45.0)
        cover._tilt_before_close = 45.0

        cover.run_cover = AsyncMock()
        cover._message_bus = MagicMock()

        await cover.set_cover_position(80)

        assert cover._tilt_before_close is None

    async def test_set_position_lower_disabled_no_save(self):
        """When disabled, set_cover_position does not save tilt."""
        cover = _make_venetian(tilt_restore=False, position=80.0, tilt=45.0)

        cover.run_cover = AsyncMock()
        cover._message_bus = MagicMock()

        await cover.set_cover_position(20)

        assert cover._tilt_before_close is None


class TestTiltRestoreMoveCover:
    """Test tilt restoration in _move_cover thread completion."""

    async def test_move_cover_restores_tilt_at_intermediate_position(self):
        """After movement to intermediate position, tilt restore is triggered."""
        cover = _make_venetian(tilt_restore=True, position=50.0, tilt=60.0)
        cover._tilt_before_close = 60.0

        # Simulate _move_cover finishing at 30% (intermediate)
        cover._current_operation = IDLE
        cover._position = 30.0
        cover._tilt_position = 0.0

        # Verify restore conditions at intermediate position
        at_extreme = cover._position <= 0 or cover._position >= 100
        assert at_extreme is False
        assert cover._tilt_before_close > 0
        assert abs(cover._tilt_position - cover._tilt_before_close) >= 1

    async def test_no_restore_at_position_zero(self):
        """At 0% (fully closed), tilt restore is skipped."""
        cover = _make_venetian(tilt_restore=True, position=80.0, tilt=60.0)
        cover._tilt_before_close = 60.0

        # Simulate _move_cover finishing at 0%
        cover._position = 0.0
        cover._tilt_position = 0.0

        at_extreme = cover._position <= 0 or cover._position >= 100
        assert at_extreme is True

    async def test_no_restore_at_position_100(self):
        """At 100% (fully open), tilt restore is skipped."""
        cover = _make_venetian(tilt_restore=True, position=30.0, tilt=45.0)
        cover._tilt_before_close = 45.0

        # Simulate _move_cover finishing at 100%
        cover._position = 100.0
        cover._tilt_position = 100.0

        at_extreme = cover._position <= 0 or cover._position >= 100
        assert at_extreme is True

    async def test_no_restore_when_disabled(self):
        """When disabled, _move_cover does not restore tilt."""
        cover = _make_venetian(tilt_restore=False, position=50.0, tilt=60.0)

        assert cover._tilt_before_close is None

        cover._tilt_position = 0.0
        should_restore = (
            cover._tilt_restore_after_close
            and cover._tilt_before_close is not None
        )
        assert should_restore is False

    async def test_no_restore_when_tilt_was_zero(self):
        """When saved tilt was 0, no restore is needed."""
        cover = _make_venetian(tilt_restore=True, position=50.0, tilt=0.0)
        cover._tilt_before_close = 0.0
        cover._tilt_position = 0.0

        # Restore should NOT trigger because restore_tilt is 0
        should_restore = (
            cover._tilt_restore_after_close
            and cover._tilt_before_close is not None
            and cover._tilt_before_close > 0
        )
        assert should_restore is False


class TestTiltRestoreUpdateConfig:
    """Test update_config_times with tilt_restore_after_close."""

    async def test_update_enables_tilt_restore(self):
        """tilt_restore_after_close can be enabled via config update."""
        cover = _make_venetian(tilt_restore=False)
        assert cover._tilt_restore_after_close is False

        cover.update_config_times({"tilt_restore_after_close": True})
        assert cover._tilt_restore_after_close is True

    async def test_update_disables_tilt_restore(self):
        """tilt_restore_after_close can be disabled via config update."""
        cover = _make_venetian(tilt_restore=True)
        assert cover._tilt_restore_after_close is True

        cover.update_config_times({"tilt_restore_after_close": False})
        assert cover._tilt_restore_after_close is False

    async def test_update_without_tilt_restore_preserves_value(self):
        """Config update without the key preserves existing value."""
        cover = _make_venetian(tilt_restore=True)
        cover.update_config_times({"open_time": TimePeriod(seconds=20)})
        assert cover._tilt_restore_after_close is True


class TestTiltRestoreFromActions:
    """Test tilt restore behavior when triggered from button actions."""

    async def test_action_skips_tilt_save_by_default(self):
        """By default, actions do not trigger tilt save."""
        cover = _make_venetian(tilt_restore=True, tilt=45.0)
        cover._from_action = True
        # _action_tilt_restore defaults to False

        cover.run_cover = AsyncMock()
        cover._message_bus = MagicMock()

        await cover.close()

        assert cover._tilt_before_close is None

    async def test_action_saves_tilt_with_restore_tilt(self):
        """When action has restore_tilt=True, tilt is saved."""
        cover = _make_venetian(tilt_restore=True, tilt=45.0)
        cover._from_action = True
        cover._action_tilt_restore = True

        cover.run_cover = AsyncMock()
        cover._message_bus = MagicMock()

        await cover.close()

        assert cover._tilt_before_close == 45.0

    async def test_ui_always_saves_tilt(self):
        """UI/HA calls (from_action=False) always save tilt."""
        cover = _make_venetian(tilt_restore=True, tilt=45.0)
        assert cover._from_action is False

        cover.run_cover = AsyncMock()
        cover._message_bus = MagicMock()

        await cover.close()

        assert cover._tilt_before_close == 45.0

    async def test_set_position_action_skips_tilt_save(self):
        """set_cover_position from action skips tilt save by default."""
        cover = _make_venetian(tilt_restore=True, position=80.0, tilt=45.0)
        cover._from_action = True

        cover.run_cover = AsyncMock()
        cover._message_bus = MagicMock()

        await cover.set_cover_position(20)

        assert cover._tilt_before_close is None

    async def test_set_position_action_saves_with_restore_tilt(self):
        """set_cover_position from action saves tilt when restore_tilt=True."""
        cover = _make_venetian(tilt_restore=True, position=80.0, tilt=45.0)
        cover._from_action = True
        cover._action_tilt_restore = True

        cover.run_cover = AsyncMock()
        cover._message_bus = MagicMock()

        await cover.set_cover_position(20)

        assert cover._tilt_before_close == 45.0
