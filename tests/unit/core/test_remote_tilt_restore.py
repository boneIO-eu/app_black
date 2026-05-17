"""Tests for remote ESPHome cover tilt restore functionality.

Tests verify that:
1. get_cover_state returns state for ESPHome devices
2. wait_for_cover_idle polls until cover reaches IDLE
3. _restore_remote_tilt waits for IDLE and sends set_tilt
4. REMOTE_COVER action dispatch schedules tilt restore when restore_tilt=True
5. Previous restore tasks are cancelled on new action
6. No restore is scheduled when tilt is 0 or unknown
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

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

from boneio.core.manager.remote import RemoteDeviceManager
from boneio.core.remote.base import RemoteDeviceProtocol


# ==================== Helpers ====================


def _make_esphome_device(
    cover_id: str = "gabinet",
    position: float = 0.5,
    tilt: float | None = 0.7,
    current_operation: int = 0,
) -> MagicMock:
    """Create a mock ESPHome remote device with cover state.

    Args:
        cover_id: Cover entity ID.
        position: Cover position (0.0-1.0).
        tilt: Cover tilt (0.0-1.0) or None if unknown.
        current_operation: 0=IDLE, 1=OPENING, 2=CLOSING.

    Returns:
        Mock ESPHome device.
    """
    device = MagicMock()
    device.protocol = RemoteDeviceProtocol.ESPHOME_API
    device._cover_states = {
        cover_id: {
            "position": position,
            "tilt": tilt,
            "current_operation": current_operation,
            "last_known_operation": 2,
        }
    }
    device.control_cover = AsyncMock(return_value=True)
    return device


def _make_remote_manager(
    device_id: str = "esp32",
    device: MagicMock | None = None,
) -> RemoteDeviceManager:
    """Create a RemoteDeviceManager with one ESPHome device.

    Args:
        device_id: Remote device ID.
        device: Pre-built mock device (or creates one with defaults).

    Returns:
        Configured RemoteDeviceManager.
    """
    mgr = RemoteDeviceManager(message_bus=MagicMock(), own_serial="blk_test")
    mgr._initialized = True
    mgr._devices[device_id] = device or _make_esphome_device()
    return mgr


# ==================== get_cover_state ====================


class TestGetCoverState:
    """Test RemoteDeviceManager.get_cover_state()."""

    def test_returns_state_for_esphome_device(self):
        """Should return cover state dict for ESPHome device."""
        mgr = _make_remote_manager()
        state = mgr.get_cover_state("esp32", "gabinet")

        assert state is not None
        assert state["position"] == 0.5
        assert state["tilt"] == 0.7
        assert state["current_operation"] == 0

    def test_returns_none_for_unknown_device(self):
        """Should return None when device doesn't exist."""
        mgr = _make_remote_manager()
        assert mgr.get_cover_state("unknown_device", "gabinet") is None

    def test_returns_none_for_unknown_cover(self):
        """Should return None when cover doesn't exist on device."""
        mgr = _make_remote_manager()
        assert mgr.get_cover_state("esp32", "unknown_cover") is None

    def test_returns_none_for_mqtt_device(self):
        """Should return None for non-ESPHome devices."""
        mqtt_device = MagicMock()
        mqtt_device.protocol = RemoteDeviceProtocol.MQTT
        mgr = _make_remote_manager(device=mqtt_device)
        assert mgr.get_cover_state("esp32", "gabinet") is None

    def test_state_reflects_tilt_none(self):
        """Should return state with tilt=None when tilt is unknown."""
        device = _make_esphome_device(tilt=None)
        mgr = _make_remote_manager(device=device)
        state = mgr.get_cover_state("esp32", "gabinet")

        assert state is not None
        assert state["tilt"] is None


# ==================== wait_for_cover_idle ====================


class TestWaitForCoverIdle:
    """Test RemoteDeviceManager.wait_for_cover_idle()."""

    async def test_returns_immediately_when_idle(self):
        """Should return True immediately when cover is already IDLE."""
        device = _make_esphome_device(current_operation=0)
        mgr = _make_remote_manager(device=device)

        result = await mgr.wait_for_cover_idle("esp32", "gabinet", timeout=5.0)
        assert result is True

    async def test_waits_for_idle_after_movement(self):
        """Should wait and return True when cover transitions to IDLE."""
        device = _make_esphome_device(current_operation=2)  # CLOSING
        mgr = _make_remote_manager(device=device)

        async def simulate_movement_end():
            """Simulate cover reaching end position after 0.3s."""
            await asyncio.sleep(0.3)
            device._cover_states["gabinet"]["current_operation"] = 0

        task = asyncio.create_task(simulate_movement_end())
        result = await mgr.wait_for_cover_idle(
            "esp32", "gabinet", timeout=5.0, poll_interval=0.1
        )
        await task

        assert result is True

    async def test_timeout_when_cover_never_stops(self):
        """Should return False on timeout when cover stays in motion."""
        device = _make_esphome_device(current_operation=1)  # OPENING
        mgr = _make_remote_manager(device=device)

        result = await mgr.wait_for_cover_idle(
            "esp32", "gabinet", timeout=0.3, poll_interval=0.1
        )
        assert result is False

    async def test_returns_false_for_non_esphome(self):
        """Should return False for non-ESPHome devices."""
        mqtt_device = MagicMock()
        mqtt_device.protocol = RemoteDeviceProtocol.MQTT
        mgr = _make_remote_manager(device=mqtt_device)

        result = await mgr.wait_for_cover_idle("esp32", "gabinet", timeout=0.3)
        assert result is False

    async def test_returns_false_for_unknown_device(self):
        """Should return False for unknown device."""
        mgr = _make_remote_manager()
        result = await mgr.wait_for_cover_idle("bad_id", "gabinet", timeout=0.3)
        assert result is False


# ==================== _restore_remote_tilt ====================


class TestRestoreRemoteTilt:
    """Test Manager._restore_remote_tilt() background task."""

    def _make_mock_manager(
        self,
        device_id: str = "esp32",
        cover_id: str = "gabinet",
        current_operation: int = 0,
    ) -> MagicMock:
        """Create a mock Manager with remote_devices for tilt restore tests.

        Args:
            device_id: Remote device ID.
            cover_id: Cover entity ID.
            current_operation: Initial cover operation state.

        Returns:
            Mock manager with necessary attributes.
        """
        from boneio.core.manager.manager import Manager

        manager = MagicMock(spec=Manager)
        manager._pending_tilt_restores = {}

        # Real remote_devices with mocked ESPHome device
        device = _make_esphome_device(
            cover_id=cover_id, current_operation=current_operation
        )
        remote_mgr = _make_remote_manager(device_id=device_id, device=device)
        manager.remote_devices = remote_mgr

        # Bind the real method
        manager._restore_remote_tilt = Manager._restore_remote_tilt.__get__(
            manager, Manager
        )
        return manager

    async def test_restores_tilt_after_idle(self):
        """Should send set_tilt after cover reaches IDLE."""
        manager = self._make_mock_manager(current_operation=0)

        await manager._restore_remote_tilt("esp32", "gabinet", 70)

        # Verify control_cover was called with tilt_position
        device = manager.remote_devices._devices["esp32"]
        device.control_cover.assert_called_once_with(
            cover_id="gabinet",
            action="TILT",
            tilt_position=70,
        )

    async def test_cleans_up_pending_dict(self):
        """Should remove itself from _pending_tilt_restores after completion."""
        manager = self._make_mock_manager(current_operation=0)
        manager._pending_tilt_restores["esp32:gabinet"] = MagicMock()

        await manager._restore_remote_tilt("esp32", "gabinet", 50)

        assert "esp32:gabinet" not in manager._pending_tilt_restores

    async def test_skips_restore_on_timeout(self):
        """Should not send set_tilt when cover never reaches IDLE."""
        manager = self._make_mock_manager(current_operation=2)  # stays CLOSING

        # Patch wait_for_cover_idle to always return False (timeout)
        manager.remote_devices.wait_for_cover_idle = AsyncMock(return_value=False)

        await manager._restore_remote_tilt("esp32", "gabinet", 70)

        device = manager.remote_devices._devices["esp32"]
        device.control_cover.assert_not_called()

    async def test_handles_cancellation(self):
        """Should handle CancelledError gracefully."""
        manager = self._make_mock_manager(current_operation=1)

        # Make wait_for_cover_idle raise CancelledError
        manager.remote_devices.wait_for_cover_idle = AsyncMock(
            side_effect=asyncio.CancelledError
        )
        manager._pending_tilt_restores["esp32:gabinet"] = MagicMock()

        await manager._restore_remote_tilt("esp32", "gabinet", 70)

        # Should clean up even on cancellation
        assert "esp32:gabinet" not in manager._pending_tilt_restores

    async def test_handles_exception(self):
        """Should handle unexpected exceptions without crashing."""
        manager = self._make_mock_manager(current_operation=0)

        # Make control_cover raise an exception
        device = manager.remote_devices._devices["esp32"]
        device.control_cover.side_effect = ConnectionError("Connection lost")

        # Should not raise
        await manager._restore_remote_tilt("esp32", "gabinet", 70)

        # Should clean up
        assert "esp32:gabinet" not in manager._pending_tilt_restores


# ==================== REMOTE_COVER dispatch integration ====================


class TestRemoteCoverRestoreTiltDispatch:
    """Test REMOTE_COVER action dispatch with restore_tilt flag."""

    async def test_no_restore_by_default(self):
        """By default, no tilt restore task should be created."""
        from boneio.core.manager.manager import Manager

        manager = MagicMock(spec=Manager)
        manager._pending_tilt_restores = {}

        device = _make_esphome_device()
        remote_mgr = _make_remote_manager(device=device)
        remote_mgr.control_cover = AsyncMock(return_value=True)
        manager.remote_devices = remote_mgr

        action_def = {
            "action": "remote_cover",
            "remote_device": "esp32",
            "cover_id": "gabinet",
            "action_cover": "CLOSE",
        }

        # Call the real method
        manager._execute_single_action = Manager._execute_single_action.__get__(
            manager, Manager
        )
        await manager._execute_single_action(action_def)

        assert len(manager._pending_tilt_restores) == 0

    async def test_restore_tilt_creates_background_task(self):
        """When restore_tilt=True, should create a background tilt restore task."""
        from boneio.core.manager.manager import Manager

        manager = MagicMock(spec=Manager)
        manager._pending_tilt_restores = {}

        device = _make_esphome_device(tilt=0.65, current_operation=0)
        remote_mgr = _make_remote_manager(device=device)
        remote_mgr.control_cover = AsyncMock(return_value=True)
        manager.remote_devices = remote_mgr
        manager._restore_remote_tilt = AsyncMock()

        action_def = {
            "action": "remote_cover",
            "remote_device": "esp32",
            "cover_id": "gabinet",
            "action_cover": "CLOSE",
            "restore_tilt": True,
        }

        manager._execute_single_action = Manager._execute_single_action.__get__(
            manager, Manager
        )
        await manager._execute_single_action(action_def)

        # Should have a pending task
        assert "esp32:gabinet" in manager._pending_tilt_restores

        # Clean up
        task = manager._pending_tilt_restores["esp32:gabinet"]
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def test_no_restore_when_tilt_is_none(self):
        """No restore task when tilt state is unknown."""
        from boneio.core.manager.manager import Manager

        manager = MagicMock(spec=Manager)
        manager._pending_tilt_restores = {}

        device = _make_esphome_device(tilt=None)
        remote_mgr = _make_remote_manager(device=device)
        remote_mgr.control_cover = AsyncMock(return_value=True)
        manager.remote_devices = remote_mgr

        action_def = {
            "action": "remote_cover",
            "remote_device": "esp32",
            "cover_id": "gabinet",
            "action_cover": "CLOSE",
            "restore_tilt": True,
        }

        manager._execute_single_action = Manager._execute_single_action.__get__(
            manager, Manager
        )
        await manager._execute_single_action(action_def)

        assert len(manager._pending_tilt_restores) == 0

    async def test_no_restore_when_tilt_is_zero(self):
        """No restore task when tilt is 0% (fully closed lamellae)."""
        from boneio.core.manager.manager import Manager

        manager = MagicMock(spec=Manager)
        manager._pending_tilt_restores = {}

        device = _make_esphome_device(tilt=0.0)
        remote_mgr = _make_remote_manager(device=device)
        remote_mgr.control_cover = AsyncMock(return_value=True)
        manager.remote_devices = remote_mgr

        action_def = {
            "action": "remote_cover",
            "remote_device": "esp32",
            "cover_id": "gabinet",
            "action_cover": "CLOSE",
            "restore_tilt": True,
        }

        manager._execute_single_action = Manager._execute_single_action.__get__(
            manager, Manager
        )
        await manager._execute_single_action(action_def)

        assert len(manager._pending_tilt_restores) == 0

    async def test_cancels_previous_restore_task(self):
        """New restore_tilt action should cancel previous pending restore."""
        from boneio.core.manager.manager import Manager

        manager = MagicMock(spec=Manager)
        manager._pending_tilt_restores = {}

        device = _make_esphome_device(tilt=0.65, current_operation=0)
        remote_mgr = _make_remote_manager(device=device)
        remote_mgr.control_cover = AsyncMock(return_value=True)
        manager.remote_devices = remote_mgr
        manager._restore_remote_tilt = AsyncMock()

        # Simulate existing pending task
        old_task = MagicMock()
        old_task.done.return_value = False
        manager._pending_tilt_restores["esp32:gabinet"] = old_task

        action_def = {
            "action": "remote_cover",
            "remote_device": "esp32",
            "cover_id": "gabinet",
            "action_cover": "CLOSE",
            "restore_tilt": True,
        }

        manager._execute_single_action = Manager._execute_single_action.__get__(
            manager, Manager
        )
        await manager._execute_single_action(action_def)

        # Old task should have been cancelled
        old_task.cancel.assert_called_once()

        # New task should be pending
        assert "esp32:gabinet" in manager._pending_tilt_restores
        new_task = manager._pending_tilt_restores["esp32:gabinet"]
        assert new_task is not old_task

        # Clean up
        if not new_task.done():
            new_task.cancel()
            try:
                await new_task
            except asyncio.CancelledError:
                pass
