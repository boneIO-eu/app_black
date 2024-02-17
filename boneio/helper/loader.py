from __future__ import annotations
import logging
import time
from collections import namedtuple
from typing import TYPE_CHECKING, Any, Callable, Dict, Union

from adafruit_mcp230xx.mcp23017 import MCP23017
from adafruit_pca9685 import PCA9685

from boneio.const import (
    ACTIONS,
    ADDRESS,
    BINARY_SENSOR,
    COVER,
    DEVICE_CLASS,
    FILTERS,
    GPIO,
    PCA,
    ID,
    INIT_SLEEP,
    INPUT,
    INPUT_SENSOR,
    KIND,
    LM75,
    MCP,
    MCP_ID,
    PCA_ID,
    MCP_TEMP_9808,
    MODEL,
    NONE,
    OUTPUT_TYPE,
    PIN,
    RELAY,
    RESTORE_STATE,
    SENSOR,
    SHOW_HA,
    UPDATE_INTERVAL,
    DallasBusTypes,
    EVENT_ENTITY,
    ExpanderTypes,
    PCF,
    PCA,
    PCF_ID,
)
from boneio.cover import Cover
from boneio.group import OutputGroup
from boneio.helper import (
    GPIOInputException,
    GPIOOutputException,
    I2CError,
    StateManager,
    ha_adc_sensor_availabilty_message,
    ha_binary_sensor_availabilty_message,
    ha_event_availabilty_message,
    ha_sensor_temp_availabilty_message,
    ha_sensor_ina_availabilty_message,
)
from boneio.helper.onewire import (
    DS2482,
    DS2482_ADDRESS,
    OneWireBus,
    AsyncBoneIOW1ThermSensor,
    OneWireAddress,
)
from boneio.helper.ha_discovery import ha_cover_availabilty_message
from boneio.helper.timeperiod import TimePeriod
from boneio.helper.pcf8575 import PCF8575
from boneio.input import GpioEventButtonOld, GpioEventButtonNew
from boneio.sensor import (
    DallasSensorDS2482,
    GpioInputBinarySensorOld,
    GpioInputBinarySensorNew,
)
from boneio.sensor.temp.dallas import DallasSensorW1

# Typing imports that create a circular dependency
if TYPE_CHECKING:
    from ..manager import Manager

from busio import I2C

from boneio.relay import GpioRelay, MCPRelay, PWMPCA, PCFRelay
from boneio.sensor import GpioADCSensor, initialize_adc

_LOGGER = logging.getLogger(__name__)


def create_adc(manager: Manager, topic_prefix: str, adc_list: list = []):
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
                send_message=manager.send_message,
                topic_prefix=topic_prefix,
                update_interval=gpio.get(UPDATE_INTERVAL, TimePeriod(seconds=60)),
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
    id = name.replace(" ", "")
    try:
        temp_sensor = TempSensor(
            id=id,
            name=name,
            i2c=i2cbusio,
            address=config[ADDRESS],
            manager=manager,
            send_message=manager.send_message,
            topic_prefix=topic_prefix,
            update_interval=config.get(UPDATE_INTERVAL, TimePeriod(seconds=60)),
            filters=config.get(FILTERS, []),
        )
        manager.send_ha_autodiscovery(
            id=id,
            name=name,
            ha_type=SENSOR,
            availability_msg_func=ha_sensor_temp_availabilty_message,
            unit_of_measurement=config.get("unit_of_measurement", "°C"),
        )
        return temp_sensor
    except I2CError as err:
        _LOGGER.error("Can't configure Temp sensor. %s", err)
        pass


expander_class = {MCP: MCP23017, PCA: PCA9685, PCF: PCF8575}


def create_expander(
    expander_dict: dict, expander_config: list, exp_type: ExpanderTypes, i2cbusio: I2C
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


def create_modbus_sensors(manager: Manager, sensors, **kwargs) -> None:
    """Create Modbus sensor for each device."""
    from boneio.sensor.modbus import ModbusSensor

    for sensor in sensors:
        name = sensor.get(ID)
        id = name.replace(" ", "")
        try:
            ModbusSensor(
                address=sensor[ADDRESS],
                id=id,
                name=name,
                manager=manager,
                model=sensor[MODEL],
                send_message=manager.send_message,
                update_interval=sensor.get(UPDATE_INTERVAL, TimePeriod(seconds=60)),
                **kwargs,
            )
        except FileNotFoundError as err:
            _LOGGER.error(
                "Can't configure Modbus sensor %s. %s. No such model in database.",
                id,
                err,
            )
            pass


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
    manager: Manager,
    topic_prefix: str,
    config: dict,
    **kwargs,
) -> Any:
    """Configure kind of relay. Most common MCP."""
    _id = config.pop(ID)

    output = OutputGroup(
        send_message=manager.send_message,
        topic_prefix=topic_prefix,
        id=_id,
        callback=lambda: None,
        **config,
        **kwargs,
    )
    return output


def configure_relay(
    manager: Manager,
    state_manager: StateManager,
    topic_prefix: str,
    relay_id: str,
    name: str,
    relay_callback: Callable,
    config: dict,
    **kwargs,
) -> Any:
    """Configure kind of relay. Most common MCP."""
    restore_state = config.pop(RESTORE_STATE, False)
    output_type = config.pop(OUTPUT_TYPE)
    restored_state = (
        state_manager.get(attr_type=RELAY, attr=relay_id, default_value=False)
        if restore_state
        else False
    )
    if output_type == NONE and state_manager.get(attr_type=RELAY, attr=relay_id):
        state_manager.del_attribute(attr_type=RELAY, attribute=relay_id)
        restored_state = False

    output = output_chooser(output_kind=config.pop(KIND), config=config)

    if getattr(output, "output_kind") == MCP:
        mcp = manager.mcp.get(getattr(output, "expander_id"))
        if not mcp:
            _LOGGER.error("No such MCP configured!")
            return None
        extra_args = {
            "pin": int(config.pop(PIN)),
            "mcp": mcp,
            "mcp_id": getattr(output, "expander_id"),
            "output_type": output_type,
        }
    elif getattr(output, "output_kind") == PCA:
        pca = manager.pca.get(getattr(output, "expander_id"))
        if not pca:
            _LOGGER.error("No such PCA configured!")
            return None
        extra_args = {
            "pin": int(config.pop(PIN)),
            "pca": pca,
            "pca_id": getattr(output, "expander_id"),
            "output_type": output_type,
        }
    elif getattr(output, "output_kind") == PCF:
        expander = manager.pcf.get(getattr(output, "expander_id"))
        if not expander:
            _LOGGER.error("No such PCF configured!")
            return None
        extra_args = {
            "pin": int(config.pop(PIN)),
            "expander": expander,
            "expander_id": getattr(output, "expander_id"),
            "output_type": output_type,
        }
    elif getattr(output, "output_kind") == GPIO:
        if GPIO not in manager.grouped_outputs:
            manager.grouped_outputs[GPIO] = {}
        extra_args = {
            "pin": config.pop(PIN),
        }
    else:
        _LOGGER.error(
            "Output kind: %s is not configured", getattr(output, "output_kind")
        )
        return

    relay = getattr(output, "OutputClass")(
        send_message=manager.send_message,
        topic_prefix=topic_prefix,
        id=relay_id,
        restored_state=restored_state,
        name=name,
        **config,
        **kwargs,
        **extra_args,
        callback=lambda: relay_callback(
            expander_id=getattr(output, "expander_id"),
            relay_id=relay_id,
            restore_state=False if output_type == NONE else restore_state,
        ),
    )
    manager.grouped_outputs[getattr(output, "expander_id")][relay_id] = relay
    return relay


def configure_event_sensor(
    gpio: dict,
    pin: str,
    press_callback: Callable,
    send_ha_autodiscovery: Callable,
    input: GpioEventButtonOld | GpioEventButtonNew | None = None
) -> GpioEventButtonOld | GpioEventButtonNew | None:
    """Configure input sensor or button."""
    try:
        GpioEventButtonClass = (
            GpioEventButtonNew
            if gpio.get("detection_type", "new") == "new"
            else GpioEventButtonOld
        )
        name = gpio.pop(ID, pin)
        if input:
            if not isinstance(input, GpioEventButtonClass):
                _LOGGER.warn(
                    "You preconfigured type of input. It's forbidden. Please restart boneIO."
                )
                return input
            input.set_actions(actions=gpio.get(ACTIONS, {}))
        else:
            input = GpioEventButtonClass(
                pin=pin,
                name=name,
                input_type=INPUT,
                empty_message_after=gpio.pop("clear_message", False),
                actions=gpio.pop(ACTIONS, {}),
                press_callback=press_callback,
                **gpio,
            )
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
        _LOGGER.error("This PIN %s can't be configured. %s", pin, err)
        pass


def configure_binary_sensor(
    gpio: dict,
    pin: str,
    press_callback: Callable,
    send_ha_autodiscovery: Callable,
    input: GpioInputBinarySensorOld | GpioInputBinarySensorNew | None = None,
) -> GpioInputBinarySensorOld | GpioInputBinarySensorNew | None:
    """Configure input sensor or button."""
    try:
        GpioInputBinarySensorClass = (
            GpioInputBinarySensorNew
            if gpio.get("detection_type", "new") == "new"
            else GpioInputBinarySensorOld
        )
        name = gpio.pop(ID, pin)
        if input:
            if not isinstance(input, GpioInputBinarySensorClass):
                _LOGGER.warn(
                    "You preconfigured type of input. It's forbidden. Please restart boneIO."
                )
                return input
            input.set_actions(actions=gpio.get(ACTIONS, {}))
        else:
            input = GpioInputBinarySensorClass(
                pin=pin,
                name=name,
                actions=gpio.pop(ACTIONS, {}),
                input_type=INPUT_SENSOR,
                empty_message_after=gpio.pop("clear_message", False),
                press_callback=press_callback,
                **gpio,
            )
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
        _LOGGER.error("This PIN %s can't be configured. %s", pin, err)
        pass


def configure_cover(
    manager: Manager,
    cover_id: str,
    state_manager: StateManager,
    send_ha_autodiscovery: Callable,
    config: dict,
    **kwargs,
) -> Cover:
    restored_state = state_manager.get(
        attr_type=COVER, attr=cover_id, default_value=100
    )

    def state_save(position: int):
        if config[RESTORE_STATE]:
            state_manager.save_attribute(
                attr_type=COVER,
                attribute=cover_id,
                value=position,
            )

    cover = Cover(
        id=cover_id,
        state_save=state_save,
        send_message=manager.send_message,
        restored_state=restored_state,
        **kwargs,
    )
    if config.get(SHOW_HA, True):
        send_ha_autodiscovery(
            id=cover.id,
            name=cover.name,
            ha_type=COVER,
            device_class=config.get(DEVICE_CLASS),
            availability_msg_func=ha_cover_availabilty_message,
        )
    _LOGGER.debug("Configured cover %s", cover_id)
    return cover


def configure_ds2482(i2cbusio: I2C, address: str = DS2482_ADDRESS) -> OneWireBus:
    ds2482 = DS2482(i2c=i2cbusio, address=address)
    ow_bus = OneWireBus(ds2482=ds2482)
    return ow_bus


def configure_dallas() -> AsyncBoneIOW1ThermSensor:
    return AsyncBoneIOW1ThermSensor


def find_onewire_devices(
    ow_bus: Union[OneWireBus, AsyncBoneIOW1ThermSensor],
    bus_id: str,
    bus_type: DallasBusTypes,
) -> Dict[OneWireAddress]:
    out = {}
    try:
        devices = ow_bus.scan()
        for device in devices:
            _addr: int = device.int_address
            _LOGGER.debug("Found device on bus %s with address %s", bus_id, hex(_addr))
            out[_addr] = device
    except RuntimeError as err:
        _LOGGER.error("Problem with scanning %s bus. %s", bus_type, err)
    return out


def create_dallas_sensor(
    manager: Manager,
    address: OneWireAddress,
    config: dict,
    **kwargs,
) -> Union[DallasSensorDS2482, DallasSensorW1]:
    name = config.get(ID) or hex(address)
    id = name.replace(" ", "")
    bus: OneWireBus = kwargs.get("bus")
    cls = DallasSensorDS2482 if bus else DallasSensorW1
    sensor = cls(
        manager=manager,
        address=address,
        id=id,
        name=name,
        update_interval=config.get(UPDATE_INTERVAL, TimePeriod(seconds=60)),
        send_message=manager.send_message,
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
            send_message=manager.send_message,
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
