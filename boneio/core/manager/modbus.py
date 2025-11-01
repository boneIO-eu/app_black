"""Modbus manager - handles all Modbus devices.

This module manages Modbus RTU/TCP devices and coordinators.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from boneio.const import ADDRESS, MODEL, UART, UARTS, UPDATE_INTERVAL
from boneio.core.utils.timeperiod import TimePeriod
from boneio.exceptions import ModbusUartException

if TYPE_CHECKING:
    from boneio.core.manager import Manager

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
            
            
            # Validate UART configuration
            uart = modbus_config.pop(UART)
            if uart and uart not in UARTS:
                raise ModbusUartException(
                    f"UART {uart} is not available. Available UARTs: {UARTS}"
                )
            
            # Initialize Modbus client
            self._modbus = Modbus(
                uart=UARTS[uart],
                baudrate=modbus_config.pop("baudrate", 9600),
                **modbus_config
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
        devices: List of device configurations
        Args:
            devices: Dictionary of device configurations
            
        Returns:
            Dictionary of ModbusCoordinator instances
        """
        coordinators = {}
        
        try:
            from boneio.modbus.coordinator import ModbusCoordinator
            
            for device_config in devices:
                try:
                    name = device_config.get("id")
                    id = name.replace(" ", "")
                    additional_data = device_config.get("data", {})
                    
                    _LOGGER.debug("Configuring Modbus coordinator: %s (address: %s, model: %s)", 
                                  name, device_config.get(ADDRESS), device_config.get(MODEL))
                    
                    coordinator = ModbusCoordinator(
                        address=device_config[ADDRESS],
                        id=id,
                        name=name,
                        manager=self._manager,
                        model=device_config[MODEL],
                        update_interval=device_config.get(
                            UPDATE_INTERVAL, TimePeriod(seconds=60)
                        ),
                        modbus=self._modbus,
                        sensors_filters=device_config.get("sensors_filters", {}),
                        additional_data=additional_data,
                    )
                    coordinators[id] = coordinator
                    _LOGGER.info("Configured Modbus coordinator: %s", id)
                    
                except Exception as err:
                    _LOGGER.error(
                        "Failed to configure Modbus coordinator %s: %s",
                        name,
                        err,
                        exc_info=True  # This will log the full traceback
                    )
        
        except ImportError as err:
            _LOGGER.error("Failed to import ModbusCoordinator: %s", err)
        
        return coordinators

    def get_coordinator(self, id: str) -> Any | None:
        """Get Modbus coordinator by ID.
        
        Args:
            id: Coordinator identifier
            
        Returns:
            ModbusCoordinator instance or None
        """
        return self._modbus_coordinators.get(id)

    def get_all_coordinators(self) -> dict[str, Any]:
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

    def get_tasks(self) -> dict[str, asyncio.Task]:
        """Get all Modbus-related tasks.
        
        Returns:
            Dictionary of tasks
        """
        tasks = {}
        
        for coordinator_id, coordinator in self._modbus_coordinators.items():
            if hasattr(coordinator, 'get_tasks'):
                coordinator_tasks = coordinator.get_tasks()
                for task_name, task in coordinator_tasks.items():
                    tasks[f"modbus_{coordinator_id}_{task_name}"] = task
        
        return tasks

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

    def reload_modbus_devices(self) -> None:
        """Reload Modbus devices configuration from file.
        
        This clears existing coordinators and recreates them
        based on the current config. The Modbus client itself is not recreated.
        Note: Existing coordinator tasks will continue running until Manager
        refreshes its task list, but new coordinators will be created.
        """
        _LOGGER.info("Reloading Modbus devices configuration")
        
        # Get config from ConfigHelper (uses cache, reloads if needed)
        config = self._manager._config_helper.reload_config()
        
        # Get new modbus_devices config
        modbus_devices = config.get("modbus_devices", [])
        
        # Clear existing coordinators
        # Note: Their tasks will be cleaned up when Manager refreshes task list
        # Old coordinators will stop working naturally as they're removed from dict
        self._modbus_coordinators.clear()
        
        # Clear autodiscovery messages for Modbus
        self._manager._config_helper.clear_autodiscovery_type(ha_type="sensor")
        
        # Recreate coordinators if Modbus client exists and devices are configured
        if self._modbus and modbus_devices:
            self._modbus_coordinators = self._configure_modbus_coordinators(
                devices=modbus_devices
            )
            
            _LOGGER.info(
                "Modbus devices reload complete: %d coordinators",
                len(self._modbus_coordinators)
            )
        else:
            _LOGGER.info("Modbus devices reload complete: no coordinators configured")
