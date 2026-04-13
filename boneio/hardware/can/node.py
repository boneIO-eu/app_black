"""BoneIO CANopen node implementation.

Defines the CANopen node for boneIO Black devices, including
Object Dictionary entries and PDO mappings.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

_LOGGER = logging.getLogger(__name__)


class NMTState(IntEnum):
    """CANopen NMT (Network Management) states."""
    
    BOOT_UP = 0x00
    STOPPED = 0x04
    OPERATIONAL = 0x05
    PRE_OPERATIONAL = 0x7F


class DeviceType(IntEnum):
    """BoneIO device types for CAN identification."""
    
    BONEIO_24X16 = 0x01
    BONEIO_32X10 = 0x02
    BONEIO_COVER = 0x03
    BONEIO_COVER_MIX = 0x04
    UNKNOWN = 0xFF


@dataclass
class OutputStateMessage:
    """Output state message structure for TPDO1.
    
    This message is sent when an output state changes on a boneIO device.
    Other devices on the CAN bus can receive this to sync their state.
    
    Attributes:
        output_index: Output index (0-47)
        state: Output state (0=OFF, 1=ON)
        brightness: Brightness level for dimmers (0-255)
    """
    
    output_index: int
    state: int
    brightness: int = 0
    
    def to_bytes(self) -> bytes:
        """Serialize to CAN message data.
        
        Returns:
            8-byte CAN message data.
        """
        return bytes([
            self.output_index & 0xFF,
            self.state & 0x01,
            self.brightness & 0xFF,
            0, 0, 0, 0, 0,  # Reserved
        ])
    
    @classmethod
    def from_bytes(cls, data: bytes) -> OutputStateMessage:
        """Deserialize from CAN message data.
        
        Args:
            data: CAN message data (at least 3 bytes).
            
        Returns:
            OutputStateMessage instance.
        """
        if len(data) < 3:
            raise ValueError(f"Data too short: {len(data)} bytes (need at least 3)")
        
        return cls(
            output_index=data[0],
            state=data[1] & 0x01,
            brightness=data[2],
        )


@dataclass
class HeartbeatMessage:
    """Heartbeat message structure.
    
    Standard CANopen heartbeat message (COB-ID: 0x700 + node_id).
    
    Attributes:
        node_id: Node ID of the sender (1-127)
        state: NMT state
    """
    
    node_id: int
    state: NMTState
    
    def to_bytes(self) -> bytes:
        """Serialize to CAN message data.
        
        Returns:
            1-byte CAN message data.
        """
        return bytes([self.state])
    
    @classmethod
    def from_bytes(cls, node_id: int, data: bytes) -> HeartbeatMessage:
        """Deserialize from CAN message data.
        
        Args:
            node_id: Node ID extracted from COB-ID.
            data: CAN message data (1 byte).
            
        Returns:
            HeartbeatMessage instance.
        """
        if len(data) < 1:
            raise ValueError("Heartbeat data is empty")
        
        try:
            state = NMTState(data[0])
        except ValueError:
            state = NMTState.OPERATIONAL  # Default to operational
        
        return cls(node_id=node_id, state=state)


@dataclass
class BoneIOCANNode:
    """Represents a boneIO device on the CAN bus.
    
    This class holds information about a discovered or configured
    boneIO device that communicates via CANopen.
    
    Attributes:
        node_id: CANopen node ID (1-127)
        name: Human-readable device name
        device_type: Type of boneIO device
        serial: Device serial number (if known)
        last_heartbeat: Timestamp of last heartbeat (None if never received)
        nmt_state: Current NMT state
        outputs: Dictionary of output states {index: state}
    """
    
    node_id: int
    name: str = ""
    device_type: DeviceType = DeviceType.UNKNOWN
    serial: str = ""
    last_heartbeat: float | None = None
    nmt_state: NMTState = NMTState.PRE_OPERATIONAL
    outputs: dict[int, int] = field(default_factory=dict)
    
    def __post_init__(self) -> None:
        """Validate node configuration."""
        if not 1 <= self.node_id <= 127:
            raise ValueError(f"Invalid node_id: {self.node_id} (must be 1-127)")
        
        if not self.name:
            self.name = f"boneIO_{self.node_id}"
    
    @property
    def is_online(self) -> bool:
        """Check if node is online (received heartbeat recently).
        
        Returns:
            True if node has sent a heartbeat.
        """
        return self.last_heartbeat is not None
    
    @property
    def is_operational(self) -> bool:
        """Check if node is in operational state.
        
        Returns:
            True if node is operational.
        """
        return self.nmt_state == NMTState.OPERATIONAL
    
    def update_heartbeat(self, timestamp: float, state: NMTState) -> None:
        """Update heartbeat information.
        
        Args:
            timestamp: Timestamp of heartbeat reception.
            state: NMT state from heartbeat.
        """
        self.last_heartbeat = timestamp
        self.nmt_state = state
        _LOGGER.debug(
            "Node %d heartbeat: state=%s",
            self.node_id,
            state.name,
        )
    
    def update_output(self, output_index: int, state: int) -> None:
        """Update output state.
        
        Args:
            output_index: Output index.
            state: New state (0=OFF, 1=ON).
        """
        self.outputs[output_index] = state
        _LOGGER.debug(
            "Node %d output %d: state=%d",
            self.node_id,
            output_index,
            state,
        )
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization.
        
        Returns:
            Dictionary representation.
        """
        return {
            "node_id": self.node_id,
            "name": self.name,
            "device_type": self.device_type.name,
            "serial": self.serial,
            "is_online": self.is_online,
            "nmt_state": self.nmt_state.name,
            "outputs": self.outputs,
        }
