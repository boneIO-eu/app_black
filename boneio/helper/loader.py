from __future__ import annotations

import logging
import asyncio
import time
from typing import TYPE_CHECKING, Any, Callable
from collections import namedtuple

from adafruit_mcp230xx.mcp23017 import MCP23017
from boneio.const import (
    ACTIONS,
    ADDRESS,
    BINARY_SENSOR,
    COVER,
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
    DEVICE_CLASS,
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
from boneio.helper.ha_discovery import ha_cover_availabilty_message
from boneio.helper.timeperiod import TimePeriod
from boneio.input.gpio import GpioInputButton

# Typing imports that create a circular dependency
if TYPE_CHECKING:
    from ..manager import Manager
from boneio.modbus import Modbus
from boneio.relay import GpioRelay, MCPRelay
from boneio.sensor import GpioADCSensor, initialize_adc
from boneio.sensor.gpio import GpioInputSensor
from busio import I2C

_LOGGER = logging.getLogger(__name__)


def create_adc(
    manager: Manager, topic_prefix: str, ha_discovery_prefix: str, adc_list: list = []
):
    """Create ADC sensor."""

    initialize_adc()

    # TODO: find what exception can ADC gpio throw.
    for gpio in adc_list:
        name = gpio.get(ID)
        id = name.replace(" ", "")
        pin = gpio[PIN]
        try:
            adc = GpioADCSensor(
                id=id,
                pin=pin,
                name=name,
                send_message=manager.send_message,
                topic_prefix=topic_prefix,
                update_interval=gpio.get(UPDATE_INTERVAL, 60),
            )
            if gpio.get(SHOW_HA, True):
                manager.send_ha_autodiscovery(
                    id=id,
                    name=name,
                    ha_type=SENSOR,
                    ha_discovery_prefix=ha_discovery_prefix,
                    availability_msg_func=ha_adc_sensor_availabilty_message,
                )
            manager.append_task(asyncio.create_task(adc.send_state()))
        except I2CError as err:
            _LOGGER.error("Can't configure ADC sensor %s. %s", id, err)
            pass


def create_temp_sensor(
    manager: Manager,
    topic_prefix: str,
    ha_discovery_prefix: str,
    sensor_type: str,
    i2cbusio: I2C,
    temp_def: dict = {},
    temp_sensors: list = [],
):
    """Create LM sensor in manager."""
    if sensor_type == LM75:
        from boneio.sensor import LM75Sensor as TempSensor
    elif sensor_type == MCP_TEMP_9808:
        from boneio.sensor import MCP9808Sensor as TempSensor
    else:
        return
    name = temp_def.get(ID)
    id = name.replace(" ", "")
    try:
        temp_sensor = TempSensor(
            id=id,
            name=name,
            i2c=i2cbusio,
            address=temp_def[ADDRESS],
            send_message=manager.send_message,
            topic_prefix=topic_prefix,
        )
        manager.send_ha_autodiscovery(
            id=id,
            name=name,
            ha_type=SENSOR,
            ha_discovery_prefix=ha_discovery_prefix,
            availability_msg_func=ha_sensor_temp_availabilty_message,
        )
        manager.append_task(asyncio.create_task(temp_sensor.send_state()))
        temp_sensors.append(temp_sensor)
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


def create_modbus_sensors(
    manager: Manager,
    topic_prefix: str,
    ha_discovery: bool,
    ha_discovery_prefix: str,
    modbus: Modbus,
    sensors,
) -> None:
    """Create Modbus sensor for each device."""
    from boneio.sensor.modbus import ModbusSensor

    for sensor in sensors:
        name = sensor.get(ID)
        id = name.replace(" ", "")
        try:
            sdm = ModbusSensor(
                modbus=modbus,
                address=sensor[ADDRESS],
                id=id,
                name=name,
                model=sensor[MODEL],
                send_message=manager.send_message,
                topic_prefix=topic_prefix,
                ha_discovery=ha_discovery,
                ha_discovery_prefix=ha_discovery_prefix,
                update_interval=sensor.get(UPDATE_INTERVAL, 30),
            )
            manager.append_task(asyncio.create_task(sdm.send_state()))
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
    ha_discovery_prefix: str,
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
                ha_discovery_prefix=ha_discovery_prefix,
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
    ha_discovery_prefix: str,
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
            ha_discovery_prefix=ha_discovery_prefix,
            availability_msg_func=ha_cover_availabilty_message,
        )
    return cover
