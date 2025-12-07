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

from boneio.const import (
    ADDRESS,
    DALLAS,
    DS2482,
    FILTERS,
    ID,
    INA219,
    LM75,
    MCP_TEMP_9808,
    ONEWIRE,
    PIN,
    SENSOR,
    SHOW_HA,
    UPDATE_INTERVAL,
    DallasBusTypes,
)
from boneio.core.utils import TimePeriod
from boneio.exceptions import I2CError
from boneio.hardware.onewire import (
    DS2482 as DS2482Bridge,
)
from boneio.hardware.onewire import (
    DS2482_ADDRESS,
    DallasSensor,
    OneWireBus,
)
from boneio.integration.homeassistant import (
    ha_adc_sensor_availabilty_message,
    ha_sensor_ina_availabilty_message,
    ha_sensor_temp_availabilty_message,
)

if TYPE_CHECKING:
    from boneio.core.manager import Manager
    from boneio.hardware.sensor.temperature import MCP9808, PCT2075

# Type alias for all temperature sensors (I2C + Dallas)
TempSensorType = "PCT2075 | MCP9808 | DallasSensor"

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
        self._temp_sensors: list[PCT2075 | MCP9808 | DallasSensor] = []
        self._ina219_sensors = []
        self._adc_sensors = []
        self._dallas_sensors = []
        self._system_sensors = []
        
        # Configure all sensor types
        self._configure_temp_sensors(sensors=sensors)
        self._configure_ina219_sensors(sensors=sensors)
        self._configure_dallas_sensors(
            dallas=dallas,
            ds2482=ds2482,
            sensors=sensors.get(ONEWIRE)
        )
        self._configure_adc(adc_list=adc)
        self._configure_system_sensors()
        
        _LOGGER.info(
            "SensorManager initialized with %d temp sensors, %d INA219, %d ADC, %d Dallas, %d system",
            len(self._temp_sensors),
            len(self._ina219_sensors),
            len(self._adc_sensors),
            len(self._dallas_sensors),
            len(self._system_sensors)
        )

    # -------------------------------------------------------------------------
    # Temperature Sensors (I2C)
    # -------------------------------------------------------------------------
    
    def _configure_temp_sensors(self, sensors: dict) -> None:
        """Configure I2C temperature sensors (PCT2075/LM75, MCP9808).
        
        Args:
            sensors: Dictionary of sensor configurations
        """
        for sensor_type, sensor_list in sensors.items():
            if sensor_type in (LM75, MCP_TEMP_9808):
                for sensor_config in sensor_list:
                    temp_sensor = self._create_temp_sensor(
                        sensor_type=sensor_type,
                        config=sensor_config,
                    )
                    if temp_sensor:
                        self._temp_sensors.append(temp_sensor)

    def _create_temp_sensor(self, sensor_type: str, config: dict) -> "PCT2075 | MCP9808 | None":
        """Create a temperature sensor instance.
        
        Args:
            sensor_type: Type of sensor (lm75 or mcp9808)
            config: Sensor configuration dictionary
            
        Returns:
            Temperature sensor instance or None on error
        """
        if sensor_type == LM75:
            from boneio.hardware.sensor.temperature.pct2075 import PCT2075 as TempSensor
        elif sensor_type == MCP_TEMP_9808:
            from boneio.hardware.sensor.temperature.mcp9808 import MCP9808 as TempSensor
        else:
            return None
        
        name = config.get(ID)
        if not name:
            return None
        
        id = name.replace(" ", "")
        
        try:
            temp_sensor = TempSensor(
                id=id,
                name=name,
                i2c=self._manager._i2cbusio,
                address=config[ADDRESS],
                manager=self._manager,
                message_bus=self._manager._message_bus,
                topic_prefix=self._manager._topic_prefix,
                update_interval=config.get(UPDATE_INTERVAL, TimePeriod(seconds=60)),
                filters=config.get(FILTERS, []),
                unit_of_measurement=config.get("unit_of_measurement", "°C"),
            )
            self._manager.send_ha_autodiscovery(
                id=id,
                name=name,
                ha_type=SENSOR,
                availability_msg_func=ha_sensor_temp_availabilty_message,
                unit_of_measurement=temp_sensor.unit_of_measurement,
            )
            return temp_sensor
        except I2CError as err:
            _LOGGER.error("Can't configure temp sensor %s: %s", name, err)
            return None

    # -------------------------------------------------------------------------
    # INA219 Power Sensors
    # -------------------------------------------------------------------------
    
    def _configure_ina219_sensors(self, sensors: dict) -> None:
        """Configure INA219 power monitoring sensors.
        
        Args:
            sensors: Dictionary of sensor configurations
        """
        if not sensors.get(INA219):
            return
            
        for sensor_config in sensors[INA219]:
            ina219 = self._create_ina219_sensor(config=sensor_config)
            if ina219:
                self._ina219_sensors.append(ina219)

    def _create_ina219_sensor(self, config: dict):
        """Create INA219 sensor instance.
        
        Args:
            config: Sensor configuration dictionary
            
        Returns:
            INA219 sensor instance or None on error
        """
        from boneio.hardware.i2c import INA219

        address = config[ADDRESS]
        id = config.get(ID, str(address)).replace(" ", "")
        
        try:
            ina219 = INA219(
                id=id,
                address=address,
                sensors=config.get("sensors", []),
                manager=self._manager,
                message_bus=self._manager._message_bus,
                topic_prefix=self._manager._topic_prefix,
                update_interval=config.get(UPDATE_INTERVAL, TimePeriod(seconds=60)),
            )
            # Send HA autodiscovery for each sub-sensor
            for sensor in ina219.sensors.values():
                self._manager.send_ha_autodiscovery(
                    id=sensor.id,
                    name=sensor.name,
                    ha_type=SENSOR,
                    availability_msg_func=ha_sensor_ina_availabilty_message,
                    unit_of_measurement=sensor.unit_of_measurement,
                    device_class=sensor.device_class,
                )
            return ina219
        except I2CError as err:
            _LOGGER.error("Can't configure INA219 sensor: %s", err)
            return None

    # -------------------------------------------------------------------------
    # Dallas 1-Wire Sensors
    # -------------------------------------------------------------------------
    
    def _configure_dallas_sensors(
        self,
        dallas: dict | None,
        ds2482: list | None,
        sensors: list | None,
    ) -> None:
        """Configure Dallas 1-Wire sensors via GPIO or DS2482 bridge.
        
        Args:
            dallas: Dallas GPIO configuration (deprecated, kept for backward compat)
            ds2482: List of DS2482 bridge configurations
            sensors: List of sensor configurations
        """
        if not sensors:
            return
        
        _ds2482_buses: dict[str, OneWireBus] = {}
        
        # Configure DS2482 I2C-to-1Wire bridges if defined
        if ds2482:
            for _single_ds in ds2482:
                _LOGGER.debug("Preparing DS2482 bus at address %s", _single_ds[ADDRESS])
                try:
                    ow_bus = self._configure_ds2482(address=_single_ds[ADDRESS])
                    _ds2482_buses[_single_ds[ID]] = ow_bus
                except Exception as err:
                    _LOGGER.error("Failed to configure DS2482 at %s: %s", _single_ds[ADDRESS], err)
        
        # Create sensor instances based on platform
        for sensor_config in sensors:
            platform = sensor_config.get("platform", "gpio_onewire")
            address = sensor_config.get("address")
            
            if not address:
                _LOGGER.warning("Sensor config missing address, skipping")
                continue
            
            _LOGGER.debug("Configuring %s sensor at address %s", platform, address)
            
            if platform == "ds2482":
                # DS2482 platform - need bus_id
                bus_id = sensor_config.get("bus_id")
                if not bus_id or bus_id not in _ds2482_buses:
                    _LOGGER.error(
                        "DS2482 sensor %s requires valid bus_id. Available: %s",
                        address, list(_ds2482_buses.keys())
                    )
                    continue
            
            # Create sensor instance
            sensor = self._create_dallas_sensor(
                address=address,
                sensor_config=sensor_config,
            )
            if sensor:
                self._dallas_sensors.append(sensor)
                self._temp_sensors.append(sensor)

    def _configure_ds2482(self, address: int = DS2482_ADDRESS) -> OneWireBus:
        """Configure DS2482 I2C-to-1Wire bridge.
        
        Args:
            address: I2C address of DS2482
            
        Returns:
            OneWireBus instance
        """
        ds2482 = DS2482Bridge(i2c=self._manager._i2cbusio, address=address)
        return OneWireBus(ds2482=ds2482)

    def _find_onewire_devices(
        self,
        ow_bus: OneWireBus,
        bus_id: str,
        bus_type: str,
    ) -> dict[str, str]:
        """Scan for 1-Wire devices on bus.
        
        Args:
            ow_bus: OneWire bus instance
            bus_id: Bus identifier
            bus_type: Type of bus (DS2482 or DALLAS)
            
        Returns:
            Dictionary mapping device addresses to bus IDs
        """
        out = {}
        try:
            devices = ow_bus.scan()
            for device in devices:
                _addr = device.hw_id
                _LOGGER.debug(
                    "Found device on bus %s with address %s", bus_id, _addr
                )
                out[_addr] = bus_id
        except RuntimeError as err:
            _LOGGER.error("Problem with scanning %s bus: %s", bus_type, err)
        return out

    def _find_dallas_gpio_devices(self, bus_id: str) -> dict[str, str]:
        """Scan for Dallas sensors using Linux kernel w1 subsystem.
        
        Uses w1thermsensor library which interfaces with the kernel's
        1-Wire driver (w1-gpio, w1-therm modules).
        
        Args:
            bus_id: Bus identifier
            
        Returns:
            Dictionary mapping device addresses to bus IDs
        """
        out: dict[str, str] = {}
        try:
            from w1thermsensor import W1ThermSensor
            from w1thermsensor.errors import KernelModuleLoadError
            
            try:
                sensors = W1ThermSensor.get_available_sensors()
                for sensor in sensors:
                    # W1ThermSensor uses hw_id format like "0215c2c917ff"
                    _addr = sensor.id
                    _LOGGER.debug(
                        "Found Dallas GPIO device on bus %s with address %s", 
                        bus_id, _addr
                    )
                    out[_addr] = bus_id
            except KernelModuleLoadError as err:
                _LOGGER.error("Can't load kernel module for Dallas sensors: %s", err)
        except ImportError as err:
            _LOGGER.error("w1thermsensor not installed: %s", err)
        except Exception as err:
            _LOGGER.error("Problem scanning Dallas GPIO bus: %s", err)
        return out

    def _create_dallas_sensor(
        self,
        address: str,
        sensor_config: dict,
    ) -> DallasSensor | None:
        """Create Dallas temperature sensor instance.
        
        Args:
            address: Device address
            sensor_config: Sensor configuration dict
            
        Returns:
            DallasSensor instance or None
        """
        # Use name from config, fallback to id, then address
        display_name = sensor_config.get("name") or sensor_config.get(ID) or address
        sensor_id = sensor_config.get(ID) or address
        sensor_id = sensor_id.replace(" ", "_").replace("-", "_")
        
        try:
            sensor = DallasSensor(
                manager=self._manager,
                message_bus=self._manager._message_bus,
                topic_prefix=self._manager._topic_prefix,
                address=address,
                id=sensor_id,
                name=display_name,
                update_interval=sensor_config.get(UPDATE_INTERVAL, TimePeriod(seconds=60)),
                filters=sensor_config.get(FILTERS, []),
            )
            if sensor_config.get(SHOW_HA, True):
                self._manager.send_ha_autodiscovery(
                    id=sensor.id,
                    name=sensor.name,
                    ha_type=SENSOR,
                    availability_msg_func=ha_sensor_temp_availabilty_message,
                    unit_of_measurement=sensor_config.get("unit_of_measurement", "°C"),
                    area=sensor_config.get("area"),
                )
            return sensor
        except Exception as err:
            _LOGGER.error("Failed to create Dallas sensor %s: %s", address, err)
            return None

    # -------------------------------------------------------------------------
    # ADC Analog Sensors
    # -------------------------------------------------------------------------
    
    def _configure_adc(self, adc_list: list[dict] | None) -> None:
        """Configure ADC analog sensors.
        
        Args:
            adc_list: List of ADC sensor configurations
        """
        if not adc_list:
            return
        
        from boneio.hardware.analog import initialize_adc
        
        initialize_adc()
        
        for gpio in adc_list:
            sensor = self._create_adc_sensor(gpio)
            if sensor:
                self._adc_sensors.append(sensor)

    def _create_adc_sensor(self, gpio: dict):
        """Create ADC sensor instance.
        
        Args:
            gpio: GPIO configuration dictionary
            
        Returns:
            ADC sensor instance or None on error
        """
        from boneio.hardware.analog import GpioADCSensor
        
        name = gpio.get(ID)
        if not name:
            return None
            
        id = name.replace(" ", "")
        pin = gpio[PIN]
        
        try:
            sensor = GpioADCSensor(
                id=id,
                pin=pin,
                name=name,
                manager=self._manager,
                message_bus=self._manager._message_bus,
                topic_prefix=self._manager._topic_prefix,
                update_interval=gpio.get(UPDATE_INTERVAL, TimePeriod(seconds=60)),
                filters=gpio.get(FILTERS, []),
            )
            if gpio.get(SHOW_HA, True):
                self._manager.send_ha_autodiscovery(
                    id=id,
                    name=name,
                    ha_type=SENSOR,
                    availability_msg_func=ha_adc_sensor_availabilty_message,
                )
            return sensor
        except I2CError as err:
            _LOGGER.error("Can't configure ADC sensor %s: %s", id, err)
            return None

    # -------------------------------------------------------------------------
    # Getters
    # -------------------------------------------------------------------------
    
    def get_temp_sensor(self, id: str) -> "PCT2075 | MCP9808 | DallasSensor | None":
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

    def get_all_temp_sensors(self) -> list:
        """Get all temperature sensors.
        
        Returns:
            List of temperature sensors
        """
        return self._temp_sensors

    def get_dallas_sensors(self) -> list:
        """Get all Dallas sensors.
        
        Returns:
            List of Dallas sensors
        """
        return self._dallas_sensors

    async def reload_dallas_sensors(self) -> None:
        """Reload Dallas sensor configuration from file.
        
        This handles:
        - Adding new sensors
        - Removing deleted sensors
        - Updating existing sensor configurations
        """
        from boneio.const import SENSOR as SENSOR_SECTION
        
        _LOGGER.info("Reloading Dallas sensors configuration")
        
        # Get fresh config
        config = self._manager._config_helper.reload_config()
        new_sensors_config = config.get(SENSOR_SECTION, [])
        ds2482_config = config.get(DS2482, [])
        
        # Get current sensor addresses
        current_addresses = {s._address for s in self._dallas_sensors}
        new_addresses = {s.get("address") for s in new_sensors_config if s.get("address")}
        
        # Find sensors to add and remove
        to_add = new_addresses - current_addresses
        to_remove = current_addresses - new_addresses
        
        _LOGGER.debug("Dallas sensors - current: %s, new: %s", current_addresses, new_addresses)
        _LOGGER.debug("Dallas sensors - to_add: %s, to_remove: %s", to_add, to_remove)
        
        # Remove deleted sensors
        for address in to_remove:
            for sensor in self._dallas_sensors[:]:
                if sensor._address == address:
                    _LOGGER.info("Removing Dallas sensor: %s", address)
                    # Remove HA autodiscovery
                    self._manager._config_helper.remove_autodiscovery_msg(SENSOR, sensor.id)
                    # Remove from lists
                    self._dallas_sensors.remove(sensor)
                    if sensor in self._temp_sensors:
                        self._temp_sensors.remove(sensor)
        
        # Add new sensors
        for sensor_config in new_sensors_config:
            address = sensor_config.get("address")
            if address and address in to_add:
                _LOGGER.info("Adding new Dallas sensor: %s", address)
                sensor = self._create_dallas_sensor(
                    address=address,
                    sensor_config=sensor_config,
                )
                if sensor:
                    self._dallas_sensors.append(sensor)
                    self._temp_sensors.append(sensor)
        
        # Update existing sensors (name, area, update_interval)
        for sensor_config in new_sensors_config:
            address = sensor_config.get("address")
            if address and address not in to_add and address not in to_remove:
                for sensor in self._dallas_sensors:
                    if sensor._address == address:
                        # Update sensor properties
                        new_name = sensor_config.get("name") or sensor_config.get(ID) or address
                        if sensor.name != new_name:
                            _LOGGER.debug("Updating Dallas sensor %s name: %s -> %s", address, sensor.name, new_name)
                            sensor._name = new_name
                        
                        # Update interval
                        new_interval = sensor_config.get(UPDATE_INTERVAL)
                        if new_interval:
                            sensor._update_interval = new_interval
                        
                        # Resend HA autodiscovery with updated info
                        if sensor_config.get(SHOW_HA, True):
                            self._manager.send_ha_autodiscovery(
                                id=sensor.id,
                                name=sensor.name,
                                ha_type=SENSOR,
                                availability_msg_func=ha_sensor_temp_availabilty_message,
                                unit_of_measurement=sensor_config.get("unit_of_measurement", "°C"),
                                area=sensor_config.get("area"),
                            )
                        break
        
        _LOGGER.info("Dallas sensors reload complete. Total: %d", len(self._dallas_sensors))

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

    def get_system_sensors(self) -> list:
        """Get all system sensors (disk, memory, CPU).
        
        Returns:
            List of system sensors
        """
        return self._system_sensors

    # -------------------------------------------------------------------------
    # System Sensors (Disk, Memory, CPU)
    # -------------------------------------------------------------------------
    
    def _configure_system_sensors(self) -> None:
        """Configure system monitoring sensors (disk, memory, CPU).
        
        Creates sensors for monitoring system resources and sends
        HA autodiscovery messages for each.
        """
        from boneio.core.sensor.system import (
            CpuUsageSensor,
            DiskUsageSensor,
            MemoryUsageSensor,
        )
        from boneio.integration.homeassistant import ha_sensor_system_availabilty_message
        
        # Disk Usage Sensor
        disk_sensor = DiskUsageSensor(
            manager=self._manager,
            message_bus=self._manager._message_bus,
            topic_prefix=self._manager._topic_prefix,
        )
        self._system_sensors.append(disk_sensor)
        self._manager.send_ha_autodiscovery(
            id=disk_sensor.id,
            name=disk_sensor.name,
            ha_type=SENSOR,
            availability_msg_func=ha_sensor_system_availabilty_message,
            unit_of_measurement="%",
            icon="mdi:harddisk",
        )
        
        # Memory Usage Sensor
        memory_sensor = MemoryUsageSensor(
            manager=self._manager,
            message_bus=self._manager._message_bus,
            topic_prefix=self._manager._topic_prefix,
        )
        self._system_sensors.append(memory_sensor)
        self._manager.send_ha_autodiscovery(
            id=memory_sensor.id,
            name=memory_sensor.name,
            ha_type=SENSOR,
            availability_msg_func=ha_sensor_system_availabilty_message,
            unit_of_measurement="%",
            icon="mdi:memory",
        )
        
        # CPU Usage Sensor
        cpu_sensor = CpuUsageSensor(
            manager=self._manager,
            message_bus=self._manager._message_bus,
            topic_prefix=self._manager._topic_prefix,
        )
        self._system_sensors.append(cpu_sensor)
        self._manager.send_ha_autodiscovery(
            id=cpu_sensor.id,
            name=cpu_sensor.name,
            ha_type=SENSOR,
            availability_msg_func=ha_sensor_system_availabilty_message,
            unit_of_measurement="%",
            icon="mdi:cpu-64-bit",
        )
        
        _LOGGER.info(
            "Configured %d system sensors: %s",
            len(self._system_sensors),
            [s.id for s in self._system_sensors]
        )

    async def send_ha_autodiscovery(self) -> None:
        """Send Home Assistant autodiscovery for all sensors.
        
        Note: Most sensors send their autodiscovery during initialization.
        This method can be used to resend all autodiscovery messages.
        """
        # Sensors typically send autodiscovery during configuration
        # This is a placeholder for any sensors that need manual resend
        pass
