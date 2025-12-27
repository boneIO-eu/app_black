"""Remote device manager.

Manages all configured remote devices and provides access to them.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from boneio.core.remote.base import (
    RemoteDevice,
    RemoteDeviceProtocol,
    RemoteDeviceType,
)
from boneio.core.remote.mqtt import MQTTRemoteDevice

if TYPE_CHECKING:
    from boneio.core.messaging import MessageBus

_LOGGER = logging.getLogger(__name__)


class RemoteDeviceManager:
    """Manager for remote devices.
    
    Handles initialization and access to all configured remote devices.
    
    Args:
        message_bus: Message bus for MQTT communication
        remote_devices_config: List of remote device configurations
    """
    
    def __init__(
        self,
        message_bus: MessageBus | None = None,
        remote_devices_config: list[dict[str, Any]] | None = None,
    ) -> None:
        """Initialize remote device manager.
        
        Args:
            message_bus: Message bus for MQTT communication
            remote_devices_config: List of remote device configurations
        """
        self._message_bus = message_bus
        self._devices: dict[str, RemoteDevice] = {}
        
        if remote_devices_config:
            self._configure_devices(remote_devices_config)
    
    def _configure_devices(self, config: list[dict[str, Any]]) -> None:
        """Configure remote devices from config.
        
        Args:
            config: List of remote device configurations
        """
        for device_config in config:
            try:
                device = self._create_device(device_config)
                if device:
                    self._devices[device.id] = device
                    _LOGGER.info(
                        "Configured remote device '%s' (protocol=%s)",
                        device.name, device.protocol.value
                    )
            except Exception as e:
                _LOGGER.error(
                    "Failed to configure remote device '%s': %s",
                    device_config.get("id", "unknown"), e
                )
    
    def _create_device(self, config: dict[str, Any]) -> RemoteDevice | None:
        """Create remote device from config.
        
        Args:
            config: Device configuration
            
        Returns:
            RemoteDevice instance or None if creation failed
        """
        device_id = config.get("id")
        name = config.get("name") or device_id or "unknown"
        protocol_str = config.get("protocol", "mqtt")
        device_type_str = config.get("device_type", "generic")
        
        if not device_id:
            _LOGGER.error("Remote device config missing 'id'")
            return None
        
        try:
            protocol = RemoteDeviceProtocol(protocol_str)
        except ValueError:
            _LOGGER.error("Unknown protocol '%s' for device '%s'", protocol_str, device_id)
            return None
        
        try:
            device_type = RemoteDeviceType(device_type_str)
        except ValueError:
            _LOGGER.warning(
                "Unknown device_type '%s' for device '%s', using 'generic'",
                device_type_str, device_id
            )
            device_type = RemoteDeviceType.GENERIC
        
        # Create protocol-specific device
        if protocol == RemoteDeviceProtocol.MQTT:
            return self._create_mqtt_device(device_id, name, device_type, config)
        elif protocol == RemoteDeviceProtocol.CAN:
            _LOGGER.warning("CAN protocol not yet implemented for device '%s'", device_id)
            return None
        elif protocol == RemoteDeviceProtocol.LOXONE:
            _LOGGER.warning("Loxone protocol not yet implemented for device '%s'", device_id)
            return None
        elif protocol == RemoteDeviceProtocol.ESPHOME_UDP:
            _LOGGER.warning("ESPHome UDP protocol not yet implemented for device '%s'", device_id)
            return None
        elif protocol == RemoteDeviceProtocol.ESPHOME_API:
            _LOGGER.warning("ESPHome API protocol not yet implemented for device '%s'", device_id)
            return None
        else:
            _LOGGER.error("Unsupported protocol '%s' for device '%s'", protocol, device_id)
            return None
    
    def _create_mqtt_device(
        self,
        device_id: str,
        name: str,
        device_type: RemoteDeviceType,
        config: dict[str, Any],
    ) -> MQTTRemoteDevice | None:
        """Create MQTT remote device.
        
        Args:
            device_id: Device ID (e.g., "blk_abc123")
            name: Device name
            device_type: Device type
            config: Full device configuration
            
        Returns:
            MQTTRemoteDevice instance or None if creation failed
        """
        mqtt_config = config.get("mqtt", {})
        outputs = mqtt_config.get("outputs", [])
        covers = mqtt_config.get("covers", [])
        
        return MQTTRemoteDevice(
            id=device_id,
            name=name,
            device_type=device_type,
            outputs=outputs,
            covers=covers,
        )
    
    def get_device(self, device_id: str) -> RemoteDevice | None:
        """Get remote device by ID.
        
        Args:
            device_id: Device ID
            
        Returns:
            RemoteDevice instance or None if not found
        """
        return self._devices.get(device_id)
    
    def get_all_devices(self) -> dict[str, RemoteDevice]:
        """Get all configured remote devices.
        
        Returns:
            Dictionary of device_id -> RemoteDevice
        """
        return self._devices.copy()
    
    async def control_output(
        self,
        device_id: str,
        output_id: str,
        action: str,
    ) -> bool:
        """Control output on remote device.
        
        Args:
            device_id: ID of the remote device
            output_id: ID of the output to control
            action: Action to perform (ON, OFF, TOGGLE)
            
        Returns:
            True if command was sent successfully
        """
        device = self.get_device(device_id)
        if not device:
            _LOGGER.error("Remote device '%s' not found", device_id)
            return False
        
        return await device.control_output(
            output_id=output_id,
            action=action,
            message_bus=self._message_bus,
        )
    
    async def control_cover(
        self,
        device_id: str,
        cover_id: str,
        action: str,
        **kwargs,
    ) -> bool:
        """Control cover on remote device.
        
        Args:
            device_id: ID of the remote device
            cover_id: ID of the cover to control
            action: Action to perform (OPEN, CLOSE, STOP, etc.)
            **kwargs: Additional parameters (position, tilt_position)
            
        Returns:
            True if command was sent successfully
        """
        device = self.get_device(device_id)
        if not device:
            _LOGGER.error("Remote device '%s' not found", device_id)
            return False
        
        return await device.control_cover(
            cover_id=cover_id,
            action=action,
            message_bus=self._message_bus,
            **kwargs,
        )
    
    def reload(self, remote_devices_config: list[dict[str, Any]] | None = None) -> None:
        """Reload remote devices from config.
        
        Args:
            remote_devices_config: New list of remote device configurations
        """
        _LOGGER.info("Reloading remote devices configuration")
        self._devices.clear()
        
        if remote_devices_config:
            self._configure_devices(remote_devices_config)
        
        _LOGGER.info("Reloaded %d remote devices", len(self._devices))
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation.
        
        Returns:
            Dictionary with all devices information
        """
        return {
            device_id: device.to_dict()
            for device_id, device in self._devices.items()
        }
