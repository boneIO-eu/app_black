from __future__ import annotations
import asyncio
import logging
from collections import deque
import datetime
from typing import Callable, Coroutine, List, Optional, Set, Union, Awaitable
from board import SCL, SDA
from busio import I2C
from concurrent.futures import ThreadPoolExecutor


from boneio.const import (
    ACTION,
    ADDRESS,
    BINARY_SENSOR,
    BUTTON,
    CLOSE,
    COVER,
    DALLAS,
    EVENT_ENTITY,
    ID,
    INA219,
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
    cover_actions,
    DS2482,
    LIGHT,
    LED,
    SET_BRIGHTNESS,
    MCP,
    PCA,
    PCF,
)
from boneio.helper import (
    GPIOInputException,
    HostData,
    I2CError,
    StateManager,
    ha_button_availabilty_message,
    ha_light_availabilty_message,
    ha_switch_availabilty_message,
    ha_led_availabilty_message,
)
from boneio.helper.util import strip_accents
from boneio.helper.config import ConfigHelper
from boneio.helper.events import EventBus
from boneio.helper.exceptions import ModbusUartException
from boneio.helper.loader import (
    configure_cover,
    configure_event_sensor,
    configure_binary_sensor,
    configure_relay,
    configure_output_group,
    create_dallas_sensor,
    create_expander,
    create_temp_sensor,
)
from boneio.helper.logger import configure_logger
from boneio.helper.yaml_util import load_config_from_file
from boneio.modbus import Modbus

from w1thermsensor.errors import KernelModuleLoadError

_LOGGER = logging.getLogger(__name__)

AVAILABILITY_FUNCTION_CHOOSER = {
    LIGHT: ha_light_availabilty_message,
    LED: ha_led_availabilty_message,
}


class Manager:
    """Manager to communicate MQTT with GPIO inputs and outputs."""

    def __init__(
        self,
        send_message: Callable[[str, Union[str, dict], bool], None],
        stop_client: Callable[[], Awaitable[None]],
        mqtt_state: Callable[[], bool],
        state_manager: StateManager,
        config_helper: ConfigHelper,
        config_file_path: str,
        relay_pins: List = [],
        event_pins: List = [],
        binary_pins: List = [],
        output_group: List = [],
        sensors: dict = {},
        modbus: dict = {},
        pca9685: list = [],
        mcp23017: list = [],
        pcf8575: list = [],
        ds2482: Optional[List] = [],
        dallas: Optional[dict] = None,
        oled: dict = {},
        adc: Optional[List] = None,
        cover: list = [],
    ) -> None:
        """Initialize the manager."""
        _LOGGER.info("Initializing manager module.")

        self._loop = asyncio.get_event_loop()

        self._config_helper = config_helper
        self._host_data = None
        self._config_file_path = config_file_path
        self._state_manager = state_manager
        self._event_bus = EventBus(loop=self._loop)

        self.send_message = send_message
        self.stop_client = stop_client
        self._mqtt_state = mqtt_state
        self._event_pins = event_pins
        self._inputs = {}
        self._binary_pins = binary_pins
        self._i2cbusio = I2C(SCL, SDA)
        self._mcp = {}
        self._pcf = {}
        self._pca = {}
        self._output = {}
        self._configured_output_groups = {}
        self._oled = None
        self._tasks: List[asyncio.Task] = []
        self._covers = {}
        self._temp_sensors = []
        self._ina219_sensors = []
        self._modbus = None

        self._configure_modbus(modbus=modbus)

        self._configure_temp_sensors(sensors=sensors)

        self._configure_modbus_sensors(sensors=sensors)
        self._configure_ina219_sensors(sensors=sensors)
        self._configure_sensors(
            dallas=dallas, ds2482=ds2482, sensors=sensors.get(ONEWIRE)
        )

        self.grouped_outputs = create_expander(
            expander_dict=self._mcp,
            expander_config=mcp23017,
            exp_type=MCP,
            i2cbusio=self._i2cbusio,
        )
        self.grouped_outputs.update(
            create_expander(
                expander_dict=self._pcf,
                expander_config=pcf8575,
                exp_type=PCF,
                i2cbusio=self._i2cbusio,
            )
        )
        self.grouped_outputs.update(
            create_expander(
                expander_dict=self._pca,
                expander_config=pca9685,
                exp_type=PCA,
                i2cbusio=self._i2cbusio,
            )
        )

        self._configure_adc(adc_list=adc)

        for _config in relay_pins:
            _name = _config.pop(ID)
            _id = strip_accents(_name)
            out = configure_relay(
                manager=self,
                state_manager=self._state_manager,
                topic_prefix=self._config_helper.topic_prefix,
                name=_name,
                relay_id=_id,
                relay_callback=self._relay_callback,
                config=_config,
                event_bus=self._event_bus,
            )
            if not out:
                continue
            self._output[_id] = out
            if out.output_type not in (NONE, COVER):
                self.send_ha_autodiscovery(
                    id=out.id,
                    name=out.name,
                    ha_type=LIGHT if out.output_type == LED else out.output_type,
                    availability_msg_func=AVAILABILITY_FUNCTION_CHOOSER.get(
                        out.output_type, ha_switch_availabilty_message
                    ),
                )
            self._loop.call_soon_threadsafe(
                self._loop.call_later,
                0.5,
                out.send_state,
            )

        for _config in cover:
            _id = strip_accents(_config[ID])
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
            if open_relay.output_type != COVER or close_relay.output_type != COVER:
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

        self._output_group = output_group
        self._configure_output_group()
        self.executor = ThreadPoolExecutor()

        _LOGGER.info("Initializing inputs. This will take a while.")
        self.configure_inputs(reload_config=False)

        if oled.get("enabled", False):
            from boneio.oled import Oled

            screens = oled.get("screens", [])

            self._host_data = HostData(
                manager=self,
                enabled_screens=screens,
                output=self.grouped_outputs,
                temp_sensor=self._temp_sensors[0] if self._temp_sensors else None,
                ina219=self._ina219_sensors[0] if self._ina219_sensors else None,
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

    @property
    def mqtt_state(self) -> bool:
        return self._mqtt_state()

    def _configure_output_group(self):
        def get_outputs(output_list):
            outputs = []
            for x in output_list:
                x = strip_accents(x)
                if x in self._output:
                    output = self._output[x]
                    if output.output_type == COVER:
                        _LOGGER.warn("You can't add cover output to group.")
                    else:
                        outputs.append(output)
            return outputs

        for group in self._output_group:
            members = get_outputs(group.pop("outputs"))
            if not members:
                _LOGGER.warn(
                    "This group %s doesn't have any valid members. Not adding it.",
                    group[ID],
                )
                continue
            _LOGGER.debug("Configuring output group %s with members: %s", group[ID], [x.name for x in members])
            configured_group = configure_output_group(
                config=group,
                manager=self,
                state_manager=self._state_manager,
                topic_prefix=self._config_helper.topic_prefix,
                relay_id=group[ID].replace(" ", ""),
                event_bus=self._event_bus,
                members=members,
            )
            self._configured_output_groups[configured_group.id] = configured_group
            if configured_group.output_type != NONE:
                self.send_ha_autodiscovery(
                    id=configured_group.id,
                    name=configured_group.name,
                    ha_type=configured_group.output_type,
                    availability_msg_func=AVAILABILITY_FUNCTION_CHOOSER.get(
                        configured_group.output_type, ha_switch_availabilty_message
                    ),
                    device_type="group",
                    icon="mdi:lightbulb-group"
                    if configured_group.output_type == LIGHT
                    else "mdi:toggle-switch-variant",
                )
            self.append_task(
                coro=configured_group.event_listener, name=configured_group.id
            )

    def configure_inputs(self, reload_config: bool = False):
        """Configure inputs. Either events or binary sensors."""

        def check_if_pin_configured(pin: str) -> bool:
            if pin in self._inputs:
                if not reload_config:
                    _LOGGER.warn("This PIN %s is already configured. Omitting it.", pin)
                    return True
            return False

        def configure_single_input(configure_sensor_func, gpio) -> None:
            try:
                pin = gpio.pop(PIN)
            except AttributeError as err:
                _LOGGER.error("Wrong config. Can't configure %s. Error %s", gpio, err)
                return
            if check_if_pin_configured(pin=pin):
                return
            input = configure_sensor_func(
                gpio=gpio,
                pin=pin,
                press_callback=self.press_callback,
                send_ha_autodiscovery=self.send_ha_autodiscovery,
                input=self._inputs.get(pin, None),
            )
            if input:
                self._inputs[input.pin] = input

        if reload_config:
            config = load_config_from_file(self._config_file_path)
            if config:
                self._event_pins = config.get(EVENT_ENTITY, [])
                self._binary_pins = config.get(BINARY_SENSOR, [])
                self._config_helper.clear_autodiscovery_type(ha_type=EVENT_ENTITY)
                self._config_helper.clear_autodiscovery_type(ha_type=BINARY_SENSOR)
        for gpio in self._event_pins:
            configure_single_input(
                configure_sensor_func=configure_event_sensor, gpio=gpio
            )
        for gpio in self._binary_pins:
            configure_single_input(
                configure_sensor_func=configure_binary_sensor, gpio=gpio
            )

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
                from boneio.sensor.temp.dallas import DallasSensorW1

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
        uart = modbus.get(UART)
        if uart and uart in UARTS:
            try:
                self._modbus = Modbus(UARTS[uart])
            except ModbusUartException:
                _LOGGER.error(
                    "This UART %s can't be used for modbus communication.",
                    uart,
                )
                self._modbus = None

    def _configure_temp_sensors(self, sensors: dict) -> None:
        for sensor_type in (LM75, MCP_TEMP_9808):
            sensor = sensors.get(sensor_type)
            if sensor:
                for temp_def in sensor:
                    temp_sensor = create_temp_sensor(
                        manager=self,
                        topic_prefix=self._config_helper.topic_prefix,
                        sensor_type=sensor_type,
                        config=temp_def,
                        i2cbusio=self._i2cbusio,
                    )
                    if temp_sensor:
                        self._temp_sensors.append(temp_sensor)

    def _configure_ina219_sensors(self, sensors: dict) -> None:
        if sensors.get(INA219):
            from boneio.helper.loader import create_ina219_sensor

            for sensor_config in sensors[INA219]:
                ina219 = create_ina219_sensor(
                    topic_prefix=self._config_helper.topic_prefix,
                    manager=self,
                    config=sensor_config,
                )
                if ina219:
                    self._ina219_sensors.append(ina219)

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
        self,
        relay_id: str,
        restore_state: bool,
        save_host_data: bool = True,
        expander_id: str | None = None,
    ) -> None:
        """Relay callback function."""
        if restore_state:
            self._state_manager.save_attribute(
                attr_type=RELAY,
                attribute=relay_id,
                value=self._output[relay_id].is_active,
            )
        if save_host_data and expander_id:
            self._host_data_callback(type=expander_id)

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
            id="logger",
            name="Logger reload",
            ha_type=BUTTON,
            availability_msg_func=ha_button_availabilty_message,
            entity_category="config",
        )
        self.send_ha_autodiscovery(
            id="restart",
            name="Restart boneIO",
            ha_type=BUTTON,
            payload_press="restart",
            availability_msg_func=ha_button_availabilty_message,
            entity_category="config",
        )
        self.send_ha_autodiscovery(
            id="inputs_reload",
            name="Reload actions",
            ha_type=BUTTON,
            payload_press="inputs_reload",
            availability_msg_func=ha_button_availabilty_message,
            entity_category="config",
        )

    @property
    def mcp(self):
        """Get MCP by it's id."""
        return self._mcp

    @property
    def pca(self):
        """Get PCA by it's id."""
        return self._pca

    @property
    def pcf(self):
        """Get PCF by it's id."""
        return self._pcf

    async def press_callback(
        self,
        x: ClickTypes,
        inpin: str,
        actions: List,
        input_type: InputTypes = INPUT,
        empty_message_after: bool = False,
        duration: float | None = None,
    ) -> None:
        """Press callback to use in input gpio.
        If relay input map is provided also toggle action on relay or cover or mqtt."""
        topic = f"{self._config_helper.topic_prefix}/{input_type}/{inpin}"

        def generate_payload():
            if input_type == INPUT:
                if duration:
                    return {"event_type": x, "duration": duration}
                return {"event_type": x}
            return x

        def get_output_and_action(device_id, action, action_output, action_cover):
            if action == OUTPUT:
                return (
                    self._output.get(
                        strip_accents(device_id), self._configured_output_groups.get(device_id)
                    ),
                    relay_actions.get(action_output),
                )
            else:
                return (self._covers.get(strip_accents(device_id)), cover_actions.get(action_cover))
        for action_definition in actions:
            _LOGGER.debug("Executing action %s", action_definition)
            if action_definition[ACTION] in (OUTPUT, COVER):
                device = action_definition.get(PIN)
                if not device:
                    continue
                (output, action) = get_output_and_action(
                    device_id=device.replace(" ", ""),
                    action=action_definition[ACTION],
                    action_output=action_definition.get("action_output"),
                    action_cover=action_definition.get("action_cover"),
                )
                if output and action:
                    _f = getattr(output, action)
                    asyncio.create_task(_f())
                else:
                    if not action:
                        _LOGGER.warn("Action doesn't exists %s. Check spelling", action)
                    if not output:
                        _LOGGER.warn("Device %s for action not found", device)
            elif action_definition[ACTION] == MQTT:
                action_topic = action_definition.get(TOPIC)
                action_payload = action_definition.get("action_mqtt_msg")
                if action_topic and action_payload:
                    self.send_message(
                        topic=action_topic, payload=action_payload, retain=False
                    )
        self._loop.run_in_executor(self.executor, lambda: self.send_message(topic=topic, payload=generate_payload(), retain=False))
        # This is similar how Z2M is clearing click sensor.
        if empty_message_after:
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
        _LOGGER.debug("Sending HA discovery for %s entity, %s.", ha_type, name)
        self._config_helper.add_autodiscovery_msg(
            topic=topic, ha_type=ha_type, payload=payload
        )
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
                    _f = getattr(target_device, action_from_msg)
                    asyncio.create_task(_f())
                else:
                    _LOGGER.debug("Action not exist %s.", message.upper())
            else:
                _LOGGER.debug("Target device not found %s.", device_id)
        elif msg_type == RELAY and command == SET_BRIGHTNESS:
            target_device = self._output.get(device_id)
            if target_device and target_device.output_type != NONE and message != "":
                target_device.set_brightness(int(message))
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
        elif msg_type == "group" and command == "set":
            target_device = self._configured_output_groups.get(device_id)
            if target_device and target_device.output_type != NONE:
                action_from_msg = relay_actions.get(message.upper())
                if action_from_msg:
                    asyncio.create_task(getattr(target_device, action_from_msg)())
                else:
                    _LOGGER.debug("Action not exist %s.", message.upper())
            else:
                _LOGGER.debug("Target device not found %s.", device_id)
        elif msg_type == BUTTON and command == "set":
            if device_id == "logger" and message == "reload":
                _LOGGER.info("Reloading logger configuration.")
                self._logger_reload()
            elif device_id == "restart" and message == "restart":
                _LOGGER.info("Exiting process. Systemd should restart it soon.")
                await self.stop_client()
            elif device_id == "inputs_reload" and message == "inputs_reload":
                _LOGGER.info("Reloading events and binary sensors actions")
                self.configure_inputs(reload_config=True)

    @property
    def output(self) -> dict:
        """Get list of output."""
        return self._output
