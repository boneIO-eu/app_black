"""CAN-based remote device implementation.

Supports controlling outputs and covers on remote boneIO devices via CANopen PDOs.
Each CANRemoteDevice wraps a BoneIOCANNode discovered on the CAN bus.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from boneio.core.remote.base import (
    RemoteDevice,
    RemoteDeviceProtocol,
    RemoteDeviceType,
)

if TYPE_CHECKING:
    from boneio.core.manager.canopen import CANopenManager
    from boneio.core.messaging import MessageBus
    from boneio.hardware.can.node import BoneIOCANNode

_LOGGER = logging.getLogger(__name__)


class CANRemoteDevice(RemoteDevice):
    """CAN-based remote device.

    Controls outputs and covers on remote boneIO devices via CANopen PDO messages.
    Wraps a BoneIOCANNode discovered through heartbeat on the CAN bus.

    Args:
        node: The discovered BoneIOCANNode instance.
        canopen_manager: Reference to the CANopenManager for sending commands.
    """

    def __init__(
        self,
        node: BoneIOCANNode,
        canopen_manager: CANopenManager,
    ) -> None:
        """Initialize CAN remote device.

        Args:
            node: The discovered BoneIOCANNode instance.
            canopen_manager: Reference to CANopenManager for sending PDOs.
        """
        super().__init__(
            id=f"can_{node.node_id}",
            name=node.name,
            protocol=RemoteDeviceProtocol.CAN,
            device_type=RemoteDeviceType.BONEIO_BLACK,
            config={"node_id": node.node_id},
        )
        self._node = node
        self._canopen_manager = canopen_manager

        _LOGGER.info(
            "Configured CAN remote device '%s' (node_id=%d)",
            node.name, node.node_id,
        )

    @property
    def node(self) -> BoneIOCANNode:
        """Get the underlying CAN node."""
        return self._node

    @property
    def node_id(self) -> int:
        """Get the CANopen node ID."""
        return self._node.node_id

    @property
    def is_online(self) -> bool:
        """Check if the remote device is online."""
        return self._node.is_online and self._node.is_operational

    async def control_output(
        self,
        output_id: str,
        action: str,
        message_bus: MessageBus | None = None,
    ) -> bool:
        """Control an output on the remote device via CAN PDO.

        Args:
            output_id: ID/index of the output to control.
            action: Action to perform (ON, OFF, TOGGLE).
            message_bus: Not used for CAN (ignored).

        Returns:
            True if command was sent successfully.
        """
        if not self.is_online:
            _LOGGER.warning(
                "Cannot control output on offline CAN device '%s' (node_id=%d)",
                self._name, self._node.node_id,
            )
            return False

        try:
            output_index = int(output_id)
        except ValueError:
            _LOGGER.error("Invalid output_id '%s' for CAN device (must be integer index)", output_id)
            return False

        state = 1 if action.upper() in ("ON", "TOGGLE") else 0

        _LOGGER.debug(
            "Sending CAN output command: device='%s', node_id=%d, output=%d, state=%d",
            self._name, self._node.node_id, output_index, state,
        )

        return await self._canopen_manager.send_command_to_node(
            target_node_id=self._node.node_id,
            output_index=output_index,
            state=state,
        )

    async def control_cover(
        self,
        cover_id: str,
        action: str,
        message_bus: MessageBus | None = None,
        **kwargs,
    ) -> bool:
        """Control a cover on the remote device via CAN PDO.

        Args:
            cover_id: ID of the cover to control.
            action: Action to perform (OPEN, CLOSE, STOP).
            message_bus: Not used for CAN (ignored).
            **kwargs: Additional parameters (position, tilt_position).

        Returns:
            True if command was sent successfully.
        """
        if not self.is_online:
            _LOGGER.warning(
                "Cannot control cover on offline CAN device '%s' (node_id=%d)",
                self._name, self._node.node_id,
            )
            return False

        # TODO: Implement cover control via CAN PDO (Faza 4)
        _LOGGER.warning(
            "Cover control via CAN not yet implemented (device='%s', cover='%s', action='%s')",
            self._name, cover_id, action,
        )
        return False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation.

        Returns:
            Dictionary with device information.
        """
        data = super().to_dict()
        data["node_id"] = self._node.node_id
        data["is_online"] = self.is_online
        data["nmt_state"] = self._node.nmt_state.name
        data["serial"] = self._node.serial
        return data
