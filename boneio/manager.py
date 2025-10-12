from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from typing import Callable, Coroutine, List, Optional, Set

from board import SCL, SDA
from busio import I2C
from w1thermsensor.errors import KernelModuleLoadError

from boneio.const import (
    ACTIONS,
    ADDRESS,
    BINARY_SENSOR,
    BUTTON,
    CLOSE,
    COVER,
    COVER_OVER_MQTT,
    DALLAS,
    DS2482,
    EVENT_ENTITY,
    ID,
    INA219,
    INPUT,
    IP,
    LED,
    LIGHT,
    LM75,
    MCP,
    MCP_TEMP_9808,
    MQTT,
    NONE,
    ON,
    ONEWIRE,
    ONLINE,
    OPEN,
    OUTPUT,
    OUTPUT_OVER_MQTT,
    PCA,
    PCF,
    PIN,
    RELAY,
    RESTORE_STATE,
    SET_BRIGHTNESS,
    STATE,
    STOP,
    SWITCH,
    TOPIC,
    UART,
    UARTS,
    VALVE,
    ClickTypes,
    cover_actions,
    relay_actions,
)
from boneio.cover import PreviousCover, TimeBasedCover
from boneio.helper import (
    GPIOInputException,
    HostData,
    I2CError,
    StateManager,
    ha_button_availabilty_message,
    ha_led_availabilty_message,
    ha_light_availabilty_message,
    ha_switch_availabilty_message,
)
from boneio.helper.config import ConfigHelper
from boneio.helper.events import EventBus
from boneio.helper.exceptions import CoverConfigurationException, ModbusUartException
from boneio.helper.gpio import GpioBaseClass
from boneio.helper.ha_discovery import ha_valve_availabilty_message
from boneio.helper.interlock import SoftwareInterlockManager
from boneio.helper.loader import (
    configure_binary_sensor,
    configure_cover,
    configure_event_sensor,
    configure_output_group,
    configure_relay,
    create_dallas_sensor,
    create_expander,
    create_serial_number_sensor,
    create_temp_sensor,
)
from boneio.helper.logger import configure_logger
from boneio.helper.util import strip_accents
from boneio.helper.yaml_util import load_config_from_file
from boneio.message_bus import MessageBus
from boneio.modbus.client import Modbus
from boneio.modbus.coordinator import ModbusCoordinator
from boneio.models import OutputState
from boneio.relay.basic import BasicRelay
from boneio.sensor.temp import TempSensor

_LOGGER = logging.getLogger(__name__)

AVAILABILITY_FUNCTION_CHOOSER = {
    LIGHT: ha_light_availabilty_message,
    LED: ha_led_availabilty_message,
    SWITCH: ha_switch_availabilty_message,
    VALVE: ha_valve_availabilty_message,
}


class Manager:
    """Manager to communicate MQTT with GPIO inputs and outputs."""

    def __init__(
        self,
        message_bus: MessageBus,
        event_bus: EventBus,
        state_manager: StateManager,
        config_helper: ConfigHelper,
        config_file_path: str,
        relay_pins: List = [],
        event_pins: List = [],
        binary_pins: List = [],
        output_group: List = [],
        sensors: dict = {},
        modbus: dict = {},
        modbus_devices: dict = {},
        pca9685: list = [],
        mcp23017: list = [],
        pcf8575: list = [],
        ds2482: Optional[List] = [],
        dallas: Optional[dict] = None,
        oled: dict = {},
        adc: Optional[List] = None,
        cover: list = [],
        web_active: bool = False,
        web_port: int = 8090,
    ) -> None:
        """Initialize the manager."""
        _LOGGER.info("Initializing manager module.")

        self._loop = asyncio.get_event_loop()

        self._config_helper: ConfigHelper = config_helper
        self._host_data = None
        self._config_file_path = config_file_path
        self._state_manager = state_manager
        self._event_bus = event_bus
        self._is_web_on = web_active
        self._web_bind_port = web_port

        self._message_bus: MessageBus = message_bus

        self.send_message = message_bus.send_message
        self._mqtt_state = message_bus.state
        self._event_pins = event_pins
        self._inputs = {}
        self._binary_pins = binary_pins
        self._i2cbusio = I2C(SCL, SDA)
        self._mcp = {}
        self._pcf = {}
        self._pca = {}
        self._outputs: dict[str, BasicRelay] = {}
        self._configured_output_groups = {}
        self._interlock_manager = SoftwareInterlockManager()

        self._oled = None
        self._tasks: List[asyncio.Task] = []
        self._config_covers = cover
        self._covers: dict[str, PreviousCover | TimeBasedCover] = {}
        self._temp_sensors: List[TempSensor] = []
        self._ina219_sensors = []
        self._modbus_coordinators = {}
        self._modbus = None
        self._screens = []

        self._configure_modbus(modbus=modbus)

        self._configure_temp_sensors(sensors=sensors)

        self._modbus_coordinators = {}
        self._configure_ina219_sensors(sensors=sensors)
        self._configure_sensors(
            dallas=dallas, ds2482=ds2482, sensors=sensors.get(ONEWIRE)
        )

        self.grouped_outputs_by_expander = create_expander(
            expander_dict=self._mcp,
            expander_config=mcp23017,
            exp_type=MCP,
            i2cbusio=self._i2cbusio,
        )
        self.grouped_outputs_by_expander.update(
            create_expander(
                expander_dict=self._pcf,
                expander_config=pcf8575,
                exp_type=PCF,
                i2cbusio=self._i2cbusio,
            )
        )
        self.grouped_outputs_by_expander.update(
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
            restore_state = _config.pop(RESTORE_STATE, False)
            _id = strip_accents(_name)
            _LOGGER.debug("Configuring relay: %s", _id)
            out = configure_relay(  # grouped_output updated here.
                manager=self,
                message_bus=message_bus,
                state_manager=self._state_manager,
                topic_prefix=self._config_helper.topic_prefix,
                name=_name,
                restore_state=restore_state,
                relay_id=_id,
                config=_config,
                event_bus=self._event_bus,
            )
            if not out:
                continue
            if restore_state:
                self._event_bus.add_event_listener(
                    event_type="output",
                    entity_id=out.id,
                    listener_id="manager",
                    target=self._relay_callback,
                )
            self._outputs[_id] = out
            if out.output_type not in (NONE, COVER):
                self.send_ha_autodiscovery(
                    id=out.id,
                    name=out.name,
                    ha_type=(LIGHT if out.output_type == LED else out.output_type),
                    availability_msg_func=AVAILABILITY_FUNCTION_CHOOSER.get(
                        out.output_type, ha_switch_availabilty_message
                    ),
                )
            self._loop.create_task(self._delayed_send_state(out))

        if self._outputs:
            self._configure_covers()

        self._outputs_group = output_group
        self._configure_output_group()

        _LOGGER.info("Initializing inputs. This will take a while.")
        self.configure_inputs(reload_config=False)

        self._serial_number_sensor = create_serial_number_sensor(
            manager=self,
            message_bus=self._message_bus,
            topic_prefix=self._config_helper.topic_prefix,
        )
        self._modbus_coordinators = self._configure_modbus_coordinators(devices=modbus_devices)

        if oled.get("enabled", False):
            from boneio.oled import Oled

            self._screens = oled.get("screens", [])
            extra_sensors = oled.get("extra_screen_sensors", [])

            self._host_data = HostData(
                manager=self,
                event_bus=self._event_bus,
                enabled_screens=self._screens,
                output=self.grouped_outputs_by_expander,
                inputs=self._inputs,
                temp_sensor=(self._temp_sensors[0] if self._temp_sensors else None),
                ina219=(self._ina219_sensors[0] if self._ina219_sensors else None),
                extra_sensors=extra_sensors,
            )
            try:
                self._oled = Oled(
                    host_data=self._host_data,
                    screen_order=self._screens,
                    grouped_outputs_by_expander=list(self.grouped_outputs_by_expander),
                    sleep_timeout=oled.get("screensaver_timeout", 60),
                    event_bus=self._event_bus,
                )
            except (GPIOInputException, I2CError) as err:
                _LOGGER.error("Can't configure OLED display. %s", err)
            finally:
                if self._oled:
                    self._oled.render_display()
        self.prepare_ha_buttons()
        _LOGGER.info("BoneIO manager is ready.")

    def set_web_server_status(self, status: bool, bind: int):
        self._is_web_on = status
        self._web_bind_port = bind

    @property
    def is_web_on(self) -> bool:
        return self._is_web_on

    @property
    def web_bind_port(self) -> int | None:
        return self._web_bind_port

    @property
    def mqtt_state(self) -> bool:
        return self._mqtt_state()

    @property
    def ina219_sensors(self) -> list:
        return self._ina219_sensors

    @property
    def modbus_coordinators(self) -> dict[str, ModbusCoordinator]:
        return self._modbus_coordinators

    @property
    def temp_sensors(self) -> list[TempSensor]:
        return self._temp_sensors

    @property
    def output_groups(self) -> dict:
        return self._configured_output_groups

    def _configure_output_group(self):
        def get_outputs(output_list):
            outputs = []
            for x in output_list:
                x = strip_accents(x)
                if x in self._outputs:
                    output = self._outputs[x]
                    if output.output_type == COVER:
                        _LOGGER.warning("You can't add cover output to group.")
                    else:
                        outputs.append(output)
            return outputs

        for group in self._outputs_group:
            members = get_outputs(group.pop("outputs"))
            if not members:
                _LOGGER.warning(
                    "This group %s doesn't have any valid members. Not adding it.",
                    group[ID],
                )
                continue
            _LOGGER.debug(
                "Configuring output group %s with members: %s",
                group[ID],
                [x.name for x in members],
            )
            configured_group = configure_output_group(
                config=group,
                message_bus=self._message_bus,
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
                        configured_group.output_type,
                        ha_switch_availabilty_message,
                    ),
                    device_type="group",
                    icon=(
                        "mdi:lightbulb-group"
                        if configured_group.output_type == LIGHT
                        else "mdi:toggle-switch-variant"
                    ),
                )
            self.append_task(
                coro=configured_group.event_listener, name=configured_group.id
            )

    def _configure_covers(self, reload_config: bool = False):
        """Configure covers."""
        if reload_config:
            config = load_config_from_file(self._config_file_path)
            self._config_covers = config.get(COVER, [])
            self._config_helper.clear_autodiscovery_type(ha_type=COVER)
        for _config in self._config_covers:
            _id = strip_accents(_config[ID])
            open_relay = self._outputs.get(_config.get("open_relay"))
            close_relay = self._outputs.get(_config.get("close_relay"))
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
                    "Can't configure cover %s. %s. Current types are: %s, %s",
                    _id,
                    "You have to explicitly set types of relays to Cover so you can't turn it on directly.",
                    open_relay.output_type,
                    close_relay.output_type,
                )
                continue
            try:
                if _id in self._covers:
                    _cover = self._covers[_id]
                    _cover.update_config_times(_config)
                    continue
                self._covers[_id] = configure_cover(
                    message_bus=self._message_bus,
                    cover_id=_id,
                    state_manager=self._state_manager,
                    config=_config,
                    open_relay=open_relay,
                    close_relay=close_relay,
                    open_time=_config.get("open_time"),
                    close_time=_config.get("close_time"),
                    tilt_duration=_config.get("tilt_duration"),
                    event_bus=self._event_bus,
                    send_ha_autodiscovery=self.send_ha_autodiscovery,
                    topic_prefix=self._config_helper.topic_prefix,
                )

            except CoverConfigurationException as err:
                _LOGGER.error("Can't configure cover %s. %s", _id, err)
                continue

    def parse_actions(self, pin: str, actions: dict) -> dict:
        """Parse actions from config."""
        parsed_actions = {}
        for click_type in actions:
            if click_type not in parsed_actions:
                parsed_actions[click_type] = []
            for action_definition in actions.get(click_type, []):
                action = action_definition.get("action")
                if action == OUTPUT:
                    entity_id = action_definition.get("pin")
                    stripped_entity_id = strip_accents(entity_id)
                    action_output = action_definition.get("action_output")
                    output = self._outputs.get(stripped_entity_id, self._configured_output_groups.get(stripped_entity_id))
                    action_to_execute = relay_actions.get(action_output)
                    if output and action_to_execute:
                        _f = getattr(output, action_to_execute)
                        if _f:
                            parsed_actions[click_type].append({
                                "action": action,
                                "pin": stripped_entity_id,
                                "action_to_execute": action_to_execute,
                            })
                            continue
                    _LOGGER.warning("Device %s for action in %s not found. Omitting.", entity_id, pin)
                elif action == COVER:
                    entity_id = action_definition.get("pin")
                    stripped_entity_id = strip_accents(entity_id)
                    action_cover = action_definition.get("action_cover")
                    extra_data = action_definition.get("data", {})
                    cover = self._covers.get(stripped_entity_id)
                    action_to_execute = cover_actions.get(action_cover)
                    if cover and action_to_execute:
                        _f = getattr(cover, action_to_execute)
                        if _f:
                            parsed_actions[click_type].append({
                                "action": action,
                                "action_to_execute": action_to_execute,
                                "pin": stripped_entity_id,
                                "extra_data": extra_data,
                            })
                            continue
                    _LOGGER.warning("Device %s for action not found. Omitting.", entity_id)
                elif action == MQTT:
                    action_mqtt_msg = action_definition.get("action_mqtt_msg")
                    action_topic = action_definition.get(TOPIC)
                    if action_topic and action_mqtt_msg:
                        parsed_actions[click_type].append({
                            "action": action,
                            "action_mqtt_msg": action_mqtt_msg,
                            "action_topic": action_topic,
                        })
                        continue
                    _LOGGER.warning("Device %s for action not found. Omitting.", entity_id)
                elif action == OUTPUT_OVER_MQTT:
                    boneio_id = action_definition.get("boneio_id")
                    action_output = action_definition.get("action_output")
                    action_to_execute = relay_actions.get(action_output.upper())
                    if boneio_id and action_to_execute:
                        parsed_actions[click_type].append({
                            "action": action,
                            "boneio_id": boneio_id,
                            "action_output": action_output,
                        })
                        continue
                    _LOGGER.warning("Device %s for action not found. Omitting.", entity_id)
                elif action == COVER_OVER_MQTT:
                    boneio_id = action_definition.get("boneio_id")
                    action_cover = action_definition.get("action_cover")
                    action_to_execute = cover_actions.get(action_cover.upper())
                    if boneio_id and action_to_execute:
                        parsed_actions[click_type].append({
                            "action": action,
                            "boneio_id": boneio_id,
                            "action_cover": action_cover,
                        })
                        continue
                    _LOGGER.warning("Device %s for action not found. Omitting.", entity_id)
        return parsed_actions

    def configure_inputs(self, reload_config: bool = False):
        """Configure inputs. Either events or binary sensors."""

        def check_if_pin_configured(pin: str) -> bool:
            if pin in self._inputs:
                if not reload_config:
                    _LOGGER.warning(
                        "This PIN %s is already configured. Omitting it.", pin
                    )
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
                manager_press_callback=self.press_callback,
                event_bus=self._event_bus,
                send_ha_autodiscovery=self.send_ha_autodiscovery,
                input=self._inputs.get(pin, None),  # for reload actions.
                actions=self.parse_actions(pin, gpio.pop(ACTIONS, {})),
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

    def append_task(
        self, coro: Coroutine, name: str = "Unknown", **kwargs
    ) -> asyncio.Task:
        """Add task to run with asyncio loop."""
        _LOGGER.debug("Appending update task for %s", name)
        task: asyncio.Task = asyncio.create_task(coro(**kwargs))
        self._tasks.append(task)
        return task

    @property
    def inputs(self) -> List[GpioBaseClass]:
        return list(self._inputs.values())

    def _configure_sensors(
        self,
        dallas: Optional[dict],
        ds2482: Optional[List],
        sensors: Optional[List],
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
                    message_bus=self._message_bus,
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
                message_bus=self._message_bus,
                topic_prefix=self._config_helper.topic_prefix,
                adc_list=adc_list,
            )

    def _configure_modbus(self, modbus: dict) -> None:
        uart = modbus.get(UART)
        if uart and uart in UARTS:
            try:
                self._modbus = Modbus(
                    uart=UARTS[uart],
                    baudrate=modbus.get("baudrate", 9600),
                    stopbits=modbus.get("stopbits", 1),
                    bytesize=modbus.get("bytesize", 8),
                    parity=modbus.get("parity", "N"),
                )
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
                        message_bus=self._message_bus,
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
                    message_bus=self._message_bus,
                    config=sensor_config,
                )
                if ina219:
                    self._ina219_sensors.append(ina219)

    def _configure_modbus_coordinators(self, devices: dict) -> dict:
        if devices and self._modbus:
            from boneio.helper.loader import create_modbus_coordinators

            return create_modbus_coordinators(
                manager=self,
                message_bus=self._message_bus,
                event_bus=self._event_bus,
                entries=devices,
                modbus=self._modbus,
                config_helper=self._config_helper,
            )
        return {}

    async def reconnect_callback(self) -> None:
        """Function to invoke when connection to MQTT is (re-)established."""
        _LOGGER.info("Sending online state.")
        topic = f"{self._config_helper.topic_prefix}/{STATE}"
        self.send_message(topic=topic, payload=ONLINE, retain=True)

    @property
    def event_bus(self) -> EventBus:
        return self._event_bus

    async def _relay_callback(
        self,
        event: OutputState,
    ) -> None:
        """Relay callback function."""
        self._state_manager.save_attribute(
            attr_type=RELAY,
            attribute=event.id,
            value=event.state == ON,
        )

    def _logger_reload(self) -> None:
        """_Logger reload function."""
        _config = load_config_from_file(config_file=self._config_file_path)
        if not _config:
            return
        configure_logger(log_config=_config.get("logger"), debug=-1)

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
        if self._covers:
            self.send_ha_autodiscovery(
                id="cover_reload",
                name="Reload times of covers",
                ha_type=BUTTON,
                payload_press="cover_reload",
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
        gpio: GpioBaseClass,
        empty_message_after: bool = False,
        duration: float | None = None,
        start_time: float | None = None,
    ) -> None:
        """Press callback to use in input gpio.
        If relay input map is provided also toggle action on relay or cover or mqtt.
        """
        actions = gpio.get_actions_of_click(click_type=x)
        topic = f"{self._config_helper.topic_prefix}/{gpio.input_type}/{gpio.pin}"


        def generate_payload():
            if gpio.input_type == INPUT:
                if duration:
                    return {"event_type": x, "duration": duration}
                return {"event_type": x}
            return x

        for action_definition in actions:
            entity_id = action_definition.get("pin")
            action = action_definition.get("action")
            
            if action == MQTT:
                action_topic = action_definition.get(TOPIC)
                action_payload = action_definition.get("action_mqtt_msg")
                if action_topic and action_payload:
                    self.send_message(
                        topic=action_topic, payload=action_payload, retain=False
                    )
                continue
            elif action == OUTPUT:
                output = self._outputs.get(entity_id, self._configured_output_groups.get(entity_id))
                action_to_execute = action_definition.get("action_to_execute")
                _LOGGER.debug(
                    "Executing action %s for output %s. Duration: %s",
                    action_to_execute,
                    output.name,
                    time.time() - start_time,
                )
                _f = getattr(output, action_to_execute)
                await _f()
            elif action == COVER:
                cover = self._covers.get(entity_id)
                action_to_execute = action_definition.get("action_to_execute")
                extra_data = action_definition.get("extra_data", {})
                _LOGGER.debug(
                    "Executing action %s for cover %s. Duration: %s",
                    action_to_execute,
                    cover.name,
                    time.time() - start_time,
                )
                _f = getattr(cover, action_to_execute)
                await _f(**extra_data)
            elif action == OUTPUT_OVER_MQTT:
                boneio_id = action_definition.get("boneio_id")
                self.send_message(
                    topic=f"{boneio_id}/cmd/relay/{entity_id}/set",
                    payload=action_definition.get("action_output"),
                    retain=False,
                )
            elif action == COVER_OVER_MQTT:
                boneio_id = action_definition.get("boneio_id")
                self.send_message(
                        topic=f"{boneio_id}/cmd/cover/{entity_id}/set",
                        payload=action_definition.get("action_cover"),
                        retain=False,
                    )

        payload = generate_payload()
        _LOGGER.debug("Sending message %s for input %s", payload, topic)
        self.send_message(topic=topic, payload=payload, retain=False)
        # This is similar how Z2M is clearing click sensor.
        if empty_message_after:
            self._loop.call_soon_threadsafe(
                self._loop.call_later, 0.2, self.send_message, topic, ""
            )

    async def toggle_output(self, output_id: str) -> str:
        """Toggle output state."""
        output = self._outputs.get(output_id)
        if output:
            if output.output_type == NONE or output.output_type == COVER:
                return "not_allowed"
            if not output.check_interlock():
                return "interlock"
            await output.async_toggle()
            return "success"
        return "not_found"

    async def receive_message(self, topic: str, message: str) -> None:
        """Callback for receiving action from Mqtt."""
        _LOGGER.debug("Processing topic %s with message %s.", topic, message)
        if topic.startswith(f"{self._config_helper.ha_discovery_prefix}/status"):
            if message == ONLINE:
                self.resend_autodiscovery()
                self._event_bus.signal_ha_online()
            return
        try:
            assert topic.startswith(self._config_helper.cmd_topic_prefix)
        except AssertionError as err:
            _LOGGER.error("Wrong topic %s. Error %s", topic, err)
            return
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
            target_device = self._outputs.get(device_id)

            if target_device and target_device.output_type != NONE:
                action_from_msg = relay_actions.get(message.upper())
                if action_from_msg:
                    _f = getattr(target_device, action_from_msg)
                    await _f()
                else:
                    _LOGGER.debug("Action not exist %s.", message.upper())
            else:
                _LOGGER.debug("Target device not found %s.", device_id)
        elif msg_type == RELAY and command == SET_BRIGHTNESS:
            target_device = self._outputs.get(device_id)
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
                    _f = getattr(cover, message.lower())
                    await _f()
            elif command == "pos":
                try:
                    await cover.set_cover_position(position=int(message))
                except ValueError as err:
                    _LOGGER.warning(err)
            elif command == "tilt":
                if message == STOP:
                    await cover.stop()
                else:
                    try:
                        await cover.set_tilt(tilt_position=int(message))
                    except ValueError as err:
                        _LOGGER.warning(err)
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
                await self.restart_request()
            elif device_id == "inputs_reload" and message == "inputs_reload":
                _LOGGER.info("Reloading events and binary sensors actions")
                self.configure_inputs(reload_config=True)
            elif device_id == "cover_reload" and message == "cover_reload":
                _LOGGER.info("Reloading covers actions")
                self._configure_covers(reload_config=True)
        elif msg_type == "modbus" and command == "set":
            target_device = self._modbus_coordinators.get(device_id)
            if target_device:
                if isinstance(message, str):
                    message = json.loads(message)
                    if "device" in message and "value" in message:
                        await target_device.write_register(value=message["value"], entity=message["device"])

    async def restart_request(self) -> None:
        _LOGGER.info("Restarting process. Systemd should restart it soon.")
        import os

        os._exit(0)  # Terminate the process

    @property
    def outputs(self) -> dict:
        """Get list of output."""
        return self._outputs

    @property
    def covers(self) -> dict:
        """Get list of covers."""
        return self._covers

    async def _delayed_send_state(self, output):
        """Send state after a delay."""
        await asyncio.sleep(0.5)
        await output.async_send_state()

    async def handle_actions(self, actions: dict) -> None:
        """Handle actions."""
        for action in actions:
            if action == MQTT:
                topic = actions[action].get(TOPIC)
                payload = actions[action].get("payload")
                if topic and payload:
                    self.send_message(topic=topic, payload=payload, retain=False)
            elif action == OUTPUT:
                output_id = actions[action].get(ID)
                output_action = actions[action].get("action")
                output = self._outputs.get(output_id)
                if output and output_action:
                    _f = getattr(output, output_action)
                    await _f()
            elif action == COVER:
                cover_id = actions[action].get(ID)
                cover_action = actions[action].get("action")
                cover = self._covers.get(cover_id)
                if cover and cover_action:
                    _f = getattr(cover, cover_action)
                    await _f()

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
        web_url = None
        if self._config_helper.is_web_active:
            if self._host_data:
                web_url = self._host_data.web_url
            elif self._config_helper.network_info and IP in self._config_helper.network_info:
                web_url = f"http://{self._config_helper.network_info[IP]}:{self._web_bind_port}"
        payload = availability_msg_func(
            topic=topic_prefix,
            id=id,
            name=name,
            model=self._config_helper.device_type.title(),
            device_name=self._config_helper.name,
            web_url=web_url,
            **kwargs,
        )
        topic = f"{self._config_helper.ha_discovery_prefix}/{ha_type}/{topic_prefix}/{id}/config"
        _LOGGER.debug("Sending HA discovery for %s entity, %s.", ha_type, name)
        self._config_helper.add_autodiscovery_msg(
            topic=topic, ha_type=ha_type, payload=payload
        )
        self.send_message(topic=topic, payload=payload, retain=True)

    def resend_autodiscovery(self) -> None:
        for msg in self._config_helper.autodiscovery_msgs:
            self.send_message(**msg, retain=True)
