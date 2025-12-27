"""MQTT-based remote device implementation.

Supports controlling outputs and covers on remote devices via MQTT.
Works with boneIO Black, ESPHome, and other MQTT-enabled devices.
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
    from boneio.core.messaging import MessageBus

_LOGGER = logging.getLogger(__name__)


class MQTTRemoteDevice(RemoteDevice):
    """MQTT-based remote device.
    
    Controls outputs and covers on remote devices via MQTT messages.
    Topic prefix is automatically derived from device_id (e.g., "boneio/blk_abc123").
    
    Args:
        id: Device identifier (e.g., "blk_abc123" for boneIO Black)
        name: Human-readable name
        device_type: Type of remote device (affects command format)
        outputs: Optional list of known outputs
        covers: Optional list of known covers
    """
    
    def __init__(
        self,
        id: str,
        name: str,
        device_type: RemoteDeviceType = RemoteDeviceType.BONEIO_BLACK,
        outputs: list[dict[str, Any]] | None = None,
        covers: list[dict[str, Any]] | None = None,
    ) -> None:
        """Initialize MQTT remote device.
        
        Args:
            id: Device identifier (e.g., "blk_abc123")
            name: Human-readable name
            device_type: Type of remote device
            outputs: Optional list of known outputs
            covers: Optional list of known covers
        """
        super().__init__(
            id=id,
            name=name,
            protocol=RemoteDeviceProtocol.MQTT,
            device_type=device_type,
            config={},
        )
        
        # Build topic prefix from device_id
        # For boneIO Black: id="blk_abc123" -> topic="boneio/blk_abc123"
        if device_type == RemoteDeviceType.BONEIO_BLACK:
            self._topic_prefix = f"boneio/{id}"
        else:
            # For other devices, use id as-is
            self._topic_prefix = id
        
        if outputs:
            self.set_outputs(outputs)
        if covers:
            self.set_covers(covers)
        
        _LOGGER.info(
            "Configured MQTT remote device '%s' (id=%s, topic=%s)",
            name, id, self._topic_prefix
        )
    
    @property
    def topic_prefix(self) -> str:
        """Get MQTT topic prefix."""
        return self._topic_prefix
    
    def _get_output_command_topic(self, output_id: str) -> str:
        """Get MQTT command topic for output.
        
        Args:
            output_id: ID of the output
            
        Returns:
            MQTT topic for sending commands
        """
        if self._device_type == RemoteDeviceType.BONEIO_BLACK:
            return f"{self._topic_prefix}/cmd/output/{output_id}/set"
        elif self._device_type == RemoteDeviceType.ESPHOME:
            return f"{self._topic_prefix}/switch/{output_id}/command"
        else:
            # Generic format
            return f"{self._topic_prefix}/cmd/output/{output_id}/set"
    
    def _get_cover_command_topic(self, cover_id: str) -> str:
        """Get MQTT command topic for cover.
        
        Args:
            cover_id: ID of the cover
            
        Returns:
            MQTT topic for sending commands
        """
        if self._device_type == RemoteDeviceType.BONEIO_BLACK:
            return f"{self._topic_prefix}/cmd/cover/{cover_id}/set"
        elif self._device_type == RemoteDeviceType.ESPHOME:
            return f"{self._topic_prefix}/cover/{cover_id}/command"
        else:
            # Generic format
            return f"{self._topic_prefix}/cmd/cover/{cover_id}/set"
    
    def _get_cover_position_topic(self, cover_id: str) -> str:
        """Get MQTT topic for setting cover position.
        
        Args:
            cover_id: ID of the cover
            
        Returns:
            MQTT topic for setting position
        """
        if self._device_type == RemoteDeviceType.BONEIO_BLACK:
            return f"{self._topic_prefix}/cmd/cover/{cover_id}/pos"
        elif self._device_type == RemoteDeviceType.ESPHOME:
            return f"{self._topic_prefix}/cover/{cover_id}/position"
        else:
            return f"{self._topic_prefix}/cmd/cover/{cover_id}/pos"
    
    async def control_output(
        self,
        output_id: str,
        action: str,
        message_bus: MessageBus | None = None,
    ) -> bool:
        """Control an output on the remote device via MQTT.
        
        Args:
            output_id: ID of the output to control
            action: Action to perform (ON, OFF, TOGGLE)
            message_bus: Message bus for sending MQTT messages
            
        Returns:
            True if command was sent successfully
        """
        if message_bus is None:
            _LOGGER.error("Cannot control remote output without message_bus")
            return False
        
        topic = self._get_output_command_topic(output_id)
        payload = action.upper()
        
        _LOGGER.debug(
            "Sending remote output command: device='%s', output='%s', action='%s', topic='%s'",
            self._name, output_id, action, topic
        )
        
        try:
            message_bus.send_message(topic=topic, payload=payload, retain=False)
            return True
        except Exception as e:
            _LOGGER.error(
                "Failed to send remote output command to '%s': %s",
                self._name, e
            )
            return False
    
    async def control_cover(
        self,
        cover_id: str,
        action: str,
        message_bus: MessageBus | None = None,
        **kwargs,
    ) -> bool:
        """Control a cover on the remote device via MQTT.
        
        Args:
            cover_id: ID of the cover to control
            action: Action to perform (OPEN, CLOSE, STOP, TOGGLE, etc.)
            message_bus: Message bus for sending MQTT messages
            **kwargs: Additional parameters (position, tilt_position)
            
        Returns:
            True if command was sent successfully
        """
        if message_bus is None:
            _LOGGER.error("Cannot control remote cover without message_bus")
            return False
        
        # Handle position setting
        position = kwargs.get("position")
        if position is not None:
            topic = self._get_cover_position_topic(cover_id)
            payload = str(position)
        else:
            topic = self._get_cover_command_topic(cover_id)
            payload = action.upper()
        
        _LOGGER.debug(
            "Sending remote cover command: device='%s', cover='%s', action='%s', topic='%s'",
            self._name, cover_id, action, topic
        )
        
        try:
            message_bus.send_message(topic=topic, payload=payload, retain=False)
            return True
        except Exception as e:
            _LOGGER.error(
                "Failed to send remote cover command to '%s': %s",
                self._name, e
            )
            return False
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation.
        
        Returns:
            Dictionary with device information
        """
        data = super().to_dict()
        data["topic_prefix"] = self._topic_prefix
        return data
