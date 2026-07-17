"""Tests for UpdateManager migration integration.

Tests cover:
- _get_migration_summary: building pending migration text for HA release_summary
- _fire_migration_event_if_pending: publishing binary_sensor state for migration alerts
- _send_migration_event_discovery: registering binary_sensor entity via HA MQTT discovery
- _publish_state_to_mqtt: release_summary includes migration info

These tests avoid importing the full boneio.core.manager package (which
requires gpiod, smbus2 and other hardware-only libraries) by loading
the update.py file directly via importlib.util.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import types
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Module-level import isolation
# ---------------------------------------------------------------------------


def _load_update_module():
    """Load boneio/core/manager/update.py in isolation.

    We must NOT register stubs under real ``boneio.*`` names in sys.modules
    because that would break other test files (e.g. test_homeassistant.py)
    that import the real modules.

    Instead we:
    1. Save any existing entries for the modules we need to stub.
    2. Temporarily register stubs under the real names.
    3. Execute the module.
    4. Restore sys.modules to the original state.

    Returns:
        The loaded update module containing UpdateManager.
    """
    stub_pkgs = [
        "boneio",
        "boneio.core",
        "boneio.core.manager",
        "boneio.core.utils",
        "boneio.core.utils.async_updater",
        "boneio.core.utils.timeperiod",
        "boneio.webui",
        "boneio.webui.services",
        "boneio.webui.services.logs",
        "boneio.integration",
        "boneio.integration.homeassistant",
        "boneio.version",
    ]

    # Save originals (if any)
    saved: dict[str, types.ModuleType | None] = {}
    for pkg in stub_pkgs:
        saved[pkg] = sys.modules.get(pkg)

    try:
        # Register temporary stubs
        for pkg in stub_pkgs:
            mod = types.ModuleType(pkg)
            mod.__path__ = []
            mod.__package__ = pkg
            sys.modules[pkg] = mod

        # Populate stubs with symbols that update.py imports
        au = sys.modules["boneio.core.utils.async_updater"]
        au.AsyncUpdater = type("AsyncUpdater", (), {"__init__": lambda self, **kw: None})

        tp = sys.modules["boneio.core.utils.timeperiod"]
        tp.TimePeriod = MagicMock

        logs = sys.modules["boneio.webui.services.logs"]
        logs.is_running_as_service = MagicMock(return_value=True)

        ver = sys.modules["boneio.version"]
        ver.__version__ = "1.3.0.test"

        ha = sys.modules["boneio.integration.homeassistant"]
        ha.ha_update_availability_message = MagicMock(return_value={"test": True})
        ha.ha_availabilty_message = MagicMock(
            return_value={
                "name": "Migration Alert",
                "unique_id": "test_migration_alert",
            }
        )
        ha.ha_migration_alert_availability_message = MagicMock(
            return_value={
                "name": "Migration Alert",
                "unique_id": "test_migration_alert",
                "state_topic": "boneio_test/migration/state",
                "value_template": "{{ value_json.state }}",
                "payload_on": "ON",
                "payload_off": "OFF",
                "json_attributes_topic": "boneio_test/migration/attributes",
                "icon": "mdi:alert-decagram",
                "entity_category": "diagnostic",
                "device_class": "problem",
            }
        )

        # Load the file directly
        update_path = Path(__file__).resolve().parents[3] / "boneio" / "core" / "manager" / "update.py"
        spec = importlib.util.spec_from_file_location("_test_update_stub_module", str(update_path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    finally:
        # Restore sys.modules — remove stubs, restore originals
        for pkg in stub_pkgs:
            original = saved[pkg]
            if original is None:
                sys.modules.pop(pkg, None)
            else:
                sys.modules[pkg] = original


_update_mod = _load_update_module()
UpdateManager = _update_mod.UpdateManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@dataclass
class FakeMigrationInfo:
    """Minimal stand-in for MigrationInfo."""

    version: str
    description: str


def _make_update_manager(
    pending: list[FakeMigrationInfo] | None = None,
    migration_runner_exists: bool = True,
) -> UpdateManager:
    """Create an UpdateManager with a mocked Manager.

    Args:
        pending: List of fake pending migrations.
        migration_runner_exists: Whether the manager has a migration_runner attr.

    Returns:
        Configured UpdateManager instance.
    """
    manager = MagicMock()
    manager._config_helper = MagicMock()
    manager._config_helper.topic_prefix = "boneio_test"
    manager._config_helper.update_channel = "stable"
    manager._config_helper.name = "Test Device"
    manager._config_helper.serial_number = "TEST123"
    manager._config_helper.ha_discovery_prefix = "homeassistant"
    manager._config_helper.device_type = "24x16"
    manager._config_helper.is_web_active = False
    manager._config_helper.cloud_registration = False
    manager._config_helper.network_info = {}
    manager._config_helper.get_area_name = MagicMock(return_value=None)
    manager._config_helper.child_devices = {}
    manager._topic_prefix = "boneio_test"
    manager.send_message = MagicMock()
    manager.publish_ha_discovery = MagicMock()
    manager._message_bus = MagicMock()
    manager._message_bus.subscribe_and_listen = AsyncMock()

    if migration_runner_exists and pending is not None:
        runner = MagicMock()
        runner._get_pending = MagicMock(return_value=pending)
        runner.pending_count = len(pending)
        runner.bootstrap_required = False
        manager.migration_runner = runner
    elif not migration_runner_exists:
        # getattr(manager, "migration_runner", None) → None
        del manager.migration_runner

    # Instantiate without __init__ (avoids AsyncUpdater background tasks)
    um = object.__new__(UpdateManager)
    um._manager = manager
    um._last_check_result = None
    um._last_published_state = None
    um._ha_discovery_sent = False
    um._update_running = False
    um.id = "update_manager"
    return um


# ---------------------------------------------------------------------------
# _get_migration_summary
# ---------------------------------------------------------------------------


class TestGetMigrationSummary:
    """Tests for _get_migration_summary."""

    def test_no_pending_returns_empty(self):
        """No pending migrations = empty string."""
        um = _make_update_manager(pending=[])
        assert um._get_migration_summary() == ""

    def test_one_pending(self):
        """Single pending migration produces correct summary."""
        pending = [FakeMigrationInfo("1.3.1", "Fast OLED boot splash")]
        um = _make_update_manager(pending=pending)
        result = um._get_migration_summary()
        assert "1" in result
        assert "pending" in result
        assert "Fast OLED boot splash" in result

    def test_three_pending(self):
        """Three pending migrations are all listed."""
        pending = [
            FakeMigrationInfo("1.3.0", "Baseline"),
            FakeMigrationInfo("1.3.1", "OLED fix"),
            FakeMigrationInfo("1.3.2", "Network fix"),
        ]
        um = _make_update_manager(pending=pending)
        result = um._get_migration_summary()
        assert "3" in result
        assert "Baseline" in result
        assert "OLED fix" in result
        assert "Network fix" in result
        assert "+0 more" not in result

    def test_four_pending_truncates(self):
        """More than 3 pending migrations shows '+N more' suffix."""
        pending = [
            FakeMigrationInfo("1.3.0", "A"),
            FakeMigrationInfo("1.3.1", "B"),
            FakeMigrationInfo("1.3.2", "C"),
            FakeMigrationInfo("1.3.3", "D"),
        ]
        um = _make_update_manager(pending=pending)
        result = um._get_migration_summary()
        assert "4" in result
        assert "+1 more" in result
        assert "D" not in result

    def test_no_migration_runner_returns_empty(self):
        """If manager has no migration_runner, returns empty."""
        um = _make_update_manager(migration_runner_exists=False)
        assert um._get_migration_summary() == ""

    def test_runner_exception_returns_empty(self):
        """If _get_pending() raises, returns empty (fail-safe)."""
        um = _make_update_manager(pending=[])
        um._manager.migration_runner._get_pending.side_effect = RuntimeError("broken")
        assert um._get_migration_summary() == ""


# ---------------------------------------------------------------------------
# _fire_migration_event_if_pending
# ---------------------------------------------------------------------------


class TestFireMigrationEvent:
    """Tests for _fire_migration_event_if_pending (binary_sensor state)."""

    def test_fires_pending_event(self):
        """Sets binary_sensor to ON when migrations are pending."""
        pending = [FakeMigrationInfo("1.3.1", "OLED fix")]
        um = _make_update_manager(pending=pending)

        asyncio.run(um._fire_migration_event_if_pending())

        # Two calls: state_topic + attributes_topic
        assert um._manager.send_message.call_count == 2
        state_call = um._manager.send_message.call_args_list[0]
        attr_call = um._manager.send_message.call_args_list[1]

        state_topic = state_call.kwargs.get("topic") or state_call[1].get("topic")
        state_payload = json.loads(state_call.kwargs.get("payload") or state_call[1].get("payload"))
        assert state_topic == "boneio_test/migration/state"
        assert state_payload["state"] == "ON"

        attr_topic = attr_call.kwargs.get("topic") or attr_call[1].get("topic")
        attr_payload = json.loads(attr_call.kwargs.get("payload") or attr_call[1].get("payload"))
        assert attr_topic == "boneio_test/migration/attributes"
        assert attr_payload["count"] == 1
        assert "OLED fix" in attr_payload["description"]

    def test_fires_ok_event_when_no_pending(self):
        """Sets binary_sensor to OFF when all migrations are applied."""
        um = _make_update_manager(pending=[])

        asyncio.run(um._fire_migration_event_if_pending())

        assert um._manager.send_message.call_count == 2
        state_call = um._manager.send_message.call_args_list[0]
        state_payload = json.loads(state_call.kwargs.get("payload") or state_call[1].get("payload"))
        assert state_payload["state"] == "OFF"

        attr_call = um._manager.send_message.call_args_list[1]
        attr_payload = json.loads(attr_call.kwargs.get("payload") or attr_call[1].get("payload"))
        assert attr_payload["count"] == 0

    def test_no_runner_does_nothing(self):
        """No migration runner = no message sent."""
        um = _make_update_manager(migration_runner_exists=False)
        asyncio.run(um._fire_migration_event_if_pending())
        um._manager.send_message.assert_not_called()

    def test_runner_exception_does_nothing(self):
        """Exception in _get_pending() = no message sent (fail-safe)."""
        um = _make_update_manager(pending=[])
        um._manager.migration_runner._get_pending.side_effect = RuntimeError("fail")
        asyncio.run(um._fire_migration_event_if_pending())
        um._manager.send_message.assert_not_called()

    def test_state_is_retained(self):
        """Migration binary_sensor state should be retained."""
        pending = [FakeMigrationInfo("1.3.1", "Fix")]
        um = _make_update_manager(pending=pending)

        asyncio.run(um._fire_migration_event_if_pending())

        for call in um._manager.send_message.call_args_list:
            retain = call.kwargs.get("retain", call[1].get("retain"))
            assert retain is True

    def test_five_pending_truncates_descriptions(self):
        """At most 5 migration descriptions in the event payload."""
        pending = [FakeMigrationInfo(f"1.3.{i}", f"Fix {i}") for i in range(7)]
        um = _make_update_manager(pending=pending)

        asyncio.run(um._fire_migration_event_if_pending())

        call_kwargs = um._manager.send_message.call_args
        payload_str = call_kwargs.kwargs.get("payload") or call_kwargs[1].get("payload")
        data = json.loads(payload_str)
        assert data["count"] == 7
        # Only first 5 descriptions joined
        assert "Fix 5" not in data["description"]
        assert "Fix 4" in data["description"]


# ---------------------------------------------------------------------------
# _send_migration_event_discovery
# ---------------------------------------------------------------------------


class TestMigrationEventDiscovery:
    """Tests for _send_migration_event_discovery (binary_sensor)."""

    def test_publishes_discovery(self):
        """Discovery message is published for migration_alert binary_sensor."""
        um = _make_update_manager(pending=[])

        asyncio.run(um._send_migration_event_discovery())

        um._manager.publish_ha_discovery.assert_called_once()
        call_args = um._manager.publish_ha_discovery.call_args
        assert call_args.kwargs["id"] == "migration_alert"
        assert call_args.kwargs["ha_type"] == "binary_sensor"

    def test_removes_legacy_event_entity(self):
        """Publishes empty payload on old event topic to remove legacy entity."""
        um = _make_update_manager(pending=[])

        asyncio.run(um._send_migration_event_discovery())

        # First send_message call should be the legacy cleanup
        legacy_call = um._manager.send_message.call_args_list[0]
        topic = legacy_call.kwargs.get("topic") or legacy_call[1].get("topic")
        payload = legacy_call.kwargs.get("payload") or legacy_call[1].get("payload")
        assert "event" in topic
        assert "migration_alert" in topic
        assert payload == ""

    def test_discovery_state_topic(self):
        """State topic uses /migration/state path."""
        um = _make_update_manager(pending=[])

        asyncio.run(um._send_migration_event_discovery())

        payload = um._manager.publish_ha_discovery.call_args.kwargs["payload"]
        assert payload["state_topic"] == "boneio_test/migration/state"

    def test_discovery_entity_category(self):
        """Binary sensor should be diagnostic category."""
        um = _make_update_manager(pending=[])

        asyncio.run(um._send_migration_event_discovery())

        payload = um._manager.publish_ha_discovery.call_args.kwargs["payload"]
        assert payload["entity_category"] == "diagnostic"

    def test_discovery_device_class(self):
        """Binary sensor should have device_class 'problem'."""
        um = _make_update_manager(pending=[])

        asyncio.run(um._send_migration_event_discovery())

        payload = um._manager.publish_ha_discovery.call_args.kwargs["payload"]
        assert payload["device_class"] == "problem"


# ---------------------------------------------------------------------------
# _publish_state_to_mqtt (integration: release_summary includes migrations)
# ---------------------------------------------------------------------------


class TestPublishStateWithMigrations:
    """Tests for release_summary including migration info."""

    def test_release_summary_includes_migration_note(self):
        """When migrations are pending, release_summary includes the note."""
        pending = [FakeMigrationInfo("1.3.1", "OLED fix")]
        um = _make_update_manager(pending=pending)

        update_info = {
            "status": "success",
            "current_version": "1.3.0",
            "latest_version": "1.3.1",
            "update_available": True,
            "release_url": "https://github.com/test",
            "release_notes": "Bug fixes",
        }

        asyncio.run(um._publish_state_to_mqtt(update_info))

        call_kwargs = um._manager.send_message.call_args
        payload = json.loads(call_kwargs.kwargs.get("payload") or call_kwargs[1].get("payload"))
        summary = payload["release_summary"]
        assert "pending" in summary.lower()
        assert "OLED fix" in summary
        assert "Bug fixes" in summary

    def test_release_summary_no_migrations(self):
        """When no migrations pending, release_summary has only release notes."""
        um = _make_update_manager(pending=[])

        update_info = {
            "status": "success",
            "current_version": "1.3.0",
            "latest_version": "1.3.1",
            "update_available": True,
            "release_url": "https://github.com/test",
            "release_notes": "Bug fixes",
        }

        asyncio.run(um._publish_state_to_mqtt(update_info))

        call_kwargs = um._manager.send_message.call_args
        payload = json.loads(call_kwargs.kwargs.get("payload") or call_kwargs[1].get("payload"))
        assert payload["release_summary"] == "Bug fixes"

    def test_release_summary_truncated_to_255(self):
        """release_summary must not exceed 255 chars (HA limit)."""
        pending = [FakeMigrationInfo(f"1.3.{i}", f"Very long migration name {i}" * 5) for i in range(5)]
        um = _make_update_manager(pending=pending)

        update_info = {
            "status": "success",
            "current_version": "1.3.0",
            "latest_version": "1.3.5",
            "update_available": True,
            "release_url": "",
            "release_notes": "A" * 200,
        }

        asyncio.run(um._publish_state_to_mqtt(update_info))

        call_kwargs = um._manager.send_message.call_args
        payload = json.loads(call_kwargs.kwargs.get("payload") or call_kwargs[1].get("payload"))
        assert len(payload["release_summary"]) <= 255

    def test_skips_publish_when_status_not_success(self):
        """Don't publish when status is not 'success'."""
        um = _make_update_manager(pending=[])

        update_info = {"status": "error", "message": "Network error"}
        asyncio.run(um._publish_state_to_mqtt(update_info))

        um._manager.send_message.assert_not_called()
