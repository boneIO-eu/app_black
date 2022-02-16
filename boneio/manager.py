import asyncio
import logging
from typing import Callable, List, Optional, Set, Union
from collections import deque
from board import SCL, SDA
from busio import I2C

from boneio.const import (
    ACTION,
    BONEIO,
    BUTTON,
    CLOSE,
    COVER,
    HOMEASSISTANT,
    ID,
    INPUT,
    LM75,
    MCP_TEMP_9808,
    MODBUS,
    MQTT,
    NONE,
    OFF,
    ON,
    ONLINE,
    OPEN,
    OUTPUT,
    PIN,
    RELAY,
    STATE,
    STOP,
    TOPIC,
    UART,
    UARTS,
    ClickTypes,
    InputTypes,
)
from boneio.helper import (
    GPIOInputException,
    HostData,
    I2CError,
    StateManager,
    ha_switch_availabilty_message,
    ha_light_availabilty_message,
    ha_button_availabilty_message,
    host_stats,
)
from boneio.helper.events import EventBus
from boneio.helper.loader import (
    configure_cover,
    configure_input,
    configure_relay,
    create_mcp23017,
    create_temp_sensor,
)
from boneio.helper.yaml import load_config_from_file
from boneio.modbus import Modbus
from boneio.helper.logger import configure_logger

_LOGGER = logging.getLogger(__name__)


class Manager:
    """Manager to communicate MQTT with GPIO inputs and outputs."""

    def __init__(
        self,
        send_message: Callable[[str, Union[str, dict], bool], None],
        state_manager: StateManager,
        config_file_path: str,
        relay_pins: List = [],
        input_pins: List = [],
        sensors: dict = {},
        topic_prefix: str = BONEIO,
        modbus: dict = None,
        ha_discovery: bool = True,
        ha_discovery_prefix: str = HOMEASSISTANT,
        mcp23017: Optional[List] = None,
        oled: dict = {},
        adc_list: Optional[List] = None,
        covers: Optional[List] = [],
    ) -> None:
        """Initialize the manager."""
        _LOGGER.info("Initializing manager module.")
        self._loop = asyncio.get_event_loop()
        self._host_data = None
        self._ha_discovery = ha_discovery
        self._config_file_path = config_file_path
        self._state_manager = state_manager
        self._event_bus = EventBus(self._loop)

        self.send_message = send_message
        self._topic_prefix = topic_prefix
        self._command_topic_prefix = f"{topic_prefix}/cmd/"
        self.subscribe_topic = f"{self._command_topic_prefix}+/+/#"
        self._input_pins = input_pins
        self._i2cbusio = I2C(SCL, SDA)
        self._mcp = {}
        self._output = {}
        self._oled = None
        self._tasks: List[asyncio.Task] = []
        self._covers = {}
        self._temp_sensors = []
        self._modbus = None
        if modbus and modbus.get(UART) in UARTS:
            self._modbus = Modbus(UARTS[modbus.get(UART)])

        for sensor_type in (LM75, MCP_TEMP_9808):
            if sensors.get(sensor_type):
                create_temp_sensor(
                    manager=self,
                    topic_prefix=topic_prefix,
                    ha_discovery_prefix=ha_discovery_prefix,
                    sensor_type=sensor_type,
                    temp_def=sensors.get(sensor_type),
                    i2cbusio=self._i2cbusio,
                    temp_sensors=self._temp_sensors,
                )

        if sensors.get(MODBUS) and self._modbus:
            from boneio.helper.loader import create_modbus_sensors

            create_modbus_sensors(
                manager=self,
                topic_prefix=topic_prefix,
                ha_discovery=ha_discovery,
                ha_discovery_prefix=ha_discovery_prefix,
                sensors=sensors.get(MODBUS),
                modbus=self._modbus,
            )

        self.grouped_outputs = create_mcp23017(
            manager=self, mcp23017=mcp23017, i2cbusio=self._i2cbusio
        )

        if adc_list:
            from boneio.helper.loader import create_adc

            create_adc(
                manager=self,
                topic_prefix=topic_prefix,
                adc_list=adc_list,
                ha_discovery_prefix=ha_discovery_prefix,
            )

        for _config in relay_pins:
            _id = _config[ID].replace(" ", "")
            out = configure_relay(
                manager=self,
                state_manager=self._state_manager,
                topic_prefix=topic_prefix,
                relay_id=_id,
                relay_callback=self._relay_callback,
                config=_config,
            )
            if not out:
                continue
            self._output[_id] = out
            if out.output_type != NONE:
                self.send_ha_autodiscovery(
                    id=out.id,
                    name=out.name,
                    ha_type=out.output_type,
                    ha_discovery_prefix=ha_discovery_prefix,
                    availability_msg_func=ha_light_availabilty_message
                    if out.is_light
                    else ha_switch_availabilty_message,
                )
            self._loop.call_soon_threadsafe(
                self._loop.call_later,
                0.5,
                out.send_state,
            )

        for _config in covers:
            _id = _config[ID].replace(" ", "")
            open_relay = self._output.get(_config.get("open_relay"))
            close_relay = self._output.get(_config.get("close_relay"))
            if open_relay.output_type != NONE or close_relay.output_type != NONE:
                _LOGGER.error(
                    "Can't configure cover %s. %s",
                    _id,
                    "You have to explicity set types of relays to None so you can't turn it on directly.",
                )
                continue
            self._covers[_id] = configure_cover(
                manager=self,
                cover_id=_id,
                state_manager=self._state_manager,
                config=_config,
                open_relay=open_relay,
                close_relay=close_relay,
                open_time=_config.get("open_time"),
                close_time=_config.get("close_time"),
                event_bus=self._event_bus,
                ha_discovery_prefix=ha_discovery_prefix,
                send_ha_autodiscovery=self.send_ha_autodiscovery,
                topic_prefix=topic_prefix,
            )

        _LOGGER.info("Initializing inputs. This will take a while.")
        input_pins = set()
        for gpio in self._input_pins:
            pin = gpio[PIN]
            if pin in input_pins:
                _LOGGER.warn("This PIN %s is already configured. Omitting it.", pin)
                continue
            input_pins.add(
                configure_input(
                    gpio=gpio,
                    pin=pin,
                    press_callback=self.press_callback,
                    ha_discovery_prefix=ha_discovery_prefix,
                    send_ha_autodiscovery=self.send_ha_autodiscovery,
                )
            )

        if oled.get("enabled", False):
            from boneio.oled import Oled

            self._host_data = HostData(
                output=self.grouped_outputs,
                temp_sensor=self._temp_sensors[0] if self._temp_sensors else None,
                callback=self._host_data_callback,
            )
            for f in host_stats.values():
                self._tasks.append(asyncio.create_task(f(self._host_data)))
            _LOGGER.debug("Gathering host data enabled.")
            try:
                self._oled = Oled(
                    host_data=self._host_data,
                    output_groups=list(self.grouped_outputs),
                    sleep_timeout=oled.get("screensaver_timeout", 60),
                )
            except (GPIOInputException, I2CError) as err:
                _LOGGER.error("Can't configure OLED display. %s", err)
        self.prepare_button(ha_discovery_prefix=ha_discovery_prefix)
        self.send_message(topic=f"{topic_prefix}/{STATE}", payload=ONLINE)
        _LOGGER.info("BoneIO manager is ready.")

    def _relay_callback(
        self, relay_type: str, relay_id: str, restore_state: bool
    ) -> None:
        """Relay callback function."""
        if restore_state:
            self._state_manager.save_attribute(
                attr_type=RELAY,
                attribute=relay_id,
                value=self._output[relay_id].is_active,
            )
        self._host_data_callback(type=relay_type)

    def _logger_reload(self) -> None:
        """_Logger reload function."""
        _config = load_config_from_file(config_file=self._config_file_path)
        if not _config:
            return
        configure_logger(log_config=_config.get("logger"), debug=-1)

    def _host_data_callback(self, type: str) -> None:
        if self._oled:
            self._oled.handle_data_update(type)

    def get_tasks(self) -> Set[asyncio.Task]:
        """Retrieve asyncio tasks to run."""
        return self._tasks

    def append_task(self, task: asyncio.Task) -> None:
        """Add task to run with asyncio loop."""
        self._tasks.append(task)

    def prepare_button(self, ha_discovery_prefix: str) -> None:
        """Prepare buttons for reload."""
        self.send_ha_autodiscovery(
            id="Logger",
            name="Logger",
            ha_type=BUTTON,
            ha_discovery_prefix=ha_discovery_prefix,
            availability_msg_func=ha_button_availabilty_message,
        )

    @property
    def mcp(self):
        """Get MCP by it's id."""
        return self._mcp

    def press_callback(
        self, x: ClickTypes, inpin: str, actions: List, input_type: InputTypes = INPUT
    ) -> None:
        """Press callback to use in input gpio.
        If relay input map is provided also toggle action on relay or cover or mqtt."""
        topic = f"{self._topic_prefix}/{input_type}/{inpin}"
        self.send_message(topic=topic, payload=x)
        for action_definition in actions:
            if action_definition[ACTION] == OUTPUT:
                device = action_definition.get(PIN)
                if not device:
                    continue
                relay = self._output.get(device.replace(" ", ""))
                if relay:
                    getattr(relay, action_definition["action_output"])()
            elif action_definition[ACTION] == MQTT:
                action_topic = action_definition.get(TOPIC)
                action_payload = action_definition.get("action_mqtt_msg")
                if action_topic and action_payload:
                    self.send_message(topic=action_topic, payload=action_payload)
            elif action_definition[ACTION] == COVER:
                device = action_definition.get(PIN)
                if not device:
                    continue
                cover = self._covers.get(device.replace(" ", ""))
                if cover:
                    getattr(cover, action_definition["action_cover"])()

        # This is similar how Z2M is clearing click sensor.
        self._loop.call_soon_threadsafe(
            self._loop.call_later, 0.2, self.send_message, topic, ""
        )

    def send_ha_autodiscovery(
        self,
        id: str,
        name: str,
        ha_discovery_prefix: str,
        ha_type: str,
        availability_msg_func: Callable,
        topic_prefix: str = None,
        **kwargs,
    ) -> None:
        """Send HA autodiscovery information for each relay."""
        if not self._ha_discovery:
            return
        if not topic_prefix:
            topic_prefix = self._topic_prefix
        msg = availability_msg_func(topic=topic_prefix, id=id, name=name, **kwargs)
        topic = f"{ha_discovery_prefix}/{ha_type}/{topic_prefix}/{id}/config"
        _LOGGER.debug("Sending HA discovery for %s, %s.", ha_type, name)
        self.send_message(topic=topic, payload=msg, retain=True)

    async def receive_message(self, topic: str, message: str) -> None:
        """Callback for receiving action from Mqtt."""
        assert topic.startswith(self._command_topic_prefix)
        topic_parts_raw = topic[len(self._command_topic_prefix) :].split("/")
        topic_parts = deque(topic_parts_raw)
        try:
            msg_type = topic_parts.popleft()
            device_id = topic_parts.popleft()
            command = topic_parts.pop()
        except IndexError:
            _LOGGER.error("Part of topic is missing. Not invoking command.")
            return

        if msg_type == RELAY and command == "set":
            target_device = self._output.get(device_id)
            if target_device and target_device.output_type != NONE:
                if message == ON:
                    target_device.turn_on()
                elif message == OFF:
                    target_device.turn_off()
        elif msg_type == COVER:
            cover = self._covers.get(device_id)
            if not cover:
                return
            if command == "set":
                if message in (
                    OPEN,
                    CLOSE,
                    STOP,
                    "toggle",
                    "toggle_open",
                    "toggle_close",
                ):
                    getattr(cover, message.lower())()
            elif command == "pos":
                position = int(message)
                if 0 <= position <= 100:
                    await cover.set_cover_position(position=position)
                else:
                    _LOGGER.warn(
                        "Positon cannot be set. Not number between 0-100. %s", message
                    )
        elif msg_type == BUTTON:
            if device_id == "logger" and command == "set":
                if message == "reload":
                    _LOGGER.info("Reloading logger configuration.")
                    self._logger_reload()

    @property
    def output(self) -> dict:
        """Get list of output."""
        return self._output
