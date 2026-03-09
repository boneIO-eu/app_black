"""CANopen client for boneIO.

Provides async wrapper around canopen-asyncio library for communication
with other CANopen nodes on the CAN bus.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from canopen import Network, LocalNode, RemoteNode

try:
    import canopen
    CANOPEN_AVAILABLE = True
except ImportError:
    CANOPEN_AVAILABLE = False
    canopen = None  # type: ignore[assignment]

_LOGGER = logging.getLogger(__name__)

# Default CAN interface settings
DEFAULT_INTERFACE = "socketcan"
DEFAULT_CHANNEL = "can0"
DEFAULT_BITRATE = 125000  # 125kbps - compatible with esphome-canopen


class CANopenClient:
    """Async CANopen client for boneIO.
    
    Manages CANopen network connection and provides methods for
    sending/receiving data to/from other CANopen nodes.
    
    Args:
        channel: CAN interface name (e.g., 'can0', 'vcan0')
        bitrate: CAN bus bitrate in bps (default: 125000)
        node_id: Local node ID (1-127)
    """
    
    def __init__(
        self,
        channel: str = DEFAULT_CHANNEL,
        bitrate: int = DEFAULT_BITRATE,
        node_id: int = 1,
    ) -> None:
        """Initialize CANopen client.
        
        Args:
            channel: CAN interface name (e.g., 'can0', 'vcan0')
            bitrate: CAN bus bitrate in bps
            node_id: Local node ID (1-127)
        """
        if not CANOPEN_AVAILABLE:
            raise ImportError(
                "canopen-asyncio is not installed. "
                "Install it with: pip install canopen-asyncio"
            )
        
        self._channel = channel
        self._bitrate = bitrate
        self._node_id = node_id
        self._network: Network | None = None
        self._local_node: LocalNode | None = None
        self._running = False
        self._loop: asyncio.AbstractEventLoop | None = None
        
        # Callbacks for received messages
        self._heartbeat_callbacks: list[Callable[[int, str], None]] = []
        self._pdo_callbacks: list[Callable[[int, bytes], None]] = []
    
    @property
    def is_connected(self) -> bool:
        """Check if connected to CAN bus."""
        return self._network is not None and self._running
    
    @property
    def node_id(self) -> int:
        """Get local node ID."""
        return self._node_id
    
    @property
    def channel(self) -> str:
        """Get CAN channel name."""
        return self._channel
    
    async def connect(self) -> bool:
        """Connect to CAN bus and start CANopen network.
        
        Returns:
            True if connection successful, False otherwise.
        """
        if self._running:
            _LOGGER.warning("CANopen client already connected")
            return True
        
        try:
            self._loop = asyncio.get_running_loop()
            
            # Create CANopen network
            self._network = canopen.Network()
            
            # Connect to CAN bus with asyncio loop
            self._network.connect(
                interface=DEFAULT_INTERFACE,
                channel=self._channel,
                bitrate=self._bitrate,
                loop=self._loop,
            )
            
            self._running = True
            _LOGGER.info(
                "CANopen client connected to %s at %d bps, node_id=%d",
                self._channel,
                self._bitrate,
                self._node_id,
            )
            return True
            
        except Exception as e:
            _LOGGER.error("Failed to connect to CAN bus: %s", e)
            self._running = False
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from CAN bus."""
        if not self._running:
            return
        
        try:
            if self._network:
                self._network.disconnect()
                self._network = None
            
            self._running = False
            _LOGGER.info("CANopen client disconnected from %s", self._channel)
            
        except Exception as e:
            _LOGGER.error("Error disconnecting from CAN bus: %s", e)
    
    async def send_heartbeat(self, state: int = 0x05) -> bool:
        """Send heartbeat message.
        
        Args:
            state: NMT state (0x00=boot, 0x04=stopped, 0x05=operational, 0x7F=pre-op)
            
        Returns:
            True if sent successfully.
        """
        if not self.is_connected:
            _LOGGER.warning("Cannot send heartbeat: not connected")
            return False
        
        try:
            # Heartbeat COB-ID: 0x700 + node_id
            cob_id = 0x700 + self._node_id
            data = bytes([state])
            
            # Send raw CAN message
            self._network.send_message(cob_id, data)
            _LOGGER.debug("Sent heartbeat: node_id=%d, state=0x%02X", self._node_id, state)
            return True
            
        except Exception as e:
            _LOGGER.error("Failed to send heartbeat: %s", e)
            return False
    
    async def send_pdo(
        self,
        pdo_number: int,
        data: bytes,
    ) -> bool:
        """Send PDO (Process Data Object) message.
        
        Args:
            pdo_number: PDO number (1-4 for TPDO)
            data: PDO data (up to 8 bytes)
            
        Returns:
            True if sent successfully.
        """
        if not self.is_connected:
            _LOGGER.warning("Cannot send PDO: not connected")
            return False
        
        if pdo_number < 1 or pdo_number > 4:
            _LOGGER.error("Invalid PDO number: %d (must be 1-4)", pdo_number)
            return False
        
        if len(data) > 8:
            _LOGGER.error("PDO data too long: %d bytes (max 8)", len(data))
            return False
        
        try:
            # TPDO COB-IDs: TPDO1=0x180+node_id, TPDO2=0x280+node_id, etc.
            base_cob_ids = {1: 0x180, 2: 0x280, 3: 0x380, 4: 0x480}
            cob_id = base_cob_ids[pdo_number] + self._node_id
            
            self._network.send_message(cob_id, data)
            _LOGGER.debug(
                "Sent TPDO%d: node_id=%d, cob_id=0x%03X, data=%s",
                pdo_number,
                self._node_id,
                cob_id,
                data.hex(),
            )
            return True
            
        except Exception as e:
            _LOGGER.error("Failed to send PDO: %s", e)
            return False
    
    async def send_output_state(
        self,
        output_index: int,
        state: int,
        brightness: int = 0,
    ) -> bool:
        """Send output state via TPDO1.
        
        This is a convenience method for sending output state changes
        to other boneIO devices on the CAN bus.
        
        Args:
            output_index: Output index (0-47)
            state: State (0=OFF, 1=ON)
            brightness: Brightness level (0-255, for dimmers)
            
        Returns:
            True if sent successfully.
        """
        # Pack data: [output_index, state, brightness, reserved...]
        data = bytes([
            output_index & 0xFF,
            state & 0x01,
            brightness & 0xFF,
            0, 0, 0, 0, 0,  # Reserved
        ])
        
        return await self.send_pdo(1, data)
    
    async def send_command_to_node(
        self,
        target_node_id: int,
        output_index: int,
        state: int,
        brightness: int = 0,
    ) -> bool:
        """Send output command to a specific node via RPDO1.

        Uses COB-ID 0x200 + target_node_id (RPDO1) to address
        a specific slave device on the CAN bus.

        Args:
            target_node_id: Node ID of the target device (1-127).
            output_index: Output index on the target device (0-47).
            state: Desired state (0=OFF, 1=ON).
            brightness: Brightness level (0-255, for dimmers).

        Returns:
            True if sent successfully.
        """
        if not self.is_connected:
            _LOGGER.warning("Cannot send command: not connected")
            return False

        try:
            # RPDO1 COB-ID: 0x200 + target_node_id
            cob_id = 0x200 + target_node_id
            data = bytes([
                output_index & 0xFF,
                state & 0x01,
                brightness & 0xFF,
                self._node_id & 0xFF,  # sender node_id for traceability
                0, 0, 0, 0,  # Reserved
            ])

            self._network.send_message(cob_id, data)
            _LOGGER.debug(
                "Sent command to node %d: RPDO1 cob_id=0x%03X, output=%d, state=%d",
                target_node_id, cob_id, output_index, state,
            )
            return True

        except Exception as e:
            _LOGGER.error("Failed to send command to node %d: %s", target_node_id, e)
            return False

    def add_heartbeat_callback(
        self,
        callback: Callable[[int, str], None],
    ) -> None:
        """Add callback for received heartbeat messages.
        
        Args:
            callback: Function(node_id, state) called on heartbeat reception.
        """
        self._heartbeat_callbacks.append(callback)
    
    def add_pdo_callback(
        self,
        callback: Callable[[int, bytes], None],
    ) -> None:
        """Add callback for received PDO messages.
        
        Args:
            callback: Function(cob_id, data) called on PDO reception.
        """
        self._pdo_callbacks.append(callback)
    
    def _on_heartbeat(self, node_id: int, state: str) -> None:
        """Handle received heartbeat message.
        
        Args:
            node_id: Node ID of sender
            state: NMT state string
        """
        _LOGGER.debug("Received heartbeat: node_id=%d, state=%s", node_id, state)
        for callback in self._heartbeat_callbacks:
            try:
                callback(node_id, state)
            except Exception as e:
                _LOGGER.error("Error in heartbeat callback: %s", e)
    
    async def __aenter__(self) -> "CANopenClient":
        """Async context manager entry."""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.disconnect()
