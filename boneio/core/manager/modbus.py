"""Modbus manager - handles all Modbus devices.

This module manages Modbus RTU/TCP devices and coordinators.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from boneio.const import ADDRESS, ID, MODEL, NAME, UART, UARTS, UPDATE_INTERVAL
from boneio.core.utils.timeperiod import TimePeriod
from boneio.exceptions import ModbusUartException

if TYPE_CHECKING:
    from boneio.core.manager import Manager
    from boneio.modbus.coordinator import ModbusCoordinator

_LOGGER = logging.getLogger(__name__)


class ModbusManager:
    """Manages Modbus devices and coordinators.
    
    This manager handles:
    - Modbus RTU/TCP client initialization
    - Modbus device coordinators
    - Modbus communication
    - Home Assistant autodiscovery for Modbus entities
    
    Args:
        manager: Parent Manager instance
        modbus_config: Modbus client configuration
        modbus_devices: Dictionary of Modbus device configurations
    """

    def __init__(
        self,
        manager: Manager,
        modbus_config: dict[str, Any],
        modbus_devices: list[dict[str, Any]],
    ):
        """Initialize Modbus manager."""
        self._manager = manager
        self._modbus = None
        self._modbus_coordinators = {}
        
        # Configure Modbus if enabled
        if modbus_config:
            self._configure_modbus(
                modbus_config=modbus_config,
                modbus_devices=modbus_devices
            )
        
        _LOGGER.info(
            "ModbusManager initialized with %d coordinators",
            len(self._modbus_coordinators)
        )

    def _configure_modbus(
        self,
        modbus_config: dict[str, Any],
        modbus_devices: list[dict[str, Any]],
    ) -> None:
        """Configure Modbus client and devices.
        
        Args:
            modbus_config: Modbus client configuration
            modbus_devices: Dictionary of device configurations
        """
        try:
            # Lazy import to avoid loading Modbus when not needed
            from boneio.modbus.client import Modbus
            
            # Work on a copy to avoid modifying the original config
            config = modbus_config.copy()
            
            # Validate UART configuration
            uart = config.pop(UART)
            if uart and uart not in UARTS:
                raise ModbusUartException(
                    f"UART {uart} is not available. Available UARTs: {UARTS}"
                )
            
            # Initialize Modbus client
            self._modbus = Modbus(
                uart=UARTS[uart],
                baudrate=config.pop("baudrate", 9600),
                **config
            )
            
            # Configure device coordinators
            if modbus_devices and self._modbus:
                self._modbus_coordinators = self._configure_modbus_coordinators(
                    devices=modbus_devices
                )
            
            _LOGGER.info("Modbus configured on UART %s", uart)
            
        except ModbusUartException as err:
            _LOGGER.error("Modbus UART configuration error: %s", err)
        except ImportError as err:
            _LOGGER.error("Failed to import Modbus modules: %s", err)
        except Exception as err:
            _LOGGER.error("Failed to configure Modbus: %s", err)

    def _configure_modbus_coordinators(self, devices: list[dict[str, Any]]) -> dict:
        """Configure Modbus device coordinators.
        
        Args:
            devices: List of device configurations
            
        Returns:
            Dictionary of ModbusCoordinator instances
        """
        coordinators = {}
        
        # Type guard - this method should only be called when _modbus is initialized
        if self._modbus is None:
            _LOGGER.error("Cannot configure coordinators: Modbus client not initialized")
            return coordinators
        
        try:
            from boneio.modbus.coordinator import ModbusCoordinator
            
            for device_config in devices:
                try:
                    # Get address and model (required)
                    address = device_config.get(ADDRESS, "")
                    model = device_config.get(MODEL, "")
                    
                    # Generate ID from address and model if not provided
                    if device_config.get(ID):
                        device_id = str(device_config[ID]).replace(" ", "").lower()
                    else:
                        device_id = f"{address}_{model}".lower().replace(" ", "_")
                    
                    # Get display name (falls back to ID)
                    display_name = device_config.get(NAME) or device_id
                    
                    # Get area for HA grouping
                    area = device_config.get("area")
                    
                    additional_data = device_config.get("data", {})
                    
                    _LOGGER.debug("Configuring Modbus coordinator: %s (address: %s, model: %s)", 
                                  display_name, address, model)
                    
                    coordinator = ModbusCoordinator(
                        address=address,
                        id=device_id,
                        name=display_name,
                        manager=self._manager,
                        model=device_config[MODEL],
                        update_interval=device_config.get(
                            UPDATE_INTERVAL, TimePeriod(seconds=60)
                        ),
                        modbus=self._modbus,
                        sensors_filters=device_config.get("sensors_filters", {}),
                        additional_data=additional_data,
                        area=area,
                    )
                    coordinators[device_id] = coordinator
                    _LOGGER.info("Configured Modbus coordinator: %s", device_id)
                    
                except Exception as err:
                    _LOGGER.error(
                        "Failed to configure Modbus coordinator %s: %s",
                        device_config.get(ID) or device_config.get(NAME) or "unknown",
                        err,
                        exc_info=True  # This will log the full traceback
                    )
        
        except ImportError as err:
            _LOGGER.error("Failed to import ModbusCoordinator: %s", err)
        
        return coordinators

    def get_coordinator(self, id: str) -> ModbusCoordinator | None:
        """Get Modbus coordinator by ID.
        
        Args:
            id: Coordinator identifier
            
        Returns:
            ModbusCoordinator instance or None
        """
        return self._modbus_coordinators.get(id)

    def get_all_coordinators(self) -> dict[str, ModbusCoordinator]:
        """Get all Modbus coordinators.
        
        Returns:
            Dictionary of ModbusCoordinator instances
        """
        return self._modbus_coordinators

    def get_modbus_client(self) -> Any | None:
        """Get Modbus client instance.
        
        Returns:
            Modbus client or None
        """
        return self._modbus

    async def send_ha_autodiscovery(self) -> None:
        """Send Home Assistant autodiscovery for all Modbus entities."""
        for coordinator in self._modbus_coordinators.values():
            if hasattr(coordinator, 'send_ha_autodiscovery'):
                try:
                    await coordinator.send_ha_autodiscovery()
                except Exception as err:
                    _LOGGER.error(
                        "Failed to send HA discovery for Modbus coordinator: %s",
                        err
                    )

    def _get_device_id_from_config(self, device_config: dict) -> str:
        """Generate device ID from config (same logic as in _configure_modbus_coordinators).
        
        Args:
            device_config: Device configuration dictionary
            
        Returns:
            Generated device ID
        """
        if device_config.get(ID):
            return str(device_config[ID]).replace(" ", "").lower()
        else:
            address = device_config.get(ADDRESS, "")
            model = device_config.get(MODEL, "")
            return f"{address}_{model}".lower().replace(" ", "_")

    def _remove_modbus_ha_discovery_for_id(self, device_id: str) -> None:
        """Remove HA autodiscovery for a specific Modbus device.
        
        Sends empty payloads to MQTT to remove entities from Home Assistant.
        Modbus devices can have multiple entity types: sensor, binary_sensor, 
        number, select, switch, text_sensor.
        
        Args:
            device_id: Device ID to remove
        """
        # Modbus uses multiple entity types
        ha_types = ["sensor", "binary_sensor", "number", "select", "switch", "text_sensor"]
        
        for ha_type in ha_types:
            # Get autodiscovery messages for this type
            type_messages = self._manager._config_helper._autodiscovery_messages.get(ha_type, {})
            
            # Find topics that contain this device_id
            topics_to_remove = []
            for topic in type_messages.keys():
                # Topic format: homeassistant/{type}/{topic_prefix}{device_id}/{entity_id}/config
                # We need to match device_id in the topic
                if f"/{device_id}" in topic or f"{device_id}_" in topic or f"{device_id}/" in topic:
                    topics_to_remove.append(topic)
            
            for topic in topics_to_remove:
                # Send empty/null payload to remove from HA (HA requires zero-length retained message)
                self._manager.send_message(topic=topic, payload=None, retain=True)
                self._manager._config_helper.remove_autodiscovery_msg(ha_type, topic)
                _LOGGER.debug("Removed HA autodiscovery for Modbus %s: %s", ha_type, topic)

    async def reload_modbus_devices(self) -> None:
        """Reload Modbus devices configuration from file.
        
        This compares old and new configurations to:
        - Remove only deleted devices from HA
        - Keep existing devices (preserving HA entity history)
        - Add new devices
        
        The Modbus client itself is not recreated.
        """
        
        _LOGGER.info("Reloading Modbus devices configuration")
        
        # Get config from ConfigHelper (uses cache, reloads if needed)
        config = self._manager._config_helper.reload_config()
        
        # Get new modbus_devices config
        new_devices = config.get("modbus_devices", [])
        
        # Build set of old device IDs
        old_device_ids = set(self._modbus_coordinators.keys())
        
        # Build set of new device IDs and map config by ID
        new_device_ids = set()
        new_device_configs = {}
        for device_config in new_devices:
            device_id = self._get_device_id_from_config(device_config)
            new_device_ids.add(device_id)
            new_device_configs[device_id] = device_config
        
        # Find devices to remove (in old but not in new)
        devices_to_remove = old_device_ids - new_device_ids
        
        # Find devices to add (in new but not in old)
        devices_to_add = new_device_ids - old_device_ids
        
        # Find devices to update (in both - check if config changed)
        devices_to_update = old_device_ids & new_device_ids
        
        _LOGGER.debug(
            "Modbus reload: remove=%s, add=%s, check_update=%s",
            devices_to_remove, devices_to_add, devices_to_update
        )
        
        # Remove deleted devices from HA and coordinators dict
        for device_id in devices_to_remove:
            _LOGGER.info("Removing Modbus device: %s", device_id)
            self._remove_modbus_ha_discovery_for_id(device_id)
            del self._modbus_coordinators[device_id]
        
        # Check for area or name changes in existing devices and recreate if needed
        devices_to_recreate = set()
        for device_id in devices_to_update:
            coordinator = self._modbus_coordinators.get(device_id)
            if coordinator:
                old_area = getattr(coordinator, 'area', None)
                new_area = new_device_configs[device_id].get("area")
                old_name = getattr(coordinator, '_name', None)
                new_name = new_device_configs[device_id].get("name")
                
                if old_area != new_area:
                    _LOGGER.info(
                        "Modbus device %s area changed: %s -> %s, recreating",
                        device_id, old_area, new_area
                    )
                    # Remove old HA Discovery
                    self._remove_modbus_ha_discovery_for_id(device_id)
                    devices_to_recreate.add(device_id)
                elif old_name != new_name:
                    _LOGGER.info(
                        "Modbus device %s name changed: %s -> %s, recreating",
                        device_id, old_name, new_name
                    )
                    # Remove old HA Discovery
                    self._remove_modbus_ha_discovery_for_id(device_id)
                    devices_to_recreate.add(device_id)
        
        # Remove coordinators that need recreation
        for device_id in devices_to_recreate:
            del self._modbus_coordinators[device_id]
        
        # Wait for HA to process the removal before sending new discovery
        if devices_to_recreate:
            _LOGGER.debug("Waiting 1.5s for HA to process discovery removal...")
            await asyncio.sleep(1.5)
        
        # Add new devices and recreated devices
        devices_to_create = devices_to_add | devices_to_recreate
        if self._modbus and devices_to_create:
            configs_to_add = [
                new_device_configs[device_id] for device_id in devices_to_create
            ]
            new_coordinators = self._configure_modbus_coordinators(devices=configs_to_add)
            self._modbus_coordinators.update(new_coordinators)
            _LOGGER.info("Added/recreated %d Modbus devices", len(new_coordinators))
        
        _LOGGER.info(
            "Modbus devices reload complete: %d coordinators (removed=%d, added=%d, recreated=%d)",
            len(self._modbus_coordinators),
            len(devices_to_remove),
            len(devices_to_add),
            len(devices_to_recreate)
        )
