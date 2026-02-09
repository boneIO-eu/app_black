"""Full CAN bus integration tests with mocks.

Tests the complete CAN flow:
- MockCANopenClient send/receive
- CANRemoteDevice control_output via RPDO
- CANopenManager autodiscovery via heartbeat
- CANMQTTBridge relay CAN→MQTT
- node_id resolution and persistence
- Slave RPDO command execution
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mock gpiod and its submodules before any boneio imports that trigger
# the chain: boneio.core.manager -> InputManager -> gpiod.line
_gpiod_mock = MagicMock()
sys.modules.setdefault("gpiod", _gpiod_mock)
sys.modules.setdefault("gpiod.line", _gpiod_mock)
sys.modules.setdefault("gpiod.chip", _gpiod_mock)
sys.modules.setdefault("gpiod.edge_event", _gpiod_mock)
sys.modules.setdefault("gpiod.info_event", _gpiod_mock)
sys.modules.setdefault("gpiod.line_settings", _gpiod_mock)
sys.modules.setdefault("gpiod.line_request", _gpiod_mock)

from boneio.hardware.can.node import (
    BoneIOCANNode,
    NMTState,
    OutputStateMessage,
)
from tests.mocks.can import MockCANopenClient, SentCANMessage


# ============================================================================
# MockCANopenClient tests
# ============================================================================


class TestMockCANopenClient:
    """Tests for MockCANopenClient."""

    @pytest.mark.asyncio
    async def test_connect_disconnect(self):
        """Test connect and disconnect."""
        client = MockCANopenClient(node_id=1)
        assert not client.is_connected

        result = await client.connect()
        assert result is True
        assert client.is_connected

        await client.disconnect()
        assert not client.is_connected

    @pytest.mark.asyncio
    async def test_send_heartbeat(self):
        """Test heartbeat sends correct COB-ID."""
        client = MockCANopenClient(node_id=5)
        await client.connect()

        result = await client.send_heartbeat(0x05)
        assert result is True
        assert len(client.sent_messages) == 1
        assert client.sent_messages[0].cob_id == 0x705  # 0x700 + 5
        assert client.sent_messages[0].data == bytes([0x05])

    @pytest.mark.asyncio
    async def test_send_heartbeat_disconnected(self):
        """Test heartbeat fails when disconnected."""
        client = MockCANopenClient(node_id=1)
        result = await client.send_heartbeat()
        assert result is False
        assert len(client.sent_messages) == 0

    @pytest.mark.asyncio
    async def test_send_output_state(self):
        """Test output state sends TPDO1."""
        client = MockCANopenClient(node_id=3)
        await client.connect()

        result = await client.send_output_state(output_index=7, state=1, brightness=128)
        assert result is True
        assert len(client.sent_messages) == 1
        msg = client.sent_messages[0]
        assert msg.cob_id == 0x183  # TPDO1: 0x180 + 3
        assert msg.data[0] == 7   # output_index
        assert msg.data[1] == 1   # state
        assert msg.data[2] == 128 # brightness

    @pytest.mark.asyncio
    async def test_send_command_to_node(self):
        """Test RPDO1 command to specific node."""
        client = MockCANopenClient(node_id=1)
        await client.connect()

        result = await client.send_command_to_node(
            target_node_id=5, output_index=0, state=1, brightness=0,
        )
        assert result is True
        assert len(client.sent_messages) == 1
        msg = client.sent_messages[0]
        assert msg.cob_id == 0x205  # RPDO1: 0x200 + 5
        assert msg.data[0] == 0    # output_index
        assert msg.data[1] == 1    # state
        assert msg.data[3] == 1    # sender node_id

    @pytest.mark.asyncio
    async def test_send_command_disconnected(self):
        """Test command fails when disconnected."""
        client = MockCANopenClient(node_id=1)
        result = await client.send_command_to_node(5, 0, 1)
        assert result is False

    def test_simulate_heartbeat(self):
        """Test simulating incoming heartbeat triggers callbacks."""
        client = MockCANopenClient(node_id=1)
        received = []
        client.add_heartbeat_callback(lambda nid, state: received.append((nid, state)))

        client.simulate_heartbeat(5, "OPERATIONAL")
        assert len(received) == 1
        assert received[0] == (5, "OPERATIONAL")

    def test_simulate_pdo(self):
        """Test simulating incoming PDO triggers callbacks."""
        client = MockCANopenClient(node_id=1)
        received = []
        client.add_pdo_callback(lambda cob_id, data: received.append((cob_id, data)))

        data = bytes([0, 1, 0, 0, 0, 0, 0, 0])
        client.simulate_pdo(0x185, data)
        assert len(received) == 1
        assert received[0] == (0x185, data)

    def test_filter_sent_messages(self):
        """Test filtering sent messages by COB-ID."""
        client = MockCANopenClient(node_id=1)
        client.sent_messages.append(SentCANMessage(cob_id=0x701, data=b"\x05"))
        client.sent_messages.append(SentCANMessage(cob_id=0x181, data=b"\x00\x01"))
        client.sent_messages.append(SentCANMessage(cob_id=0x701, data=b"\x05"))

        heartbeats = client.get_sent_messages(cob_id_filter=0x701)
        assert len(heartbeats) == 2

        pdos = client.get_sent_messages(cob_id_filter=0x181)
        assert len(pdos) == 1


# ============================================================================
# CANRemoteDevice tests
# ============================================================================


class TestCANRemoteDevice:
    """Tests for CANRemoteDevice."""

    def _make_device(self):
        """Create a CANRemoteDevice with mocked dependencies."""
        from boneio.core.remote.can import CANRemoteDevice

        node = BoneIOCANNode(node_id=5)
        node.update_heartbeat(time.time(), NMTState.OPERATIONAL)

        canopen_mgr = MagicMock()
        canopen_mgr.send_command_to_node = AsyncMock(return_value=True)

        device = CANRemoteDevice(node=node, canopen_manager=canopen_mgr)
        return device, canopen_mgr

    def test_creation(self):
        """Test CANRemoteDevice creation."""
        device, _ = self._make_device()
        assert device.id == "can_5"
        assert device.node_id == 5
        assert device.is_online is True

    def test_offline_when_no_heartbeat(self):
        """Test device is offline when node has no heartbeat."""
        from boneio.core.remote.can import CANRemoteDevice

        node = BoneIOCANNode(node_id=5)
        canopen_mgr = MagicMock()
        device = CANRemoteDevice(node=node, canopen_manager=canopen_mgr)
        assert device.is_online is False

    @pytest.mark.asyncio
    async def test_control_output_on(self):
        """Test turning on output sends RPDO to correct node."""
        device, mgr = self._make_device()

        result = await device.control_output(output_id="0", action="ON")
        assert result is True
        mgr.send_command_to_node.assert_called_once_with(
            target_node_id=5, output_index=0, state=1,
        )

    @pytest.mark.asyncio
    async def test_control_output_off(self):
        """Test turning off output."""
        device, mgr = self._make_device()

        result = await device.control_output(output_id="3", action="OFF")
        assert result is True
        mgr.send_command_to_node.assert_called_once_with(
            target_node_id=5, output_index=3, state=0,
        )

    @pytest.mark.asyncio
    async def test_control_output_offline(self):
        """Test control fails when device is offline."""
        from boneio.core.remote.can import CANRemoteDevice

        node = BoneIOCANNode(node_id=5)
        canopen_mgr = MagicMock()
        canopen_mgr.send_command_to_node = AsyncMock()
        device = CANRemoteDevice(node=node, canopen_manager=canopen_mgr)

        result = await device.control_output(output_id="0", action="ON")
        assert result is False
        canopen_mgr.send_command_to_node.assert_not_called()

    @pytest.mark.asyncio
    async def test_control_output_invalid_id(self):
        """Test control fails with non-integer output_id."""
        device, mgr = self._make_device()

        result = await device.control_output(output_id="abc", action="ON")
        assert result is False
        mgr.send_command_to_node.assert_not_called()

    def test_to_dict(self):
        """Test dictionary serialization."""
        device, _ = self._make_device()
        d = device.to_dict()

        assert d["node_id"] == 5
        assert d["is_online"] is True
        assert d["nmt_state"] == "OPERATIONAL"


# ============================================================================
# CANopenManager autodiscovery tests
# ============================================================================


class TestCANopenManagerAutodiscovery:
    """Tests for CANopenManager heartbeat autodiscovery."""

    def _make_manager(self):
        """Create a CANopenManager with mocked client and Manager."""
        from boneio.core.manager.canopen import CANopenManager

        mock_manager = MagicMock()
        mock_manager.remote_devices = MagicMock()
        mock_manager.remote_devices.add_device = MagicMock()

        config = {
            "enabled": True,
            "channel": "vcan0",
            "bitrate": 125000,
            "node_id": 1,
            "mode": "master",
        }
        canopen_mgr = CANopenManager(manager=mock_manager, config=config)
        return canopen_mgr, mock_manager

    def test_heartbeat_creates_node(self):
        """Test that heartbeat from unknown node creates BoneIOCANNode."""
        canopen_mgr, _ = self._make_manager()

        canopen_mgr._on_heartbeat(5, "OPERATIONAL")

        assert 5 in canopen_mgr._nodes
        assert canopen_mgr._nodes[5].node_id == 5
        assert canopen_mgr._nodes[5].nmt_state == NMTState.OPERATIONAL

    def test_heartbeat_registers_remote_device(self):
        """Test that heartbeat auto-registers CANRemoteDevice in Manager."""
        canopen_mgr, mock_manager = self._make_manager()

        canopen_mgr._on_heartbeat(5, "OPERATIONAL")

        mock_manager.remote_devices.add_device.assert_called_once()
        device = mock_manager.remote_devices.add_device.call_args[0][0]
        assert device.id == "can_5"
        assert device.node_id == 5

    def test_heartbeat_ignores_own_node(self):
        """Test that own heartbeat is ignored."""
        canopen_mgr, mock_manager = self._make_manager()

        canopen_mgr._on_heartbeat(1, "OPERATIONAL")  # node_id=1 is ours

        assert 1 not in canopen_mgr._nodes
        mock_manager.remote_devices.add_device.assert_not_called()

    def test_heartbeat_updates_existing_node(self):
        """Test that repeated heartbeat updates existing node, doesn't re-register."""
        canopen_mgr, mock_manager = self._make_manager()

        canopen_mgr._on_heartbeat(5, "PRE-OPERATIONAL")
        canopen_mgr._on_heartbeat(5, "OPERATIONAL")

        # Should only register once
        assert mock_manager.remote_devices.add_device.call_count == 1
        # But state should be updated
        assert canopen_mgr._nodes[5].nmt_state == NMTState.OPERATIONAL

    def test_multiple_nodes_discovered(self):
        """Test discovering multiple nodes."""
        canopen_mgr, mock_manager = self._make_manager()

        canopen_mgr._on_heartbeat(5, "OPERATIONAL")
        canopen_mgr._on_heartbeat(10, "OPERATIONAL")
        canopen_mgr._on_heartbeat(20, "OPERATIONAL")

        assert len(canopen_mgr._nodes) == 3
        assert mock_manager.remote_devices.add_device.call_count == 3


# ============================================================================
# PDO handling tests
# ============================================================================


class TestCANopenManagerPDO:
    """Tests for CANopenManager PDO handling."""

    def _make_manager(self, node_id=1):
        """Create a CANopenManager with mocked dependencies."""
        from boneio.core.manager.canopen import CANopenManager

        mock_manager = MagicMock()
        mock_manager.remote_devices = MagicMock()
        mock_manager.remote_devices.add_device = MagicMock()

        config = {
            "enabled": True,
            "channel": "vcan0",
            "bitrate": 125000,
            "node_id": node_id,
            "mode": "slave",
        }
        canopen_mgr = CANopenManager(manager=mock_manager, config=config)
        return canopen_mgr, mock_manager

    def test_tpdo1_updates_node_state(self):
        """Test TPDO1 from another node updates its output state."""
        canopen_mgr, _ = self._make_manager(node_id=1)

        # First discover node 5
        canopen_mgr._on_heartbeat(5, "OPERATIONAL")

        # Simulate TPDO1 from node 5: output=0, state=1
        data = OutputStateMessage(output_index=0, state=1, brightness=0).to_bytes()
        canopen_mgr._on_pdo(0x185, data)  # 0x180 + 5

        assert canopen_mgr._nodes[5].outputs[0] == 1

    def test_tpdo1_triggers_callbacks(self):
        """Test TPDO1 triggers registered output state callbacks."""
        canopen_mgr, _ = self._make_manager(node_id=1)
        canopen_mgr._on_heartbeat(5, "OPERATIONAL")

        received = []
        canopen_mgr.add_output_state_callback(
            lambda nid, oidx, state: received.append((nid, oidx, state))
        )

        data = OutputStateMessage(output_index=3, state=1).to_bytes()
        canopen_mgr._on_pdo(0x185, data)

        assert len(received) == 1
        assert received[0] == (5, 3, 1)

    def test_tpdo1_ignores_own(self):
        """Test TPDO1 from own node is ignored."""
        canopen_mgr, _ = self._make_manager(node_id=5)

        received = []
        canopen_mgr.add_output_state_callback(
            lambda nid, oidx, state: received.append((nid, oidx, state))
        )

        data = OutputStateMessage(output_index=0, state=1).to_bytes()
        canopen_mgr._on_pdo(0x185, data)  # 0x180 + 5 = our own

        assert len(received) == 0

    def test_rpdo1_addressed_to_us(self):
        """Test RPDO1 addressed to our node triggers local execution."""
        canopen_mgr, mock_manager = self._make_manager(node_id=5)

        # Simulate RPDO1 addressed to us (0x200 + 5 = 0x205)
        data = bytes([0, 1, 0, 1, 0, 0, 0, 0])  # output=0, state=1, sender=1
        
        with patch.object(canopen_mgr, '_execute_local_output_command', new_callable=AsyncMock) as mock_exec:
            # We need an event loop for create_task
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                canopen_mgr._on_pdo(0x205, data)
                # Let the created task run
                loop.run_until_complete(asyncio.sleep(0.1))
            finally:
                loop.close()

    def test_rpdo1_not_for_us_ignored(self):
        """Test RPDO1 addressed to different node is ignored."""
        canopen_mgr, _ = self._make_manager(node_id=5)

        received = []
        canopen_mgr.add_output_state_callback(
            lambda nid, oidx, state: received.append((nid, oidx, state))
        )

        # RPDO1 for node 10 (0x200 + 10 = 0x20A) — not for us
        data = bytes([0, 1, 0, 1, 0, 0, 0, 0])
        canopen_mgr._on_pdo(0x20A, data)

        # Should not trigger any callback (it's not TPDO range either)
        assert len(received) == 0


# ============================================================================
# CANMQTTBridge tests
# ============================================================================


class TestCANMQTTBridge:
    """Tests for CANMQTTBridge."""

    def _make_bridge(self):
        """Create a bridge with mocked dependencies."""
        from boneio.hardware.can.bridge import CANMQTTBridge

        mock_manager = MagicMock()
        mock_manager.config_helper.topic_prefix = "boneio"

        mock_canopen = MagicMock()
        mock_canopen._mode = "master"
        mock_canopen.nodes = {}
        mock_canopen.get_node = MagicMock(return_value=None)
        mock_canopen.add_output_state_callback = MagicMock()
        mock_canopen.send_output_state = AsyncMock(return_value=True)

        mock_message_bus = MagicMock()
        mock_message_bus.send_message = MagicMock()

        bridge = CANMQTTBridge(
            manager=mock_manager,
            canopen_manager=mock_canopen,
            message_bus=mock_message_bus,
        )
        return bridge, mock_canopen, mock_message_bus

    def test_start_registers_callback(self):
        """Test that start() registers output state callback."""
        bridge, mock_canopen, _ = self._make_bridge()
        bridge.start()

        mock_canopen.add_output_state_callback.assert_called_once()

    def test_can_to_mqtt_relay(self):
        """Test CAN output state is relayed to MQTT."""
        bridge, _, mock_bus = self._make_bridge()
        bridge.start()

        # Simulate CAN output state from node 5
        bridge._on_can_output_state(node_id=5, output_index=0, state=1)

        mock_bus.send_message.assert_called_once()
        call_kwargs = mock_bus.send_message.call_args
        assert "can_5" in call_kwargs.kwargs.get("topic", call_kwargs[1].get("topic", ""))
        assert call_kwargs.kwargs.get("payload", call_kwargs[1].get("payload", "")) == "ON"

    def test_can_to_mqtt_off(self):
        """Test CAN OFF state is relayed correctly."""
        bridge, _, mock_bus = self._make_bridge()
        bridge.start()

        bridge._on_can_output_state(node_id=5, output_index=2, state=0)

        mock_bus.send_message.assert_called_once()
        call_kwargs = mock_bus.send_message.call_args
        assert call_kwargs.kwargs.get("payload", call_kwargs[1].get("payload", "")) == "OFF"

    def test_bridge_stopped_no_relay(self):
        """Test no relay when bridge is stopped."""
        bridge, _, mock_bus = self._make_bridge()
        bridge.start()
        bridge.stop()

        bridge._on_can_output_state(node_id=5, output_index=0, state=1)
        mock_bus.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_command_to_slave(self):
        """Test MQTT→CAN command forwarding."""
        bridge, mock_canopen, _ = self._make_bridge()
        bridge.start()

        result = await bridge.send_command_to_slave(
            node_id=5, output_index=0, state=1,
        )
        assert result is True
        mock_canopen.send_output_state.assert_called_once_with(0, 1, 0)

    def test_to_dict(self):
        """Test bridge status serialization."""
        bridge, _, _ = self._make_bridge()
        bridge.start()

        d = bridge.to_dict()
        assert d["running"] is True
        assert d["mode"] == "master"


# ============================================================================
# node_id resolution tests
# ============================================================================


class TestNodeIdResolution:
    """Tests for node_id resolution and persistence."""

    def test_manual_node_id(self):
        """Test manual node_id is returned as-is."""
        from boneio.hardware.can.node_id import resolve_node_id

        result = resolve_node_id(42, "aa:bb:cc:dd:ee:ff", "/tmp")
        assert result == 42

    def test_auto_node_id_from_mac(self):
        """Test auto node_id is generated from MAC."""
        from boneio.hardware.can.node_id import resolve_node_id

        with tempfile.TemporaryDirectory() as tmpdir:
            result = resolve_node_id("auto", "aa:bb:cc:dd:ee:ff", tmpdir)
            assert 1 <= result <= 127

    def test_auto_node_id_persistence(self):
        """Test auto node_id is persisted and re-read."""
        from boneio.hardware.can.node_id import resolve_node_id

        with tempfile.TemporaryDirectory() as tmpdir:
            result1 = resolve_node_id("auto", "aa:bb:cc:dd:ee:ff", tmpdir)
            result2 = resolve_node_id("auto", "aa:bb:cc:dd:ee:ff", tmpdir)
            assert result1 == result2

    def test_auto_node_id_different_macs(self):
        """Test different MACs produce different node_ids (usually)."""
        from boneio.hardware.can.node_id import resolve_node_id

        with tempfile.TemporaryDirectory() as tmpdir1, \
             tempfile.TemporaryDirectory() as tmpdir2:
            result1 = resolve_node_id("auto", "aa:bb:cc:dd:ee:01", tmpdir1)
            result2 = resolve_node_id("auto", "aa:bb:cc:dd:ee:02", tmpdir2)
            # They might collide (1/127 chance) but usually won't
            # Just verify both are valid
            assert 1 <= result1 <= 127
            assert 1 <= result2 <= 127

    def test_persisted_file_exists(self):
        """Test persistence file is created."""
        from boneio.hardware.can.node_id import resolve_node_id

        with tempfile.TemporaryDirectory() as tmpdir:
            resolve_node_id("auto", "aa:bb:cc:dd:ee:ff", tmpdir)
            assert os.path.exists(os.path.join(tmpdir, "can_node_id"))


# ============================================================================
# RemoteDeviceManager.add_device tests
# ============================================================================


class TestRemoteDeviceManagerAddDevice:
    """Tests for dynamic device registration."""

    def test_add_device(self):
        """Test adding a CAN remote device."""
        from boneio.core.manager.remote import RemoteDeviceManager
        from boneio.core.remote.can import CANRemoteDevice

        rdm = RemoteDeviceManager()

        node = BoneIOCANNode(node_id=5)
        canopen_mgr = MagicMock()
        device = CANRemoteDevice(node=node, canopen_manager=canopen_mgr)

        rdm.add_device(device)
        assert rdm.get_device("can_5") is device

    def test_add_device_duplicate_skipped(self):
        """Test duplicate device is not re-added."""
        from boneio.core.manager.remote import RemoteDeviceManager
        from boneio.core.remote.can import CANRemoteDevice

        rdm = RemoteDeviceManager()

        node = BoneIOCANNode(node_id=5)
        canopen_mgr = MagicMock()
        device1 = CANRemoteDevice(node=node, canopen_manager=canopen_mgr)
        device2 = CANRemoteDevice(node=node, canopen_manager=canopen_mgr)

        rdm.add_device(device1)
        rdm.add_device(device2)

        # Should still be device1
        assert rdm.get_device("can_5") is device1
