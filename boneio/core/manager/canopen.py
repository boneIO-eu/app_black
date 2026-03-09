"""CANopen manager for boneIO.

Manages CANopen network communication between boneIO devices.
Handles node discovery, heartbeat monitoring, and PDO exchange.
"""

from __future__ import annotations

import asyncio
import logging
import os
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
        self._node_id: int | str = self._config.get("node_id", 1)
        self._mode = self._config.get("mode", "master")
        self._auto_setup = self._config.get("auto_setup", True)
        self._restart_on_error = self._config.get("restart_on_error", True)
        
        self._client: CANopenClient | None = None
        self._nodes: dict[int, BoneIOCANNode] = {}
        self._running = False
        
        self._heartbeat_task: asyncio.Task | None = None
        self._monitor_task: asyncio.Task | None = None
        self._bridge = None  # CANMQTTBridge, initialized in start() for master mode
        
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
    def node_id(self) -> int | str:
        """Get local node ID (int after start, may be 'auto' before)."""
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
            # Resolve node_id if set to 'auto'
            if self._node_id == "auto" or (isinstance(self._node_id, str) and self._node_id.lower() == "auto"):
                from boneio.hardware.can.node_id import resolve_node_id
                mac = ""
                config_dir = ""
                if self._manager is not None:
                    mac = self._manager.config_helper.network_info.get("mac", "")
                    config_dir = os.path.dirname(self._manager._config_file_path)
                self._node_id = resolve_node_id(self._node_id, mac, config_dir)

            # Auto-setup CAN interface if configured
            if self._auto_setup:
                from boneio.hardware.can.interface import setup_can_interface, interface_exists
                if not interface_exists(self._channel):
                    _LOGGER.error("CAN interface %s does not exist in the system", self._channel)
                    return False
                if not await setup_can_interface(self._channel, self._bitrate):
                    _LOGGER.error("Failed to auto-setup CAN interface %s", self._channel)
                    return False

            # Create and connect client (node_id is guaranteed int after resolve)
            self._client = CANopenClient(
                channel=self._channel,
                bitrate=self._bitrate,
                node_id=int(self._node_id),
            )
            
            if not await self._client.connect():
                _LOGGER.error("Failed to connect to CAN bus")
                return False
            
            # Register callbacks
            self._client.add_heartbeat_callback(self._on_heartbeat)
            self._client.add_pdo_callback(self._on_pdo)
            
            # Check for node_id collision (listen 3s for heartbeats)
            collision = await self._check_node_id_collision()
            if collision:
                _LOGGER.warning(
                    "Node ID %d collision detected, cannot start CANopen",
                    self._node_id,
                )
                await self._client.disconnect()
                self._client = None
                return False
            
            # Start background tasks
            self._running = True
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            self._monitor_task = asyncio.create_task(self._monitor_loop())
            
            # Start CAN-MQTT bridge in master mode
            if self._mode == "master" and self._manager is not None:
                from boneio.hardware.can.bridge import CANMQTTBridge
                self._bridge = CANMQTTBridge(
                    manager=self._manager,
                    canopen_manager=self,
                    message_bus=self._manager.message_bus,
                )
                self._bridge.start()

            _LOGGER.info(
                "CANopen manager started: channel=%s, bitrate=%d, node_id=%d, mode=%s",
                self._channel,
                self._bitrate,
                self._node_id,
                self._mode,
            )
            return True
            
        except Exception as e:
            _LOGGER.error("Failed to start CANopen manager: %s", e)
            self._running = False
            return False
    
    async def _check_node_id_collision(self, listen_seconds: float = 3.0) -> bool:
        """Check if another node on the bus uses the same node_id.

        Listens for heartbeat messages for `listen_seconds`. If a heartbeat
        from our own node_id is received, a collision is detected.

        Args:
            listen_seconds: How long to listen for collisions.

        Returns:
            True if collision detected.
        """
        collision_detected = False
        own_id = int(self._node_id)

        def _collision_cb(node_id: int, state: str) -> None:
            nonlocal collision_detected
            if node_id == own_id:
                collision_detected = True

        # Temporarily register collision callback
        if self._client is not None:
            self._client.add_heartbeat_callback(_collision_cb)

        _LOGGER.info(
            "Checking for node_id %d collision (%0.1fs)...", own_id, listen_seconds
        )
        await asyncio.sleep(listen_seconds)

        # Remove temporary callback
        if self._client is not None and _collision_cb in self._client._heartbeat_callbacks:
            self._client._heartbeat_callbacks.remove(_collision_cb)

        if collision_detected:
            _LOGGER.warning("Collision: another node is using node_id %d", own_id)
        else:
            _LOGGER.info("No node_id collision detected for %d", own_id)

        return collision_detected

    async def stop(self) -> None:
        """Stop CANopen manager."""
        if not self._running:
            return
        
        self._running = False
        
        # Stop bridge
        if self._bridge is not None:
            self._bridge.stop()
            self._bridge = None
        
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
        if not self.is_connected or self._client is None:
            return False
        
        return await self._client.send_output_state(output_index, state, brightness)
    
    async def send_command_to_node(
        self,
        target_node_id: int,
        output_index: int,
        state: int,
        brightness: int = 0,
    ) -> bool:
        """Send output command to a specific node via RPDO.

        Args:
            target_node_id: Target CAN node ID (1-127).
            output_index: Output index on the target device (0-47).
            state: Desired state (0=OFF, 1=ON).
            brightness: Brightness level (0-255).

        Returns:
            True if sent successfully.
        """
        if not self.is_connected or self._client is None:
            return False

        return await self._client.send_command_to_node(
            target_node_id, output_index, state, brightness
        )

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
                if self._client is None:
                    break
                await self._client.send_heartbeat(NMTState.OPERATIONAL)
                await asyncio.sleep(HEARTBEAT_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as e:
                _LOGGER.error("Error in heartbeat loop: %s", e)
                await asyncio.sleep(HEARTBEAT_INTERVAL)
        
        _LOGGER.debug("Heartbeat loop stopped")
    
    async def _monitor_loop(self) -> None:
        """Background task for monitoring node timeouts and bus-off recovery."""
        _LOGGER.debug("Monitor loop started")
        
        while self._running:
            try:
                current_time = time.time()
                
                # Check node timeouts
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
                
                # Check for bus-off and auto-restart
                if self._restart_on_error:
                    from boneio.hardware.can.interface import get_can_state
                    can_state = await get_can_state(self._channel)
                    if can_state == "BUS-OFF":
                        _LOGGER.warning("CAN bus-off detected on %s, restarting interface", self._channel)
                        from boneio.hardware.can.interface import restart_can_interface
                        if await restart_can_interface(self._channel, self._bitrate):
                            _LOGGER.info("CAN interface %s restarted successfully", self._channel)
                        else:
                            _LOGGER.error("Failed to restart CAN interface %s", self._channel)
                
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

            # Auto-register as CANRemoteDevice in Manager
            if self._manager is not None:
                from boneio.core.remote.can import CANRemoteDevice
                can_device = CANRemoteDevice(
                    node=self._nodes[node_id],
                    canopen_manager=self,
                )
                self._manager.remote_devices.add_device(can_device)
        
        self._nodes[node_id].update_heartbeat(time.time(), nmt_state)
    
    def _on_pdo(self, cob_id: int, data: bytes) -> None:
        """Handle received PDO message.
        
        Handles two PDO types:
        - TPDO1 (0x180 + node_id): output state broadcast from other nodes
        - RPDO1 (0x200 + node_id): command addressed to us from master
        
        Args:
            cob_id: COB-ID of the message
            data: PDO data
        """
        # RPDO1: 0x200 + our_node_id — command addressed to us (slave mode)
        if cob_id == 0x200 + int(self._node_id) and len(data) >= 3:
            output_index = data[0]
            state = data[1] & 0x01
            sender_id = data[3] if len(data) > 3 else 0
            _LOGGER.info(
                "Received command from node %d: output=%d, state=%d",
                sender_id, output_index, state,
            )
            # Execute locally via Manager
            if self._manager is not None:
                asyncio.get_event_loop().create_task(
                    self._execute_local_output_command(output_index, state)
                )
            return

        # TPDO1: 0x180 + node_id — output state broadcast from other nodes
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
    
    async def _execute_local_output_command(self, output_index: int, state: int) -> None:
        """Execute output command locally (slave receiving RPDO from master).

        Finds the output by index and toggles/sets it.

        Args:
            output_index: Output index (0-47).
            state: Desired state (0=OFF, 1=ON).
        """
        if self._manager is None:
            return

        try:
            outputs = self._manager.outputs
            output_list = list(outputs.get_all_outputs().values())
            if output_index >= len(output_list):
                _LOGGER.warning(
                    "CAN command for output index %d but only %d outputs configured",
                    output_index, len(output_list),
                )
                return

            output = output_list[output_index]
            if state == 1:
                await output.async_turn_on()
            else:
                await output.async_turn_off()
            _LOGGER.info(
                "Executed CAN command: output[%d]=%s -> %s",
                output_index, output.name if hasattr(output, "name") else str(output_index),
                "ON" if state else "OFF",
            )
        except Exception as e:
            _LOGGER.error("Failed to execute local output command: %s", e)

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
            "mode": self._mode,
            "nodes": [node.to_dict() for node in self._nodes.values()],
        }
