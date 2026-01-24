"""CANopen manager for boneIO.

Manages CANopen network communication between boneIO devices.
Handles node discovery, heartbeat monitoring, and PDO exchange.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any, Callable

from boneio.hardware.can.client import CANopenClient, CANOPEN_AVAILABLE
from boneio.hardware.can.node import (
    BoneIOCANNode,
    DeviceType,
    HeartbeatMessage,
    NMTState,
    OutputStateMessage,
)

if TYPE_CHECKING:
    from boneio.core.manager import Manager

_LOGGER = logging.getLogger(__name__)

# Heartbeat interval in seconds
HEARTBEAT_INTERVAL = 1.0

# Node timeout in seconds (consider offline if no heartbeat)
NODE_TIMEOUT = 5.0


class CANopenManager:
    """Manager for CANopen communication between boneIO devices.
    
    Handles:
    - Connection to CAN bus
    - Periodic heartbeat transmission
    - Discovery and monitoring of other nodes
    - PDO exchange for output state synchronization
    
    Args:
        manager: Main boneIO manager instance
        config: CANopen configuration dictionary
    """
    
    def __init__(
        self,
        manager: Manager | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize CANopen manager.
        
        Args:
            manager: Main boneIO manager instance
            config: CANopen configuration with keys:
                - enabled: bool (default: False)
                - channel: str (default: 'can0')
                - bitrate: int (default: 125000)
                - node_id: int (default: 1)
        """
        self._manager = manager
        self._config = config or {}
        
        self._enabled = self._config.get("enabled", False)
        self._channel = self._config.get("channel", "can0")
        self._bitrate = self._config.get("bitrate", 125000)
        self._node_id = self._config.get("node_id", 1)
        
        self._client: CANopenClient | None = None
        self._nodes: dict[int, BoneIOCANNode] = {}
        self._running = False
        
        self._heartbeat_task: asyncio.Task | None = None
        self._monitor_task: asyncio.Task | None = None
        
        # Callbacks for external handlers
        self._output_state_callbacks: list[Callable[[int, int, int], None]] = []
    
    @property
    def is_enabled(self) -> bool:
        """Check if CANopen is enabled in configuration."""
        return self._enabled and CANOPEN_AVAILABLE
    
    @property
    def is_connected(self) -> bool:
        """Check if connected to CAN bus."""
        return self._client is not None and self._client.is_connected
    
    @property
    def node_id(self) -> int:
        """Get local node ID."""
        return self._node_id
    
    @property
    def nodes(self) -> dict[int, BoneIOCANNode]:
        """Get dictionary of discovered nodes."""
        return self._nodes
    
    async def start(self) -> bool:
        """Start CANopen manager.
        
        Connects to CAN bus and starts heartbeat/monitoring tasks.
        
        Returns:
            True if started successfully.
        """
        if not self.is_enabled:
            _LOGGER.info("CANopen is disabled or not available")
            return False
        
        if self._running:
            _LOGGER.warning("CANopen manager already running")
            return True
        
        try:
            # Create and connect client
            self._client = CANopenClient(
                channel=self._channel,
                bitrate=self._bitrate,
                node_id=self._node_id,
            )
            
            if not await self._client.connect():
                _LOGGER.error("Failed to connect to CAN bus")
                return False
            
            # Register callbacks
            self._client.add_heartbeat_callback(self._on_heartbeat)
            self._client.add_pdo_callback(self._on_pdo)
            
            # Start background tasks
            self._running = True
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            self._monitor_task = asyncio.create_task(self._monitor_loop())
            
            _LOGGER.info(
                "CANopen manager started: channel=%s, bitrate=%d, node_id=%d",
                self._channel,
                self._bitrate,
                self._node_id,
            )
            return True
            
        except Exception as e:
            _LOGGER.error("Failed to start CANopen manager: %s", e)
            self._running = False
            return False
    
    async def stop(self) -> None:
        """Stop CANopen manager."""
        if not self._running:
            return
        
        self._running = False
        
        # Cancel background tasks
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None
        
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None
        
        # Disconnect client
        if self._client:
            await self._client.disconnect()
            self._client = None
        
        _LOGGER.info("CANopen manager stopped")
    
    async def send_output_state(
        self,
        output_index: int,
        state: int,
        brightness: int = 0,
    ) -> bool:
        """Send output state change to CAN bus.
        
        Other boneIO devices on the bus will receive this and can
        react accordingly (e.g., for synchronized lighting).
        
        Args:
            output_index: Output index (0-47)
            state: State (0=OFF, 1=ON)
            brightness: Brightness for dimmers (0-255)
            
        Returns:
            True if sent successfully.
        """
        if not self.is_connected:
            return False
        
        return await self._client.send_output_state(output_index, state, brightness)
    
    def add_output_state_callback(
        self,
        callback: Callable[[int, int, int], None],
    ) -> None:
        """Add callback for received output state changes.
        
        Args:
            callback: Function(node_id, output_index, state) called on reception.
        """
        self._output_state_callbacks.append(callback)
    
    def get_node(self, node_id: int) -> BoneIOCANNode | None:
        """Get node by ID.
        
        Args:
            node_id: Node ID to look up.
            
        Returns:
            BoneIOCANNode if found, None otherwise.
        """
        return self._nodes.get(node_id)
    
    def get_online_nodes(self) -> list[BoneIOCANNode]:
        """Get list of online nodes.
        
        Returns:
            List of nodes that have sent heartbeat recently.
        """
        return [node for node in self._nodes.values() if node.is_online]
    
    async def _heartbeat_loop(self) -> None:
        """Background task for sending periodic heartbeats."""
        _LOGGER.debug("Heartbeat loop started")
        
        while self._running:
            try:
                await self._client.send_heartbeat(NMTState.OPERATIONAL)
                await asyncio.sleep(HEARTBEAT_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as e:
                _LOGGER.error("Error in heartbeat loop: %s", e)
                await asyncio.sleep(HEARTBEAT_INTERVAL)
        
        _LOGGER.debug("Heartbeat loop stopped")
    
    async def _monitor_loop(self) -> None:
        """Background task for monitoring node timeouts."""
        _LOGGER.debug("Monitor loop started")
        
        while self._running:
            try:
                current_time = time.time()
                
                for node in list(self._nodes.values()):
                    if node.last_heartbeat is not None:
                        elapsed = current_time - node.last_heartbeat
                        if elapsed > NODE_TIMEOUT and node.is_online:
                            _LOGGER.warning(
                                "Node %d timed out (no heartbeat for %.1fs)",
                                node.node_id,
                                elapsed,
                            )
                            node.nmt_state = NMTState.PRE_OPERATIONAL
                
                await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                break
            except Exception as e:
                _LOGGER.error("Error in monitor loop: %s", e)
                await asyncio.sleep(1.0)
        
        _LOGGER.debug("Monitor loop stopped")
    
    def _on_heartbeat(self, node_id: int, state: str) -> None:
        """Handle received heartbeat message.
        
        Args:
            node_id: Node ID of sender
            state: NMT state string
        """
        if node_id == self._node_id:
            return  # Ignore own heartbeat
        
        # Map state string to NMTState
        state_map = {
            "BOOT-UP": NMTState.BOOT_UP,
            "STOPPED": NMTState.STOPPED,
            "OPERATIONAL": NMTState.OPERATIONAL,
            "PRE-OPERATIONAL": NMTState.PRE_OPERATIONAL,
        }
        nmt_state = state_map.get(state, NMTState.OPERATIONAL)
        
        # Create or update node
        if node_id not in self._nodes:
            self._nodes[node_id] = BoneIOCANNode(node_id=node_id)
            _LOGGER.info("Discovered new CANopen node: %d", node_id)
        
        self._nodes[node_id].update_heartbeat(time.time(), nmt_state)
    
    def _on_pdo(self, cob_id: int, data: bytes) -> None:
        """Handle received PDO message.
        
        Args:
            cob_id: COB-ID of the message
            data: PDO data
        """
        # Extract node_id from COB-ID
        # TPDO1: 0x180 + node_id
        if 0x181 <= cob_id <= 0x1FF:
            node_id = cob_id - 0x180
            
            if node_id == self._node_id:
                return  # Ignore own PDO
            
            try:
                msg = OutputStateMessage.from_bytes(data)
                _LOGGER.debug(
                    "Received output state from node %d: output=%d, state=%d",
                    node_id,
                    msg.output_index,
                    msg.state,
                )
                
                # Update node state
                if node_id in self._nodes:
                    self._nodes[node_id].update_output(msg.output_index, msg.state)
                
                # Call registered callbacks
                for callback in self._output_state_callbacks:
                    try:
                        callback(node_id, msg.output_index, msg.state)
                    except Exception as e:
                        _LOGGER.error("Error in output state callback: %s", e)
                        
            except Exception as e:
                _LOGGER.error("Failed to parse PDO data: %s", e)
    
    def to_dict(self) -> dict[str, Any]:
        """Get manager status as dictionary.
        
        Returns:
            Dictionary with manager status.
        """
        return {
            "enabled": self._enabled,
            "connected": self.is_connected,
            "channel": self._channel,
            "bitrate": self._bitrate,
            "node_id": self._node_id,
            "nodes": [node.to_dict() for node in self._nodes.values()],
        }
