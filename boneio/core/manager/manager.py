"""Main Manager class - orchestrates all subsystems.

This is the central coordinator that manages all BoneIO subsystems.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any

from boneio.const import (
    BUTTON,
    COVER,
    COVER_OVER_MQTT,
    MQTT,
    NONE,
    ONLINE,
    OUTPUT,
    OUTPUT_OVER_MQTT,
    SET_BRIGHTNESS,
    STATE,
    cover_actions,
    output_actions,
)
from boneio.core.config import ConfigHelper
from boneio.core.events import EventBus
from boneio.core.manager.covers import CoverManager
from boneio.core.manager.display import DisplayManager
from boneio.core.manager.inputs import InputManager
from boneio.core.manager.modbus import ModbusManager
from boneio.core.manager.outputs import OutputManager
from boneio.core.manager.sensors import SensorManager
from boneio.core.manager.remote import RemoteDeviceManager
from boneio.core.discovery import BlackDiscoveryPublisher
from boneio.core.messaging import MessageBus
from boneio.core.state import StateManager
from boneio.hardware.i2c.bus import SMBus2I2C

if TYPE_CHECKING:
    pass

_LOGGER = logging.getLogger(__name__)


class Manager:
    """Main application manager - orchestrates all subsystems.
    
    This class coordinates:
    - Outputs (relay, switch, light, LED, valve)
    - Inputs (event, binary_sensor)
    - Covers (time-based, previous-state, venetian)
    - Sensors (temperature, power, analog)
    - Modbus (RTU/TCP devices)
    - Display (OLED)
    
    Each subsystem is managed by a dedicated sub-manager for better
    separation of concerns and maintainability.
    
    Args:
        message_bus: MQTT message bus
        event_bus: Internal event bus
        state_manager: State persistence manager
        config_helper: Configuration helper
        config_file_path: Path to config file
        relay_pins: List of relay configurations
        event_pins: List of event button configurations
        binary_pins: List of binary sensor configurations
        output_group: List of output group configurations
        sensors: Dictionary of sensor configurations
        modbus: Modbus client configuration
        modbus_devices: Dictionary of Modbus device configurations
        pca9685: List of PCA9685 configurations
        mcp23017: List of MCP23017 configurations
        pcf8575: List of PCF8575 configurations
        ds2482: List of DS2482 configurations
        dallas: Dallas 1-Wire configuration
        oled: OLED display configuration
        adc: List of ADC configurations
        cover: List of cover configurations
        web_active: Whether web server is active
        web_port: Web server port
    """

    def __init__(
        self,
        message_bus: MessageBus,
        event_bus: EventBus,
        state_manager: StateManager,
        config_helper: ConfigHelper,
        config_file_path: str,
        relay_pins: list[dict] = [],
        event_pins: list[dict] = [],
        binary_pins: list[dict] = [],
        output_group: list[dict] = [],
        sensors: dict[str, list] = {},
        modbus: dict[str, Any] = {},
        modbus_devices: list[dict[str, Any]] = [],
        pca9685: list[dict] = [],
        mcp23017: list[dict] = [],
        pcf8575: list[dict] = [],
        ds2482: list[dict] | None = [],
        dallas: dict[str, Any] | None = None,
        oled: dict[str, Any] = {},
        adc: list[dict] | None = None,
        cover: list[dict] = [],
        remote_devices: list[dict] = [],
        web_active: bool = False,
        web_port: int = 8090,
    ) -> None:
        """Initialize the manager and all subsystems."""
        _LOGGER.info("Initializing Manager with modular architecture")
        
        # Core components
        self._loop = None
        self._tasks: list[asyncio.Task] = []
        self._message_bus = message_bus
        self._event_bus = event_bus
        self._state_manager = state_manager
        self._config_helper = config_helper
        self._config_file_path = config_file_path
        self._topic_prefix = config_helper.topic_prefix
        
        # Hardware errors storage for WebUI
        self._hardware_errors: list[dict[str, Any]] = []
        
        # Web server info
        self._web_active = web_active
        self._web_port = web_port
        
        # MQTT shortcuts
        self.send_message = message_bus.send_message
        
        # Initialize I2C bus
        _LOGGER.debug("Initializing I2C bus with smbus2")
        self._i2cbusio = SMBus2I2C(bus_number=2)
        
        # Initialize subsystem managers
        _LOGGER.info("Initializing subsystem managers")
        
        # 1. OutputManager - must be first (covers depend on it)
        self.outputs = OutputManager(
            manager=self,
            relay_pins=relay_pins,
            pca9685=pca9685,
            mcp23017=mcp23017,
            pcf8575=pcf8575,
            output_group=output_group,
        )
        
        # 2. SensorManager
        self.sensors = SensorManager(
            manager=self,
            sensors=sensors,
            dallas=dallas,
            ds2482=ds2482,
            adc=adc,
        )
        
        # 3. ModbusManager (optional)
        self.modbus = ModbusManager(
            manager=self,
            modbus_config=modbus,
            modbus_devices=modbus_devices,
        )
        
        # 4. CoverManager (depends on outputs)
        self.covers = CoverManager(
            manager=self,
            cover_config=cover,
        )
        
        # 5. InputManager
        self.inputs = InputManager(
            manager=self,
            event_pins=event_pins,
            binary_pins=binary_pins,
        )
        
        # 6. DisplayManager (depends on sensors, inputs, outputs)
        self.display = DisplayManager(
            manager=self,
            oled_config=oled,
        )
        
        # 7. RemoteDeviceManager (optional - for controlling remote devices)
        self.remote_devices = RemoteDeviceManager(
            message_bus=message_bus,
            remote_devices_config=remote_devices,
            own_serial=config_helper.serial_no,
        )
        
        # 8. BlackDiscoveryPublisher (publishes device info for autodiscovery of neighboring BoneIO devices)
        self._discovery_publisher = BlackDiscoveryPublisher(
            manager=self,
            message_bus=message_bus,
        )
        
        # Configure virtual energy sensors (must be after outputs are initialized)
        self.sensors.configure_virtual_energy_sensors()
        
        # NOTE: Input event listener is registered in InputManager.__init__
        # (removing duplicate registration here that caused double event handling)
        
        _LOGGER.info("Manager initialization complete")

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        """Get event loop lazily."""
        if self._loop is None:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = asyncio.get_event_loop()
        return self._loop

    @property
    def message_bus(self) -> MessageBus:
        """Get message bus."""
        return self._message_bus

    @property
    def event_bus(self) -> EventBus:
        """Get event bus."""
        return self._event_bus

    @property
    def state_manager(self) -> StateManager:
        """Get state manager."""
        return self._state_manager

    @property
    def config_helper(self) -> ConfigHelper:
        return self._config_helper
        
    @property
    def is_web_on(self) -> bool:
        """Check if web server is active."""
        return self._web_active


    @property
    def web_bind_port(self) -> int:
        """Get web server port."""
        return self._web_port

    @property
    def mqtt_state(self) -> bool:
        """Get MQTT connection state."""
        return self._message_bus.state

    def set_web_server_status(self, status: bool, bind: int) -> None:
        """Set web server status and port.
        
        Args:
            status: Web server active status
            bind: Web server bind port
        """
        self._web_active = status
        self._web_port = bind
        _LOGGER.info("Web server status set to %s on port %s", status, bind)

    def append_task(
        self,
        coro: Callable[..., Coroutine],
        name: str = "Unknown",
        **kwargs
    ) -> asyncio.Task:
        """Add task to run with asyncio loop.
        
        Args:
            coro: Callable that returns a coroutine
            name: Task name for debugging
            **kwargs: Arguments passed to coro
            
        Returns:
            Created asyncio.Task
        """
        _LOGGER.debug("Appending task: %s", name)
        task = asyncio.create_task(coro(**kwargs))
        self._tasks.append(task)
        return task

    def get_tasks(self) -> dict[str, asyncio.Task]:
        """Get all registered tasks.
        
        All tasks are registered via append_task() which is called by AsyncUpdater.
        
        Returns:
            Dictionary of all tasks
        """
        return {f"task_{i}": task for i, task in enumerate(self._tasks)}

    async def send_all_ha_autodiscovery(self) -> None:
        """Send Home Assistant autodiscovery for all entities."""
        _LOGGER.info("Sending HA autodiscovery messages")
        
        await self.outputs.send_ha_autodiscovery()
        await self.inputs.send_ha_autodiscovery()
        await self.covers.send_ha_autodiscovery()
        await self.sensors.send_ha_autodiscovery()
        await self.modbus.send_ha_autodiscovery()
        await self.display.send_ha_autodiscovery()

    def send_ha_autodiscovery(
        self,
        id: str,
        name: str,
        ha_type: str,
        output_type: str | None = None,
        **kwargs
    ) -> None:
        """Send HA autodiscovery message for a single entity.
        
        This is a compatibility method for subsystems that need
        to send individual discovery messages.
        
        Args:
            id: Entity identifier
            name: Entity name
            ha_type: Home Assistant entity type
            output_type: Output type (optional, used for outputs like LIGHT, LED, SWITCH, VALVE)
            **kwargs: Additional parameters
        """
        from boneio.const import BUTTON, LED, LIGHT, SWITCH, VALVE
        from boneio.integration.homeassistant import (
            ha_button_availabilty_message,
            ha_group_availabilty_message,
            ha_led_availabilty_message,
            ha_light_availabilty_message,
            ha_switch_availabilty_message,
            ha_valve_availabilty_message,
        )
        
        # Check if this is a group (passed via kwargs)
        is_group = kwargs.pop('is_group', False)
        
        # Determine availability function based on output_type (for outputs)
        availability_msg_func = None
        if is_group:
            # Groups use special availability function with 'group' device_type
            availability_msg_func = ha_group_availabilty_message
            kwargs = {**kwargs, "output_type": output_type}
        elif output_type:
            availability_function_chooser = {
                LIGHT: ha_light_availabilty_message,
                LED: ha_led_availabilty_message,
                SWITCH: ha_switch_availabilty_message,
                VALVE: ha_valve_availabilty_message,
            }
            availability_msg_func = availability_function_chooser.get(
                output_type, ha_switch_availabilty_message
            )
        
        # Override with specific ha_type functions
        if ha_type == COVER:
            from boneio.integration.homeassistant import ha_cover_availabilty_message
            availability_msg_func = ha_cover_availabilty_message
        elif ha_type == BUTTON:
            availability_msg_func = ha_button_availabilty_message
        
        # Use availability_msg_func from kwargs if provided (for sensors)
        if 'availability_msg_func' in kwargs:
            availability_msg_func = kwargs.pop('availability_msg_func')
        
        # Call availability function if defined
        if availability_msg_func:
            payload = availability_msg_func(
                id=id,
                name=name,
                config_helper=self._config_helper,
                **kwargs
            )
            topic = f"{self._config_helper.ha_discovery_prefix}/{ha_type}/{self._config_helper.serial_no}/{id}/config"
            _LOGGER.debug("Sending HA discovery for %s entity, %s.", ha_type, name)
            self._config_helper.add_autodiscovery_msg(
                topic=topic, ha_type=ha_type, payload=payload
            )
            self.send_message(topic=topic, payload=payload, retain=True)

    def parse_actions(self, pin: str, actions: dict) -> dict:
        """Parse actions configuration.
        
        Args:
            pin: Pin identifier
            actions: Actions dictionary
            
        Returns:
            Parsed actions dictionary
        """
        from boneio.const import TOPIC, REMOTE_OUTPUT, REMOTE_COVER
        from boneio.core.utils import strip_accents
        
        parsed_actions = {}
        for click_type in actions:
            if click_type not in parsed_actions:
                parsed_actions[click_type] = []
            for action_definition in actions.get(click_type, []):
                action = action_definition.get("action")
                
                if action == OUTPUT:
                    # Support both new 'boneio_output' and legacy 'pin' for backward compatibility
                    entity_id = action_definition.get("boneio_output") or action_definition.get("pin")
                    stripped_entity_id = strip_accents(entity_id)
                    action_output = action_definition.get("action_output")
                    output = self.outputs.get_output(stripped_entity_id) or self.outputs.get_output_group(stripped_entity_id)
                    action_to_execute = output_actions.get(action_output)
                    if output and action_to_execute:
                        _f = getattr(output, action_to_execute, None)
                        if _f:
                            parsed_actions[click_type].append({
                                "action": action,
                                "pin": stripped_entity_id,
                                "action_to_execute": action_to_execute,
                            })
                            continue
                    _LOGGER.warning("Device %s for action in %s not found. Omitting.", entity_id, pin)
                    
                elif action == COVER:
                    # Support both new 'boneio_cover' and legacy 'pin' for backward compatibility
                    entity_id = action_definition.get("boneio_cover") or action_definition.get("pin")
                    stripped_entity_id = strip_accents(entity_id)
                    action_cover = action_definition.get("action_cover")
                    extra_data = action_definition.get("data", {})
                    cover = self.covers.get_cover(stripped_entity_id)
                    action_to_execute = cover_actions.get(action_cover)
                    if cover and action_to_execute:
                        _f = getattr(cover, action_to_execute, None)
                        if _f:
                            parsed_actions[click_type].append({
                                "action": action,
                                "pin": stripped_entity_id,
                                "action_to_execute": action_to_execute,
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
                    _LOGGER.warning("MQTT action missing topic or message for %s", pin)
                    
                elif action == OUTPUT_OVER_MQTT:
                    boneio_id = action_definition.get("boneio_id")
                    action_output = action_definition.get("action_output")
                    action_to_execute = output_actions.get(action_output.upper())
                    if boneio_id and action_to_execute:
                        parsed_actions[click_type].append({
                            "action": action,
                            "boneio_id": boneio_id,
                            "action_output": action_output,
                        })
                        continue
                    _LOGGER.warning("OUTPUT_OVER_MQTT action missing data for %s", pin)
                    
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
                    _LOGGER.warning("COVER_OVER_MQTT action missing data for %s", pin)
                
                elif action == REMOTE_OUTPUT:
                    # Remote output on another device (via remote_devices)
                    remote_device = action_definition.get("remote_device")
                    output_id = action_definition.get("output_id")
                    action_output = action_definition.get("action_output", "TOGGLE")
                    if remote_device and output_id:
                        parsed_actions[click_type].append({
                            "action": action,
                            "remote_device": remote_device,
                            "output_id": output_id,
                            "action_output": action_output,
                        })
                        continue
                    _LOGGER.warning("REMOTE_OUTPUT action missing remote_device or output_id for %s", pin)
                
                elif action == REMOTE_COVER:
                    # Remote cover on another device (via remote_devices)
                    remote_device = action_definition.get("remote_device")
                    cover_id = action_definition.get("cover_id")
                    action_cover = action_definition.get("action_cover", "TOGGLE")
                    extra_data = action_definition.get("data", {})
                    if remote_device and cover_id:
                        parsed_actions[click_type].append({
                            "action": action,
                            "remote_device": remote_device,
                            "cover_id": cover_id,
                            "action_cover": action_cover,
                            "extra_data": extra_data,
                        })
                        continue
                    _LOGGER.warning("REMOTE_COVER action missing remote_device or cover_id for %s", pin)
                    
        return parsed_actions

    async def execute_actions(
        self,
        actions: list
    ) -> None:
        """Execute list of actions.
        
        Args:
            actions: List of actions to execute
        """
        from boneio.const import REMOTE_OUTPUT, REMOTE_COVER
        
        start_time = time.time()
        
        for action_definition in actions:
            action = action_definition.get("action")
            
            if action == MQTT:
                action_topic = action_definition.get("action_topic")
                action_payload = action_definition.get("action_mqtt_msg")
                if action_topic and action_payload:
                    self.send_message(
                        topic=action_topic,
                        payload=action_payload,
                        retain=False
                    )
                continue
                
            elif action == OUTPUT:
                output_id = action_definition.get("pin") or action_definition.get("boneio_output")
                output = self.outputs.get_output(output_id) or self.outputs.get_output_group(output_id)
                if not output:
                    _LOGGER.warning("Output %s not found for action", output_id)
                    continue
                action_to_execute = action_definition.get("action_to_execute")
                _LOGGER.debug(
                    "Executing action %s for output %s. Duration: %s",
                    action_to_execute,
                    output.name if hasattr(output, 'name') else output_id,
                    time.time() - start_time,
                )
                _f = getattr(output, action_to_execute)
                await _f()
                
            elif action == COVER:
                cover_id = action_definition.get("pin") or action_definition.get("boneio_cover")
                cover = self.covers.get_cover(cover_id)
                if not cover:
                    _LOGGER.warning("Cover %s not found for action", cover_id)
                    continue
                action_to_execute = action_definition.get("action_to_execute")
                extra_data = action_definition.get("extra_data", {})
                _LOGGER.debug(
                    "Executing action %s for cover %s. Duration: %s",
                    action_to_execute,
                    cover.name if hasattr(cover, 'name') else cover_id,
                    time.time() - start_time,
                )
                _f = getattr(cover, action_to_execute)
                await _f(**extra_data)
                
            elif action == OUTPUT_OVER_MQTT:
                boneio_id = action_definition.get("boneio_id")
                output_id = action_definition.get("boneio_output") or action_definition.get("pin")
                action_output = action_definition.get("action_output")
                self.send_message(
                    topic=f"{boneio_id}/cmd/output/{output_id}/set",
                    payload=action_output,
                    retain=False,
                )
                
            elif action == COVER_OVER_MQTT:
                boneio_id = action_definition.get("boneio_id")
                cover_id = action_definition.get("boneio_cover") or action_definition.get("pin")
                action_cover = action_definition.get("action_cover")
                self.send_message(
                    topic=f"{boneio_id}/cmd/cover/{cover_id}/set",
                    payload=action_cover,
                    retain=False,
                )
            
            elif action == REMOTE_OUTPUT:
                # Control output on remote device
                remote_device_id = action_definition.get("remote_device")
                output_id = action_definition.get("output_id")
                action_output = action_definition.get("action_output", "TOGGLE")
                await self.remote_devices.control_output(
                    device_id=remote_device_id,
                    output_id=output_id,
                    action=action_output,
                )
            
            elif action == REMOTE_COVER:
                # Control cover on remote device
                remote_device_id = action_definition.get("remote_device")
                cover_id = action_definition.get("cover_id")
                action_cover = action_definition.get("action_cover", "TOGGLE")
                extra_data = action_definition.get("extra_data", {})
                await self.remote_devices.control_cover(
                    device_id=remote_device_id,
                    cover_id=cover_id,
                    action=action_cover,
                    **extra_data,
                )

    def _reload_logger(self) -> None:
        """Reload logger configuration from config file.
        
        This allows hot-reloading of log levels without restarting the application.
        """
        from boneio.core.utils.logger import configure_logger
        
        config = self._config_helper.get_config()
        log_config = config.get("logger", {})
        
        _LOGGER.info("Reloading logger configuration")
        configure_logger(log_config, debug=0)
        _LOGGER.info("Logger configuration reloaded successfully")

    def _reload_remote_devices(self) -> None:
        """Reload remote devices configuration from config file.
        
        This allows hot-reloading of remote devices without restarting the application.
        """
        config = self._config_helper.get_config()
        remote_devices_config = config.get("remote_devices", [])
        
        _LOGGER.info("Reloading remote devices configuration")
        self.remote_devices.reload(remote_devices_config)
        _LOGGER.info("Remote devices configuration reloaded successfully")
    
    async def publish_discovery(self) -> None:
        """Publish all device discovery information to MQTT.
        
        This should be called after manager is fully initialized.
        """
        if hasattr(self, '_discovery_publisher'):
            await self._discovery_publisher.publish_discovery()
        else:
            _LOGGER.warning("Discovery publisher not initialized")
    
    async def _publish_discovery_for_sections(self, sections: list[str]) -> None:
        """Publish discovery only for specific sections.
        
        Maps config sections to discovery topics:
        - output -> outputs
        - cover -> covers
        - input, event, binary_sensor -> inputs
        - sensor, virtual_energy_sensor -> sensors
        - modbus_devices -> modbus
        
        Args:
            sections: List of reloaded config section names
        """
        if not hasattr(self, '_discovery_publisher'):
            _LOGGER.warning("Discovery publisher not initialized")
            return
        
        publisher = self._discovery_publisher
        
        # Map config sections to discovery methods
        section_to_discovery = {
            "output": publisher.publish_outputs,
            "cover": publisher.publish_covers,
            "input": publisher.publish_inputs,
            "event": publisher.publish_inputs,
            "binary_sensor": publisher.publish_inputs,
            "sensor": publisher.publish_sensors,
            "virtual_energy_sensor": publisher.publish_sensors,
            "modbus_devices": publisher.publish_modbus,
        }
        
        published = set()
        for section in sections:
            if section in section_to_discovery:
                method = section_to_discovery[section]
                method_name = method.__name__
                if method_name not in published:
                    method()
                    published.add(method_name)
        
        if published:
            _LOGGER.info("Published discovery for sections: %s", list(published))

    async def reload_config(self, reload_sections: list[str] | None = None) -> dict:
        """Reload configuration from file.
        
        This method allows hot-reloading of specific configuration sections
        without requiring a full application restart.
        
        Args:
            reload_sections: Optional list of section names to reload.
                           If None, reloads all supported sections (output, cover, input, modbus_devices).
                           Supported sections: 'output', 'cover', 'input', 'event', 'binary_sensor', 
                           'modbus_devices', 'sensor', 'virtual_energy_sensor', 'logger', 'remote_devices'
        
        Returns:
            dict: Status of reload operation with details:
                - status: 'success', 'partial', or 'error'
                - reloaded_sections: List of successfully reloaded sections
                - failed_sections: List of sections that failed to reload
        """
        from boneio.const import BINARY_SENSOR, COVER, EVENT_ENTITY, OUTPUT
        
        _LOGGER.info("Starting config reload")
        
        # Reload config cache in ConfigHelper
        try:
            config = self._config_helper.reload_config()
            # Update areas mapping from reloaded config
            self._config_helper.set_areas(config.get("areas", []))
        except Exception as e:
            _LOGGER.error(f"Failed to reload config: {e}")
            return {
                "status": "error",
                "message": str(e),
                "reloaded_sections": [],
                "failed_sections": []
            }
        
        reloaded_sections = []
        failed_sections = []
        
        import inspect
        
        # Sections that support hot reload (some are async, some are sync)
        hot_reloadable_sections = {
            OUTPUT: self.outputs.reload_outputs,
            "output_group": self.outputs.reload_outputs,  # Alias for "output" (reloads both outputs and groups)
            COVER: self.covers.reload_covers,
            "input": self.inputs.reload_inputs,  # Reloads both event and binary_sensor (async)
            EVENT_ENTITY: self.inputs.reload_inputs,  # Alias for "input" (async)
            BINARY_SENSOR: self.inputs.reload_inputs,  # Alias for "input" (async)
            "modbus_devices": self.modbus.reload_modbus_devices,
            "sensor": self.sensors.reload_dallas_sensors,  # Dallas temperature sensors
            "virtual_energy_sensor": self.sensors.reload_virtual_energy_sensors,  # Virtual energy sensors
            "logger": self._reload_logger,  # Logger configuration
            "remote_devices": self._reload_remote_devices,  # Remote devices configuration
        }
        
        # If specific sections requested, filter
        if reload_sections:
            sections_to_reload = {}
            for section in reload_sections:
                if section in hot_reloadable_sections:
                    sections_to_reload[section] = hot_reloadable_sections[section]
                else:
                    _LOGGER.warning(f"Unknown reload section: {section}")
        else:
            # By default, reload all supported sections (but only once for inputs)
            sections_to_reload = {
                OUTPUT: hot_reloadable_sections[OUTPUT],
                COVER: hot_reloadable_sections[COVER],
                "input": hot_reloadable_sections["input"],
                "modbus_devices": hot_reloadable_sections["modbus_devices"],
                "sensor": hot_reloadable_sections["sensor"],
            }
        
        # Execute reloads (handle both sync and async functions)
        for section, reload_func in sections_to_reload.items():
            try:
                if inspect.iscoroutinefunction(reload_func):
                    await reload_func()
                else:
                    reload_func()
                reloaded_sections.append(section)
                _LOGGER.info(f"Successfully reloaded section: {section}")
            except Exception as e:
                _LOGGER.error(f"Failed to reload section {section}: {e}", exc_info=True)
                failed_sections.append({"section": section, "error": str(e)})
        
        # Determine status
        if failed_sections:
            status = "partial" if reloaded_sections else "error"
        else:
            status = "success"
        
        result = {
            "status": status,
            "reloaded_sections": reloaded_sections,
            "failed_sections": failed_sections,
        }
        
        if status == "success":
            _LOGGER.info("Config reload completed successfully")
            # Publish updated discovery for reloaded sections
            await self._publish_discovery_for_sections(reloaded_sections)
        elif status == "partial":
            _LOGGER.warning("Config reload completed with some failures")
            # Publish discovery for successfully reloaded sections
            await self._publish_discovery_for_sections(reloaded_sections)
        else:
            _LOGGER.error("Config reload failed")
        
        return result

    def resend_autodiscovery(self) -> None:
        """Resend all HA autodiscovery messages."""
        for msg in self._config_helper.autodiscovery_msgs:
            self.send_message(**msg, retain=True)

    async def reconnect_callback(self) -> None:
        """Function to invoke when connection to MQTT is (re-)established.
        
        Sends online status to MQTT.
        """
        _LOGGER.info("Sending online state.")
        topic = f"{self._config_helper.topic_prefix}/{STATE}"
        self.send_message(topic=topic, payload=ONLINE, retain=True)

    async def receive_message(self, topic: str, message: str) -> None:
        """Callback for receiving MQTT messages.
        
        Handles:
        - HA status messages (online/offline)
        - BoneIO discovery messages (autodiscovery of neighboring devices)
        - Relay/output commands (set, brightness)
        - Cover commands
        
        Args:
            topic: MQTT topic
            message: MQTT message payload
        """
        _LOGGER.debug("Processing topic %s with message %s.", topic, message)
        
        # Handle HA status messages
        if topic.startswith(f"{self._config_helper.ha_discovery_prefix}/status"):
            if message == ONLINE:
                self.resend_autodiscovery()
                self._event_bus.signal_ha_online()
            return
        
        # Handle BoneIO discovery messages (autodiscovery of neighboring devices)
        if self._config_helper.receive_boneio_autodiscovery and self.remote_devices.is_discovery_topic(topic):
            self.remote_devices.handle_discovery_message(topic, message)
            return
        
        # Verify topic starts with command prefix
        try:
            assert topic.startswith(self._config_helper.cmd_topic_prefix)
        except AssertionError as err:
            _LOGGER.error("Wrong topic %s. Error %s", topic, err)
            return
        
        # Parse topic parts
        topic_parts_raw = topic[len(self._config_helper.cmd_topic_prefix):].split("/")
        topic_parts = deque(topic_parts_raw)
        
        try:
            msg_type = topic_parts.popleft()
            device_id = topic_parts.popleft()
            command = topic_parts.pop()
            _LOGGER.debug(
                "Divide topic to: msg_type: %s, device_id: %s, command: %s",
                msg_type, device_id, command
            )
        except IndexError:
            _LOGGER.error("Part of topic is missing. Not invoking command.")
            return
        
        # Handle relay/output commands
        if msg_type == OUTPUT and command == "set":
            target_device = self.outputs.get_output(device_id)
            if target_device and target_device.output_type != "none":
                action_from_msg = output_actions.get(message.upper())
                if action_from_msg:
                    _f = getattr(target_device, action_from_msg)
                    await _f()
                else:
                    _LOGGER.debug("Action not exist %s.", message.upper())
            else:
                _LOGGER.debug("Target device not found %s.", device_id)
            return
        
        if msg_type == OUTPUT and command == SET_BRIGHTNESS:
            target_device = self.outputs.get_output(device_id)
            if target_device and target_device.output_type != "none" and message != "":
                target_device.set_brightness(int(message))
            else:
                _LOGGER.debug("Target device not found %s.", device_id)
            return
        
        if msg_type == COVER:
            cover = self.covers.get_cover(device_id)
            if cover:
                if command == "pos":
                    # Set cover position
                    try:
                        position = int(message)
                        await cover.set_cover_position(position)
                    except ValueError:
                        _LOGGER.warning("Invalid cover position value: %s", message)
                else:
                    # Handle open/close/stop/toggle actions
                    action = cover_actions.get(message.upper())
                    if action:
                        _f = getattr(cover, action)
                        await _f()
                    else:
                        _LOGGER.debug("Cover action not exist %s.", message.upper())
            else:
                _LOGGER.debug("Cover not found %s.", device_id)
            return
        
        if msg_type == "group" and command == "set":
            target_device = self.outputs.get_output_group(device_id)
            if target_device and target_device.output_type != NONE:
                action_from_msg = output_actions.get(message.upper())
                if action_from_msg:
                    asyncio.create_task(getattr(target_device, action_from_msg)())
                else:
                    _LOGGER.debug("Action not exist %s.", message.upper())
            else:
                _LOGGER.debug("Target device not found %s.", device_id)
            return

        if msg_type == BUTTON and command == "set":
            if device_id == "inputs_reload" and message == "inputs_reload":
                _LOGGER.info("Reloading events and binary sensors actions")
                asyncio.create_task(self.inputs.reload_inputs())
            elif device_id == "cover_reload" and message == "cover_reload":
                _LOGGER.info("Reloading covers actions")
                self.covers.reload_covers()
            elif device_id == "outputs_reload" and message == "outputs_reload":
                _LOGGER.info("Reloading outputs and groups")
                asyncio.create_task(self.outputs.reload_outputs())
            return

        if msg_type == "modbus" and command == "set":
            target_device = self.modbus.get_all_coordinators().get(device_id)
            if target_device:
                if isinstance(message, str):
                    try:
                        parsed_msg: dict = json.loads(message)
                        device_name = parsed_msg.get("device")
                        value = parsed_msg.get("value")
                        if device_name and value is not None:
                            entity = target_device.find_entity(device_name)
                            if entity:
                                await target_device.write_register(value=value, entity=entity)
                    except json.JSONDecodeError:
                        _LOGGER.warning("Invalid JSON in modbus message: %s", message)
            return

        _LOGGER.debug("Unknown message type %s.", msg_type)
            
