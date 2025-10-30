"""Sensor manager - handles all sensor devices.

This module manages all sensor devices including:
- Temperature sensors (I2C: PCT2075/LM75, MCP9808)
- Dallas 1-Wire sensors (DS18B20, etc.)
- Power monitoring (INA219)
- Analog sensors (ADC)
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from boneio.const import ADDRESS, DALLAS, DS2482, ID, INA219, ONEWIRE
from boneio.core.config.loader import (
    configure_ds2482,
    create_adc,
    create_dallas_sensor,
    create_ina219_sensor,
    create_temp_sensor,
    find_onewire_devices,
)
from boneio.exceptions import I2CError

if TYPE_CHECKING:
    from boneio.core.manager import Manager
    from boneio.hardware.sensor.temperature import MCP9808, PCT2075

_LOGGER = logging.getLogger(__name__)


class SensorManager:
    """Manages all sensors (temperature, power, analog).
    
    This manager handles:
    - I2C temperature sensors (PCT2075/LM75, MCP9808)
    - Dallas 1-Wire sensors (DS18B20, etc.)
    - INA219 power monitoring sensors
    - ADC analog sensors
    - Sensor initialization and updates
    - Home Assistant autodiscovery
    
    Args:
        manager: Parent Manager instance
        sensors: Dictionary of sensor configurations by type
        dallas: Dallas 1-Wire configuration
        ds2482: List of DS2482 I2C-to-1Wire bridge configurations
        adc: List of ADC sensor configurations
    """

    def __init__(
        self,
        manager: Manager,
        sensors: dict[str, list],
        dallas: dict[str, Any] | None,
        ds2482: list[dict] | None,
        adc: list[dict] | None,
    ):
        """Initialize sensor manager."""
        self._manager = manager
        self._temp_sensors: list[PCT2075 | MCP9808] = []
        self._ina219_sensors = []
        self._adc_sensors = []
        
        # Configure all sensor types
        self._configure_temp_sensors(sensors=sensors)
        self._configure_ina219_sensors(sensors=sensors)
        self._configure_dallas_sensors(
            dallas=dallas,
            ds2482=ds2482,
            sensors=sensors.get(ONEWIRE)
        )
        self._configure_adc(adc_list=adc)
        
        _LOGGER.info(
            "SensorManager initialized with %d temp sensors, %d INA219, %d ADC",
            len(self._temp_sensors),
            len(self._ina219_sensors),
            len(self._adc_sensors)
        )

    def _configure_temp_sensors(self, sensors: dict) -> None:
        """Configure I2C temperature sensors (PCT2075/LM75, MCP9808).
        
        Args:
            sensors: Dictionary of sensor configurations
        """
        for sensor_type, sensor_list in sensors.items():
            if sensor_type in ("lm75", "mcp9808"):
                for sensor_config in sensor_list:
                    try:
                        temp_sensor = create_temp_sensor(
                            manager=self._manager,
                            message_bus=self._manager._message_bus,
                            topic_prefix=self._manager._topic_prefix,
                            sensor_type=sensor_type,
                            i2cbusio=self._manager._i2cbusio,
                            config=sensor_config,
                        )
                        if temp_sensor:
                            self._temp_sensors.append(temp_sensor)
                    except I2CError as err:
                        _LOGGER.error("Failed to configure temp sensor: %s", err)

    def _configure_ina219_sensors(self, sensors: dict) -> None:
        """Configure INA219 power monitoring sensors.
        
        Args:
            sensors: Dictionary of sensor configurations
        """
        if sensors.get(INA219):
            for sensor_config in sensors[INA219]:
                try:
                    ina219 = create_ina219_sensor(
                        manager=self._manager,
                        message_bus=self._manager._message_bus,
                        topic_prefix=self._manager._topic_prefix,
                        config=sensor_config,
                    )
                    if ina219:
                        self._ina219_sensors.append(ina219)
                except I2CError as err:
                    _LOGGER.error("Failed to configure INA219 sensor: %s", err)

    def _configure_dallas_sensors(
        self,
        dallas: dict | None,
        ds2482: list | None,
        sensors: list | None,
    ) -> None:
        """Configure Dallas 1-Wire sensors via GPIO or DS2482 bridge.
        
        Args:
            dallas: Dallas GPIO configuration
            ds2482: List of DS2482 bridge configurations
            sensors: List of sensor configurations
        """
        if not ds2482 and not dallas:
            return
        
        _one_wire_devices = {}
        _ds_onewire_bus = {}
        
        # Configure DS2482 I2C-to-1Wire bridges
        if ds2482:
            from boneio.hardware.onewire import DallasSensor
            
            for _single_ds in ds2482:
                _LOGGER.debug("Preparing DS2482 bus at address %s", _single_ds[ADDRESS])
                
                try:
                    _ds_onewire_bus[_single_ds[ID]] = configure_ds2482(
                        i2cbusio=self._manager._i2cbusio,
                        address=_single_ds[ADDRESS]
                    )
                    _one_wire_devices.update(
                        find_onewire_devices(
                            ow_bus=_ds_onewire_bus[_single_ds[ID]],
                            bus_id=_single_ds[ID],
                            bus_type=DS2482,
                        )
                    )
                except Exception as err:
                    _LOGGER.error("Failed to configure DS2482 at %s: %s", _single_ds[ADDRESS], err)
        
        # Configure Dallas GPIO bus
        if dallas:
            _LOGGER.debug("Preparing Dallas GPIO bus")
            try:
                from w1thermsensor.errors import KernelModuleLoadError

                from boneio.core.config.loader import get_w1_sensor_class
                
                try:
                    _one_wire_devices.update(
                        find_onewire_devices(
                            ow_bus=get_w1_sensor_class()(),
                            bus_id=dallas[ID],
                            bus_type=DALLAS,
                        )
                    )
                except KernelModuleLoadError as err:
                    _LOGGER.error("Can't load kernel module for Dallas sensors: %s", err)
            except Exception as err:
                _LOGGER.error("Failed to configure Dallas GPIO bus: %s", err)
        
        # Create Dallas sensor instances
        if sensors:
            from boneio.hardware.onewire import DallasSensor
            
            for address, bus_id in _one_wire_devices.items():
                _LOGGER.debug("Configuring Dallas sensor %s for boneIO", address)
                try:
                    sensor = create_dallas_sensor(
                        manager=self._manager,
                        message_bus=self._manager._message_bus,
                        address=address,
                        topic_prefix=self._manager._topic_prefix,
                        sensors_config=sensors,
                        cls=DallasSensor,
                    )
                    if sensor:
                        self._temp_sensors.append(sensor)
                except Exception as err:
                    _LOGGER.error("Failed to create Dallas sensor %s: %s", address, err)

    def _configure_adc(self, adc_list: list[dict] | None) -> None:
        """Configure ADC analog sensors.
        
        Args:
            adc_list: List of ADC sensor configurations
        """
        if not adc_list:
            return
        
        try:
            adc_sensors = create_adc(
                manager=self._manager,
                message_bus=self._manager._message_bus,
                topic_prefix=self._manager._topic_prefix,
                adc_list=adc_list,
            )
            if adc_sensors:
                self._adc_sensors.extend(adc_sensors)
        except Exception as err:
            _LOGGER.error("Failed to configure ADC sensors: %s", err)

    def get_temp_sensor(self, id: str) -> PCT2075 | MCP9808 | None:
        """Get temperature sensor by ID.
        
        Args:
            id: Sensor identifier
            
        Returns:
            Temperature sensor instance or None
        """
        for sensor in self._temp_sensors:
            if sensor.id == id:
                return sensor
        return None

    def get_all_temp_sensors(self) -> list[PCT2075 | MCP9808]:
        """Get all temperature sensors.
        
        Returns:
            List of temperature sensors
        """
        return self._temp_sensors

    def get_ina219_sensors(self) -> list:
        """Get all INA219 sensors.
        
        Returns:
            List of INA219 sensors
        """
        return self._ina219_sensors

    def get_adc_sensors(self) -> list:
        """Get all ADC sensors.
        
        Returns:
            List of ADC sensors
        """
        return self._adc_sensors

    def get_tasks(self) -> dict[str, asyncio.Task]:
        """Get all sensor-related tasks.
        
        Returns:
            Dictionary of tasks
        """
        tasks = {}
        
        # Temperature sensor tasks
        for i, sensor in enumerate(self._temp_sensors):
            if hasattr(sensor, 'get_tasks'):
                sensor_tasks = sensor.get_tasks()
                for task_name, task in sensor_tasks.items():
                    tasks[f"temp_sensor_{i}_{task_name}"] = task
        
        # INA219 tasks
        for i, sensor in enumerate(self._ina219_sensors):
            if hasattr(sensor, 'get_tasks'):
                sensor_tasks = sensor.get_tasks()
                for task_name, task in sensor_tasks.items():
                    tasks[f"ina219_{i}_{task_name}"] = task
        
        # ADC tasks
        for i, sensor in enumerate(self._adc_sensors):
            if hasattr(sensor, 'get_tasks'):
                sensor_tasks = sensor.get_tasks()
                for task_name, task in sensor_tasks.items():
                    tasks[f"adc_{i}_{task_name}"] = task
        
        return tasks

    async def send_ha_autodiscovery(self) -> None:
        """Send Home Assistant autodiscovery for all sensors."""
        # Temperature sensors
        for sensor in self._temp_sensors:
            if hasattr(sensor, 'send_ha_discovery'):
                try:
                    await sensor.send_ha_discovery()
                except Exception as err:
                    _LOGGER.error("Failed to send HA discovery for temp sensor: %s", err)
        
        # INA219 sensors
        for sensor in self._ina219_sensors:
            if hasattr(sensor, 'send_ha_discovery'):
                try:
                    await sensor.send_ha_discovery()
                except Exception as err:
                    _LOGGER.error("Failed to send HA discovery for INA219: %s", err)
        
        # ADC sensors
        for sensor in self._adc_sensors:
            if hasattr(sensor, 'send_ha_discovery'):
                try:
                    await sensor.send_ha_discovery()
                except Exception as err:
                    _LOGGER.error("Failed to send HA discovery for ADC: %s", err)
