from __future__ import annotations

import logging
import time
from collections import namedtuple
from typing import TYPE_CHECKING, Any
from collections.abc import Callable

from adafruit_mcp230xx.mcp23017 import MCP23017
from adafruit_pca9685 import PCA9685

from boneio.const import (
    ADDRESS,
    BINARY_SENSOR,
    COVER,
    DEVICE_CLASS,
    EVENT_ENTITY,
    FILTERS,
    GPIO,
    ID,
    INIT_SLEEP,
    INPUT,
    INPUT_SENSOR,
    KIND,
    LM75,
    MCP,
    MCP_ID,
    MCP_TEMP_9808,
    MODEL,
    NONE,
    OUTPUT_TYPE,
    PCA,
    PCA_ID,
    PCF,
    PCF_ID,
    PIN,
    RELAY,
    RESTORE_STATE,
    SENSOR,
    SHOW_HA,
    UPDATE_INTERVAL,
    DallasBusTypes,
    ExpanderTypes,
)
from boneio.cover import PreviousCover, TimeBasedCover, VenetianCover
from boneio.group import OutputGroup
from boneio.helper import (
    CoverConfigurationException,
    GPIOInputException,
    GPIOOutputException,
    I2CError,
    ha_adc_sensor_availabilty_message,
    ha_binary_sensor_availabilty_message,
    ha_event_availabilty_message,
    ha_sensor_ina_availabilty_message,
    ha_sensor_temp_availabilty_message,
)
from boneio.core.state import StateManager
from boneio.core.events import EventBus
from boneio.helper.ha_discovery import (
    ha_cover_availabilty_message,
    ha_cover_with_tilt_availabilty_message,
    ha_sensor_availabilty_message,
    ha_virtual_energy_sensor_discovery_message,
)
from boneio.helper.onewire import (
    DS2482,
    DS2482_ADDRESS,
    OneWireBus,
)
from boneio.helper.pcf8575 import PCF8575
from boneio.core.utils import TimePeriod
from boneio.input import GpioEventButton, GpioInputBinarySensor
from boneio.core.messaging.basic import MessageBus
from boneio.modbus.coordinator import ModbusCoordinator
from boneio.sensor.temp.dallas import DallasSensor
from boneio.sensor.serial_number import SerialNumberSensor
from w1thermsensor import W1ThermSensor

# Typing imports that create a circular dependency
if TYPE_CHECKING:
    from ..manager import Manager

# Use smbus2 wrapper for Python 3.13+ on Debian 13
from boneio.helper.i2c_wrapper import SMBus2I2CWrapper as I2C

from boneio.relay import PWMPCA, GpioRelay, MCPRelay, PCFRelay
from boneio.sensor import GpioADCSensor, initialize_adc

_LOGGER = logging.getLogger(__name__)


def create_adc(manager: Manager, message_bus: MessageBus, topic_prefix: str, adc_list: list = []):
    """Create ADC sensor."""

    initialize_adc()

    # TODO: find what exception can ADC gpio throw.
    for gpio in adc_list:
        name = gpio.get(ID)
        id = name.replace(" ", "")
        pin = gpio[PIN]
        try:
            GpioADCSensor(
                id=id,
                pin=pin,
                name=name,
                manager=manager,
                message_bus=message_bus,
                topic_prefix=topic_prefix,
                update_interval=gpio.get(
                    UPDATE_INTERVAL, TimePeriod(seconds=60)
                ),
                filters=gpio.get(FILTERS, []),
            )
            if gpio.get(SHOW_HA, True):
                manager.send_ha_autodiscovery(
                    id=id,
                    name=name,
                    ha_type=SENSOR,
                    availability_msg_func=ha_adc_sensor_availabilty_message,
                )
        except I2CError as err:
            _LOGGER.error("Can't configure ADC sensor %s. %s", id, err)
            pass


def create_temp_sensor(
    manager: Manager,
    message_bus: MessageBus,
    topic_prefix: str,
    sensor_type: str,
    i2cbusio: I2C,
    config: dict = {},
):
    """Create LM sensor in manager."""
    if sensor_type == LM75:
        from boneio.sensor import LM75Sensor as TempSensor
    elif sensor_type == MCP_TEMP_9808:
        from boneio.sensor import MCP9808Sensor as TempSensor
    else:
        return
    name = config.get(ID)
    if not name:
        return
    id = name.replace(" ", "")
    try:
        temp_sensor = TempSensor(
            id=id,
            name=name,
            i2c=i2cbusio,
            address=config[ADDRESS],
            manager=manager,
            message_bus=message_bus,
            topic_prefix=topic_prefix,
            update_interval=config.get(UPDATE_INTERVAL, TimePeriod(seconds=60)),
            filters=config.get(FILTERS, []),
            unit_of_measurement=config.get("unit_of_measurement", "°C"),
        )
        manager.send_ha_autodiscovery(
            id=id,
            name=name,
            ha_type=SENSOR,
            availability_msg_func=ha_sensor_temp_availabilty_message,
            unit_of_measurement=temp_sensor.unit_of_measurement,
        )
        return temp_sensor
    except I2CError as err:
        _LOGGER.error("Can't configure Temp sensor. %s", err)
        pass


def create_serial_number_sensor(
    manager: Manager,
    message_bus: MessageBus,
    topic_prefix: str,
):
    """Create Serial number sensor in manager."""
    sensor = SerialNumberSensor(
        id="serial_number",
        name="Serial number",
        manager=manager,
        message_bus=message_bus,
        topic_prefix=topic_prefix,
    )
    manager.send_ha_autodiscovery(
        id="serial_number",
        name="Serial number",
        ha_type=SENSOR,
        entity_category="diagnostic",
        availability_msg_func=ha_sensor_availabilty_message,
    )
    return sensor

expander_class = {MCP: MCP23017, PCA: PCA9685, PCF: PCF8575}


def create_expander(
    expander_dict: dict,
    expander_config: list,
    exp_type: ExpanderTypes,
    i2cbusio: I2C,
) -> dict:
    grouped_outputs = {}
    for expander in expander_config:
        id = expander[ID] or expander[ADDRESS]
        try:
            expander_dict[id] = expander_class[exp_type](
                i2c=i2cbusio, address=expander[ADDRESS], reset=False
            )
            sleep_time = expander.get(INIT_SLEEP, TimePeriod(seconds=0))
            if sleep_time.total_seconds > 0:
                _LOGGER.debug(
                    f"Sleeping for {sleep_time.total_seconds}s while {exp_type} {id} is initializing."
                )
                time.sleep(sleep_time.total_seconds)
            else:
                _LOGGER.debug(f"{exp_type} {id} is initializing.")
            grouped_outputs[id] = {}
        except TimeoutError as err:
            _LOGGER.error("Can't connect to %s %s. %s", exp_type, id, err)
            pass
    return grouped_outputs


def create_modbus_coordinators(manager: Manager, message_bus: MessageBus, entries, **kwargs) -> dict[str, ModbusCoordinator]:
    """Create Modbus sensor for each device."""
    
    modbus_coordinators = {}
    for entry in entries:
        name = entry.get(ID)
        id = name.replace(" ", "")
        additional_data = entry.get("data", {})
        try:
            modbus_coordinators[id.lower()] = ModbusCoordinator(
                address=entry[ADDRESS],
                id=id,
                name=name,
                manager=manager,
                model=entry[MODEL],
                message_bus=message_bus,
                update_interval=entry.get(
                    UPDATE_INTERVAL, TimePeriod(seconds=60)
                ),
                sensors_filters=entry.get("sensors_filters", {}),
                additional_data=additional_data,
                **kwargs,
            )
        except FileNotFoundError as err:
            _LOGGER.error(
                "Can't configure Modbus sensor %s. %s. No such model in database.",
                id,
                err,
            )
            pass
    return modbus_coordinators


OutputEntry = namedtuple("OutputEntry", "OutputClass output_kind expander_id")


def output_chooser(output_kind: str, config):
    """Get named tuple based on input."""
    if output_kind == MCP:
        expander_id = config.pop(MCP_ID, None)
        return OutputEntry(MCPRelay, MCP, expander_id)
    elif output_kind == GPIO:
        return OutputEntry(GpioRelay, GPIO, GPIO)
    elif output_kind == PCA:
        expander_id = config.pop(PCA_ID, None)
        return OutputEntry(PWMPCA, PCA, expander_id)
    elif output_kind == PCF:
        expander_id = config.pop(PCF_ID, None)
        return OutputEntry(PCFRelay, PCF, expander_id)
    else:
        raise GPIOOutputException(f"""Output type {output_kind} dont exists""")


def configure_output_group(
    message_bus: MessageBus,
    topic_prefix: str,
    config: dict,
    **kwargs,
) -> Any:
    """Configure kind of relay. Most common MCP."""
    _id = config.pop(ID)

    output = OutputGroup(
        message_bus=message_bus,
        topic_prefix=topic_prefix,
        id=_id,
        callback=lambda: None,
        **config,
        **kwargs,
    )
    return output


def configure_relay(
    manager: Manager,
    message_bus: MessageBus,
    state_manager: StateManager,
    topic_prefix: str,
    relay_id: str,
    name: str,
    config: dict,
    restore_state: bool = False,
    **kwargs,
) -> Any:
    """Configure kind of relay. Most common MCP."""
    output_type = config.pop(OUTPUT_TYPE)
    restored_state = (
        state_manager.get(attr_type=RELAY, attr=relay_id, default_value=False)
        if restore_state
        else False
    )
    if output_type == NONE and state_manager.get(
        attr_type=RELAY, attr=relay_id
    ):
        state_manager.del_attribute(attr_type=RELAY, attribute=relay_id)
        restored_state = False

    output = output_chooser(output_kind=config.pop(KIND), config=config)
    output_kind = getattr(output, "output_kind")
    expander_id = getattr(output, "expander_id")

    if output_kind == MCP:
        mcp = manager.mcp.get(expander_id)
        if not mcp:
            _LOGGER.error("No such MCP configured!")
            return None
        extra_args = {
            "pin": int(config.pop(PIN)),
            "mcp": mcp,
            "mcp_id": expander_id,
            "output_type": output_type,
        }
    elif output_kind == PCA:
        pca = manager.pca.get(expander_id)
        if not pca:
            _LOGGER.error("No such PCA configured!")
            return None
        extra_args = {
            "pin": int(config.pop(PIN)),
            "pca": pca,
            "pca_id": expander_id,
            "output_type": output_type,
        }
    elif output_kind == PCF:
        expander = manager.pcf.get(expander_id)
        if not expander:
            _LOGGER.error("No such PCF configured!")
            return None
        extra_args = {
            "pin": int(config.pop(PIN)),
            "expander": expander,
            "expander_id": expander_id,
            "output_type": output_type,
        }
    elif output_kind == GPIO:
        if GPIO not in manager.grouped_outputs_by_expander:
            manager.grouped_outputs_by_expander[GPIO] = {}
        extra_args = {
            "pin": config.pop(PIN),
        }
    else:
        _LOGGER.error(
            "Output kind: %s is not configured", getattr(output, "output_kind")
        )
        return

    interlock_groups = config.get("interlock_group", [])
    if isinstance(interlock_groups, str):
        interlock_groups = [interlock_groups]

    relay = getattr(output, "OutputClass")(
        message_bus=message_bus,
        topic_prefix=topic_prefix,
        id=relay_id,
        restored_state=restored_state,
        interlock_manager=manager._interlock_manager,
        interlock_groups=interlock_groups,
        name=name,
        **config,
        **kwargs,
        **extra_args,
    )
    manager._interlock_manager.register(relay, interlock_groups)
    manager.grouped_outputs_by_expander[expander_id][relay_id] = relay
    if relay.is_virtual_power:
        manager.send_ha_autodiscovery(
            id=f"{relay_id}_virtual_power",
            relay_id=relay_id,
            name=f"{name} Virtual Power",
            ha_type="sensor",
            device_type="energy",
            availability_msg_func=ha_virtual_energy_sensor_discovery_message,
            unit_of_measurement="W",
            device_class="power",
            state_class="measurement",
            value_template="{{ value_json.power }}"
        )
        manager.send_ha_autodiscovery(
            id=f"{relay_id}_virtual_energy",
            relay_id=relay_id,
            name=f"{name} Virtual Energy",
            ha_type="sensor",
            device_type="energy",
            availability_msg_func=ha_virtual_energy_sensor_discovery_message,
            unit_of_measurement="Wh",
            device_class="energy",
            state_class="total_increasing",
            value_template="{{ value_json.energy }}"
        )
    if relay.is_virtual_volume_flow_rate:
        manager.send_ha_autodiscovery(
            id=f"{relay_id}_virtual_volume_flow_rate",
            relay_id=relay_id,
            name=f"{name} Virtual Volume Flow Rate",
            ha_type="sensor",
            device_type="energy",
            availability_msg_func=ha_virtual_energy_sensor_discovery_message,
            unit_of_measurement="L/h",
            device_class="volume_flow_rate",
            state_class="measurement",
            value_template="{{ value_json.volume_flow_rate }}"
        )
        manager.send_ha_autodiscovery(
            id=f"{relay_id}_virtual_consumption",
            relay_id=relay_id,
            name=f"{name} Virtual consumption",
            ha_type="sensor",
            device_type="energy",
            availability_msg_func=ha_virtual_energy_sensor_discovery_message,
            unit_of_measurement="L",
            device_class="water",
            state_class="total_increasing",
            value_template="{{ value_json.water }}"
        )
    return relay


def configure_event_sensor(
    gpio: dict,
    pin: str,
    event_bus: EventBus,
    send_ha_autodiscovery: Callable,
    input: GpioEventButton | None = None,
    actions: dict = {},
) -> GpioEventButton | None:
    """Configure event input sensor with multiclick detection.
    
    Args:
        gpio: GPIO configuration dictionary
        pin: Pin name (e.g., "P8_30")
        event_bus: EventBus instance for publishing events
        send_ha_autodiscovery: Callback for HA autodiscovery
        input: Existing input instance (for reload)
        actions: Dictionary of actions for different click types
        
    Returns:
        Configured GpioEventButton instance or None on error
    """
    try:
        name = gpio.pop(ID, pin)
        
        # Reload: update existing input's actions
        if input:
            if not isinstance(input, GpioEventButton):
                _LOGGER.warning(
                    "Cannot reconfigure input type for %s. Restart required.", pin
                )
                return input
            input.set_actions(actions=actions)
        else:
            # Create new event input
            input = GpioEventButton(
                pin=pin,
                name=name,
                input_type=INPUT,
                actions=actions,
                event_bus=event_bus,
                **gpio,
            )
        
        # Register with Home Assistant
        if gpio.get(SHOW_HA, True):
            send_ha_autodiscovery(
                id=pin,
                name=name,
                ha_type=EVENT_ENTITY,
                device_class=gpio.get(DEVICE_CLASS, None),
                availability_msg_func=ha_event_availabilty_message,
            )
        
        return input
        
    except GPIOInputException as err:
        _LOGGER.error("Failed to configure event input on pin %s: %s", pin, err)
        return None


def configure_binary_sensor(
    gpio: dict,
    pin: str,
    event_bus: EventBus,
    send_ha_autodiscovery: Callable,
    input: GpioInputBinarySensor | None = None,
    actions: dict = {},
) -> GpioInputBinarySensor | None:
    """Configure binary sensor input with state detection.
    
    Args:
        gpio: GPIO configuration dictionary
        pin: Pin name (e.g., "P8_30")
        event_bus: EventBus instance for publishing events
        send_ha_autodiscovery: Callback for HA autodiscovery
        input: Existing input instance (for reload)
        actions: Dictionary of actions for different states
        
    Returns:
        Configured GpioInputBinarySensor instance or None on error
    """
    try:
        name = gpio.pop(ID, pin)
        
        # Reload: update existing input's actions
        if input:
            if not isinstance(input, GpioInputBinarySensor):
                _LOGGER.warning(
                    "Cannot reconfigure input type for %s. Restart required.", pin
                )
                return input
            input.set_actions(actions=actions)
        else:
            # Create new binary sensor input
            input = GpioInputBinarySensor(
                pin=pin,
                name=name,
                actions=actions,
                input_type=INPUT_SENSOR,
                event_bus=event_bus,
                **gpio,
            )
        
        # Register with Home Assistant
        if gpio.get(SHOW_HA, True):
            send_ha_autodiscovery(
                id=pin,
                name=name,
                ha_type=BINARY_SENSOR,
                device_class=gpio.get(DEVICE_CLASS, None),
                availability_msg_func=ha_binary_sensor_availabilty_message,
            )
        
        return input
        
    except GPIOInputException as err:
        _LOGGER.error("Failed to configure binary sensor on pin %s: %s", pin, err)
        return None


def configure_cover(
    message_bus: MessageBus,
    cover_id: str,
    state_manager: StateManager,
    send_ha_autodiscovery: Callable,
    config: dict,
    tilt_duration: TimePeriod | None,
    **kwargs,
) -> PreviousCover | TimeBasedCover:
    
    platform = config.get("platform", "previous")
    def state_save(value: dict[str, int]):
        if config[RESTORE_STATE]:
            state_manager.save_attribute(
                attr_type=COVER,
                attribute=cover_id,
                value=value,
            )
    if platform == "venetian":
        if not tilt_duration:
            raise CoverConfigurationException("Tilt duration must be configured for tilt cover.")
        _LOGGER.debug("Configuring tilt cover %s", cover_id)
        restored_state: dict = state_manager.get(
            attr_type=COVER, attr=cover_id, default_value={"position": 100, "tilt_position": 100}
        )
        if isinstance(restored_state, (float, int)):
            restored_state = {"position": restored_state, "tilt_position": 100}
        cover = VenetianCover(
            id=cover_id,
            state_save=state_save,
            message_bus=message_bus,
            restored_state=restored_state,
            tilt_duration=tilt_duration,
            actuator_activation_duration=config.get("actuator_activation_duration", TimePeriod(milliseconds=0)),
            **kwargs,
        )
        availability_msg_func = ha_cover_with_tilt_availabilty_message
    elif platform == "time_based":
        _LOGGER.debug("Configuring time-based cover %s", cover_id)
        restored_state: dict = state_manager.get(
            attr_type=COVER, attr=cover_id, default_value={"position": 100}
        )
        if isinstance(restored_state, (float, int)):
            restored_state = {"position": restored_state}
        cover = TimeBasedCover(
            id=cover_id,
            state_save=state_save,
            message_bus=message_bus,
            restored_state=restored_state,
            **kwargs,
        )
        availability_msg_func = ha_cover_availabilty_message
    else:
        _LOGGER.debug("Configuring previous cover %s", cover_id)
        restored_state: dict = state_manager.get(
            attr_type=COVER, attr=cover_id, default_value={"position": 100}
        )
        if isinstance(restored_state, (float, int)):
            restored_state = {"position": restored_state}
        cover = PreviousCover(
            id=cover_id,
            state_save=state_save,
            message_bus=message_bus,
            restored_state=restored_state,
            **kwargs,
        )
        availability_msg_func = ha_cover_availabilty_message
    if config.get(SHOW_HA, True):
        send_ha_autodiscovery(
            id=cover.id,
            name=cover.name,
            ha_type=COVER,
            device_class=config.get(DEVICE_CLASS),
            availability_msg_func=availability_msg_func,
        )
    _LOGGER.debug("Configured cover %s", cover_id)
    return cover


def configure_ds2482(
    i2cbusio: I2C, address: str = DS2482_ADDRESS
) -> OneWireBus:
    ds2482 = DS2482(i2c=i2cbusio, address=address)
    ow_bus = OneWireBus(ds2482=ds2482)
    return ow_bus


def get_w1_sensor_class():
    """Return the W1ThermSensor class for direct kernel access to 1-Wire sensors."""
    return W1ThermSensor


def find_onewire_devices(
    ow_bus: OneWireBus | W1ThermSensor,
    bus_id: str,
    bus_type: DallasBusTypes,
) -> dict[str, str]:
    out = {}
    try:
        devices = ow_bus.scan()
        for device in devices:
            _addr = device.id if hasattr(device, 'id') else device
            _LOGGER.debug(
                "Found device on bus %s with address %s", bus_id, _addr
            )
            out[_addr] = _addr
    except RuntimeError as err:
        _LOGGER.error("Problem with scanning %s bus. %s", bus_type, err)
    return out


def create_dallas_sensor(
    manager: Manager,
    message_bus: MessageBus,
    address: str,
    config: dict,
    **kwargs,
) -> DallasSensor:
    name = config.get(ID) or address
    id = name.replace(" ", "")
    cls = DallasSensor
    sensor = cls(
        manager=manager,
        message_bus=message_bus,
        address=address,
        id=id,
        name=name,
        update_interval=config.get(UPDATE_INTERVAL, TimePeriod(seconds=60)),
        filters=config.get(FILTERS, []),
        **kwargs,
    )
    if config.get(SHOW_HA, True):
        manager.send_ha_autodiscovery(
            id=sensor.id,
            name=sensor.name,
            ha_type=SENSOR,
            availability_msg_func=ha_sensor_temp_availabilty_message,
            unit_of_measurement=config.get("unit_of_measurement", "°C"),
        )
    return sensor


def create_ina219_sensor(
    manager: Manager,
    message_bus: MessageBus,
    topic_prefix: str,
    config: dict = {},
):
    """Create INA219 sensor in manager."""
    from boneio.sensor import INA219

    address = config[ADDRESS]
    id = config.get(ID, str(address)).replace(" ", "")
    try:
        ina219 = INA219(
            id=id,
            address=address,
            sensors=config.get("sensors", []),
            manager=manager,
            message_bus=message_bus,
            topic_prefix=topic_prefix,
            update_interval=config.get(UPDATE_INTERVAL, TimePeriod(seconds=60)),
        )
        for sensor in ina219.sensors.values():
            manager.send_ha_autodiscovery(
                id=sensor.id,
                name=sensor.name,
                ha_type=SENSOR,
                availability_msg_func=ha_sensor_ina_availabilty_message,
                unit_of_measurement=sensor.unit_of_measurement,
                device_class=sensor.device_class,
            )
        return ina219
    except I2CError as err:
        _LOGGER.error("Can't configure Temp sensor. %s", err)
        pass
