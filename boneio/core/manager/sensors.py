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
    ON,
    ONEWIRE,
    PIN,
    SENSOR,
    SHOW_HA,
    UPDATE_INTERVAL,
    VIRTUAL_ENERGY_SENSOR,
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
    from boneio.components.sensor import VirtualEnergySensor
    from boneio.models.events import OutputEvent

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
        self._virtual_energy_sensors = []
        self._virtual_energy_sensor_configs = sensors.get(VIRTUAL_ENERGY_SENSOR, [])
        
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
        # Note: virtual_energy_sensors are configured after outputs are ready
        
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

    def get_virtual_energy_sensors(self) -> list["VirtualEnergySensor"]:
        """Get all virtual energy sensors.
        
        Returns:
            List of VirtualEnergySensor instances
        """
        return self._virtual_energy_sensors

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
                    # Remove HA autodiscovery - find all topics for this sensor
                    matching_topics = self._manager._config_helper.get_autodiscovery_topics_for_id(sensor.id)
                    for ha_type, topic in matching_topics:
                        _LOGGER.debug("Removing HA Discovery for sensor %s: %s", sensor.id, topic)
                        # Send empty/null payload to remove from HA (HA requires zero-length retained message)
                        self._manager.send_message(topic=topic, payload=None, retain=True)
                        # Remove from internal cache
                        self._manager._config_helper.remove_autodiscovery_msg(ha_type, topic)
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
        
        # Broadcast updated states to WebSocket clients
        await self._broadcast_all_sensor_states()

    async def _broadcast_all_sensor_states(self) -> None:
        """Broadcast current state of all sensors via WebSocket.
        
        This is called after reload to ensure frontend receives
        the updated sensor list immediately.
        """
        import time
        timestamp = time.time()
        
        # Update all Dallas sensors
        for sensor in self._dallas_sensors:
            try:
                await sensor.async_update(timestamp)
            except Exception as e:
                _LOGGER.debug("Error broadcasting sensor state %s: %s", sensor.id, e)
        
        # Update all I2C temperature sensors
        for sensor in self._temp_sensors:
            if sensor not in self._dallas_sensors:  # Avoid duplicates
                try:
                    await sensor.async_update(timestamp)
                except Exception as e:
                    _LOGGER.debug("Error broadcasting sensor state %s: %s", sensor.id, e)

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

    def configure_virtual_energy_sensors(self) -> None:
        """Configure virtual energy sensors after outputs are initialized.
        
        This must be called after OutputsManager has configured all outputs,
        as virtual energy sensors need references to output objects.
        """
        from boneio.components.sensor import VirtualEnergySensor
        from boneio.integration.homeassistant import ha_virtual_energy_sensor_availabilty_message
        from boneio.core.utils.util import sanitize_string
        
        # Track used IDs to detect duplicates
        used_ids: set[str] = set()
        
        for config in self._virtual_energy_sensor_configs:
            name = config.get("name")
            output_id = config.get("output_id")
            sensor_type = config.get("sensor_type")
            
            if not name or not output_id or not sensor_type:
                _LOGGER.error(
                    "Invalid virtual_energy_sensor config: name=%s, output_id=%s, sensor_type=%s",
                    name, output_id, sensor_type
                )
                continue
            
            # Get the output reference
            output = self._manager.outputs.get_output(output_id)
            if not output:
                _LOGGER.error(
                    "Output '%s' not found for virtual_energy_sensor '%s'",
                    output_id, name
                )
                continue
            
            # Generate ID if not provided
            sensor_id = config.get("id") or sanitize_string(name)
            
            # Check for duplicate IDs
            if sensor_id in used_ids:
                _LOGGER.error(
                    "Duplicate virtual_energy_sensor ID '%s' (from name '%s'). Skipping.",
                    sensor_id, name
                )
                continue
            used_ids.add(sensor_id)
            
            area = config.get("area")
            
            # Get power_usage or flow_rate based on sensor_type
            power_usage = config.get("power_usage") if sensor_type == "power" else None
            flow_rate = config.get("flow_rate") if sensor_type == "water" else None
            
            if sensor_type == "power" and power_usage is None:
                _LOGGER.error(
                    "power_usage required for sensor_type='power' in virtual_energy_sensor '%s'",
                    name
                )
                continue
            if sensor_type == "water" and flow_rate is None:
                _LOGGER.error(
                    "flow_rate required for sensor_type='water' in virtual_energy_sensor '%s'",
                    name
                )
                continue
            
            # Create the sensor
            sensor = VirtualEnergySensor(
                id=sensor_id,
                name=name,
                output=output,
                message_bus=self._manager._message_bus,
                event_bus=self._manager._event_bus,
                loop=self._manager.loop,
                topic_prefix=self._manager._topic_prefix,
                sensor_type=sensor_type,
                power_usage=power_usage,
                flow_rate=flow_rate,
                area=area,
            )
            self._virtual_energy_sensors.append(sensor)
            
            # Register event listener to track output state changes
            self._manager._event_bus.add_event_listener(
                event_type="output",
                entity_id=output_id,
                listener_id=f"virtual_energy_{sensor_id}",
                target=lambda event, s=sensor: self._on_output_state_change(event, s),
            )
            
            # Send HA autodiscovery
            if sensor_type == "power":
                # Power sensor (W)
                self._manager.send_ha_autodiscovery(
                    id=f"{sensor_id}_power",
                    name=f"{name} Power",
                    ha_type=SENSOR,
                    availability_msg_func=ha_virtual_energy_sensor_availabilty_message,
                    unit_of_measurement="W",
                    device_class="power",
                    state_class="measurement",
                    area=area,
                )
                # Energy sensor (Wh)
                self._manager.send_ha_autodiscovery(
                    id=f"{sensor_id}_energy",
                    name=f"{name} Energy",
                    ha_type=SENSOR,
                    availability_msg_func=ha_virtual_energy_sensor_availabilty_message,
                    unit_of_measurement="Wh",
                    device_class="energy",
                    state_class="total_increasing",
                    area=area,
                )
            elif sensor_type == "water":
                # Flow rate sensor (L/h)
                self._manager.send_ha_autodiscovery(
                    id=f"{sensor_id}_flow",
                    name=f"{name} Flow Rate",
                    ha_type=SENSOR,
                    availability_msg_func=ha_virtual_energy_sensor_availabilty_message,
                    unit_of_measurement="L/h",
                    device_class="volume_flow_rate",
                    state_class="measurement",
                    area=area,
                )
                # Water consumption sensor (L)
                self._manager.send_ha_autodiscovery(
                    id=f"{sensor_id}_water",
                    name=f"{name} Water",
                    ha_type=SENSOR,
                    availability_msg_func=ha_virtual_energy_sensor_availabilty_message,
                    unit_of_measurement="L",
                    device_class="water",
                    state_class="total_increasing",
                    area=area,
                )
            
            # Start tracking if output is already ON
            if output.state == ON:
                sensor.start_tracking()
            
            _LOGGER.info(
                "Configured virtual_energy_sensor: id=%s, name=%s, output=%s, type=%s",
                sensor_id, name, output_id, sensor_type
            )
        
        if self._virtual_energy_sensors:
            _LOGGER.info(
                "Configured %d virtual energy sensors",
                len(self._virtual_energy_sensors)
            )

    def _on_output_state_change(self, event: "OutputEvent", sensor: "VirtualEnergySensor") -> None:
        """Handle output state change for virtual energy sensor."""
        from boneio.const import ON
        
        if not event:
            return
        
        output_state = getattr(event, 'state', None)
        if not output_state:
            return
        
        state_value = getattr(output_state, 'state', None)
        if state_value == ON:
            sensor.start_tracking()
        else:
            sensor.stop_tracking()

    async def reload_virtual_energy_sensors(self) -> None:
        """Reload virtual energy sensor configuration from file.
        
        This handles:
        - Adding new sensors
        - Removing deleted sensors
        - Updating existing sensor configurations
        """
        from boneio.components.sensor import VirtualEnergySensor
        from boneio.integration.homeassistant import ha_virtual_energy_sensor_availabilty_message
        from boneio.core.utils.util import sanitize_string
        
        _LOGGER.info("Reloading virtual energy sensors configuration")
        
        # Get fresh config - virtual_energy_sensor is a top-level section
        config = self._manager._config_helper.reload_config()
        new_configs = config.get(VIRTUAL_ENERGY_SENSOR, [])
        
        # Get current and new sensor IDs, detecting duplicates
        current_ids = {s.id for s in self._virtual_energy_sensors}
        new_ids = set()
        duplicate_ids = set()
        for cfg in new_configs:
            sensor_id = cfg.get("id") or sanitize_string(cfg.get("name", ""))
            if sensor_id:
                if sensor_id in new_ids:
                    duplicate_ids.add(sensor_id)
                    _LOGGER.error(
                        "Duplicate virtual_energy_sensor ID '%s' detected. Only first occurrence will be used.",
                        sensor_id
                    )
                else:
                    new_ids.add(sensor_id)
        
        _LOGGER.debug("Virtual energy sensors - current: %s, new: %s, duplicates: %s", current_ids, new_ids, duplicate_ids)
        
        # Find sensors to add and remove
        to_add = new_ids - current_ids
        to_remove = current_ids - new_ids
        
        # Remove deleted sensors
        for sensor_id in to_remove:
            for sensor in self._virtual_energy_sensors[:]:
                if sensor.id == sensor_id:
                    _LOGGER.info("Removing virtual energy sensor: %s", sensor_id)
                    
                    # Stop tracking
                    sensor.stop_tracking()
                    
                    # Remove event listener
                    self._manager._event_bus.remove_event_listener(
                        event_type="output",
                        listener_id=f"virtual_energy_{sensor_id}",
                    )
                    
                    # Remove HA autodiscovery for both power/energy or flow/water sensors
                    for suffix in ["_power", "_energy", "_flow", "_water"]:
                        full_id = f"{sensor_id}{suffix}"
                        matching_topics = self._manager._config_helper.get_autodiscovery_topics_for_id(full_id)
                        for ha_type, topic in matching_topics:
                            _LOGGER.debug("Removing HA Discovery for sensor %s: %s", full_id, topic)
                            self._manager.send_message(topic=topic, payload=None, retain=True)
                            self._manager._config_helper.remove_autodiscovery_msg(ha_type, topic)
                    
                    # Remove from list
                    self._virtual_energy_sensors.remove(sensor)
        
        # Add new sensors (skip duplicates - only first occurrence is used)
        added_ids = set()
        for cfg in new_configs:
            sensor_id = cfg.get("id") or sanitize_string(cfg.get("name", ""))
            if sensor_id and sensor_id in to_add and sensor_id not in added_ids and sensor_id not in duplicate_ids:
                _LOGGER.info("Adding new virtual energy sensor: %s", sensor_id)
                self._create_virtual_energy_sensor(cfg)
                added_ids.add(sensor_id)
        
        # Update existing sensors
        for cfg in new_configs:
            sensor_id = cfg.get("id") or sanitize_string(cfg.get("name", ""))
            if sensor_id and sensor_id not in to_add and sensor_id not in to_remove:
                for sensor in self._virtual_energy_sensors:
                    if sensor.id == sensor_id:
                        # Update sensor properties
                        new_name = cfg.get("name")
                        if new_name and sensor.name != new_name:
                            _LOGGER.debug("Updating virtual energy sensor %s name: %s -> %s", sensor_id, sensor.name, new_name)
                            sensor._name = new_name
                        
                        # Update power_usage or flow_rate
                        sensor_type = cfg.get("sensor_type")
                        if sensor_type == "power":
                            new_power = cfg.get("power_usage")
                            if new_power and sensor._power_usage != new_power:
                                sensor._power_usage = new_power
                        elif sensor_type == "water":
                            new_flow = cfg.get("flow_rate")
                            if new_flow and sensor._flow_rate != new_flow:
                                sensor._flow_rate = new_flow
                        
                        # Resend HA autodiscovery with updated info
                        area = cfg.get("area")
                        if sensor_type == "power":
                            self._manager.send_ha_autodiscovery(
                                id=f"{sensor_id}_power",
                                name=f"{new_name} Power",
                                ha_type=SENSOR,
                                availability_msg_func=ha_virtual_energy_sensor_availabilty_message,
                                unit_of_measurement="W",
                                device_class="power",
                                state_class="measurement",
                                area=area,
                            )
                            self._manager.send_ha_autodiscovery(
                                id=f"{sensor_id}_energy",
                                name=f"{new_name} Energy",
                                ha_type=SENSOR,
                                availability_msg_func=ha_virtual_energy_sensor_availabilty_message,
                                unit_of_measurement="Wh",
                                device_class="energy",
                                state_class="total_increasing",
                                area=area,
                            )
                        elif sensor_type == "water":
                            self._manager.send_ha_autodiscovery(
                                id=f"{sensor_id}_flow",
                                name=f"{new_name} Flow Rate",
                                ha_type=SENSOR,
                                availability_msg_func=ha_virtual_energy_sensor_availabilty_message,
                                unit_of_measurement="L/h",
                                device_class="volume_flow_rate",
                                state_class="measurement",
                                area=area,
                            )
                            self._manager.send_ha_autodiscovery(
                                id=f"{sensor_id}_water",
                                name=f"{new_name} Water",
                                ha_type=SENSOR,
                                availability_msg_func=ha_virtual_energy_sensor_availabilty_message,
                                unit_of_measurement="L",
                                device_class="water",
                                state_class="total_increasing",
                                area=area,
                            )
                        break
        
        # Update internal config cache
        self._virtual_energy_sensor_configs = new_configs
        
        _LOGGER.info("Virtual energy sensors reload complete. Total: %d", len(self._virtual_energy_sensors))
        
        # Broadcast updated states
        await self._broadcast_virtual_energy_states()

    def _create_virtual_energy_sensor(self, config: dict) -> None:
        """Create a single virtual energy sensor from config.
        
        Args:
            config: Sensor configuration dictionary
        """
        from boneio.components.sensor import VirtualEnergySensor
        from boneio.integration.homeassistant import ha_virtual_energy_sensor_availabilty_message
        from boneio.core.utils.util import sanitize_string
        
        name = config.get("name")
        output_id = config.get("output_id")
        sensor_type = config.get("sensor_type")
        
        if not name or not output_id or not sensor_type:
            _LOGGER.error(
                "Invalid virtual_energy_sensor config: name=%s, output_id=%s, sensor_type=%s",
                name, output_id, sensor_type
            )
            return
        
        # Get the output reference
        output = self._manager.outputs.get_output(output_id)
        if not output:
            _LOGGER.error(
                "Output '%s' not found for virtual_energy_sensor '%s'",
                output_id, name
            )
            return
        
        # Generate ID if not provided
        sensor_id = config.get("id") or sanitize_string(name)
        area = config.get("area")
        
        # Get power_usage or flow_rate based on sensor_type
        power_usage = config.get("power_usage") if sensor_type == "power" else None
        flow_rate = config.get("flow_rate") if sensor_type == "water" else None
        
        if sensor_type == "power" and power_usage is None:
            _LOGGER.error(
                "power_usage required for sensor_type='power' in virtual_energy_sensor '%s'",
                name
            )
            return
        if sensor_type == "water" and flow_rate is None:
            _LOGGER.error(
                "flow_rate required for sensor_type='water' in virtual_energy_sensor '%s'",
                name
            )
            return
        
        # Create the sensor
        sensor = VirtualEnergySensor(
            id=sensor_id,
            name=name,
            output=output,
            message_bus=self._manager._message_bus,
            event_bus=self._manager._event_bus,
            loop=self._manager.loop,
            topic_prefix=self._manager._topic_prefix,
            sensor_type=sensor_type,
            power_usage=power_usage,
            flow_rate=flow_rate,
            area=area,
        )
        self._virtual_energy_sensors.append(sensor)
        
        # Register event listener to track output state changes
        self._manager._event_bus.add_event_listener(
            event_type="output",
            entity_id=output_id,
            listener_id=f"virtual_energy_{sensor_id}",
            target=lambda event, s=sensor: self._on_output_state_change(event, s),
        )
        
        # Send HA autodiscovery
        if sensor_type == "power":
            self._manager.send_ha_autodiscovery(
                id=f"{sensor_id}_power",
                name=f"{name} Power",
                ha_type=SENSOR,
                availability_msg_func=ha_virtual_energy_sensor_availabilty_message,
                unit_of_measurement="W",
                device_class="power",
                state_class="measurement",
                area=area,
            )
            self._manager.send_ha_autodiscovery(
                id=f"{sensor_id}_energy",
                name=f"{name} Energy",
                ha_type=SENSOR,
                availability_msg_func=ha_virtual_energy_sensor_availabilty_message,
                unit_of_measurement="Wh",
                device_class="energy",
                state_class="total_increasing",
                area=area,
            )
        elif sensor_type == "water":
            self._manager.send_ha_autodiscovery(
                id=f"{sensor_id}_flow",
                name=f"{name} Flow Rate",
                ha_type=SENSOR,
                availability_msg_func=ha_virtual_energy_sensor_availabilty_message,
                unit_of_measurement="L/h",
                device_class="volume_flow_rate",
                state_class="measurement",
                area=area,
            )
            self._manager.send_ha_autodiscovery(
                id=f"{sensor_id}_water",
                name=f"{name} Water",
                ha_type=SENSOR,
                availability_msg_func=ha_virtual_energy_sensor_availabilty_message,
                unit_of_measurement="L",
                device_class="water",
                state_class="total_increasing",
                area=area,
            )
        
        # Start tracking if output is already ON
        if output.state == ON:
            sensor.start_tracking()
        
        _LOGGER.info(
            "Configured virtual_energy_sensor: id=%s, name=%s, output=%s, type=%s",
            sensor_id, name, output_id, sensor_type
        )

    async def _broadcast_virtual_energy_states(self) -> None:
        """Broadcast current state of all virtual energy sensors via WebSocket."""
        for sensor in self._virtual_energy_sensors:
            try:
                sensor._send_state()
            except Exception as e:
                _LOGGER.debug("Error broadcasting virtual energy sensor state %s: %s", sensor.id, e)

    async def send_ha_autodiscovery(self) -> None:
        """Send Home Assistant autodiscovery for all sensors.
        
        Note: Most sensors send their autodiscovery during initialization.
        This method can be used to resend all autodiscovery messages.
        """
        # Sensors typically send autodiscovery during configuration
        # This is a placeholder for any sensors that need manual resend
        pass
