"""Remote device manager.

Manages all configured remote devices and provides access to them.
Supports autodiscovery of neighboring BoneIO Black devices via MQTT.
"""

from __future__ import annotations

import json
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

# Discovery topic pattern: boneio/blk_{serial}/discovery/{type}
DISCOVERY_TOPIC_PREFIX = "boneio"
DISCOVERY_SUBTOPIC = "discovery"


class RemoteDeviceManager:
    """Manager for remote devices.
    
    Handles initialization and access to all configured remote devices.
    Supports autodiscovery of neighboring BoneIO Black devices via MQTT.
    
    Args:
        message_bus: Message bus for MQTT communication
        remote_devices_config: List of remote device configurations
        own_serial: Serial number of this device (to exclude from autodiscovery)
    """
    
    def __init__(
        self,
        message_bus: MessageBus | None = None,
        remote_devices_config: list[dict[str, Any]] | None = None,
        own_serial: str | None = None,
        name: str | None = None,
    ) -> None:
        """Initialize remote device manager.
        
        Args:
            message_bus: Message bus for MQTT communication
            remote_devices_config: List of remote device configurations
            own_serial: Serial number of this device (to exclude from autodiscovery)
        """
        self._message_bus = message_bus
        self._devices: dict[str, RemoteDevice] = {}
        self._own_serial = own_serial
        self._name = name
        # Track autodiscovered devices separately from configured ones
        self._autodiscovered_devices: dict[str, MQTTRemoteDevice] = {}
        # Track devices that manage this boneIO (received via discovery/managed_by topic)
        self._managed_by_devices: dict[str, dict[str, Any]] = {}
        
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
                    # Publish managed_by to the remote device
                    self._publish_managed_by(device)
            except Exception as e:
                _LOGGER.error(
                    "Failed to configure remote device '%s': %s",
                    device_config.get("id", "unknown"), e
                )
    
    def _publish_managed_by(self, device: RemoteDevice) -> None:
        """Publish managed_by message to remote device.
        
        Tells the remote device that we are managing it.
        Topic: boneio/{remote_device_id}/discovery/managed_by/{our_serial}
        
        Args:
            device: Remote device to notify
        """
        if not self._own_serial:
            _LOGGER.debug("Cannot publish managed_by - own_serial not set")
            return
        
        if not self._message_bus:
            _LOGGER.debug("Cannot publish managed_by - message_bus not set")
            return
        
        if not isinstance(device, MQTTRemoteDevice):
            return
        
        # Build topic: boneio/{remote_device}/discovery/managed_by/{our_serial}
        topic = f"{device.topic_prefix}/discovery/managed_by/{self._own_serial}"
        
        # Build payload with our device info
        payload = json.dumps({
            "name": self._name or self._own_serial,
            "serial": self._own_serial,
        })
        
        self._message_bus.send_message(
            topic=topic,
            payload=payload,
            retain=True,
        )
        _LOGGER.info(
            "Published managed_by to %s (topic=%s)",
            device.id, topic
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
    
    # ==================== Autodiscovery ====================
    
    def get_discovery_topic(self) -> str:
        """Get MQTT topic pattern for autodiscovery subscription.
        
        Returns:
            Topic pattern like "boneio/+/discovery/#"
        """
        return f"{DISCOVERY_TOPIC_PREFIX}/+/{DISCOVERY_SUBTOPIC}/#"
    
    def is_discovery_topic(self, topic: str) -> bool:
        """Check if topic is a discovery topic.
        
        Args:
            topic: MQTT topic string
            
        Returns:
            True if topic matches discovery pattern
        """
        parts = topic.split("/")
        # Pattern: boneio/{device_id}/discovery/{type}
        return (
            len(parts) >= 4
            and parts[0] == DISCOVERY_TOPIC_PREFIX
            and parts[2] == DISCOVERY_SUBTOPIC
        )
    
    def handle_discovery_message(self, topic: str, payload: str) -> None:
        """Handle incoming discovery message from another BoneIO device.
        
        Parses the discovery payload and creates/updates the remote device.
        
        Args:
            topic: MQTT topic (e.g., "boneio/blk_abc123/discovery/outputs")
            payload: JSON payload with discovery data
        """
        if not self.is_discovery_topic(topic):
            return
        
        parts = topic.split("/")
        device_id = parts[1]  # e.g., "blk_abc123"
        discovery_type = parts[3] if len(parts) > 3 else None  # e.g., "outputs", "covers", "device"
        
        # Handle managed_by BEFORE skipping own device check
        # Topic: boneio/{our_device}/discovery/managed_by/{manager_serial}
        # This is for messages TO our device, so device_id will be our serial
        if discovery_type == "managed_by":
            manager_serial = parts[4] if len(parts) > 4 else None
            if manager_serial and self._own_serial != manager_serial:
                try:
                    data = json.loads(payload) if payload else None
                except json.JSONDecodeError as e:
                    _LOGGER.warning("Invalid JSON in managed_by payload: %s", e)
                    return
                if data:
                    self.handle_managed_by_discovery(manager_serial, data)
                else:
                    # Empty payload - remove managed_by entry
                    if manager_serial in self._managed_by_devices:
                        del self._managed_by_devices[manager_serial]
                        _LOGGER.info("Removed managed_by device: %s", manager_serial)
            return
        
        # Skip our own device (for other discovery types)
        if self._own_serial and device_id == self._own_serial:
            _LOGGER.debug("Ignoring discovery from own device: %s", device_id)
            return
        
        # Skip if this device is already configured manually
        if device_id in self._devices:
            _LOGGER.debug(
                "Device %s is manually configured, updating from discovery",
                device_id
            )
            self._update_configured_device_from_discovery(device_id, discovery_type, payload)
            return
        
        # Parse payload
        try:
            data = json.loads(payload) if payload else None
        except json.JSONDecodeError as e:
            _LOGGER.warning("Invalid JSON in discovery payload for %s: %s", topic, e)
            return
        
        if data is None:
            # Empty payload means device is offline/removed
            self._remove_autodiscovered_device(device_id)
            return
        
        # Process discovery by type
        if discovery_type == "device":
            self._handle_device_discovery(device_id, data)
        elif discovery_type == "outputs":
            self._handle_outputs_discovery(device_id, data)
        elif discovery_type == "covers":
            self._handle_covers_discovery(device_id, data)
        else:
            _LOGGER.debug("Ignoring discovery type '%s' for device %s", discovery_type, device_id)
    
    def _handle_device_discovery(self, device_id: str, data: dict[str, Any]) -> None:
        """Handle device info discovery.
        
        Creates a new autodiscovered device if not exists.
        
        Args:
            device_id: Device ID (e.g., "blk_abc123")
            data: Device info payload
        """
        if device_id not in self._autodiscovered_devices:
            name = data.get("name", device_id)
            device = MQTTRemoteDevice(
                id=device_id,
                name=name,
                device_type=RemoteDeviceType.BONEIO_BLACK,
            )
            self._autodiscovered_devices[device_id] = device
            _LOGGER.info(
                "Autodiscovered BoneIO device: %s (%s), firmware=%s",
                name, device_id, data.get("firmware", "unknown")
            )
        else:
            # Update name if changed
            device = self._autodiscovered_devices[device_id]
            new_name = data.get("name")
            if new_name and new_name != device.name:
                device._name = new_name
                _LOGGER.debug("Updated autodiscovered device name: %s -> %s", device_id, new_name)
    
    def _handle_outputs_discovery(self, device_id: str, data: list[dict[str, Any]]) -> None:
        """Handle outputs discovery.
        
        Updates outputs list for autodiscovered device.
        
        Args:
            device_id: Device ID
            data: List of output definitions
        """
        device = self._autodiscovered_devices.get(device_id)
        if not device:
            # Device info not received yet, create placeholder
            device = MQTTRemoteDevice(
                id=device_id,
                name=device_id,
                device_type=RemoteDeviceType.BONEIO_BLACK,
            )
            self._autodiscovered_devices[device_id] = device
            _LOGGER.debug("Created placeholder for autodiscovered device: %s", device_id)
        
        # Update outputs
        device.set_outputs(data)
        _LOGGER.debug(
            "Updated outputs for autodiscovered device %s: %d outputs",
            device_id, len(data)
        )
    
    def _handle_covers_discovery(self, device_id: str, data: list[dict[str, Any]]) -> None:
        """Handle covers discovery.
        
        Updates covers list for autodiscovered device.
        
        Args:
            device_id: Device ID
            data: List of cover definitions
        """
        device = self._autodiscovered_devices.get(device_id)
        if not device:
            # Device info not received yet, create placeholder
            device = MQTTRemoteDevice(
                id=device_id,
                name=device_id,
                device_type=RemoteDeviceType.BONEIO_BLACK,
            )
            self._autodiscovered_devices[device_id] = device
            _LOGGER.debug("Created placeholder for autodiscovered device: %s", device_id)
        
        # Update covers
        device.set_covers(data)
        _LOGGER.debug(
            "Updated covers for autodiscovered device %s: %d covers",
            device_id, len(data)
        )
    
    def _update_configured_device_from_discovery(
        self, device_id: str, discovery_type: str | None, payload: str
    ) -> None:
        """Update manually configured device with discovery data.
        
        This allows manually configured devices to receive autodiscovered
        outputs/covers without overwriting the manual configuration.
        
        Args:
            device_id: Device ID
            discovery_type: Type of discovery (outputs, covers, etc.)
            payload: JSON payload
        """
        device = self._devices.get(device_id)
        if not device or not isinstance(device, MQTTRemoteDevice):
            return
        
        try:
            data = json.loads(payload) if payload else None
        except json.JSONDecodeError:
            return
        
        if data is None:
            return
        
        if discovery_type == "outputs":
            # Only update if device has no manually configured outputs
            if not device.outputs:
                device.set_outputs(data)
                _LOGGER.info(
                    "Updated configured device %s with autodiscovered outputs: %d",
                    device_id, len(data)
                )
        elif discovery_type == "covers":
            # Only update if device has no manually configured covers
            if not device.covers:
                device.set_covers(data)
                _LOGGER.info(
                    "Updated configured device %s with autodiscovered covers: %d",
                    device_id, len(data)
                )
    
    def _remove_autodiscovered_device(self, device_id: str) -> None:
        """Remove autodiscovered device.
        
        Args:
            device_id: Device ID to remove
        """
        if device_id in self._autodiscovered_devices:
            del self._autodiscovered_devices[device_id]
            _LOGGER.info("Removed autodiscovered device: %s", device_id)
    
    def get_autodiscovered_device(self, device_id: str) -> MQTTRemoteDevice | None:
        """Get autodiscovered device by ID.
        
        Args:
            device_id: Device ID
            
        Returns:
            MQTTRemoteDevice or None
        """
        return self._autodiscovered_devices.get(device_id)
    
    def get_all_autodiscovered_devices(self) -> dict[str, MQTTRemoteDevice]:
        """Get all autodiscovered devices.
        
        Returns:
            Dictionary of device_id -> MQTTRemoteDevice
        """
        return self._autodiscovered_devices.copy()
    
    def get_all_available_devices(self) -> dict[str, RemoteDevice]:
        """Get all available devices (configured + autodiscovered).
        
        Configured devices take precedence over autodiscovered ones.
        
        Returns:
            Dictionary of device_id -> RemoteDevice
        """
        # Start with autodiscovered, then overlay configured
        all_devices: dict[str, RemoteDevice] = {}
        for device_id, device in self._autodiscovered_devices.items():
            all_devices[device_id] = device
        for device_id, device in self._devices.items():
            all_devices[device_id] = device
        return all_devices
    
    def autodiscovered_to_dict(self) -> dict[str, Any]:
        """Convert autodiscovered devices to dictionary representation.
        
        Returns:
            Dictionary with autodiscovered devices information
        """
        return {
            device_id: device.to_dict()
            for device_id, device in self._autodiscovered_devices.items()
        }
    
    def get_managed_by_devices(self) -> dict[str, dict[str, Any]]:
        """Get devices that manage this boneIO.
        
        Returns:
            Dictionary of serial -> device info
        """
        return self._managed_by_devices.copy()
    
    def handle_managed_by_discovery(self, manager_serial: str, data: dict[str, Any] | None) -> None:
        """Handle managed_by discovery message.
        
        Called when another boneIO publishes to our discovery/managed_by topic.
        
        Args:
            manager_serial: Serial of the managing device
            data: Device info (id, name, serial) or None to remove
        """
        if data is None:
            # Empty payload means device no longer manages us
            if manager_serial in self._managed_by_devices:
                del self._managed_by_devices[manager_serial]
                _LOGGER.info("Removed managed_by device: %s", manager_serial)
            return
        
        self._managed_by_devices[manager_serial] = {
            "id": data.get("id", manager_serial),
            "name": data.get("name", manager_serial),
            "serial": manager_serial,
        }
        _LOGGER.info(
            "Added managed_by device: %s (%s)",
            data.get("name", manager_serial), manager_serial
        )
