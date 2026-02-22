"""Unit tests for CoverManager - cover relay reload.

Tests verify that when cover relay configuration changes (e.g. from OUT_01/OUT_02
to OUT_03/OUT_04), the CoverManager correctly updates the relay references
on existing cover instances during reload, without requiring a full app restart.
"""

from __future__ import annotations

import asyncio
import sys
from unittest.mock import MagicMock, patch

import pytest

# Mock gpiod before importing boneio modules
mock_gpiod = MagicMock()
mock_gpiod.line = MagicMock()
mock_gpiod.line.Bias = MagicMock()
mock_gpiod.line.Direction = MagicMock()
mock_gpiod.line.Edge = MagicMock()
mock_gpiod.EdgeEvent = MagicMock()
mock_gpiod.LineRequest = MagicMock()
sys.modules['gpiod'] = mock_gpiod
sys.modules['gpiod.line'] = mock_gpiod.line

from boneio.const import COVER
from boneio.core.utils import TimePeriod


def _make_mock_relay(relay_id: str) -> MagicMock:
    """Create a mock relay output with given ID.

    Args:
        relay_id: Identifier for the mock relay.

    Returns:
        MagicMock mimicking an MCPOutput with id property and turn_on/turn_off.
    """
    relay = MagicMock()
    relay.id = relay_id
    relay.turn_on = MagicMock()
    relay.turn_off = MagicMock()
    relay.async_send_state = MagicMock()
    return relay


def _make_mock_manager(outputs: dict[str, MagicMock]) -> MagicMock:
    """Create a mock Manager with outputs and required sub-managers.

    Args:
        outputs: Dict mapping output_id -> mock relay object.

    Returns:
        MagicMock mimicking the Manager class.
    """
    manager = MagicMock()
    manager.outputs.get_output = lambda output_id: outputs.get(output_id)
    manager.outputs.get_all_outputs.return_value = outputs
    manager._topic_prefix = "boneio"
    manager._message_bus = MagicMock()
    manager._event_bus = MagicMock()
    manager._state_manager = MagicMock()
    manager._state_manager.get.return_value = {"position": 100}
    manager._config_helper = MagicMock()
    manager._config_helper.topic_prefix = "boneio"
    manager._config_helper.ha_discovery = True
    manager._config_helper.ha_discovery_prefix = "homeassistant"
    manager._config_helper.get_autodiscovery_topics_for_id.return_value = []
    manager.send_message = MagicMock()
    manager.publish_ha_discovery = MagicMock()
    manager.loop = asyncio.new_event_loop()
    return manager


class TestCoverManagerRelayReload:
    """Tests for CoverManager relay update on configuration reload."""

    @pytest.fixture
    def event_loop(self):
        """Provide an event loop for tests that need asyncio."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        yield loop
        loop.close()

    @pytest.fixture
    def relays(self):
        """Create four mock relays: OUT_01..OUT_04."""
        return {
            "OUT_01": _make_mock_relay("OUT_01"),
            "OUT_02": _make_mock_relay("OUT_02"),
            "OUT_03": _make_mock_relay("OUT_03"),
            "OUT_04": _make_mock_relay("OUT_04"),
        }

    @pytest.fixture
    def initial_cover_config(self):
        """Cover config with OUT_01 (open) and OUT_02 (close)."""
        return [
            {
                "id": "test_cover",
                "platform": "time_based",
                "open_relay": "OUT_01",
                "close_relay": "OUT_02",
                "open_time": TimePeriod(seconds=10),
                "close_time": TimePeriod(seconds=10),
                "restore_state": False,
                "show_in_ha": False,
            }
        ]

    @pytest.fixture
    def updated_cover_config(self):
        """Cover config with OUT_03 (open) and OUT_04 (close)."""
        return [
            {
                "id": "test_cover",
                "platform": "time_based",
                "open_relay": "OUT_03",
                "close_relay": "OUT_04",
                "open_time": TimePeriod(seconds=10),
                "close_time": TimePeriod(seconds=10),
                "restore_state": False,
                "show_in_ha": False,
            }
        ]

    def test_initial_cover_has_correct_relays(self, event_loop, relays, initial_cover_config):
        """Test that a newly created cover has the correct relay references."""
        manager = _make_mock_manager(relays)

        from boneio.core.manager.covers import CoverManager
        cover_mgr = CoverManager(manager=manager, cover_config=initial_cover_config)

        cover = cover_mgr.get_cover("test_cover")
        assert cover is not None, "Cover 'test_cover' should exist"
        assert cover._open_relay.id == "OUT_01"
        assert cover._close_relay.id == "OUT_02"
        assert cover.kind == "time"

    def test_relay_update_on_reload(self, event_loop, relays, initial_cover_config, updated_cover_config):
        """Test that relays are updated when config changes and reload is triggered."""
        manager = _make_mock_manager(relays)

        from boneio.core.manager.covers import CoverManager
        cover_mgr = CoverManager(manager=manager, cover_config=initial_cover_config)

        cover = cover_mgr.get_cover("test_cover")
        assert cover._open_relay.id == "OUT_01"
        assert cover._close_relay.id == "OUT_02"

        # Simulate reload: ConfigHelper returns new config with different relays
        manager._config_helper.reload_config.return_value = {
            COVER: updated_cover_config,
        }

        cover_mgr.reload_covers()

        # Same cover object, but relays should be updated
        cover_after = cover_mgr.get_cover("test_cover")
        assert cover_after is cover, "Should be the same cover instance (not recreated)"
        assert cover_after._open_relay.id == "OUT_03", "Open relay should be updated to OUT_03"
        assert cover_after._close_relay.id == "OUT_04", "Close relay should be updated to OUT_04"

    def test_relay_unchanged_on_reload_same_config(self, event_loop, relays, initial_cover_config):
        """Test that relays stay the same when config doesn't change."""
        manager = _make_mock_manager(relays)

        from boneio.core.manager.covers import CoverManager
        cover_mgr = CoverManager(manager=manager, cover_config=initial_cover_config)

        cover = cover_mgr.get_cover("test_cover")
        original_open = cover._open_relay
        original_close = cover._close_relay

        # Reload with same config
        manager._config_helper.reload_config.return_value = {
            COVER: initial_cover_config,
        }

        cover_mgr.reload_covers()

        cover_after = cover_mgr.get_cover("test_cover")
        assert cover_after is cover
        # Relay objects are replaced (same id though), that's fine
        assert cover_after._open_relay.id == "OUT_01"
        assert cover_after._close_relay.id == "OUT_02"

    def test_platform_change_recreates_cover(self, event_loop, relays, initial_cover_config):
        """Test that changing platform from time_based to venetian recreates the cover."""
        manager = _make_mock_manager(relays)

        from boneio.core.manager.covers import CoverManager
        cover_mgr = CoverManager(manager=manager, cover_config=initial_cover_config)

        cover_before = cover_mgr.get_cover("test_cover")
        assert cover_before.kind == "time"

        venetian_config = [
            {
                "id": "test_cover",
                "platform": "venetian",
                "open_relay": "OUT_03",
                "close_relay": "OUT_04",
                "open_time": TimePeriod(seconds=10),
                "close_time": TimePeriod(seconds=10),
                "tilt_duration": TimePeriod(seconds=2),
                "actuator_activation_duration": TimePeriod(milliseconds=0),
                "restore_state": False,
                "show_in_ha": False,
            }
        ]

        manager._config_helper.reload_config.return_value = {
            COVER: venetian_config,
        }

        cover_mgr.reload_covers()

        cover_after = cover_mgr.get_cover("test_cover")
        assert cover_after is not cover_before, "Cover should be recreated when platform changes"
        assert cover_after.kind == "venetian"
        assert cover_after._open_relay.id == "OUT_03"
        assert cover_after._close_relay.id == "OUT_04"

    def test_cover_times_updated_on_reload(self, event_loop, relays, initial_cover_config):
        """Test that open_time and close_time are updated on reload."""
        manager = _make_mock_manager(relays)

        from boneio.core.manager.covers import CoverManager
        cover_mgr = CoverManager(manager=manager, cover_config=initial_cover_config)

        cover = cover_mgr.get_cover("test_cover")
        assert cover._open_time == 10000  # 10s in ms
        assert cover._close_time == 10000

        new_config = [
            {
                "id": "test_cover",
                "platform": "time_based",
                "open_relay": "OUT_01",
                "close_relay": "OUT_02",
                "open_time": TimePeriod(seconds=20),
                "close_time": TimePeriod(seconds=15),
                "restore_state": False,
                "show_in_ha": False,
            }
        ]

        manager._config_helper.reload_config.return_value = {
            COVER: new_config,
        }

        cover_mgr.reload_covers()

        assert cover._open_time == 20000, "Open time should be updated to 20s"
        assert cover._close_time == 15000, "Close time should be updated to 15s"

    def test_unknown_platform_falls_back_to_time_based(self, event_loop, relays):
        """Test that unknown platform falls back to time_based with a warning."""
        manager = _make_mock_manager(relays)

        config = [
            {
                "id": "test_cover",
                "platform": "unknown_platform",
                "open_relay": "OUT_01",
                "close_relay": "OUT_02",
                "open_time": TimePeriod(seconds=10),
                "close_time": TimePeriod(seconds=10),
                "restore_state": False,
                "show_in_ha": False,
            }
        ]

        from boneio.core.manager.covers import CoverManager
        cover_mgr = CoverManager(manager=manager, cover_config=config)

        cover = cover_mgr.get_cover("test_cover")
        assert cover is not None, "Cover should be created despite unknown platform"
        assert cover.kind == "time", "Should fall back to time_based"

    def test_cover_removed_on_reload(self, event_loop, relays, initial_cover_config):
        """Test that a cover is removed when it disappears from config after reload."""
        manager = _make_mock_manager(relays)

        from boneio.core.manager.covers import CoverManager
        cover_mgr = CoverManager(manager=manager, cover_config=initial_cover_config)

        assert cover_mgr.get_cover("test_cover") is not None
        assert len(cover_mgr.get_all_covers()) == 1

        # Reload with empty config (cover deleted by user)
        manager._config_helper.reload_config.return_value = {
            COVER: [],
        }

        cover_mgr.reload_covers()

        assert cover_mgr.get_cover("test_cover") is None, "Cover should be removed after reload"
        assert len(cover_mgr.get_all_covers()) == 0, "No covers should remain"

    def test_one_cover_removed_another_stays(self, event_loop, relays):
        """Test that only the deleted cover is removed, others stay."""
        manager = _make_mock_manager(relays)

        two_covers_config = [
            {
                "id": "cover_a",
                "platform": "time_based",
                "open_relay": "OUT_01",
                "close_relay": "OUT_02",
                "open_time": TimePeriod(seconds=10),
                "close_time": TimePeriod(seconds=10),
                "restore_state": False,
                "show_in_ha": False,
            },
            {
                "id": "cover_b",
                "platform": "time_based",
                "open_relay": "OUT_03",
                "close_relay": "OUT_04",
                "open_time": TimePeriod(seconds=10),
                "close_time": TimePeriod(seconds=10),
                "restore_state": False,
                "show_in_ha": False,
            },
        ]

        from boneio.core.manager.covers import CoverManager
        cover_mgr = CoverManager(manager=manager, cover_config=two_covers_config)

        assert len(cover_mgr.get_all_covers()) == 2

        # Reload with only cover_b (cover_a deleted)
        manager._config_helper.reload_config.return_value = {
            COVER: [two_covers_config[1]],
        }

        cover_mgr.reload_covers()

        assert cover_mgr.get_cover("cover_a") is None, "cover_a should be removed"
        assert cover_mgr.get_cover("cover_b") is not None, "cover_b should still exist"
        assert len(cover_mgr.get_all_covers()) == 1
