import asyncio
import logging
import time
from typing import Any, Callable, List, Optional, Set, Union

from adafruit_mcp230xx.mcp23017 import MCP23017
from board import SCL, SDA
from busio import I2C

from boneio.const import (
    ACTION,
    ACTIONS,
    ADDRESS,
    GPIO,
    HA_TYPE,
    HOMEASSISTANT,
    ID,
    INIT_SLEEP,
    INPUT,
    KIND,
    MCP,
    MCP_ID,
    OFF,
    ON,
    ONLINE,
    OUTPUT,
    PIN,
    RELAY,
    STATE,
    ClickTypes,
    InputTypes,
    SENSOR,
    SHOW_HA,
    BINARY_SENSOR,
    INPUT_SENSOR,
    UPDATE_INTERVAL,
)
from boneio.helper import (
    HostData,
    ha_relay_availibilty_message,
    ha_input_availibilty_message,
    ha_adc_sensor_availibilty_message,
    ha_sensor_temp_availibilty_message,
    ha_binary_sensor_availibilty_message,
    host_stats,
    GPIOInputException,
    I2CError,
)
from boneio.input import GpioInputButton

from boneio.relay import GpioRelay, MCPRelay
from boneio.sensor import GpioInputSensor

_LOGGER = logging.getLogger(__name__)


class Manager:
    """Manager to communicate MQTT with GPIO inputs and outputs."""

    def __init__(
        self,
        send_message: Callable[[str, Union[str, dict]], None],
        topic_prefix: str,
        relay_pins: List,
        input_pins: List,
        lm75: dict = None,
        ha_discovery: bool = True,
        ha_discovery_prefix: str = HOMEASSISTANT,
        mcp23017: Optional[List] = None,
        oled: bool = False,
        adc_list: Optional[List] = None,
    ) -> None:
        """Initialize the manager."""
        _LOGGER.info("Initializing manager module.")
        self._loop = asyncio.get_event_loop()
        self._host_data = None

        self.send_message = send_message
        self._topic_prefix = topic_prefix
        self.relay_topic = f"{topic_prefix}/{RELAY}/+/set"
        self._input_pins = input_pins
        self._i2cbusio = I2C(SCL, SDA)
        self._mcp = {}
        self._grouped_outputs = {}
        self._oled = None
        self._tasks: List[asyncio.Task] = []
        self._lm75 = None

        def create_lm75_sensor():
            """Create LM sensor in manager."""
            from .sensor.lm75 import LM75Sensor

            name = lm75.get(ID)
            id = name.replace(" ", "")
            try:
                self._lm75 = LM75Sensor(
                    id=id,
                    name=name,
                    i2c=self._i2cbusio,
                    address=lm75[ADDRESS],
                    send_message=self.send_message,
                    topic_prefix=topic_prefix,
                )
                self.send_ha_autodiscovery(
                    id=id,
                    name=name,
                    ha_type="sensor",
                    prefix=ha_discovery_prefix,
                    availibilty_msg_func=ha_sensor_temp_availibilty_message,
                )
                self._tasks.append(asyncio.create_task(self._lm75.send_state()))
            except I2CError as err:
                _LOGGER.error("Can't configure LM75 sensor. %s", err)
                pass

        def create_mcp23017():
            """Create MCP23017."""
            for mcp in mcp23017:
                id = mcp[ID] or mcp[ADDRESS]
                try:
                    self._mcp[id] = MCP23017(i2c=self._i2cbusio, address=mcp[ADDRESS])
                    sleep_time = mcp.get(INIT_SLEEP, 0)
                    _LOGGER.debug(
                        f"Sleeping for {sleep_time}s while MCP {id} is initializing."
                    )
                    time.sleep(sleep_time)
                    self._grouped_outputs[id] = {}
                except TimeoutError as err:
                    _LOGGER.error("Can't connect to MCP %s. %s", id, err)
                    pass

        def create_adc():
            from boneio.sensor import initialize_adc, GpioADCSensor

            initialize_adc()

            ## TODO: find what exception can ADC gpio throw.
            for gpio in adc_list:
                name = gpio.get(ID)
                id = name.replace(" ", "")
                pin = gpio[PIN]
                try:
                    adc = GpioADCSensor(
                        id=id,
                        pin=pin,
                        name=name,
                        send_message=self.send_message,
                        topic_prefix=topic_prefix,
                        update_interval=gpio.get(UPDATE_INTERVAL, 60),
                    )
                    self.send_ha_autodiscovery(
                        id=id,
                        name=name,
                        ha_type=SENSOR,
                        prefix=ha_discovery_prefix,
                        availibilty_msg_func=ha_adc_sensor_availibilty_message,
                    )
                    self._tasks.append(asyncio.create_task(adc.send_state()))
                except I2CError as err:
                    _LOGGER.error("Can't configure ADC sensor %s. %s", id, err)
                    pass

            return True

        if lm75:
            create_lm75_sensor()

        if mcp23017:
            create_mcp23017()

        if adc_list:
            create_adc()

        def configure_relay(gpio: dict) -> Any:
            """Configure kind of relay. Most common MCP."""
            relay_id = gpio[ID].replace(" ", "")
            if gpio[KIND] == MCP:
                mcp_id = gpio.get(MCP_ID, "")
                mcp = self._mcp.get(mcp_id)
                if not mcp:
                    _LOGGER.error("No such MCP configured!")
                    return
                mcp_relay = MCPRelay(
                    pin=int(gpio[PIN]),
                    id=gpio[ID],
                    send_message=self.send_message,
                    topic_prefix=topic_prefix,
                    mcp=mcp,
                    mcp_id=mcp_id,
                    ha_type=gpio[HA_TYPE],
                    callback=lambda: self._host_data_callback(mcp_id),
                )
                self._grouped_outputs[mcp_id][relay_id] = mcp_relay
                return mcp_relay
            elif gpio[KIND] == GPIO:
                if not GPIO in self._grouped_outputs:
                    self._grouped_outputs[GPIO] = {}
                gpio_relay = GpioRelay(
                    pin=gpio[PIN],
                    id=gpio[ID],
                    send_message=self.send_message,
                    topic_prefix=topic_prefix,
                    callback=lambda: self._host_data_callback(GPIO),
                )
                self._grouped_outputs[GPIO][relay_id] = gpio_relay
                return gpio_relay

        self.output = {
            gpio[ID].replace(" ", ""): configure_relay(gpio) for gpio in relay_pins
        }
        for out in self.output.values():
            if ha_discovery:
                self.send_ha_autodiscovery(
                    id=out.id,
                    name=out.name,
                    ha_type=out.ha_type,
                    prefix=ha_discovery_prefix,
                    availibilty_msg_func=ha_relay_availibilty_message,
                )
            self._loop.call_soon_threadsafe(
                self._loop.call_later,
                0.5,
                out.send_state,
            )

        def configure_input(gpio):
            try:
                pin = gpio[PIN]
                input_type = gpio.get(KIND)
                if input_type == SENSOR:
                    GpioInputSensor(
                        pin=pin,
                        press_callback=lambda x, i: self.press_callback(
                            x=x,
                            inpin=i,
                            actions=gpio.get(ACTIONS, {}),
                            input_type=INPUT_SENSOR,
                        ),
                        rest_pin=gpio,
                    )
                    availibilty_msg_func = ha_binary_sensor_availibilty_message
                    ha_type = BINARY_SENSOR
                else:
                    GpioInputButton(
                        pin=pin,
                        press_callback=lambda x, i: self.press_callback(
                            x=x,
                            inpin=i,
                            actions=gpio.get(ACTIONS, {}),
                            input_type=INPUT,
                        ),
                        rest_pin=gpio,
                    )
                    availibilty_msg_func = ha_input_availibilty_message
                    ha_type = SENSOR
                if gpio.get(SHOW_HA, True):
                    self.send_ha_autodiscovery(
                        id=pin,
                        name=gpio.get(ID, pin),
                        ha_type=ha_type,
                        prefix=ha_discovery_prefix,
                        availibilty_msg_func=availibilty_msg_func,
                    )
            except GPIOInputException as err:
                _LOGGER.error("This PIN %s can't be configured. %s", pin, err)
                pass

        _LOGGER.info("Initializing inputs. This will take a while.")
        for gpio in self._input_pins:
            configure_input(gpio=gpio)

        if oled:
            from boneio.oled import Oled

            self._host_data = HostData(
                output=self._grouped_outputs,
                lm75=self._lm75,
                callback=self._host_data_callback,
            )
            for f in host_stats.values():
                self._tasks.append(asyncio.create_task(f(self._host_data)))
            _LOGGER.debug("Gathering host data enabled.")
            try:
                self._oled = Oled(
                    host_data=self._host_data, output_groups=list(self._grouped_outputs)
                )
            except (GPIOInputException, I2CError) as err:
                _LOGGER.error("Can't configure OLED display. %s", err)

        self.send_message(topic=f"{topic_prefix}/{STATE}", payload=ONLINE)
        _LOGGER.info("BoneIO manager is ready.")

    def _host_data_callback(self, type):
        if self._oled:
            self._oled.handle_data_update(type)

    def get_tasks(self) -> Set[asyncio.Task]:
        return self._tasks

    def press_callback(
        self, x: ClickTypes, inpin: str, actions: dict, input_type: InputTypes = INPUT
    ) -> None:
        """Press callback to use in input gpio.
        If relay input map is provided also toggle action on relay."""
        topic = f"{self._topic_prefix}/{input_type}/{inpin}"
        self.send_message(topic=topic, payload=x)
        action = actions.get(x)
        if action:
            if action[ACTION] == OUTPUT:
                """For now only output type is supported"""
                relay = self.output.get(action[PIN].replace(" ", ""))
                if relay:
                    relay.toggle()
        # This is similar how Z2M is clearing click sensor.
        self._loop.call_soon_threadsafe(self.send_message, topic, "")

    def send_ha_autodiscovery(
        self,
        id: str,
        name: str,
        prefix: str,
        availibilty_msg_func: Callable,
        ha_type: str = "switch",
    ) -> None:
        """Send HA autodiscovery information for each relay."""
        msg = availibilty_msg_func(topic=self._topic_prefix, id=id, name=name)
        topic = f"{prefix}/{ha_type}/{self._topic_prefix}/{id}/config"
        _LOGGER.debug("Sending HA discovery for %s, %s.", ha_type, name)
        self.send_message(topic=topic, payload=msg)

    def receive_message(self, topic: str, message: str) -> None:
        """Callback for receiving action from Mqtt."""
        extracted_relay = topic.replace(f"{self._topic_prefix}/{RELAY}/", "").replace(
            "/set", ""
        )
        target_device = self.output.get(extracted_relay)
        if target_device:
            if message == ON:
                target_device.turn_on()
            elif message == OFF:
                target_device.turn_off()
