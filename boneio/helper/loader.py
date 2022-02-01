from __future__ import annotations

import logging
import asyncio
import time
from typing import TYPE_CHECKING, Any, Callable

from adafruit_mcp230xx.mcp23017 import MCP23017
from boneio.const import (
    ACTIONS,
    ADDRESS,
    BINARY_SENSOR,
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
)
from boneio.helper import (
    GPIOInputException,
    I2CError,
    StateManager,
    ha_adc_sensor_availabilty_message,
    ha_binary_sensor_availabilty_message,
    ha_input_availabilty_message,
    ha_sensor_temp_availabilty_message,
)
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
            manager.send_ha_autodiscovery(
                id=id,
                name=name,
                ha_type=SENSOR,
                ha_discovery_prefix=ha_discovery_prefix,
                availabilty_msg_func=ha_adc_sensor_availabilty_message,
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
            availabilty_msg_func=ha_sensor_temp_availabilty_message,
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
            manager._mcp[id] = MCP23017(i2c=i2cbusio, address=mcp[ADDRESS])
            sleep_time = mcp.get(INIT_SLEEP, 0)
            _LOGGER.debug(f"Sleeping for {sleep_time}s while MCP {id} is initializing.")
            time.sleep(sleep_time)
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


def configure_relay(
    manager: Manager,
    state_manager: StateManager,
    topic_prefix: str,
    relay_id: str,
    relay_callback: Callable,
    config: dict,
) -> Any:
    """Configure kind of relay. Most common MCP."""
    relay_id = config[ID].replace(" ", "")
    restored_state = (
        state_manager.get(attr_type=RELAY, attr=relay_id)
        if config[RESTORE_STATE]
        else False
    )
    if config[KIND] == MCP:
        mcp_id = config.get(MCP_ID, "")
        mcp = manager.mcp.get(mcp_id)
        if not mcp:
            _LOGGER.error("No such MCP configured!")
            return
        mcp_relay = MCPRelay(
            pin=int(config[PIN]),
            id=config[ID],
            send_message=manager.send_message,
            topic_prefix=topic_prefix,
            mcp=mcp,
            mcp_id=mcp_id,
            output_type=config[OUTPUT_TYPE].lower(),
            restored_state=restored_state,
            callback=lambda: relay_callback(
                relay_type=mcp_id,
                relay_id=relay_id,
                restore_state=False
                if config[OUTPUT_TYPE] == NONE
                else config[RESTORE_STATE],
            ),
        )
        manager.grouped_outputs[mcp_id][relay_id] = mcp_relay
        return mcp_relay
    elif config[KIND] == GPIO:
        if GPIO not in manager.grouped_outputs:
            manager.grouped_outputs[GPIO] = {}
        gpio_relay = GpioRelay(
            pin=config[PIN],
            id=config[ID],
            send_message=manager.send_message,
            topic_prefix=topic_prefix,
            restored_state=restored_state,
            callback=lambda: relay_callback(
                relay_type=GPIO,
                relay_id=relay_id,
                restore_state=False
                if config[OUTPUT_TYPE] == NONE
                else config[RESTORE_STATE],
            ),
        )
        manager.grouped_outputs[GPIO][relay_id] = gpio_relay
        return gpio_relay


def configure_input(
    gpio: dict,
    pin: str,
    press_callback: Callable,
    send_ha_autodiscovery: Callable,
    ha_discovery_prefix: str,
) -> str:
    try:
        input_type = gpio.get(KIND)
        if input_type == SENSOR:
            GpioInputSensor(
                pin=pin,
                press_callback=lambda x, i: press_callback(
                    x=x,
                    inpin=i,
                    actions=gpio.get(ACTIONS, {}),
                    input_type=INPUT_SENSOR,
                ),
                rest_pin=gpio,
            )
            availabilty_msg_func = ha_binary_sensor_availabilty_message
            ha_type = BINARY_SENSOR
        else:
            GpioInputButton(
                pin=pin,
                press_callback=lambda x, i: press_callback(
                    x=x,
                    inpin=i,
                    actions=gpio.get(ACTIONS, {}),
                    input_type=INPUT,
                ),
                rest_pin=gpio,
            )
            availabilty_msg_func = ha_input_availabilty_message
            ha_type = SENSOR
        if gpio.get(SHOW_HA, True):
            send_ha_autodiscovery(
                id=pin,
                name=gpio.get(ID, pin),
                ha_type=ha_type,
                ha_discovery_prefix=ha_discovery_prefix,
                availabilty_msg_func=availabilty_msg_func,
            )
        return pin
    except GPIOInputException as err:
        _LOGGER.error("This PIN %s can't be configured. %s", pin, err)
        pass
