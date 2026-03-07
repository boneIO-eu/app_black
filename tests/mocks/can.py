"""Mock CAN client for testing.

Provides mock implementations of CANopenClient and related CAN components
for testing without real CAN hardware.

Example:
    mock_client = MockCANopenClient(node_id=1)
    await mock_client.connect()
    await mock_client.send_command_to_node(5, 0, 1)
    assert mock_client.sent_messages[-1] == (0x205, b'\\x00\\x01\\x00\\x01...')
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

_LOGGER = logging.getLogger(__name__)


@dataclass
class SentCANMessage:
    """Record of a sent CAN message.

    Attributes:
        cob_id: COB-ID of the message.
        data: Raw CAN data bytes.
        description: Human-readable description.
    """

    cob_id: int
    data: bytes
    description: str = ""


class MockCANopenClient:
    """Mock CANopenClient for testing without CAN hardware.

    Simulates CANopenClient behavior: connect/disconnect, send heartbeat,
    send PDO, send command to node, and callback registration.

    Args:
        channel: CAN channel name (ignored in mock).
        bitrate: CAN bitrate (stored for verification).
        node_id: Our node ID.
    """

    def __init__(
        self,
        channel: str = "vcan0",
        bitrate: int = 125000,
        node_id: int = 1,
    ) -> None:
        """Initialize mock CAN client.

        Args:
            channel: CAN channel name.
            bitrate: CAN bitrate.
            node_id: Our node ID.
        """
        self._channel = channel
        self._bitrate = bitrate
        self._node_id = node_id
        self._connected = False

        self._heartbeat_callbacks: list[Callable[[int, str], None]] = []
        self._pdo_callbacks: list[Callable[[int, bytes], None]] = []

        # Track all sent messages for assertions
        self.sent_messages: list[SentCANMessage] = []

    @property
    def is_connected(self) -> bool:
        """Check if connected."""
        return self._connected

    async def connect(self) -> bool:
        """Simulate CAN connection.

        Returns:
            True (always succeeds in mock).
        """
        self._connected = True
        _LOGGER.debug("MockCANopenClient connected (channel=%s)", self._channel)
        return True

    async def disconnect(self) -> None:
        """Simulate CAN disconnection."""
        self._connected = False
        _LOGGER.debug("MockCANopenClient disconnected")

    async def send_heartbeat(self, state: int = 0x05) -> bool:
        """Simulate sending heartbeat.

        Args:
            state: NMT state byte.

        Returns:
            True if connected.
        """
        if not self._connected:
            return False
        cob_id = 0x700 + self._node_id
        data = bytes([state])
        self.sent_messages.append(SentCANMessage(
            cob_id=cob_id, data=data,
            description=f"heartbeat node={self._node_id} state=0x{state:02X}",
        ))
        return True

    async def send_pdo(self, pdo_number: int, data: bytes) -> bool:
        """Simulate sending PDO.

        Args:
            pdo_number: PDO number (1-4).
            data: PDO data (up to 8 bytes).

        Returns:
            True if connected and valid.
        """
        if not self._connected:
            return False
        if pdo_number < 1 or pdo_number > 4:
            return False
        if len(data) > 8:
            return False

        base_cob_ids = {1: 0x180, 2: 0x280, 3: 0x380, 4: 0x480}
        cob_id = base_cob_ids[pdo_number] + self._node_id
        self.sent_messages.append(SentCANMessage(
            cob_id=cob_id, data=data,
            description=f"TPDO{pdo_number} node={self._node_id}",
        ))
        return True

    async def send_output_state(
        self, output_index: int, state: int, brightness: int = 0,
    ) -> bool:
        """Simulate sending output state via TPDO1.

        Args:
            output_index: Output index.
            state: State (0/1).
            brightness: Brightness (0-255).

        Returns:
            True if sent.
        """
        data = bytes([
            output_index & 0xFF,
            state & 0x01,
            brightness & 0xFF,
            0, 0, 0, 0, 0,
        ])
        return await self.send_pdo(1, data)

    async def send_command_to_node(
        self,
        target_node_id: int,
        output_index: int,
        state: int,
        brightness: int = 0,
    ) -> bool:
        """Simulate sending RPDO1 command to a specific node.

        Args:
            target_node_id: Target node ID.
            output_index: Output index.
            state: Desired state.
            brightness: Brightness.

        Returns:
            True if sent.
        """
        if not self._connected:
            return False

        cob_id = 0x200 + target_node_id
        data = bytes([
            output_index & 0xFF,
            state & 0x01,
            brightness & 0xFF,
            self._node_id & 0xFF,
            0, 0, 0, 0,
        ])
        self.sent_messages.append(SentCANMessage(
            cob_id=cob_id, data=data,
            description=f"RPDO1 to node={target_node_id} output={output_index} state={state}",
        ))
        return True

    def add_heartbeat_callback(self, callback: Callable[[int, str], None]) -> None:
        """Register heartbeat callback.

        Args:
            callback: Function(node_id, state_str).
        """
        self._heartbeat_callbacks.append(callback)

    def add_pdo_callback(self, callback: Callable[[int, bytes], None]) -> None:
        """Register PDO callback.

        Args:
            callback: Function(cob_id, data).
        """
        self._pdo_callbacks.append(callback)

    def simulate_heartbeat(self, node_id: int, state: str = "OPERATIONAL") -> None:
        """Simulate receiving a heartbeat from another node.

        Triggers all registered heartbeat callbacks.

        Args:
            node_id: Sender node ID.
            state: NMT state string.
        """
        for cb in self._heartbeat_callbacks:
            try:
                cb(node_id, state)
            except Exception as e:
                _LOGGER.error("Error in heartbeat callback: %s", e)

    def simulate_pdo(self, cob_id: int, data: bytes) -> None:
        """Simulate receiving a PDO message.

        Triggers all registered PDO callbacks.

        Args:
            cob_id: COB-ID of the message.
            data: PDO data.
        """
        for cb in self._pdo_callbacks:
            try:
                cb(cob_id, data)
            except Exception as e:
                _LOGGER.error("Error in PDO callback: %s", e)

    def get_sent_messages(self, cob_id_filter: int | None = None) -> list[SentCANMessage]:
        """Get sent messages, optionally filtered by COB-ID.

        Args:
            cob_id_filter: If set, only return messages with this COB-ID.

        Returns:
            List of sent messages.
        """
        if cob_id_filter is not None:
            return [m for m in self.sent_messages if m.cob_id == cob_id_filter]
        return self.sent_messages.copy()

    def clear_sent_messages(self) -> None:
        """Clear all sent message records."""
        self.sent_messages.clear()
