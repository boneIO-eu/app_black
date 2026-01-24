"""Tests for CANopen module.

These tests verify the basic functionality of the CANopen client and node classes.
For full integration testing, a virtual CAN interface (vcan0) is required.
"""

from __future__ import annotations

import pytest

from boneio.hardware.can.node import (
    BoneIOCANNode,
    DeviceType,
    HeartbeatMessage,
    NMTState,
    OutputStateMessage,
)


class TestOutputStateMessage:
    """Tests for OutputStateMessage class."""
    
    def test_to_bytes(self):
        """Test serialization to bytes."""
        msg = OutputStateMessage(output_index=5, state=1, brightness=128)
        data = msg.to_bytes()
        
        assert len(data) == 8
        assert data[0] == 5  # output_index
        assert data[1] == 1  # state
        assert data[2] == 128  # brightness
        assert data[3:] == bytes([0, 0, 0, 0, 0])  # reserved
    
    def test_from_bytes(self):
        """Test deserialization from bytes."""
        data = bytes([10, 1, 255, 0, 0, 0, 0, 0])
        msg = OutputStateMessage.from_bytes(data)
        
        assert msg.output_index == 10
        assert msg.state == 1
        assert msg.brightness == 255
    
    def test_from_bytes_short_data(self):
        """Test deserialization with insufficient data."""
        with pytest.raises(ValueError, match="Data too short"):
            OutputStateMessage.from_bytes(bytes([1, 2]))
    
    def test_roundtrip(self):
        """Test serialization/deserialization roundtrip."""
        original = OutputStateMessage(output_index=42, state=0, brightness=64)
        data = original.to_bytes()
        restored = OutputStateMessage.from_bytes(data)
        
        assert restored.output_index == original.output_index
        assert restored.state == original.state
        assert restored.brightness == original.brightness


class TestHeartbeatMessage:
    """Tests for HeartbeatMessage class."""
    
    def test_to_bytes(self):
        """Test serialization to bytes."""
        msg = HeartbeatMessage(node_id=5, state=NMTState.OPERATIONAL)
        data = msg.to_bytes()
        
        assert len(data) == 1
        assert data[0] == 0x05  # OPERATIONAL
    
    def test_from_bytes(self):
        """Test deserialization from bytes."""
        msg = HeartbeatMessage.from_bytes(node_id=3, data=bytes([0x05]))
        
        assert msg.node_id == 3
        assert msg.state == NMTState.OPERATIONAL
    
    def test_from_bytes_boot_up(self):
        """Test deserialization of boot-up state."""
        msg = HeartbeatMessage.from_bytes(node_id=1, data=bytes([0x00]))
        
        assert msg.state == NMTState.BOOT_UP
    
    def test_from_bytes_empty(self):
        """Test deserialization with empty data."""
        with pytest.raises(ValueError, match="empty"):
            HeartbeatMessage.from_bytes(node_id=1, data=bytes())


class TestBoneIOCANNode:
    """Tests for BoneIOCANNode class."""
    
    def test_creation(self):
        """Test node creation with default values."""
        node = BoneIOCANNode(node_id=5)
        
        assert node.node_id == 5
        assert node.name == "boneIO_5"
        assert node.device_type == DeviceType.UNKNOWN
        assert node.is_online is False
        assert node.is_operational is False
    
    def test_creation_with_name(self):
        """Test node creation with custom name."""
        node = BoneIOCANNode(node_id=10, name="Living Room")
        
        assert node.name == "Living Room"
    
    def test_invalid_node_id_low(self):
        """Test that node_id < 1 raises error."""
        with pytest.raises(ValueError, match="Invalid node_id"):
            BoneIOCANNode(node_id=0)
    
    def test_invalid_node_id_high(self):
        """Test that node_id > 127 raises error."""
        with pytest.raises(ValueError, match="Invalid node_id"):
            BoneIOCANNode(node_id=128)
    
    def test_update_heartbeat(self):
        """Test heartbeat update."""
        node = BoneIOCANNode(node_id=5)
        
        assert node.is_online is False
        
        node.update_heartbeat(timestamp=1000.0, state=NMTState.OPERATIONAL)
        
        assert node.is_online is True
        assert node.is_operational is True
        assert node.last_heartbeat == 1000.0
        assert node.nmt_state == NMTState.OPERATIONAL
    
    def test_update_output(self):
        """Test output state update."""
        node = BoneIOCANNode(node_id=5)
        
        node.update_output(output_index=3, state=1)
        node.update_output(output_index=7, state=0)
        
        assert node.outputs[3] == 1
        assert node.outputs[7] == 0
    
    def test_to_dict(self):
        """Test dictionary serialization."""
        node = BoneIOCANNode(
            node_id=5,
            name="Test Node",
            device_type=DeviceType.BONEIO_24X16,
            serial="ABC123",
        )
        node.update_heartbeat(1000.0, NMTState.OPERATIONAL)
        node.update_output(0, 1)
        
        d = node.to_dict()
        
        assert d["node_id"] == 5
        assert d["name"] == "Test Node"
        assert d["device_type"] == "BONEIO_24X16"
        assert d["serial"] == "ABC123"
        assert d["is_online"] is True
        assert d["nmt_state"] == "OPERATIONAL"
        assert d["outputs"] == {0: 1}


class TestNMTState:
    """Tests for NMTState enum."""
    
    def test_values(self):
        """Test NMT state values match CANopen standard."""
        assert NMTState.BOOT_UP == 0x00
        assert NMTState.STOPPED == 0x04
        assert NMTState.OPERATIONAL == 0x05
        assert NMTState.PRE_OPERATIONAL == 0x7F


class TestDeviceType:
    """Tests for DeviceType enum."""
    
    def test_values(self):
        """Test device type values."""
        assert DeviceType.BONEIO_24X16 == 0x01
        assert DeviceType.BONEIO_32X10 == 0x02
        assert DeviceType.BONEIO_COVER == 0x03
        assert DeviceType.UNKNOWN == 0xFF
