"""CAN ↔ MQTT bridge for boneIO.

Relays data between CAN bus and MQTT broker, enabling slave devices
(no LAN) to communicate with Home Assistant through a master device.

Master mode:
  - Receives output state PDOs from CAN slaves → publishes to MQTT
  - Receives MQTT commands for slaves → sends CAN PDOs to slaves

Slave mode:
  - Sends local output state changes as CAN PDOs → master relays to MQTT
  - Receives CAN PDOs with commands from master → executes locally

The bridge is protocol-agnostic at the PDO level, so it works with both
boneIO native PDOs and esphome-canopen OD-based messages in the future.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from boneio.core.manager import Manager
    from boneio.core.manager.canopen import CANopenManager
    from boneio.core.messaging import MessageBus

_LOGGER = logging.getLogger(__name__)


class CANMQTTBridge:
    """Bridge between CAN bus and MQTT for master/slave communication.

    On the master side, this bridge:
    - Listens for output state PDOs from CAN slaves and publishes
      their state to MQTT (so HA sees them).
    - Subscribes to MQTT command topics for slave devices and forwards
      commands as CAN PDOs.

    Args:
        manager: Main boneIO manager.
        canopen_manager: CANopen manager instance.
        message_bus: MQTT message bus.
    """

    def __init__(
        self,
        manager: Manager,
        canopen_manager: CANopenManager,
        message_bus: MessageBus,
    ) -> None:
        """Initialize CAN-MQTT bridge.

        Args:
            manager: Main boneIO manager.
            canopen_manager: CANopen manager instance.
            message_bus: MQTT message bus.
        """
        self._manager = manager
        self._canopen = canopen_manager
        self._message_bus = message_bus
        self._running = False

        # Topic prefix for bridged slave devices
        self._topic_prefix = manager.config_helper.topic_prefix

    def start(self) -> None:
        """Start the bridge by registering callbacks."""
        if self._running:
            return

        self._running = True

        # Register CAN → MQTT: output state from slaves
        self._canopen.add_output_state_callback(self._on_can_output_state)

        _LOGGER.info("CAN-MQTT bridge started")

    def stop(self) -> None:
        """Stop the bridge."""
        self._running = False
        _LOGGER.info("CAN-MQTT bridge stopped")

    def _on_can_output_state(
        self, node_id: int, output_index: int, state: int
    ) -> None:
        """Handle output state received from CAN slave → publish to MQTT.

        Publishes the slave's output state so Home Assistant can see it.
        Topic format: boneio/can_{node_id}/state/output/{output_index}

        Args:
            node_id: CAN node ID of the slave.
            output_index: Output index on the slave.
            state: Output state (0=OFF, 1=ON).
        """
        if not self._running:
            return

        # Look up node info for better topic naming
        node = self._canopen.get_node(node_id)
        device_id = f"can_{node_id}"
        if node and node.serial:
            device_id = node.serial

        topic = f"boneio/{device_id}/state/output/{output_index}"
        payload = "ON" if state else "OFF"

        _LOGGER.debug(
            "CAN→MQTT: node=%d output=%d state=%s topic=%s",
            node_id, output_index, payload, topic,
        )

        try:
            self._message_bus.send_message(
                topic=topic, payload=payload, retain=True,
            )
        except Exception as e:
            _LOGGER.error("Failed to relay CAN state to MQTT: %s", e)

    async def send_command_to_slave(
        self,
        node_id: int,
        output_index: int,
        state: int,
        brightness: int = 0,
    ) -> bool:
        """Send a command from MQTT to a CAN slave via PDO.

        Called when master receives an MQTT command targeting a slave device.

        Args:
            node_id: Target CAN node ID.
            output_index: Output index on the slave.
            state: Desired state (0=OFF, 1=ON).
            brightness: Brightness for dimmers (0-255).

        Returns:
            True if command was sent successfully.
        """
        _LOGGER.debug(
            "MQTT→CAN: node=%d output=%d state=%d",
            node_id, output_index, state,
        )
        return await self._canopen.send_output_state(
            output_index, state, brightness
        )

    def to_dict(self) -> dict[str, Any]:
        """Get bridge status as dictionary.

        Returns:
            Dictionary with bridge status.
        """
        return {
            "running": self._running,
            "mode": self._canopen._mode,
            "bridged_nodes": len(self._canopen.nodes),
        }
