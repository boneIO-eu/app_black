from __future__ import annotations

import logging
import time
from collections import namedtuple
from typing import TYPE_CHECKING, Any, Callable, Dict, Union

from adafruit_mcp230xx.mcp23017 import MCP23017

from boneio.const import (
    ACTIONS,
    ADDRESS,
    BINARY_SENSOR,
    COVER,
    DEVICE_CLASS,
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
    PIN,
    RELAY,
    RESTORE_STATE,
    SENSOR,
    SHOW_HA,
    UPDATE_INTERVAL,
    DallasBusTypes,
)
from boneio.cover import Cover
from boneio.helper import (
    GPIOInputException,
    I2CError,
    StateManager,
    ha_adc_sensor_availabilty_message,
    ha_binary_sensor_availabilty_message,
    ha_input_availabilty_message,
    ha_sensor_temp_availabilty_message,
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
from boneio.input.gpio import GpioInputButton
from boneio.sensor import DallasSensorDS2482
from boneio.sensor.temp.dallas import DallasSensorW1

# Typing imports that create a circular dependency
if TYPE_CHECKING:
    from ..manager import Manager

from busio import I2C

from boneio.relay import GpioRelay, MCPRelay
from boneio.sensor import GpioADCSensor, initialize_adc
from boneio.sensor.gpio import GpioInputSensor

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


def create_mcp23017(
    manager: Manager,
    mcp23017: list,
    i2cbusio: I2C,
) -> dict:
    """Create MCP23017."""
    grouped_outputs = {}
    for mcp in mcp23017:
        id = mcp[ID] or mcp[ADDRESS]
        try:
            manager._mcp[id] = MCP23017(i2c=i2cbusio, address=mcp[ADDRESS], reset=False)
            sleep_time = mcp.get(INIT_SLEEP, TimePeriod(seconds=0))
            _LOGGER.debug(
                f"Sleeping for {sleep_time.total_seconds}s while MCP {id} is initializing."
            )
            time.sleep(sleep_time.total_seconds)
            grouped_outputs[id] = {}
        except TimeoutError as err:
            _LOGGER.error("Can't connect to MCP %s. %s", id, err)
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


OutputEntry = namedtuple("OutputEntry", "OutputClass output_kind output_id")


def output_chooser(output_kind: str, mcp_id: str | None):
    """Get named tuple based on input."""
    if output_kind == MCP:
        return OutputEntry(MCPRelay, MCP, mcp_id)
    else:
        return OutputEntry(GpioRelay, GPIO, GPIO)


def configure_relay(
    manager: Manager,
    state_manager: StateManager,
    topic_prefix: str,
    relay_id: str,
    relay_callback: Callable,
    config: dict,
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

    output = output_chooser(
        output_kind=config.pop(KIND), mcp_id=config.pop(MCP_ID, None)
    )

    if getattr(output, "output_kind") == MCP:
        mcp = manager.mcp.get(getattr(output, "output_id"))
        if not mcp:
            _LOGGER.error("No such MCP configured!")
            return None
        kwargs = {
            "pin": int(config.pop(PIN)),
            "mcp": mcp,
            "mcp_id": getattr(output, "output_id"),
            "output_type": output_type,
        }
    elif getattr(output, "output_kind") == GPIO:
        if GPIO not in manager.grouped_outputs:
            manager.grouped_outputs[GPIO] = {}
        kwargs = {
            "pin": config.pop(PIN),
        }
    else:
        return
    relay = getattr(output, "OutputClass")(
        send_message=manager.send_message,
        topic_prefix=topic_prefix,
        id=config.pop(ID),
        restored_state=restored_state,
        **config,
        **kwargs,
        callback=lambda: relay_callback(
            relay_type=getattr(output, "output_id"),
            relay_id=relay_id,
            restore_state=False if output_type == NONE else restore_state,
        ),
    )
    manager.grouped_outputs[getattr(output, "output_id")][relay_id] = relay
    return relay


InputEntry = namedtuple(
    "InputEntry", "InputClass input_type ha_type availability_msg_f"
)


def input_chooser(input_type: str):
    """Get named tuple based on input."""
    if input_type == SENSOR:
        return InputEntry(
            GpioInputSensor,
            INPUT_SENSOR,
            BINARY_SENSOR,
            ha_binary_sensor_availabilty_message,
        )
    else:
        return InputEntry(GpioInputButton, INPUT, SENSOR, ha_input_availabilty_message)


def configure_input(
    gpio: dict,
    pin: str,
    press_callback: Callable,
    send_ha_autodiscovery: Callable,
) -> str:
    """Configure input sensor or button."""
    try:
        input = input_chooser(input_type=gpio.get(KIND))
        getattr(input, "InputClass")(
            pin=pin,
            press_callback=lambda x, i: press_callback(
                x=x,
                inpin=i,
                actions=gpio.get(ACTIONS, {}).get(x, []),
                input_type=getattr(input, "input_type"),
            ),
            rest_pin=gpio,
        )
        if gpio.get(SHOW_HA, True):
            send_ha_autodiscovery(
                id=pin,
                name=gpio.get(ID, pin),
                ha_type=getattr(input, "ha_type"),
                availability_msg_func=getattr(input, "availability_msg_f"),
            )
        return pin
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
