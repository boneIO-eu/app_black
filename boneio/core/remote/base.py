"""Base classes for remote device support.

This module defines the abstract base class for all remote device implementations.
Each protocol (MQTT, CAN, Loxone, ESPHome) will have its own implementation.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from boneio.core.messaging import MessageBus

_LOGGER = logging.getLogger(__name__)


class RemoteDeviceProtocol(str, Enum):
    """Supported remote device protocols."""
    
    MQTT = "mqtt"
    CAN = "can"
    LOXONE = "loxone"
    ESPHOME_UDP = "esphome_udp"
    ESPHOME_API = "esphome_api"


class RemoteDeviceType(str, Enum):
    """Supported remote device types."""
    
    BONEIO_BLACK = "boneio_black"
    ESPHOME = "esphome"
    LOXONE_MINISERVER = "loxone_miniserver"
    GENERIC = "generic"


class RemoteDevice(ABC):
    """Abstract base class for remote devices.
    
    Remote devices represent external devices that can be controlled
    from this boneIO instance. Each protocol has its own implementation.
    
    Args:
        id: Unique identifier for this remote device
        name: Human-readable name
        protocol: Communication protocol
        device_type: Type of remote device
        config: Protocol-specific configuration
    """
    
    def __init__(
        self,
        id: str,
        name: str,
        protocol: RemoteDeviceProtocol,
        device_type: RemoteDeviceType = RemoteDeviceType.GENERIC,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize remote device.
        
        Args:
            id: Unique identifier for this remote device
            name: Human-readable name
            protocol: Communication protocol
            device_type: Type of remote device
            config: Protocol-specific configuration
        """
        self._id = id
        self._name = name
        self._protocol = protocol
        self._device_type = device_type
        self._config = config or {}
        
        # Optional lists of known outputs/covers for UI dropdown
        self._outputs: list[dict[str, str]] = []
        self._covers: list[dict[str, str]] = []
        
        _LOGGER.debug(
            "Initialized remote device '%s' (protocol=%s, type=%s)",
            name, protocol.value, device_type.value
        )
    
    @property
    def id(self) -> str:
        """Get device ID."""
        return self._id
    
    @property
    def name(self) -> str:
        """Get device name."""
        return self._name
    
    @property
    def protocol(self) -> RemoteDeviceProtocol:
        """Get device protocol."""
        return self._protocol
    
    @property
    def device_type(self) -> RemoteDeviceType:
        """Get device type."""
        return self._device_type
    
    @property
    def outputs(self) -> list[dict[str, str]]:
        """Get list of known outputs (for UI dropdown)."""
        return self._outputs
    
    @property
    def covers(self) -> list[dict[str, str]]:
        """Get list of known covers (for UI dropdown)."""
        return self._covers
    
    def set_outputs(self, outputs: list[dict[str, Any]]) -> None:
        """Set list of known outputs.
        
        Args:
            outputs: List of output definitions with 'id' and optional 'name'
        """
        self._outputs = [
            {"id": o.get("id", ""), "name": o.get("name", o.get("id", ""))}
            for o in outputs if o.get("id")
        ]
    
    def set_covers(self, covers: list[dict[str, Any]]) -> None:
        """Set list of known covers.
        
        Args:
            covers: List of cover definitions with 'id' and optional 'name'
        """
        self._covers = [
            {"id": c.get("id", ""), "name": c.get("name", c.get("id", ""))}
            for c in covers if c.get("id")
        ]
    
    @abstractmethod
    async def control_output(
        self,
        output_id: str,
        action: str,
        message_bus: MessageBus | None = None,
    ) -> bool:
        """Control an output on the remote device.
        
        Args:
            output_id: ID of the output to control
            action: Action to perform (ON, OFF, TOGGLE)
            message_bus: Optional message bus for MQTT-based protocols
            
        Returns:
            True if command was sent successfully
        """
        pass
    
    @abstractmethod
    async def control_cover(
        self,
        cover_id: str,
        action: str,
        message_bus: MessageBus | None = None,
        **kwargs,
    ) -> bool:
        """Control a cover on the remote device.
        
        Args:
            cover_id: ID of the cover to control
            action: Action to perform (OPEN, CLOSE, STOP, TOGGLE, etc.)
            message_bus: Optional message bus for MQTT-based protocols
            **kwargs: Additional parameters (position, tilt_position)
            
        Returns:
            True if command was sent successfully
        """
        pass
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation.
        
        Returns:
            Dictionary with device information
        """
        return {
            "id": self._id,
            "name": self._name,
            "protocol": self._protocol.value,
            "device_type": self._device_type.value,
            "outputs": self._outputs,
            "covers": self._covers,
        }
