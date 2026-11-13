"""Modbus manager - handles all Modbus devices.

This module manages Modbus RTU/TCP devices and coordinators.
"""

from __future__ import annotations

import asyncio
import copy
import logging
from typing import TYPE_CHECKING, Any

from boneio.const import ADDRESS, ID, MODEL, NAME, UART, UARTS, UPDATE_INTERVAL
from boneio.core.utils.timeperiod import TimePeriod, parse_time_to_ms, parse_time_to_seconds
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
        # Device id -> what its coordinator was built from, to tell on a
        # reload whether it must be built again.
        self._coordinator_built_from: dict[str, dict[str, Any]] = {}
        
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
            
            # Convert TimePeriod values to numeric before passing to client
            timeout = parse_time_to_seconds(
                config.pop("timeout", None), default=1.5
            )
            inter_device_delay = parse_time_to_ms(
                config.pop("inter_device_delay", None), default=5
            ) or 5
            
            # Initialize Modbus client
            self._modbus = Modbus(
                uart=UARTS[uart],
                baudrate=config.pop("baudrate", 9600),
                timeout=timeout,
                inter_device_delay=inter_device_delay,
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
            from boneio.modbus.definition import load_definition
            from boneio.modbus.simulator import SimulatedClient
            
            for device_config in devices:
                try:
                    inputs = self._coordinator_inputs(device_config)
                    device_id = inputs["id"]
                    _LOGGER.debug("Configuring Modbus coordinator: %s (address: %s, model: %s)",
                                  inputs["name"], inputs["address"], inputs["model"])
                    coordinator = ModbusCoordinator(
                        manager=self._manager,
                        modbus=self._modbus,
                        entity_labels=device_config.get("entity_labels", {}),
                        **inputs,
                    )
                    self._coordinator_built_from[device_id] = copy.deepcopy(inputs)
                    coordinators[device_id] = coordinator
                    if isinstance(self._modbus.client, SimulatedClient):
                        self._modbus.client.add_device(int(inputs["address"]), load_definition(inputs["model"]))
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

    def _coordinator_inputs(self, device_config: dict[str, Any]) -> dict[str, Any]:
        """Constructor arguments of a device's coordinator, in one form.

        The config at startup is validated and a reloaded one is raw YAML;
        both give the same arguments for the same file. Entity labels are not
        here: they are applied to a running coordinator.
        """
        device_id = self._get_device_id_from_config(device_config)
        return {
            "address": device_config.get(ADDRESS, ""),
            "id": device_id,
            "name": device_config.get(NAME) or device_id,
            "model": device_config.get(MODEL, ""),
            "update_interval": TimePeriod(
                seconds=parse_time_to_seconds(device_config.get(UPDATE_INTERVAL), default=30)
            ),
            "sensors_filters": device_config.get("sensors_filters") or {},
            "additional_data": device_config.get("data") or {},
            "area": device_config.get("area"),
            "has_custom_id": bool(device_config.get(ID)),
            "read_only": bool(device_config.get("read_only", False)),
            "entity_visibility": device_config.get("entity_visibility") or {},
        }

    def _drop_coordinator(self, device_id: str) -> None:
        """Forget a coordinator and end its polling, so it never announces itself again."""
        self._modbus_coordinators.pop(device_id).stop_updates()
        self._coordinator_built_from.pop(device_id, None)

    def _remove_modbus_ha_discovery_for_id(self, device_id: str) -> None:
        """Remove HA autodiscovery for a specific Modbus device.
        
        Sends empty payloads to MQTT to remove entities from Home Assistant.
        Only the topics the device itself names go, so an entity of another
        device whose id merely starts the same way stays.

        Args:
            device_id: Device ID to remove
        """
        coordinator = self._modbus_coordinators.get(device_id)
        if coordinator is None:
            return
        config_helper = self._manager._config_helper
        for ha_type, topic in coordinator.discovery_topics():
            if not config_helper.is_topic_in_autodiscovery(topic):
                continue
            # HA removes an entity on a zero-length retained message.
            self._manager.send_message(topic=topic, payload=None, retain=True)
            config_helper.remove_autodiscovery_msg(ha_type, topic)
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
        
        # Get config from ConfigHelper (already reloaded by Manager)
        config = self._manager._config_helper.get_config()
        
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
            self._drop_coordinator(device_id)
        
        # A coordinator takes its config only when built: any change but the
        # labels means building it again.
        devices_to_recreate = set()
        for device_id in devices_to_update:
            if self._coordinator_built_from.get(device_id) == self._coordinator_inputs(
                new_device_configs[device_id]
            ):
                continue
            _LOGGER.info("Modbus device %s config changed, recreating", device_id)
            self._remove_modbus_ha_discovery_for_id(device_id)
            self._drop_coordinator(device_id)
            devices_to_recreate.add(device_id)

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
            
            # Send online status for newly created/recreated coordinators
            # This ensures the new availability topic gets the online status immediately
            for coordinator in new_coordinators.values():
                try:
                    await coordinator.send_online_status()
                except Exception as err:
                    _LOGGER.error(
                        "Failed to send online status for coordinator %s: %s",
                        coordinator.id,
                        err
                    )
        
        _LOGGER.info(
            "Modbus devices reload complete: %d coordinators (removed=%d, added=%d, recreated=%d)",
            len(self._modbus_coordinators),
            len(devices_to_remove),
            len(devices_to_add),
            len(devices_to_recreate)
        )
