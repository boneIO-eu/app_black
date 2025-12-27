"""BoneIO Discovery Publisher.

Publishes device discovery information to MQTT for autodiscovery by other devices.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from boneio.core.manager import Manager
    from boneio.core.messaging import MessageBus

_LOGGER = logging.getLogger(__name__)


class BlackDiscoveryPublisher:
    """Publishes BoneIO Black device discovery information to MQTT.
    
    This is NOT Home Assistant discovery - it's for autodiscovery
    of neighboring BoneIO Black devices.
    
    Discovery is split into separate topics for efficiency:
    - discovery/device  - Device info (id, name, serial, firmware)
    - discovery/outputs - Available outputs
    - discovery/covers  - Available covers
    - discovery/inputs  - Available inputs
    - discovery/sensors - Available sensors
    - discovery/modbus  - Available modbus devices
    
    All topics are published with retain=True.
    """
    
    def __init__(self, manager: Manager, message_bus: MessageBus) -> None:
        """Initialize discovery publisher.
        
        Args:
            manager: Manager instance
            message_bus: Message bus for MQTT communication
        """
        self._manager = manager
        self._message_bus = message_bus
        self._base_topic = f"{manager._config_helper.topic_prefix}/discovery"
    
    def _publish(self, subtopic: str, payload: Any) -> None:
        """Publish payload to discovery subtopic with retain.
        
        Args:
            subtopic: Subtopic name (e.g., "device", "outputs")
            payload: Payload to publish (will be JSON encoded)
        """
        topic = f"{self._base_topic}/{subtopic}"
        payload_json = json.dumps(payload)
        self._message_bus.send_message(topic=topic, payload=payload_json, retain=True)
        _LOGGER.debug("Published discovery/%s: %s", subtopic, payload_json)
    
    def _build_device_info(self) -> dict[str, Any]:
        """Build device information payload."""
        from boneio.version import __version__
        
        config_helper = self._manager._config_helper
        device_info = {
            "id": config_helper._serial_no or "unknown",
            "name": config_helper.name,
            "serial_number": config_helper._serial_no or "unknown",
            "type": "black",
            "firmware": __version__,
            "topic_prefix": config_helper.topic_prefix,
        }
        if config_helper._network_info:
            device_info["ip"] = config_helper._network_info.get("ip", "")
        return device_info
    
    def _build_outputs(self) -> list[dict[str, Any]]:
        """Build outputs list (excludes cover outputs - those are in discovery/covers)."""
        outputs = []
        if hasattr(self._manager, 'outputs') and self._manager.outputs:
            for output_id, output in self._manager.outputs._outputs.items():
                # Skip cover outputs - they are published in discovery/covers
                output_type = getattr(output, 'output_type', None)
                if output_type == 'cover':
                    continue
                output_info = {
                    "id": output_id,
                    "name": getattr(output, 'name', output_id),
                }
                if output_type:
                    output_info["type"] = output_type
                outputs.append(output_info)
        return outputs
    
    def _build_covers(self) -> list[dict[str, Any]]:
        """Build covers list."""
        covers = []
        if hasattr(self._manager, 'covers') and self._manager.covers:
            for cover_id, cover in self._manager.covers._covers.items():
                covers.append({
                    "id": cover_id,
                    "name": getattr(cover, 'name', cover_id),
                })
        return covers
    
    def _build_inputs(self) -> list[dict[str, Any]]:
        """Build inputs list."""
        inputs = []
        if hasattr(self._manager, 'inputs') and self._manager.inputs:
            for input_id, input_device in self._manager.inputs._inputs.items():
                inputs.append({
                    "id": input_id,
                    "name": getattr(input_device, 'name', input_id),
                })
        return inputs
    
    def _build_sensors(self) -> list[dict[str, Any]]:
        """Build sensors list."""
        sensors = []
        if hasattr(self._manager, 'sensors') and self._manager.sensors:
            if hasattr(self._manager.sensors, '_dallas_sensors'):
                for sensor in self._manager.sensors._dallas_sensors:
                    sensors.append({
                        "id": sensor.id,
                        "name": sensor.name,
                        "type": "temperature",
                    })
            if hasattr(self._manager.sensors, '_adc_sensors'):
                for sensor in self._manager.sensors._adc_sensors:
                    sensors.append({
                        "id": sensor.id,
                        "name": sensor.name,
                        "type": "adc",
                    })
        return sensors
    
    def _build_modbus(self) -> list[dict[str, Any]]:
        """Build modbus devices list."""
        modbus_devices = []
        if hasattr(self._manager, 'modbus') and self._manager.modbus:
            if hasattr(self._manager.modbus, '_modbus_coordinators'):
                for device_id, device in self._manager.modbus._modbus_coordinators.items():
                    device_info = {
                        "id": device_id,
                        "name": getattr(device, 'name', device_id),
                    }
                    if hasattr(device, 'model'):
                        device_info["model"] = device.model
                    modbus_devices.append(device_info)
        return modbus_devices
    
    # Public methods for publishing individual sections
    
    def publish_device(self) -> None:
        """Publish device info to discovery/device."""
        self._publish("device", self._build_device_info())
    
    def publish_outputs(self) -> None:
        """Publish outputs list to discovery/outputs."""
        self._publish("outputs", self._build_outputs())
    
    def publish_covers(self) -> None:
        """Publish covers list to discovery/covers."""
        self._publish("covers", self._build_covers())
    
    def publish_inputs(self) -> None:
        """Publish inputs list to discovery/inputs."""
        self._publish("inputs", self._build_inputs())
    
    def publish_sensors(self) -> None:
        """Publish sensors list to discovery/sensors."""
        self._publish("sensors", self._build_sensors())
    
    def publish_modbus(self) -> None:
        """Publish modbus devices list to discovery/modbus."""
        self._publish("modbus", self._build_modbus())
    
    async def publish_discovery(self) -> None:
        """Publish all discovery sections.
        
        Publishes to:
        - boneio/{device_id}/discovery/device
        - boneio/{device_id}/discovery/outputs
        - boneio/{device_id}/discovery/covers
        - boneio/{device_id}/discovery/inputs
        - boneio/{device_id}/discovery/sensors
        - boneio/{device_id}/discovery/modbus
        
        All with retain=True.
        
        Does nothing if send_boneio_autodiscovery is disabled in config.
        """
        # Check if autodiscovery publishing is enabled
        if not self._manager._config_helper.send_boneio_autodiscovery:
            _LOGGER.debug("BoneIO autodiscovery publishing is disabled")
            return
        
        try:
            device_info = self._build_device_info()
            _LOGGER.info(
                "Publishing discovery for device '%s' to '%s/*'",
                device_info["id"],
                self._base_topic
            )
            
            self.publish_device()
            self.publish_outputs()
            self.publish_covers()
            self.publish_inputs()
            self.publish_sensors()
            self.publish_modbus()
            
            _LOGGER.info("Discovery published successfully")
            
        except Exception as e:
            _LOGGER.error("Failed to publish discovery: %s", e, exc_info=True)
