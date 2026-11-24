"""Modbus manager - handles all Modbus devices.

This module manages Modbus RTU/TCP devices and coordinators.
"""

from __future__ import annotations

import asyncio
import copy
import logging
from typing import TYPE_CHECKING, Any

from boneio.const import ADDRESS, ID, MODEL, NAME, UPDATE_INTERVAL
from boneio.core.config.modbus_buses import device_bus, serial_device
from boneio.core.config.modbus_buses import device_id as modbus_device_id
from boneio.core.config.yaml_util import normalize_section
from boneio.core.utils.timeperiod import TimePeriod, parse_time_to_ms, parse_time_to_seconds

if TYPE_CHECKING:
    from boneio.core.manager import Manager
    from boneio.modbus.client import Modbus
    from boneio.modbus.coordinator import ModbusCoordinator

_LOGGER = logging.getLogger(__name__)


class ModbusManager:
    """Manages Modbus buses, device coordinators and their HA discovery.

    Each bus has its own ``Modbus`` client, so a slow or missing port holds
    up only its own devices. A device polls on the bus it names, else on the
    first bus. The bus list is read once at start; a reload rebuilds devices.

    Args:
        manager: Parent Manager instance
        modbus_config: The list of buses (``id``, ``port`` and line settings)
        modbus_devices: List of Modbus device configurations
    """

    def __init__(
        self,
        manager: Manager,
        modbus_config: list[dict[str, Any]],
        modbus_devices: list[dict[str, Any]],
    ):
        """Initialize Modbus manager."""
        self._manager = manager
        self._bus_configs = modbus_config or []
        self._buses: dict[str, Modbus] = {}
        self._modbus_coordinators = {}
        # Device id -> what its coordinator was built from, to tell on a
        # reload whether it must be built again.
        self._coordinator_built_from: dict[str, dict[str, Any]] = {}

        for bus in self._bus_configs:
            self._start_bus(bus)
        if modbus_devices and not self._bus_configs:
            _LOGGER.warning(
                "%d Modbus devices configured but no Modbus bus; they are not started.",
                len(modbus_devices),
            )
        elif modbus_devices:
            self._modbus_coordinators = self._configure_modbus_coordinators(
                devices=list(self._unique_devices(modbus_devices).values())
            )

        _LOGGER.info(
            "ModbusManager initialized with %d buses and %d coordinators",
            len(self._buses),
            len(self._modbus_coordinators),
        )

    def _start_bus(self, bus: dict[str, Any]) -> None:
        """Build one bus's client; a failure is logged and leaves the others."""
        try:
            # Lazy import to avoid loading Modbus when not needed
            from boneio.modbus.client import Modbus

            self._buses[bus[ID]] = Modbus(
                port=serial_device(bus["port"]),
                baudrate=bus.get("baudrate", 9600),
                stopbits=bus.get("stopbits", 1),
                bytesize=bus.get("bytesize", 8),
                parity=bus.get("parity", "N"),
                timeout=parse_time_to_seconds(bus.get("timeout"), default=1.5),
                inter_device_delay=parse_time_to_ms(bus.get("inter_device_delay"), default=5) or 5,
            )
            _LOGGER.info("Modbus bus %s configured on %s", bus[ID], bus["port"])
        except Exception as err:
            _LOGGER.error("Failed to configure Modbus bus %s on %s: %s", bus.get(ID), bus.get("port"), err)

    def _unique_devices(self, devices: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """Device configs by id; of two with one id the first is kept, the other logged."""
        unique: dict[str, dict[str, Any]] = {}
        for device_config in devices:
            device_id = self._get_device_id_from_config(device_config)
            if device_id in unique:
                _LOGGER.error("Modbus device %r skipped: another device has the same id.", device_id)
                continue
            unique[device_id] = device_config
        return unique

    def _configure_modbus_coordinators(self, devices: list[dict[str, Any]]) -> dict:
        """Build a coordinator for each device on the client of its bus.

        A device whose bus is not running is skipped with an error.

        Args:
            devices: List of device configurations

        Returns:
            Dictionary of ModbusCoordinator instances
        """
        coordinators = {}

        try:
            from boneio.modbus.coordinator import ModbusCoordinator
            from boneio.modbus.definition import load_definition
            from boneio.modbus.simulator import SimulatedClient

            for device_config in devices:
                try:
                    inputs = self._coordinator_inputs(device_config)
                    device_id = inputs["id"]
                    modbus = self._buses.get(inputs["bus"])
                    if modbus is None:
                        _LOGGER.error(
                            "Modbus device %r skipped: its bus %r is not running.", device_id, inputs["bus"]
                        )
                        continue
                    _LOGGER.debug("Configuring Modbus coordinator: %s (address: %s, model: %s, bus: %s)",
                                  inputs["name"], inputs["address"], inputs["model"], inputs["bus"])
                    coordinator = ModbusCoordinator(
                        manager=self._manager,
                        modbus=modbus,
                        entity_labels=device_config.get("entity_labels", {}),
                        **{key: value for key, value in inputs.items() if key != "bus"},
                    )
                    self._coordinator_built_from[device_id] = copy.deepcopy(inputs)
                    coordinators[device_id] = coordinator
                    if isinstance(modbus.client, SimulatedClient):
                        modbus.client.add_device(int(inputs["address"]), load_definition(inputs["model"]))
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

    def get_modbus_client(self, bus: str | None = None) -> Modbus | None:
        """The client of a bus, by default the first; None if it is not running."""
        if bus is None:
            if not self._bus_configs:
                return None
            bus = self._bus_configs[0][ID]
        return self._buses.get(bus)

    def bus_ids(self) -> list[str]:
        """Ids of the running buses, in config order."""
        return list(self._buses)

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
        return modbus_device_id(device_config)

    def _coordinator_inputs(self, device_config: dict[str, Any]) -> dict[str, Any]:
        """Constructor arguments of a device's coordinator, in one form.

        Takes a normalized device config, as startup and the reload both pass
        it, so the same file gives the same arguments. Entity labels are not
        here: they are applied to a running coordinator.
        """
        device_id = self._get_device_id_from_config(device_config)
        return {
            "address": device_config.get(ADDRESS, ""),
            "id": device_id,
            "bus": device_bus(device_config, self._bus_configs),
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
        
        The buses and their clients are not recreated.
        """
        
        _LOGGER.info("Reloading Modbus devices configuration")
        
        # Get config from ConfigHelper (already reloaded by Manager)
        config = self._manager._config_helper.get_config()
        
        # The fast reload reads raw YAML; compare and build from what startup
        # would have made of it.
        new_devices = normalize_section("modbus_devices", config.get("modbus_devices") or [])
        
        # Build set of old device IDs
        old_device_ids = set(self._modbus_coordinators.keys())
        
        # Build set of new device IDs and map config by ID
        new_device_configs = self._unique_devices(new_devices)
        new_device_ids = set(new_device_configs)
        
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
        if self._buses and devices_to_create:
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
