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
            "SensorManager initialized with %d temp sensors, %d INA219, %d ADC, %d Dallas",
            len(self._temp_sensors),
            len(self._ina219_sensors),
            len(self._adc_sensors),
            len(self._dallas_sensors)
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
            for _single_ds in ds2482:
                _LOGGER.debug("Preparing DS2482 bus at address %s", _single_ds[ADDRESS])
                
                try:
                    ow_bus = self._configure_ds2482(address=_single_ds[ADDRESS])
                    _ds_onewire_bus[_single_ds[ID]] = ow_bus
                    _one_wire_devices.update(
                        self._find_onewire_devices(
                            ow_bus=ow_bus,
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
                _one_wire_devices.update(
                    self._find_dallas_gpio_devices(
                        bus_id=dallas[ID],
                    )
                )
            except Exception as err:
                _LOGGER.error("Failed to configure Dallas GPIO bus: %s", err)
        
        # Create Dallas sensor instances
        if sensors and _one_wire_devices:
            for address in _one_wire_devices.keys():
                _LOGGER.debug("Configuring Dallas sensor %s for boneIO", address)
                sensor = self._create_dallas_sensor(
                    address=address,
                    sensors_config=sensors,
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
        sensors_config: list,
    ) -> DallasSensor | None:
        """Create Dallas temperature sensor instance.
        
        Args:
            address: Device address
            sensors_config: List of sensor configurations
            
        Returns:
            DallasSensor instance or None
        """
        # Find config for this address
        config = {}
        for sensor_cfg in sensors_config:
            if sensor_cfg.get(ADDRESS) == address or sensor_cfg.get(ID) == address:
                config = sensor_cfg
                break
        
        name = config.get(ID) or address
        id = name.replace(" ", "")
        
        try:
            sensor = DallasSensor(
                manager=self._manager,
                message_bus=self._manager._message_bus,
                topic_prefix=self._manager._topic_prefix,
                address=address,
                id=id,
                name=name,
                update_interval=config.get(UPDATE_INTERVAL, TimePeriod(seconds=60)),
                filters=config.get(FILTERS, []),
            )
            if config.get(SHOW_HA, True):
                self._manager.send_ha_autodiscovery(
                    id=sensor.id,
                    name=sensor.name,
                    ha_type=SENSOR,
                    availability_msg_func=ha_sensor_temp_availabilty_message,
                    unit_of_measurement=config.get("unit_of_measurement", "°C"),
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

    async def send_ha_autodiscovery(self) -> None:
        """Send Home Assistant autodiscovery for all sensors.
        
        Note: Most sensors send their autodiscovery during initialization.
        This method can be used to resend all autodiscovery messages.
        """
        # Sensors typically send autodiscovery during configuration
        # This is a placeholder for any sensors that need manual resend
        pass
