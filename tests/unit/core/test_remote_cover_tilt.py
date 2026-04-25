"""Unit tests for remote cover tilt support filtering.

Tests verify that:
1. Discovery publishes 'kind' and 'supports_tilt' for covers
2. RemoteDevice.set_covers() preserves tilt info from discovery
3. MQTTRemoteDevice.to_dict() nests covers under 'mqtt' key
4. Discovery enriches manually configured covers with tilt info
5. Tilt actions are only available for venetian covers
"""

from __future__ import annotations

import json
import sys
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

# Mock gpiod before importing boneio modules
mock_gpiod = MagicMock()
mock_gpiod.line = MagicMock()
mock_gpiod.line.Bias = MagicMock()
mock_gpiod.line.Direction = MagicMock()
mock_gpiod.line.Edge = MagicMock()
mock_gpiod.EdgeEvent = MagicMock()
mock_gpiod.LineRequest = MagicMock()
sys.modules.setdefault("gpiod", mock_gpiod)
sys.modules.setdefault("gpiod.line", mock_gpiod.line)

from boneio.core.remote.base import RemoteDeviceProtocol, RemoteDeviceType
from boneio.core.remote.mqtt import MQTTRemoteDevice


# ==================== Fixtures ====================


def _make_mock_cover(cover_id: str, name: str, kind: str) -> MagicMock:
    """Create a mock cover with kind property.

    Args:
        cover_id: Cover identifier.
        name: Human-readable name.
        kind: 'time' or 'venetian'.

    Returns:
        MagicMock mimicking a BaseCover.
    """
    cover = MagicMock()
    cover.name = name
    cover.kind = kind
    return cover


def _make_mock_manager_with_covers(
    covers: dict[str, MagicMock],
) -> MagicMock:
    """Create a mock Manager with cover sub-manager.

    Args:
        covers: Dict of cover_id -> mock cover.

    Returns:
        MagicMock mimicking a Manager.
    """
    manager = MagicMock()
    manager.covers._covers = covers
    manager._config_helper.topic_prefix = "boneio/blk_test123"
    manager._config_helper.send_boneio_autodiscovery = True
    manager._config_helper.name = "TestDevice"
    manager._config_helper._serial_no = "blk_test123"
    manager._config_helper._network_info = {"ip": "192.168.1.100"}
    return manager


# ==================== Discovery Build Covers ====================


class TestDiscoveryBuildCovers:
    """Test BlackDiscoveryPublisher._build_covers() includes tilt info."""

    def test_time_based_cover_has_supports_tilt_false(self):
        """Time-based cover should have supports_tilt=False and kind='time'."""
        from boneio.core.discovery import BlackDiscoveryPublisher

        covers = {
            "bedroom": _make_mock_cover("bedroom", "Bedroom Cover", "time"),
        }
        manager = _make_mock_manager_with_covers(covers)
        message_bus = MagicMock()

        publisher = BlackDiscoveryPublisher(manager, message_bus)
        result = publisher._build_covers()

        assert len(result) == 1
        assert result[0]["id"] == "bedroom"
        assert result[0]["name"] == "Bedroom Cover"
        assert result[0]["kind"] == "time"
        assert result[0]["supports_tilt"] is False

    def test_venetian_cover_has_supports_tilt_true(self):
        """Venetian cover should have supports_tilt=True and kind='venetian'."""
        from boneio.core.discovery import BlackDiscoveryPublisher

        covers = {
            "living_room": _make_mock_cover("living_room", "Living Room Blind", "venetian"),
        }
        manager = _make_mock_manager_with_covers(covers)
        message_bus = MagicMock()

        publisher = BlackDiscoveryPublisher(manager, message_bus)
        result = publisher._build_covers()

        assert len(result) == 1
        assert result[0]["id"] == "living_room"
        assert result[0]["kind"] == "venetian"
        assert result[0]["supports_tilt"] is True

    def test_mixed_covers(self):
        """Mix of time and venetian covers should have correct tilt flags."""
        from boneio.core.discovery import BlackDiscoveryPublisher

        covers = {
            "cover_a": _make_mock_cover("cover_a", "Cover A", "time"),
            "cover_b": _make_mock_cover("cover_b", "Cover B", "venetian"),
            "cover_c": _make_mock_cover("cover_c", "Cover C", "time"),
        }
        manager = _make_mock_manager_with_covers(covers)
        message_bus = MagicMock()

        publisher = BlackDiscoveryPublisher(manager, message_bus)
        result = publisher._build_covers()

        assert len(result) == 3
        result_map = {c["id"]: c for c in result}

        assert result_map["cover_a"]["supports_tilt"] is False
        assert result_map["cover_b"]["supports_tilt"] is True
        assert result_map["cover_c"]["supports_tilt"] is False

    def test_cover_without_kind_defaults_to_time(self):
        """Cover without kind attribute should default to kind='time'."""
        from boneio.core.discovery import BlackDiscoveryPublisher

        cover = MagicMock(spec=[])  # No 'kind' attribute
        cover.name = "Unknown Cover"
        covers = {"unknown": cover}
        manager = _make_mock_manager_with_covers(covers)
        message_bus = MagicMock()

        publisher = BlackDiscoveryPublisher(manager, message_bus)
        result = publisher._build_covers()

        assert len(result) == 1
        assert result[0]["kind"] == "time"
        assert result[0]["supports_tilt"] is False

    def test_empty_covers(self):
        """No covers should return empty list."""
        from boneio.core.discovery import BlackDiscoveryPublisher

        manager = _make_mock_manager_with_covers({})
        message_bus = MagicMock()

        publisher = BlackDiscoveryPublisher(manager, message_bus)
        result = publisher._build_covers()

        assert result == []


# ==================== RemoteDevice.set_covers ====================


class TestSetCoversPreservesTiltInfo:
    """Test RemoteDevice.set_covers() preserves kind and supports_tilt."""

    def test_set_covers_with_supports_tilt(self):
        """set_covers should preserve supports_tilt field from discovery data."""
        device = MQTTRemoteDevice(id="blk_test", name="Test Device")
        device.set_covers([
            {"id": "cover1", "name": "Cover 1", "kind": "time", "supports_tilt": False},
            {"id": "cover2", "name": "Cover 2", "kind": "venetian", "supports_tilt": True},
        ])

        assert len(device.covers) == 2
        cover_map = {c["id"]: c for c in device.covers}

        assert cover_map["cover1"]["supports_tilt"] is False
        assert cover_map["cover1"]["kind"] == "time"
        assert cover_map["cover2"]["supports_tilt"] is True
        assert cover_map["cover2"]["kind"] == "venetian"

    def test_set_covers_derives_supports_tilt_from_kind(self):
        """When supports_tilt is missing, it should be derived from kind."""
        device = MQTTRemoteDevice(id="blk_test", name="Test Device")
        device.set_covers([
            {"id": "cover1", "name": "Cover 1", "kind": "time"},
            {"id": "cover2", "name": "Cover 2", "kind": "venetian"},
        ])

        cover_map = {c["id"]: c for c in device.covers}

        assert cover_map["cover1"]["supports_tilt"] is False
        assert cover_map["cover2"]["supports_tilt"] is True

    def test_set_covers_without_tilt_info(self):
        """Covers without kind/supports_tilt should not have these fields."""
        device = MQTTRemoteDevice(id="blk_test", name="Test Device")
        device.set_covers([
            {"id": "cover1", "name": "Cover 1"},
        ])

        assert len(device.covers) == 1
        assert "supports_tilt" not in device.covers[0]
        assert "kind" not in device.covers[0]

    def test_set_covers_skips_entries_without_id(self):
        """Entries without 'id' should be silently skipped."""
        device = MQTTRemoteDevice(id="blk_test", name="Test Device")
        device.set_covers([
            {"name": "No ID Cover"},
            {"id": "valid", "name": "Valid Cover"},
            {"id": "", "name": "Empty ID"},
        ])

        assert len(device.covers) == 1
        assert device.covers[0]["id"] == "valid"

    def test_set_covers_uses_id_as_default_name(self):
        """When name is missing, id should be used as fallback."""
        device = MQTTRemoteDevice(id="blk_test", name="Test Device")
        device.set_covers([
            {"id": "cover_abc"},
        ])

        assert device.covers[0]["name"] == "cover_abc"


# ==================== MQTTRemoteDevice.to_dict ====================


class TestMQTTRemoteDeviceToDict:
    """Test MQTTRemoteDevice.to_dict() structure."""

    def test_to_dict_nests_covers_under_mqtt(self):
        """to_dict should return covers under 'mqtt.covers' key."""
        device = MQTTRemoteDevice(
            id="blk_abc",
            name="Test BoneIO",
            covers=[
                {"id": "c1", "name": "Cover 1", "kind": "time", "supports_tilt": False},
            ],
        )
        result = device.to_dict()

        assert "mqtt" in result
        assert "covers" in result["mqtt"]
        assert len(result["mqtt"]["covers"]) == 1
        assert result["mqtt"]["covers"][0]["id"] == "c1"
        assert result["mqtt"]["covers"][0]["supports_tilt"] is False

    def test_to_dict_nests_outputs_under_mqtt(self):
        """to_dict should return outputs under 'mqtt.outputs' key."""
        device = MQTTRemoteDevice(
            id="blk_abc",
            name="Test BoneIO",
            outputs=[{"id": "out1", "name": "Output 1"}],
        )
        result = device.to_dict()

        assert "mqtt" in result
        assert "outputs" in result["mqtt"]
        assert len(result["mqtt"]["outputs"]) == 1
        assert result["mqtt"]["outputs"][0]["id"] == "out1"

    def test_to_dict_includes_required_fields(self):
        """to_dict should include id, name, protocol, device_type, topic_prefix."""
        device = MQTTRemoteDevice(id="blk_abc", name="Test")
        result = device.to_dict()

        assert result["id"] == "blk_abc"
        assert result["name"] == "Test"
        assert result["protocol"] == "mqtt"
        assert result["device_type"] == "boneio_black"
        assert result["topic_prefix"] == "boneio/blk_abc"

    def test_to_dict_tilt_info_preserved_in_mqtt_covers(self):
        """Tilt info should be in mqtt.covers entries."""
        device = MQTTRemoteDevice(
            id="blk_abc",
            name="Test",
            covers=[
                {"id": "venetian1", "name": "V1", "kind": "venetian", "supports_tilt": True},
                {"id": "time1", "name": "T1", "kind": "time", "supports_tilt": False},
            ],
        )
        result = device.to_dict()
        cover_map = {c["id"]: c for c in result["mqtt"]["covers"]}

        assert cover_map["venetian1"]["supports_tilt"] is True
        assert cover_map["time1"]["supports_tilt"] is False


# ==================== Discovery Enrichment ====================


class TestDiscoveryEnrichesConfiguredCovers:
    """Test _update_configured_device_from_discovery enriches tilt info."""

    def _make_remote_manager_with_device(
        self, device: MQTTRemoteDevice
    ) -> "RemoteDeviceManager":
        """Create a RemoteDeviceManager with a single configured device.

        Args:
            device: Pre-configured MQTTRemoteDevice.

        Returns:
            RemoteDeviceManager instance.
        """
        from boneio.core.manager.remote import RemoteDeviceManager

        mgr = RemoteDeviceManager(message_bus=MagicMock(), own_serial="blk_myself")
        mgr._devices[device.id] = device
        mgr._initialized = True
        return mgr

    def test_enriches_covers_with_tilt_from_discovery(self):
        """Configured covers without tilt info should be enriched from discovery."""
        device = MQTTRemoteDevice(
            id="blk_remote",
            name="Remote Device",
            covers=[
                {"id": "cover1", "name": "Cover 1"},
                {"id": "cover2", "name": "Cover 2"},
            ],
        )
        mgr = self._make_remote_manager_with_device(device)

        # Simulate discovery payload with tilt info
        discovery_covers = [
            {"id": "cover1", "name": "Cover 1", "kind": "time", "supports_tilt": False},
            {"id": "cover2", "name": "Cover 2", "kind": "venetian", "supports_tilt": True},
        ]
        payload = json.dumps(discovery_covers)

        mgr._update_configured_device_from_discovery("blk_remote", "covers", payload)

        cover_map = {c["id"]: c for c in device.covers}
        assert cover_map["cover1"]["supports_tilt"] is False
        assert cover_map["cover1"]["kind"] == "time"
        assert cover_map["cover2"]["supports_tilt"] is True
        assert cover_map["cover2"]["kind"] == "venetian"

    def test_does_not_overwrite_existing_tilt_info(self):
        """If covers already have supports_tilt, discovery should not overwrite."""
        device = MQTTRemoteDevice(
            id="blk_remote",
            name="Remote Device",
            covers=[
                {"id": "cover1", "name": "Cover 1", "kind": "time", "supports_tilt": False},
            ],
        )
        mgr = self._make_remote_manager_with_device(device)

        # Discovery says tilt=True but cover already has tilt=False
        discovery_covers = [
            {"id": "cover1", "name": "Cover 1", "kind": "venetian", "supports_tilt": True},
        ]
        payload = json.dumps(discovery_covers)

        mgr._update_configured_device_from_discovery("blk_remote", "covers", payload)

        # Should NOT overwrite — existing value preserved
        assert device.covers[0]["supports_tilt"] is False

    def test_populates_covers_from_discovery_when_empty(self):
        """When device has no covers, discovery should populate them with tilt info."""
        device = MQTTRemoteDevice(id="blk_remote", name="Remote Device")
        assert device.covers == []

        mgr = self._make_remote_manager_with_device(device)

        discovery_covers = [
            {"id": "cover1", "name": "Cover 1", "kind": "venetian", "supports_tilt": True},
        ]
        payload = json.dumps(discovery_covers)

        mgr._update_configured_device_from_discovery("blk_remote", "covers", payload)

        assert len(device.covers) == 1
        assert device.covers[0]["supports_tilt"] is True
        assert device.covers[0]["kind"] == "venetian"

    def test_ignores_unknown_cover_ids_in_discovery(self):
        """Discovery covers not matching configured covers should be ignored."""
        device = MQTTRemoteDevice(
            id="blk_remote",
            name="Remote Device",
            covers=[{"id": "cover1", "name": "Cover 1"}],
        )
        mgr = self._make_remote_manager_with_device(device)

        discovery_covers = [
            {"id": "cover999", "name": "Unknown", "kind": "venetian", "supports_tilt": True},
        ]
        payload = json.dumps(discovery_covers)

        mgr._update_configured_device_from_discovery("blk_remote", "covers", payload)

        # cover1 should remain unchanged (no tilt info added)
        assert "supports_tilt" not in device.covers[0]

    def test_handles_invalid_json_gracefully(self):
        """Invalid JSON payload should not crash."""
        device = MQTTRemoteDevice(
            id="blk_remote",
            name="Remote Device",
            covers=[{"id": "cover1", "name": "Cover 1"}],
        )
        mgr = self._make_remote_manager_with_device(device)

        mgr._update_configured_device_from_discovery("blk_remote", "covers", "{invalid json")

        # Covers should remain unchanged
        assert len(device.covers) == 1
        assert "supports_tilt" not in device.covers[0]


# ==================== Autodiscovery Handle Covers ====================


class TestAutodiscoveryHandleCovers:
    """Test _handle_covers_discovery preserves tilt info on autodiscovered devices."""

    def test_autodiscovered_covers_have_tilt_info(self):
        """Covers received via autodiscovery should retain tilt fields."""
        from boneio.core.manager.remote import RemoteDeviceManager

        mgr = RemoteDeviceManager(message_bus=MagicMock(), own_serial="blk_myself")
        mgr._initialized = True

        # Create an autodiscovered device placeholder
        autodiscovered = MQTTRemoteDevice(id="blk_neighbor", name="Neighbor")
        mgr._autodiscovered_devices["blk_neighbor"] = autodiscovered

        # Handle covers discovery
        covers_data = [
            {"id": "blind1", "name": "Blind 1", "kind": "venetian", "supports_tilt": True},
            {"id": "roller1", "name": "Roller 1", "kind": "time", "supports_tilt": False},
        ]
        mgr._handle_covers_discovery("blk_neighbor", covers_data)

        cover_map = {c["id"]: c for c in autodiscovered.covers}
        assert cover_map["blind1"]["supports_tilt"] is True
        assert cover_map["blind1"]["kind"] == "venetian"
        assert cover_map["roller1"]["supports_tilt"] is False
        assert cover_map["roller1"]["kind"] == "time"

    def test_autodiscovered_to_dict_has_tilt_in_mqtt_covers(self):
        """Autodiscovered device to_dict should have tilt info in mqtt.covers."""
        from boneio.core.manager.remote import RemoteDeviceManager

        mgr = RemoteDeviceManager(message_bus=MagicMock(), own_serial="blk_myself")
        mgr._initialized = True

        autodiscovered = MQTTRemoteDevice(id="blk_neighbor", name="Neighbor")
        mgr._autodiscovered_devices["blk_neighbor"] = autodiscovered

        covers_data = [
            {"id": "blind1", "name": "Blind 1", "kind": "venetian", "supports_tilt": True},
        ]
        mgr._handle_covers_discovery("blk_neighbor", covers_data)

        result = autodiscovered.to_dict()
        assert result["mqtt"]["covers"][0]["supports_tilt"] is True
