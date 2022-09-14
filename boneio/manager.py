import asyncio
import logging
from collections import deque
from typing import Callable, Coroutine, List, Optional, Set, Union
from board import SCL, SDA
from busio import I2C

from boneio.const import (
    ACTION,
    ADDRESS,
    BUTTON,
    CLOSE,
    COVER,
    DALLAS,
    ID,
    INPUT,
    LM75,
    MCP_TEMP_9808,
    MODBUS,
    MQTT,
    NONE,
    ONEWIRE,
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
    relay_actions,
    DS2482,
)
from boneio.helper import (
    GPIOInputException,
    HostData,
    I2CError,
    StateManager,
    ha_button_availabilty_message,
    ha_light_availabilty_message,
    ha_switch_availabilty_message,
)
from boneio.helper.config import ConfigHelper
from boneio.helper.events import EventBus
from boneio.helper.exceptions import ModbusUartException
from boneio.helper.loader import (
    configure_cover,
    configure_input,
    configure_relay,
    create_dallas_sensor,
    create_mcp23017,
    create_temp_sensor,
)
from boneio.helper.logger import configure_logger
from boneio.helper.yaml_util import load_config_from_file
from boneio.modbus import Modbus

from w1thermsensor.errors import KernelModuleLoadError

_LOGGER = logging.getLogger(__name__)


class Manager:
    """Manager to communicate MQTT with GPIO inputs and outputs."""

    def __init__(
        self,
        send_message: Callable[[str, Union[str, dict], bool], None],
        state_manager: StateManager,
        config_helper: ConfigHelper,
        config_file_path: str,
        relay_pins: List = [],
        input_pins: List = [],
        sensors: dict = {},
        modbus: dict = None,
        mcp23017: Optional[List] = None,
        ds2482: Optional[List] = [],
        dallas: Optional[dict] = None,
        oled: dict = {},
        adc_list: Optional[List] = None,
        covers: Optional[List] = [],
    ) -> None:
        """Initialize the manager."""
        _LOGGER.info("Initializing manager module.")

        self._loop = asyncio.get_event_loop()
        self._config_helper = config_helper
        self._host_data = None
        self._config_file_path = config_file_path
        self._state_manager = state_manager
        self._event_bus = EventBus(self._loop)
        self._autodiscovery_messages = []

        self.send_message = send_message
        self._input_pins = input_pins
        self._i2cbusio = I2C(SCL, SDA)
        self._mcp = {}
        self._output = {}
        self._oled = None
        self._tasks: List[asyncio.Task] = []
        self._covers = {}
        self._temp_sensors = []
        self._modbus = None

        self._configure_modbus(modbus=modbus)

        self._configure_temp_sensors(sensors=sensors)

        self._configure_modbus_sensors(sensors=sensors)
        self._configure_sensors(
            dallas=dallas, ds2482=ds2482, sensors=sensors.get(ONEWIRE)
        )

        self.grouped_outputs = create_mcp23017(
            manager=self, mcp23017=mcp23017, i2cbusio=self._i2cbusio
        )

        self._configure_adc(adc_list=adc_list)

        for _config in relay_pins:
            _id = _config[ID].replace(" ", "")
            out = configure_relay(
                manager=self,
                state_manager=self._state_manager,
                topic_prefix=self._config_helper.topic_prefix,
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
            if not open_relay:
                _LOGGER.error(
                    "Can't configure cover %s. This relay doesn't exist.",
                    _config.get("open_relay"),
                )
                continue
            if not close_relay:
                _LOGGER.error(
                    "Can't configure cover %s. This relay doesn't exist.",
                    _config.get("close_relay"),
                )
                continue
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
                send_ha_autodiscovery=self.send_ha_autodiscovery,
                topic_prefix=self._config_helper.topic_prefix,
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
                    send_ha_autodiscovery=self.send_ha_autodiscovery,
                )
            )

        if oled.get("enabled", False):
            from boneio.oled import Oled

            screens = oled.get("screens")

            self._host_data = HostData(
                manager=self,
                enabled_screens=screens,
                output=self.grouped_outputs,
                temp_sensor=self._temp_sensors[0] if self._temp_sensors else None,
                callback=self._host_data_callback,
            )
            try:
                self._oled = Oled(
                    host_data=self._host_data,
                    screen_order=screens,
                    output_groups=list(self.grouped_outputs),
                    sleep_timeout=oled.get("screensaver_timeout", 60),
                )
            except (GPIOInputException, I2CError) as err:
                _LOGGER.error("Can't configure OLED display. %s", err)
        self.prepare_ha_buttons()

        _LOGGER.info("BoneIO manager is ready.")

    def append_task(self, coro: Coroutine, name: str = "Unknown") -> asyncio.Future:
        """Add task to run with asyncio loop."""
        _LOGGER.debug("Appending update task for %s", name)
        task: asyncio.Future = asyncio.create_task(coro())
        self._tasks.append(task)
        return task

    def _configure_sensors(
        self, dallas: Optional[dict], ds2482: Optional[List], sensors: Optional[List]
    ):
        """
        Configure Dallas sensors via GPIO PIN bus or DS2482 bus.
        """
        if not ds2482 and not dallas:
            return
        from boneio.helper.loader import (
            find_onewire_devices,
        )

        _one_wire_devices = {}
        _ds_onewire_bus = {}

        for _single_ds in ds2482:
            _LOGGER.debug("Preparing DS2482 bus at address %s.", _single_ds[ADDRESS])
            from boneio.helper.loader import (
                configure_ds2482,
            )
            from boneio.sensor import DallasSensorDS2482

            _ds_onewire_bus[_single_ds[ID]] = configure_ds2482(
                i2cbusio=self._i2cbusio, address=_single_ds[ADDRESS]
            )
            _one_wire_devices.update(
                find_onewire_devices(
                    ow_bus=_ds_onewire_bus[_single_ds[ID]],
                    bus_id=_single_ds[ID],
                    bus_type=DS2482,
                )
            )
        if dallas:
            _LOGGER.debug("Preparing Dallas bus.")
            from boneio.helper.loader import configure_dallas

            try:
                from w1thermsensor.kernel import load_kernel_modules

                load_kernel_modules()
                from boneio.sensor.temp.dallas_w1 import DallasSensorW1

                _one_wire_devices.update(
                    find_onewire_devices(
                        ow_bus=configure_dallas(),
                        bus_id=dallas[ID],
                        bus_type=DALLAS,
                    )
                )
            except KernelModuleLoadError as err:
                _LOGGER.error("Can't configure Dallas W1 device %s", err)
                pass

        for sensor in sensors:
            address = _one_wire_devices.get(sensor[ADDRESS])
            if not address:
                continue
            ds2482_bus_id = sensor.get("bus_id")
            if ds2482_bus_id and ds2482_bus_id in _ds_onewire_bus:
                kwargs = {
                    "bus": _ds_onewire_bus[ds2482_bus_id],
                    "cls": DallasSensorDS2482,
                }
            else:
                kwargs = {"cls": DallasSensorW1}
            _LOGGER.debug("Configuring sensor %s for boneIO", address)
            self._temp_sensors.append(
                create_dallas_sensor(
                    manager=self,
                    address=address,
                    topic_prefix=self._config_helper.topic_prefix,
                    config=sensor,
                    **kwargs,
                )
            )

    def _configure_adc(self, adc_list: Optional[List]) -> None:
        if adc_list:
            from boneio.helper.loader import create_adc

            create_adc(
                manager=self,
                topic_prefix=self._config_helper.topic_prefix,
                adc_list=adc_list,
            )

    def _configure_modbus(self, modbus: dict) -> None:
        if modbus and modbus.get(UART) in UARTS:
            try:
                self._modbus = Modbus(UARTS[modbus.get(UART)])
            except ModbusUartException:
                _LOGGER.error(
                    "This UART %s can't be used for modbus communication.",
                    modbus.get(UART),
                )
                self._modbus = None

    def _configure_temp_sensors(self, sensors: dict) -> None:
        for sensor_type in (LM75, MCP_TEMP_9808):
            if sensors.get(sensor_type):
                for temp_def in sensors.get(sensor_type):
                    temp_sensor = create_temp_sensor(
                        manager=self,
                        topic_prefix=self._config_helper.topic_prefix,
                        sensor_type=sensor_type,
                        config=temp_def,
                        i2cbusio=self._i2cbusio,
                    )
                    if temp_sensor:
                        self._temp_sensors.append(temp_sensor)

    def _configure_modbus_sensors(self, sensors: dict) -> None:
        if sensors.get(MODBUS) and self._modbus:
            from boneio.helper.loader import create_modbus_sensors

            create_modbus_sensors(
                manager=self,
                event_bus=self._event_bus,
                sensors=sensors.get(MODBUS),
                modbus=self._modbus,
                config_helper=self._config_helper,
            )

    async def reconnect_callback(self) -> None:
        """Function to invoke when connection to MQTT is (re-)established."""
        _LOGGER.info("Sending online state.")
        topic = f"{self._config_helper.topic_prefix}/{STATE}"
        self.send_message(topic=topic, payload=ONLINE, retain=True)

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

    def prepare_ha_buttons(self) -> None:
        """Prepare HA buttons for reload."""
        self.send_ha_autodiscovery(
            id="Logger",
            name="Logger reload",
            ha_type=BUTTON,
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
        topic = f"{self._config_helper.topic_prefix}/{input_type}/{inpin}"
        self.send_message(topic=topic, payload=x)
        for action_definition in actions:
            _LOGGER.debug("Executing action %s", action_definition)
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
        ha_type: str,
        availability_msg_func: Callable,
        topic_prefix: str = None,
        **kwargs,
    ) -> None:
        """Send HA autodiscovery information for each relay."""
        if not self._config_helper.ha_discovery:
            return
        topic_prefix = topic_prefix or self._config_helper.topic_prefix
        payload = availability_msg_func(topic=topic_prefix, id=id, name=name, **kwargs)
        topic = f"{self._config_helper.ha_discovery_prefix}/{ha_type}/{topic_prefix}/{id}/config"
        _LOGGER.debug("Sending HA discovery for %s, %s.", ha_type, name)
        self._config_helper.add_autodiscovery_msg(topic=topic, payload=payload)
        self.send_message(topic=topic, payload=payload, retain=True)

    def resend_autodiscovery(self) -> None:
        for msg in self._config_helper.autodiscovery_msgs:
            self.send_message(**msg, retain=True)

    async def receive_message(self, topic: str, message: str) -> None:
        """Callback for receiving action from Mqtt."""
        _LOGGER.debug("Processing topic %s with message %s.", topic, message)
        if topic.startswith(f"{self._config_helper.ha_discovery_prefix}/status"):
            if message == ONLINE:
                self.resend_autodiscovery()
                self._event_bus.signal_ha_online()
            return
        assert topic.startswith(self._config_helper.cmd_topic_prefix)
        topic_parts_raw = topic[len(self._config_helper.cmd_topic_prefix) :].split("/")
        topic_parts = deque(topic_parts_raw)
        try:
            msg_type = topic_parts.popleft()
            device_id = topic_parts.popleft()
            command = topic_parts.pop()
            _LOGGER.debug(
                "Divide topic to: msg_type: %s, device_id: %s, command: %s",
                msg_type,
                device_id,
                command,
            )
        except IndexError:
            _LOGGER.error("Part of topic is missing. Not invoking command.")
            return

        if msg_type == RELAY and command == "set":
            target_device = self._output.get(device_id)

            if target_device and target_device.output_type != NONE:
                action_from_msg = relay_actions.get(message.upper())
                if action_from_msg:
                    getattr(target_device, action_from_msg)()
                else:
                    _LOGGER.debug("Action not exist %s.", message.upper())
            else:
                _LOGGER.debug("Target device not found %s.", device_id)
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
        elif msg_type == BUTTON and command == "set":
            if device_id == "logger" and message == "reload":
                _LOGGER.info("Reloading logger configuration.")
                self._logger_reload()

    @property
    def output(self) -> dict:
        """Get list of output."""
        return self._output
