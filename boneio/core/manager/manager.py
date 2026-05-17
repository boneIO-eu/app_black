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
from datetime import datetime
from typing import TYPE_CHECKING, Any

from boneio.const import (
    BUTTON,
    CAN,
    COVER,
    COVER_OVER_MQTT,
    ENABLED,
    MQTT,
    NONE,
    OFF,
    ON,
    ONLINE,
    OUTPUT,
    OUTPUT_OVER_MQTT,
    REMOTE_COVER,
    REMOTE_OUTPUT,
    SET_BRIGHTNESS,
    STATE,
    TOGGLE,
    cover_actions,
    filter_cover_extra_data,
    output_actions,
)
from boneio.core.config import ConfigHelper
from boneio.core.discovery import BlackDiscoveryPublisher
from boneio.core.events import EventBus
from boneio.core.manager.action_conditions import precompile_conditions, should_execute_action
from boneio.core.manager.covers import CoverManager
from boneio.core.manager.display import DisplayManager
from boneio.core.manager.inputs import InputManager
from boneio.core.manager.irrigation import IrrigationManager
from boneio.core.manager.modbus import ModbusManager
from boneio.core.manager.outputs import OutputManager
from boneio.core.manager.remote import RemoteDeviceManager
from boneio.core.manager.sensors import SensorManager
from boneio.core.manager.templates import TemplateManager
from boneio.core.manager.update import UpdateManager
from boneio.core.messaging import MessageBus
from boneio.core.state import StateManager
from boneio.hardware.i2c.bus import SMBus2I2C
from boneio.migrations import MigrationRunner, MigrationStatus

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
        relay_pins: list[dict] | None = None,
        event_pins: list[dict] | None = None,
        binary_pins: list[dict] | None = None,
        output_group: list[dict] | None = None,
        sensors: dict[str, list] | None = None,
        modbus: dict[str, Any] | None = None,
        modbus_devices: list[dict[str, Any]] | None = None,
        pca9685: list[dict] | None = None,
        mcp23017: list[dict] | None = None,
        pcf8575: list[dict] | None = None,
        ds2482: list[dict] | None = None,
        dallas: dict[str, Any] | None = None,
        oled: dict[str, Any] | None = None,
        adc: list[dict] | None = None,
        cover: list[dict] | None = None,
        template: list[dict] | None = None,
        irrigation: list[dict] | None = None,
        remote_devices: list[dict] | None = None,
        can: dict[str, Any] | None = None,
        web_active: bool = False,
        web_port: int = 8090,
        early_oled_device: Any | None = None,
    ) -> None:
        """Initialize the manager and all subsystems."""
        _LOGGER.info("Initializing Manager with modular architecture")

        # Resolve mutable defaults
        relay_pins = relay_pins or []
        event_pins = event_pins or []
        binary_pins = binary_pins or []
        output_group = output_group or []
        sensors = sensors or {}
        modbus = modbus or {}
        modbus_devices = modbus_devices or []
        pca9685 = pca9685 or []
        mcp23017 = mcp23017 or []
        pcf8575 = pcf8575 or []
        ds2482 = ds2482 or []
        oled = oled or {}
        cover = cover or []
        template = template or []
        irrigation = irrigation or []
        remote_devices = remote_devices or []
        can = can or {}

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

        # Pending delayed actions: key = "input_id" -> list of asyncio.Tasks
        # Used by the delay/delay_cancel_on action system (e.g. motion sensors)
        self._pending_delayed_actions: dict[str, list[asyncio.Task]] = {}

        # Startup status tracking
        self._startup_status: str = "initializing"
        self._startup_complete: bool = False
        self._websocket_manager: Any | None = None
        self._early_oled_device = early_oled_device

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
            early_oled_device=self._early_oled_device,
        )

        # 7. RemoteDeviceManager (optional - for controlling remote devices)
        self.remote_devices = RemoteDeviceManager(
            message_bus=message_bus,
            remote_devices_config=remote_devices,
            own_serial=config_helper.serial_no,
            name=self.config_helper.name,
        )

        # 8. BlackDiscoveryPublisher (publishes device info for autodiscovery of neighboring BoneIO devices)
        self._discovery_publisher = BlackDiscoveryPublisher(
            manager=self,
            message_bus=message_bus,
        )

        # 9. UpdateManager (checks for software updates and publishes to HA)
        self.update_manager = UpdateManager(
            manager=self,
        )

        # 10. MigrationRunner (system-level OS migrations)
        self.migration_runner = MigrationRunner()

        # 10. TemplateManager (thermostats, alarm panels, etc.)
        # Separate irrigation entries from template list — they are handled
        # by IrrigationManager, not TemplateManager, even though the frontend
        # configures them as a template platform.
        non_irrigation_templates = [e for e in template if e.get("platform") != "irrigation"]
        irrigation_from_template = [e for e in template if e.get("platform") == "irrigation"]

        # Register remote outputs (must be after OutputManager and RemoteDeviceManager,
        # but before IrrigationManager which needs to find remote outputs in OutputManager)
        self.register_remote_outputs()

        self.templates = TemplateManager(
            manager=self,
            template_config=non_irrigation_templates,
        )

        # 11. CANopenManager (optional - CAN bus communication)
        self.canopen = None
        if can.get(ENABLED, False):
            from boneio.core.manager.canopen import CANopenManager

            self.canopen = CANopenManager(
                manager=self,
                config=can,
            )

        # 12. IrrigationManager — merge dedicated irrigation section
        # with irrigation entries from template section.
        merged_irrigation = list(irrigation) + irrigation_from_template
        self.irrigation = IrrigationManager(
            manager=self,
            irrigation_config=merged_irrigation,
        )

        # Configure virtual energy sensors (must be after outputs are initialized)
        self.sensors.configure_virtual_energy_sensors()

        # NOTE: Input event listener is registered in InputManager.__init__
        # (removing duplicate registration here that caused double event handling)

        # Run system migration startup check (discovers pending migrations,
        # detects bootstrap_required, applies if helper is installed).
        try:
            migration_status = self.migration_runner.startup_check()
            _LOGGER.info(
                "Migration startup_check finished: status=%s, pending=%d, bootstrap_required=%s",
                migration_status.value,
                self.migration_runner.pending_count,
                self.migration_runner.bootstrap_required,
            )
        except Exception as exc:
            _LOGGER.error("Migration startup_check failed: %s", exc, exc_info=True)

        _LOGGER.info("Manager initialization complete")

    async def start_canopen(self) -> None:
        """Start CANopen manager if configured."""
        if self.canopen is not None:
            can_started = await self.canopen.start()
            if can_started:
                _LOGGER.info("CANopen manager started successfully")
            else:
                _LOGGER.warning("CANopen manager failed to start")
                self.canopen = None

    async def stop(self) -> None:
        """Stop manager async tasks.

        This should be called during shutdown to cleanly stop:
        - CANopen manager
        - ESPHome connections
        - Other async tasks
        """
        _LOGGER.info("Stopping manager async tasks")

        # Stop CANopen manager
        if self.canopen is not None:
            try:
                await self.canopen.stop()
            except Exception as e:
                _LOGGER.error("Error stopping CANopen manager: %s", e)

        # Stop irrigation controllers and schedules
        try:
            await self.irrigation.stop()
        except Exception as e:
            _LOGGER.error("Error stopping irrigation manager: %s", e)

        # Stop ESPHome connections
        await self.remote_devices.stop_all_connections()

        _LOGGER.info("Manager async tasks stopped")

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

    async def set_startup_status(self, status: str, message: str) -> None:
        """Set and broadcast startup status to WebSocket clients.

        Args:
            status: Machine-readable status key (e.g. 'connecting_mqtt')
            message: Human-readable status message
        """
        self._startup_status = status
        _LOGGER.info("Startup status: %s", message)
        if self._websocket_manager:
            await self._websocket_manager.broadcast(
                {
                    "event_type": "startup_status",
                    "status": status,
                    "message": message,
                    "complete": False,
                }
            )

    async def mark_startup_complete(self) -> None:
        """Mark startup as complete and notify WebSocket clients."""
        self._startup_complete = True
        self._startup_status = "ready"
        _LOGGER.info("Startup complete")

        # Always hand off early_oled so it stops drawing boot status messages.
        # DisplayManager.handoff() is only called when oled: is in config,
        # but early_oled can still be painting if the OLED section is absent.
        try:
            from boneio.hardware.display.early_oled import handoff, is_taken_over

            if not is_taken_over():
                handoff()
                _LOGGER.debug("Early OLED handed off at startup completion")
        except Exception:
            pass

        if self._websocket_manager:
            await self._websocket_manager.broadcast(
                {
                    "event_type": "startup_status",
                    "status": "ready",
                    "message": "",
                    "complete": True,
                }
            )

    def append_task(self, coro: Callable[..., Coroutine], name: str = "Unknown", **kwargs) -> asyncio.Task:
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
        await self.update_manager.send_ha_autodiscovery()
        await self.templates.send_ha_autodiscovery()
        await self.irrigation.send_ha_autodiscovery()

    async def republish_all_entity_states(self) -> None:
        """Re-publish current state of all entities to MQTT only.

        After HA autodiscovery is re-sent, Home Assistant creates new entities
        but they have no state data until the next state change. This method
        forces an immediate re-publication of the known state of every entity
        (outputs, covers, binary sensors, sensors, etc.) so that HA picks up
        the current values right away instead of showing 'unknown'.

        IMPORTANT: This publishes ONLY to MQTT topics — it does NOT trigger
        EventBus events, so WebSocket clients (frontend) are unaffected.
        The frontend already holds correct state; only HA needs re-sync.
        """
        _LOGGER.info("Re-publishing all entity states to MQTT")
        topic_prefix = self._config_helper.topic_prefix

        # 1. Outputs & groups — publish ON/OFF state on MQTT only
        for output in self.outputs.get_all_outputs().values():
            if output.output_type not in (COVER, NONE):
                try:
                    state = ON if output.is_active else OFF
                    self._message_bus.send_message(
                        topic=f"{topic_prefix}/{OUTPUT}/{output.id}",
                        payload={STATE: state},
                        retain=True,
                    )
                except Exception as e:
                    _LOGGER.debug("Error re-publishing output state %s: %s", output.id, e)

        for group in self.outputs.get_all_output_groups().values():
            try:
                state = ON if group.is_active else OFF
                self._message_bus.send_message(
                    topic=f"{topic_prefix}/{OUTPUT}/{group.id}",
                    payload={STATE: state},
                    retain=True,
                )
            except Exception as e:
                _LOGGER.debug("Error re-publishing group state %s: %s", group.id, e)

        # 2. Covers — publish position + state on MQTT only
        for cover in self.covers.get_all_covers().values():
            try:
                self._message_bus.send_message(
                    topic=f"{topic_prefix}/{COVER}/{cover.id}/state",
                    payload=cover.state,
                )
                self._message_bus.send_message(
                    topic=f"{topic_prefix}/{COVER}/{cover.id}/pos",
                    payload=json.dumps(cover.json_position),
                )
            except Exception as e:
                _LOGGER.debug("Error re-publishing cover state %s: %s", cover.id, e)

        # 3. Binary sensors — publish pressed/released state via MQTT only
        self._republish_binary_sensor_states()

        # 4. Sensors (Dallas, ADC, system) — re-publish last known value
        await self._republish_sensor_states_mqtt()

        # 5. Online status
        self.send_message(
            topic=f"{self._config_helper.topic_prefix}/state",
            payload="online",
            retain=True,
        )

        _LOGGER.info("All entity states re-published to MQTT")

    def _republish_binary_sensor_states(self) -> None:
        """Re-publish the last known state of all binary sensors to MQTT.

        Binary sensors don't have a periodic update loop — their state
        is only published on GPIO change events. After an HA discovery
        re-send we need to push the current state once so HA doesn't
        show 'unknown'.
        """
        from boneio.components.input.binary_sensor import GpioInputBinarySensor

        topic_prefix = self._config_helper.topic_prefix
        for input_id, inp in self.inputs.get_all_inputs().items():
            if isinstance(inp, GpioInputBinarySensor):
                try:
                    state = inp.last_state  # "pressed" or "released"
                    if state:
                        self.send_message(
                            topic=f"{topic_prefix}/input/{input_id}",
                            payload=state,
                        )
                except Exception as e:
                    _LOGGER.debug(
                        "Error re-publishing binary sensor state %s: %s",
                        input_id,
                        e,
                    )

    async def _republish_sensor_states_mqtt(self) -> None:
        """Re-publish last known sensor values to MQTT only.

        Triggers an async update on each sensor which publishes to MQTT
        via the message_bus. This does NOT fire EventBus events.
        """
        timestamp = time.time()

        # Dallas and I2C temperature sensors
        for sensor in self.sensors.get_all_temp_sensors():
            try:
                await sensor.async_update(timestamp)
            except Exception as e:
                _LOGGER.debug("Error re-publishing sensor state %s: %s", sensor.id, e)

    def publish_ha_discovery(
        self,
        id: str,
        ha_type: str,
        payload: dict,
    ) -> None:
        """Publish a pre-built HA autodiscovery payload.

        This is a thin helper that handles topic construction, caching
        and MQTT publishing.  Each subsystem is responsible for building
        its own *payload* via the appropriate ``ha_*_availabilty_message``
        function.

        Args:
            id: Entity identifier (used in the MQTT topic).
            ha_type: Home Assistant entity type (sensor, light, cover …).
            payload: Ready-to-publish discovery payload dict.
        """
        topic = f"{self._config_helper.ha_discovery_prefix}/{ha_type}/{self._config_helper.serial_no}/{id}/config"
        _LOGGER.debug("Sending HA discovery for %s entity %s.", ha_type, id)
        self._config_helper.add_autodiscovery_msg(topic=topic, ha_type=ha_type, payload=payload)
        self.send_message(topic=topic, payload=payload, retain=True)

    async def _handle_update_install_command(self, topic: str, payload: str) -> None:
        """Handle update install command from Home Assistant.

        Args:
            topic: MQTT topic
            payload: MQTT payload (should be "INSTALL")
        """
        _LOGGER.info("Received update install command: %s", payload)
        await self.update_manager.handle_install_command(payload)

    def parse_actions(self, pin: str, actions: dict) -> dict:
        """Parse actions configuration.

        Args:
            pin: Pin identifier
            actions: Actions dictionary

        Returns:
            Parsed actions dictionary
        """
        from boneio.const import TOPIC
        from boneio.core.utils import strip_accents

        def _copy_long_press_meta(parsed_action: dict, action_definition: dict) -> None:
            """Copy long press meta fields (duration thresholds, repeat), delay, and conditions to parsed action."""
            for key in ("min_duration", "max_duration"):
                if action_definition.get(key) is not None:
                    parsed_action[key] = action_definition[key]
            if action_definition.get("repeat"):
                parsed_action["repeat"] = True
                ri = action_definition.get("repeat_interval", 1000)
                # TimePeriod object from schema validation -> convert to ms
                if hasattr(ri, "total_milliseconds"):
                    parsed_action["repeat_interval"] = ri.total_milliseconds
                else:
                    parsed_action["repeat_interval"] = ri
            # Copy delay fields for cancelable timer support
            delay_val = action_definition.get("delay")
            if delay_val is not None:
                if hasattr(delay_val, "total_in_seconds"):
                    parsed_action["delay"] = delay_val.total_in_seconds
                elif isinstance(delay_val, (int, float)):
                    parsed_action["delay"] = float(delay_val)
                _LOGGER.debug("Action has delay: %.1fs", parsed_action.get("delay", 0))
            cancel_on = action_definition.get("delay_cancel_on")
            if cancel_on:
                parsed_action["delay_cancel_on"] = cancel_on
            # Copy condition/conditions for conditional execution
            for key in ("condition", "conditions"):
                if action_definition.get(key) is not None:
                    parsed_action[key] = action_definition[key]
            # Pre-compile conditions for fast evaluation at action time
            compiled = precompile_conditions(parsed_action)
            if compiled is not None:
                parsed_action["_compiled_conditions"] = compiled

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
                    action_output = action_definition.get("action_output", TOGGLE)
                    output = self.outputs.get_output(stripped_entity_id) or self.outputs.get_output_group(
                        stripped_entity_id
                    )
                    action_to_execute = output_actions.get(action_output)
                    if output and action_to_execute:
                        _f = getattr(output, action_to_execute, None)
                        if _f:
                            parsed_action = {
                                "action": action,
                                "pin": stripped_entity_id,
                                "action_to_execute": action_to_execute,
                            }
                            _copy_long_press_meta(parsed_action, action_definition)
                            _LOGGER.debug(
                                "Parsed OUTPUT action for %s: output=%s, action=%s, min_dur=%s, max_dur=%s",
                                pin,
                                stripped_entity_id,
                                action_to_execute,
                                parsed_action.get("min_duration"),
                                parsed_action.get("max_duration"),
                            )
                            parsed_actions[click_type].append(parsed_action)
                            continue
                    _LOGGER.warning("Device %s for action in %s not found. Omitting.", entity_id, pin)

                elif action == COVER:
                    # Support both new 'boneio_cover' and legacy 'pin' for backward compatibility
                    entity_id = action_definition.get("boneio_cover") or action_definition.get("pin")
                    stripped_entity_id = strip_accents(entity_id)
                    action_cover = action_definition.get("action_cover", TOGGLE)
                    extra_data = action_definition.get("data", {})
                    cover = self.covers.get_cover(stripped_entity_id)
                    action_to_execute = cover_actions.get(action_cover)
                    if cover and action_to_execute:
                        _f = getattr(cover, action_to_execute, None)
                        if _f:
                            parsed_action = {
                                "action": action,
                                "pin": stripped_entity_id,
                                "action_to_execute": action_to_execute,
                                "extra_data": extra_data,
                            }
                            _copy_long_press_meta(parsed_action, action_definition)
                            parsed_actions[click_type].append(parsed_action)
                            continue
                    _LOGGER.warning("Device %s for action not found. Omitting.", entity_id)

                elif action == MQTT:
                    action_mqtt_msg = action_definition.get("action_mqtt_msg")
                    action_topic = action_definition.get(TOPIC)
                    if action_topic and action_mqtt_msg:
                        parsed_action = {
                            "action": action,
                            "action_mqtt_msg": action_mqtt_msg,
                            "action_topic": action_topic,
                        }
                        _copy_long_press_meta(parsed_action, action_definition)
                        parsed_actions[click_type].append(parsed_action)
                        continue
                    _LOGGER.warning("MQTT action missing topic or message for %s", pin)

                elif action == OUTPUT_OVER_MQTT:
                    boneio_id = action_definition.get("boneio_id")
                    action_output = action_definition.get("action_output")
                    action_to_execute = output_actions.get(action_output.upper())
                    if boneio_id and action_to_execute:
                        parsed_action = {
                            "action": action,
                            "boneio_id": boneio_id,
                            "action_output": action_output,
                        }
                        _copy_long_press_meta(parsed_action, action_definition)
                        parsed_actions[click_type].append(parsed_action)
                        continue
                    _LOGGER.warning("OUTPUT_OVER_MQTT action missing data for %s", pin)

                elif action == COVER_OVER_MQTT:
                    boneio_id = action_definition.get("boneio_id")
                    action_cover = action_definition.get("action_cover")
                    action_to_execute = cover_actions.get(action_cover.upper())
                    if boneio_id and action_to_execute:
                        parsed_action = {
                            "action": action,
                            "boneio_id": boneio_id,
                            "action_cover": action_cover,
                        }
                        _copy_long_press_meta(parsed_action, action_definition)
                        parsed_actions[click_type].append(parsed_action)
                        continue
                    _LOGGER.warning("COVER_OVER_MQTT action missing data for %s", pin)

                elif action == REMOTE_OUTPUT:
                    # Remote output on another device (via remote_devices)
                    remote_device = action_definition.get("remote_device")
                    output_id = action_definition.get("output_id")
                    action_output = action_definition.get("action_output", "TOGGLE")
                    if remote_device and output_id:
                        parsed_action = {
                            "action": action,
                            "remote_device": remote_device,
                            "output_id": output_id,
                            "action_output": action_output,
                        }
                        # Copy optional light/WLED parameters
                        for opt_key in (
                            "brightness",
                            "color_temp",
                            "rgb",
                            "transition",
                            "effect",
                            "palette",
                            "brightness_step",
                            "effect_speed",
                            "effect_intensity",
                            "colors",
                            "presets",
                        ):
                            val = action_definition.get(opt_key)
                            if val is not None:
                                parsed_action[opt_key] = val
                        # Convert transition TimePeriod to float seconds
                        if "transition" in parsed_action:
                            t_val = parsed_action["transition"]
                            if hasattr(t_val, "total_in_seconds"):
                                parsed_action["transition"] = t_val.total_in_seconds
                            elif not isinstance(t_val, (int, float)):
                                parsed_action["transition"] = 0.0
                        _copy_long_press_meta(parsed_action, action_definition)
                        parsed_actions[click_type].append(parsed_action)
                        continue
                    _LOGGER.warning("REMOTE_OUTPUT action missing remote_device or output_id for %s", pin)

                elif action == REMOTE_COVER:
                    # Remote cover on another device (via remote_devices)
                    remote_device = action_definition.get("remote_device")
                    cover_id = action_definition.get("cover_id")
                    action_cover = action_definition.get("action_cover", "TOGGLE")
                    extra_data = action_definition.get("data", {})
                    if remote_device and cover_id:
                        parsed_action = {
                            "action": action,
                            "remote_device": remote_device,
                            "cover_id": cover_id,
                            "action_cover": action_cover,
                            "extra_data": extra_data,
                        }
                        _copy_long_press_meta(parsed_action, action_definition)
                        parsed_actions[click_type].append(parsed_action)
                        continue
                    _LOGGER.warning("REMOTE_COVER action missing remote_device or cover_id for %s", pin)

        return parsed_actions

    def _resolve_entity_state(self, entity_type: str, entity_id: str) -> Any:
        """Resolve a boneIO entity by type and ID for condition evaluation.

        Used by the conditions system to check entity states.

        Args:
            entity_type: Entity type ('binary_sensor', 'cover', 'output', 'light')
            entity_id: Entity ID

        Returns:
            Entity object or None if not found
        """
        if entity_type in ("output", "light"):
            return self.outputs.get_output(entity_id) or self.outputs.get_output_group(entity_id)
        elif entity_type == "cover":
            return self.covers.get_cover(entity_id)
        elif entity_type == "binary_sensor":
            return self.inputs.get_input(entity_id)
        else:
            _LOGGER.warning("Unknown entity type for condition: %s", entity_type)
            return None

    async def execute_actions(
        self,
        actions: list,
        duration: float | None = None,
        executed_actions: set[int] | None = None,
        last_repeat_times: dict[int, float] | None = None,
        input_id: str | None = None,
    ) -> set[int]:
        """Execute list of actions.

        Args:
            actions: List of actions to execute
            duration: Current duration in seconds (for long press threshold checking)
            executed_actions: Set of action indices already executed (for long press)
            last_repeat_times: Dict mapping action index to last execution duration_ms (for repeat throttling)
            input_id: Optional input entity ID (used for delay cancel tracking)

        Returns:
            Set of action indices that were executed
        """
        if executed_actions is None:
            executed_actions = set()
        if last_repeat_times is None:
            last_repeat_times = {}

        duration_ms = (duration or 0) * 1000  # Convert to ms

        # Compute datetime once for all condition evaluations in this batch
        now_dt = datetime.now()

        for idx, action_definition in enumerate(actions):
            is_repeat = action_definition.get("repeat", False)
            repeat_interval_ms = action_definition.get("repeat_interval", 1000)

            # Skip if already executed (unless it's a repeat action)
            if idx in executed_actions and not is_repeat:
                continue

            # Check duration thresholds
            min_dur = action_definition.get("min_duration")  # ms
            max_dur = action_definition.get("max_duration")  # ms

            if min_dur is not None or max_dur is not None:
                # Action has duration thresholds
                if min_dur is not None and duration_ms < min_dur:
                    continue  # Duration too short
                if max_dur is not None and duration_ms >= max_dur:
                    continue  # Duration too long
            else:
                if is_repeat:
                    # Repeat action - check interval throttling
                    now_ms = duration_ms
                    last_time = last_repeat_times.get(idx, 0.0)
                    if last_time > 0 and (now_ms - last_time) < repeat_interval_ms:
                        continue
                else:
                    # Action without thresholds - execute only once (on first long event)
                    if idx in executed_actions:
                        continue

            # Check conditions (time, date, state) — uses pre-compiled fast path
            compiled_cond = action_definition.get("_compiled_conditions")
            if compiled_cond is not None and not should_execute_action(
                compiled_cond,
                now_dt,
                self._resolve_entity_state,
            ):
                _LOGGER.debug("Action %d: condition not met, skipping", idx)
                continue

            # Handle delayed actions
            delay_seconds = action_definition.get("delay")
            if delay_seconds and delay_seconds > 0 and input_id:
                _LOGGER.info(
                    "Scheduling delayed action %d for input '%s': %.1fs delay",
                    idx,
                    input_id,
                    delay_seconds,
                )
                task = asyncio.create_task(
                    self._run_delayed_action(input_id, action_definition, delay_seconds)
                )
                self._pending_delayed_actions.setdefault(input_id, []).append(task)
                # Don't mark as executed — will be executed after delay
                continue

            await self._execute_single_action(action_definition, idx)

            # Mark action as executed
            if is_repeat:
                # For repeat actions, track timing instead of marking as permanently executed
                last_repeat_times[idx] = duration_ms
            executed_actions.add(idx)

        return executed_actions

    async def _execute_single_action(self, action_definition: dict, idx: int = 0) -> None:
        """Execute a single parsed action.

        This is extracted from execute_actions to enable reuse for delayed
        action execution.

        Args:
            action_definition: Parsed action dictionary
            idx: Action index (for logging/cycling)
        """
        action = action_definition.get("action")
        start_time = time.time()

        # ── Common field extraction ──────────────────────────────────
        # Resolve entity_id once based on action type to avoid duplicate guards.
        entity_id: str | None = None
        action_to_execute: str | None = None
        remote_device_id: str | None = None

        if action in (OUTPUT, COVER):
            entity_id = action_definition.get("pin") or action_definition.get(
                "boneio_output" if action == OUTPUT else "boneio_cover"
            )
            action_to_execute = action_definition.get("action_to_execute")
            if not entity_id or not action_to_execute:
                _LOGGER.warning(
                    "Missing entity ID or action_to_execute for %s action", action
                )
                return

        elif action in (REMOTE_OUTPUT, REMOTE_COVER):
            remote_device_id = action_definition.get("remote_device")
            entity_id = action_definition.get(
                "output_id" if action == REMOTE_OUTPUT else "cover_id"
            )
            if not remote_device_id or not entity_id:
                _LOGGER.warning(
                    "Missing remote_device or entity ID for %s action", action
                )
                return

        # ── Action dispatch ──────────────────────────────────────────
        if action == MQTT:
            action_topic = action_definition.get("action_topic")
            action_payload = action_definition.get("action_mqtt_msg")
            if action_topic and action_payload:
                self.send_message(topic=action_topic, payload=action_payload, retain=False)

        elif action == OUTPUT:
            assert entity_id and action_to_execute  # guaranteed by guard above
            output = self.outputs.get_output(entity_id) or self.outputs.get_output_group(entity_id)
            if not output:
                _LOGGER.warning("Output %s not found for action", entity_id)
                return
            _LOGGER.debug(
                "Executing action %s for output %s. Duration: %s",
                action_to_execute,
                output.name if hasattr(output, "name") else entity_id,
                time.time() - start_time,
            )
            _f = getattr(output, action_to_execute)
            await _f()

        elif action == COVER:
            assert entity_id and action_to_execute  # guaranteed by guard above
            cover = self.covers.get_cover(entity_id)
            if not cover:
                _LOGGER.warning("Cover %s not found for action", entity_id)
                return
            extra_data = action_definition.get("extra_data", {})
            # Filter extra_data to only pass params accepted by each action
            filtered_data = filter_cover_extra_data(action_to_execute, extra_data)
            _LOGGER.debug(
                "Executing action %s for cover %s. Duration: %s",
                action_to_execute,
                cover.name if hasattr(cover, "name") else entity_id,
                time.time() - start_time,
            )
            _f = getattr(cover, action_to_execute)
            await _f(**filtered_data)

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
            assert entity_id and remote_device_id  # guaranteed by guard above
            action_output = action_definition.get("action_output", "TOGGLE")

            # Clamp transition to repeat_interval to avoid overlapping animations
            transition_val = action_definition.get("transition")
            if transition_val and action_definition.get("repeat"):
                repeat_interval = action_definition.get("repeat_interval")
                if repeat_interval:
                    ri_seconds = (
                        repeat_interval.total_in_seconds
                        if hasattr(repeat_interval, "total_in_seconds")
                        else repeat_interval / 1000.0
                    )
                    if transition_val > ri_seconds:
                        _LOGGER.debug(
                            "Clamping transition %.3fs to repeat_interval %.3fs",
                            transition_val,
                            ri_seconds,
                        )
                        transition_val = ri_seconds
                action_definition = {**action_definition, "transition": transition_val}

            if action_output == "CYCLE_COLOR":
                await self.remote_devices.cycle_color(
                    device_id=remote_device_id,
                    output_id=entity_id,
                    colors=action_definition.get("colors", []),
                    action_idx=idx,
                    transition=action_definition.get("transition"),
                )

            elif action_output == "CYCLE_PRESET":
                await self.remote_devices.cycle_preset(
                    device_id=remote_device_id,
                    output_id=entity_id,
                    presets=action_definition.get("presets", []),
                    action_idx=idx,
                    transition=action_definition.get("transition"),
                )

            else:
                await self.remote_devices.control_output(
                    device_id=remote_device_id,
                    output_id=entity_id,
                    action=action_output,
                    brightness=action_definition.get("brightness"),
                    brightness_step=action_definition.get("brightness_step"),
                    color_temp=action_definition.get("color_temp"),
                    rgb=action_definition.get("rgb"),
                    transition=action_definition.get("transition"),
                    effect=action_definition.get("effect"),
                    palette=action_definition.get("palette"),
                    effect_speed=action_definition.get("effect_speed"),
                    effect_intensity=action_definition.get("effect_intensity"),
                )

        elif action == REMOTE_COVER:
            assert entity_id and remote_device_id  # guaranteed by guard above
            action_cover = action_definition.get("action_cover", "TOGGLE")
            extra_data = action_definition.get("extra_data", {})
            await self.remote_devices.control_cover(
                device_id=remote_device_id,
                cover_id=entity_id,
                action=action_cover,
                **extra_data,
            )

    async def _run_delayed_action(
        self, input_id: str, action_definition: dict, delay_seconds: float
    ) -> None:
        """Execute an action after a delay, unless cancelled.

        This coroutine sleeps for the specified delay and then executes
        the action. It is wrapped in an asyncio.Task so it can be
        cancelled by :meth:`cancel_delayed_actions`.

        Args:
            input_id: Input entity ID that triggered this delayed action
            action_definition: Parsed action dictionary to execute
            delay_seconds: Number of seconds to wait before executing
        """
        try:
            _LOGGER.debug(
                "Delayed action for input '%s': waiting %.1fs before executing",
                input_id,
                delay_seconds,
            )
            await asyncio.sleep(delay_seconds)
            _LOGGER.info(
                "Delayed action for input '%s': timer expired, executing action",
                input_id,
            )
            await self._execute_single_action(action_definition)
        except asyncio.CancelledError:
            _LOGGER.info(
                "Delayed action for input '%s' was cancelled (motion re-detected?)",
                input_id,
            )
        finally:
            # Clean up: remove this task from the pending list.
            # Note: asyncio tasks report done()=False inside their own finally,
            # so we filter by identity (current_task) instead of done() state.
            current = asyncio.current_task()
            tasks = self._pending_delayed_actions.get(input_id, [])
            self._pending_delayed_actions[input_id] = [
                t for t in tasks if t is not current and not t.done()
            ]
            if not self._pending_delayed_actions[input_id]:
                self._pending_delayed_actions.pop(input_id, None)

    def cancel_delayed_actions(self, input_id: str) -> int:
        """Cancel all pending delayed actions for a given input.

        Called when an event matching ``delay_cancel_on`` arrives for
        the input, e.g. motion re-detected cancels the pending OFF timer.

        Args:
            input_id: Input entity ID whose delayed actions to cancel

        Returns:
            Number of cancelled tasks
        """
        tasks = self._pending_delayed_actions.pop(input_id, [])
        cancelled = 0
        for task in tasks:
            if not task.done():
                task.cancel()
                cancelled += 1
        if cancelled:
            _LOGGER.info(
                "Cancelled %d pending delayed action(s) for input '%s'",
                cancelled,
                input_id,
            )
        return cancelled

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

    async def _reload_remote_devices(self) -> None:
        """Reload remote devices configuration from config file.

        This allows hot-reloading of remote devices without restarting the application.
        Handles ESPHome connections properly (stops old, starts new).
        Also re-registers remote inputs (binary sensors from remote devices).
        """
        config = self._config_helper.get_config()
        remote_devices_config = config.get("remote_devices", [])

        _LOGGER.info("Reloading remote devices configuration")
        # Clean up old remote inputs and outputs before reload
        self.inputs.unregister_remote_inputs()
        self.unregister_remote_outputs()
        await self.remote_devices.reload(remote_devices_config)
        # Re-register remote inputs and outputs from config
        self.register_remote_inputs()
        self.register_remote_outputs()
        # Broadcast all input states so frontend picks up new/removed remote inputs
        self.inputs._broadcast_all_input_states()
        _LOGGER.info("Remote devices configuration reloaded successfully")

    async def _reload_remote_inputs(self) -> None:
        """Reload only the remote_inputs section (without reloading devices).

        Used when only remote input config changed (actions, mode, etc.)
        but the remote devices themselves didn't change.
        """
        _LOGGER.info("Reloading remote inputs configuration")
        self.inputs.unregister_remote_inputs()
        self.register_remote_inputs()
        # Broadcast all input states so frontend picks up new/removed remote inputs
        self.inputs._broadcast_all_input_states()
        _LOGGER.info("Remote inputs configuration reloaded successfully")

    def register_remote_inputs(self) -> None:
        """Register remote inputs from the ``remote_inputs`` config section.

        Delegates to :meth:`InputManager.register_remote_inputs`.
        Should be called after :meth:`RemoteDeviceManager.initialize`.
        """
        config = self._config_helper.get_config()
        remote_inputs_config = config.get("remote_inputs", [])
        self.inputs.register_remote_inputs(self.remote_devices, remote_inputs_config)

    # Keep backward-compatible alias
    register_esphome_binary_sensors = register_remote_inputs

    def register_remote_outputs(self) -> None:
        """Register remote outputs from the ``remote_outputs`` config section.

        Creates ``RemoteOutputBase`` instances and registers them in
        :class:`OutputManager` so they are available for irrigation,
        output groups, and frontend display.
        """
        from boneio.components.output.remote import RemoteOutputBase

        config = self._config_helper.get_config()
        remote_outputs_config: list[dict] = config.get("remote_outputs", [])

        if not remote_outputs_config:
            return

        for out_cfg in remote_outputs_config:
            device_id = out_cfg.get("device_id", "")
            output_id = out_cfg.get("output_id", "")
            remote_source = out_cfg.get("remote_source", "esphome_api")

            if not device_id or not output_id:
                _LOGGER.error("Remote output config missing device_id or output_id: %s", out_cfg)
                continue

            # Build entity ID
            entity_id = out_cfg.get("id", "").strip()
            if not entity_id:
                entity_id = f"{device_id}_{output_id}".replace("-", "_")

            name = str(out_cfg.get("name") or entity_id)
            output_type = str(out_cfg.get("output_type", "switch"))
            show_in_ha = bool(out_cfg.get("show_in_ha", False))
            area = out_cfg.get("area")
            on_disconnect = str(out_cfg.get("on_disconnect", "ignore"))

            # Check for duplicates
            if self.outputs.get_output(entity_id) is not None:
                _LOGGER.warning(
                    "Remote output '%s' conflicts with existing output, skipping",
                    entity_id,
                )
                continue

            remote_output = RemoteOutputBase(
                id=entity_id,
                name=name,
                device_id=device_id,
                output_id=output_id,
                remote_source=remote_source,
                event_bus=self._event_bus,
                output_type=output_type,
                show_in_ha=show_in_ha,
                area=area,
                on_disconnect=on_disconnect,
            )

            # Set the device manager reference if the device is already loaded.
            # ESPHome devices may not be in _devices yet (loaded in background),
            # so _device_manager may remain None — resolved lazily in
            # RemoteOutputBase.control_output() or when the device connects.
            device = self.remote_devices.get_device(device_id)
            if device is not None:
                remote_output._device_manager = device
                remote_output._register_state_callback()
            else:
                # Store reference to remote_devices so the output can
                # resolve its device manager lazily when needed.
                remote_output._remote_devices_ref = self.remote_devices
                _LOGGER.debug(
                    "Remote output '%s': device '%s' not yet available, will resolve lazily",
                    entity_id,
                    device_id,
                )

            # Register in OutputManager so it's available everywhere
            self.outputs._outputs[entity_id] = remote_output  # type: ignore[assignment]
            _LOGGER.info(
                "Registered remote output: id='%s' device='%s' output='%s' type='%s'",
                entity_id,
                device_id,
                output_id,
                output_type,
            )

        _LOGGER.info(
            "Remote outputs registered: %d total",
            sum(1 for o in self.outputs._outputs.values() if getattr(o, "is_remote", False)),
        )

    def unregister_remote_outputs(self) -> None:
        """Remove all remote outputs from OutputManager."""
        remote_ids = [oid for oid, o in self.outputs._outputs.items() if getattr(o, "is_remote", False)]
        for oid in remote_ids:
            del self.outputs._outputs[oid]
            _LOGGER.debug("Unregistered remote output: %s", oid)

    async def _reload_remote_outputs(self) -> None:
        """Reload only the remote_outputs section.

        Used when remote output config changed but remote devices didn't.
        """
        _LOGGER.info("Reloading remote outputs configuration")
        self.unregister_remote_outputs()
        self.register_remote_outputs()

    async def _reload_templates_and_irrigation(self) -> None:
        """Reload templates and irrigation when the template section changes.

        The template section may contain irrigation-platform entries, so both
        TemplateManager and IrrigationManager must be reloaded together.
        TemplateManager.reload_templates filters out irrigation entries internally.
        """
        await self.templates.reload_templates()
        await self.irrigation.reload_irrigation()

    async def publish_discovery(self) -> None:
        """Publish all device discovery information to MQTT.

        This should be called after manager is fully initialized.
        """
        await self.send_all_ha_autodiscovery()

        if hasattr(self, "_discovery_publisher"):
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
        if not hasattr(self, "_discovery_publisher"):
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
            "adc": publisher.publish_sensors,
            "irrigation": publisher.publish_irrigation,
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
                           Supported sections: 'output', 'cover', 'input', 'event', 'binary_sensor', 'adc',
                           'modbus_devices', 'sensor', 'virtual_energy_sensor', 'logger', 'remote_devices', 'oled'

        Returns:
            dict: Status of reload operation with details:
                - status: 'success', 'partial', or 'error'
                - reloaded_sections: List of successfully reloaded sections
                - failed_sections: List of sections that failed to reload
        """
        from boneio.const import BINARY_SENSOR, EVENT_ENTITY

        _LOGGER.info("Starting config reload")

        # Reload config cache in ConfigHelper
        # NOTE: reload_config() calls load_config_from_file() which may run
        # full Cerberus validation (~20s) on disk cache miss. Run in a thread
        # executor to keep the event loop responsive (MQTT, WS, modbus).
        try:
            config = await asyncio.to_thread(self._config_helper.reload_config)
            # Update areas mapping from reloaded config
            self._config_helper.set_areas(config.get("areas", []))
        except Exception as e:
            _LOGGER.error(f"Failed to reload config: {e}")
            return {"status": "error", "message": str(e), "reloaded_sections": [], "failed_sections": []}

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
            "remote_inputs": self._reload_remote_inputs,  # Remote inputs (binary sensors from remote devices)
            "remote_outputs": self._reload_remote_outputs,  # Remote outputs (switches/lights from remote devices)
            "template": self._reload_templates_and_irrigation,  # Thermostats, alarm panels, and irrigation
            "irrigation": self.irrigation.reload_irrigation,  # Irrigation controllers
            "adc": self.sensors.reload_adc_sensors,  # ADC analog sensors
            "areas": lambda: None,  # Areas are already reloaded in reload_config above
            "oled": self.display.reload_oled,  # OLED display screens, screensaver
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

        Sends online status to MQTT and starts template MQTT subscriptions.
        """
        _LOGGER.info("Sending online state.")
        topic = f"{self._config_helper.topic_prefix}/{STATE}"
        self.send_message(topic=topic, payload=ONLINE, retain=True)

        # Immediately refresh OLED MQTT status (event-driven, no polling delay)
        self.display.notify_mqtt_state_changed()

        # Start template entities (subscribe to MQTT command topics)
        await self.templates.start()
        await self.irrigation.start()

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
        topic_parts_raw = topic[len(self._config_helper.cmd_topic_prefix) :].split("/")
        topic_parts = deque(topic_parts_raw)

        try:
            msg_type = topic_parts.popleft()
            device_id = topic_parts.popleft()
            command = topic_parts.pop()
            _LOGGER.debug("Divide topic to: msg_type: %s, device_id: %s, command: %s", msg_type, device_id, command)
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

        # Handle adjustable duration commands (set_duration)
        if msg_type == OUTPUT and command == "set_duration":
            target_device = self.outputs.get_output(device_id)
            if target_device and target_device.adjustable_duration_enabled:
                try:
                    value = float(message)
                    # HA sends value in the user-configured unit — convert to seconds
                    if target_device.duration_unit == "min":
                        seconds = value * 60
                    else:
                        seconds = value
                    target_device.set_adjustable_duration(seconds)
                    # Persist to state manager (always in seconds)
                    self._state_manager.save_attribute(
                        attr_type="adjustable_duration",
                        attribute=device_id,
                        value=target_device.adjustable_duration,
                    )
                    # Publish updated duration back to MQTT (in the user's unit)
                    if target_device.duration_unit == "min":
                        publish_value = round(target_device.adjustable_duration / 60, 2)
                    else:
                        publish_value = target_device.adjustable_duration
                    self._message_bus.send_message(
                        topic=f"{self._topic_prefix}/{OUTPUT}/{device_id}/duration",
                        payload={"value": publish_value},
                        retain=True,
                    )
                except (TypeError, ValueError):
                    _LOGGER.warning("Invalid duration value '%s' for output '%s'", message, device_id)
            else:
                _LOGGER.debug("Output '%s' does not support adjustable duration", device_id)
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
                elif command == "tilt":
                    # Set cover tilt position (only for VenetianCover)
                    from boneio.components.cover.venetian import VenetianCover

                    if isinstance(cover, VenetianCover):
                        try:
                            tilt = int(message)
                            await cover.set_tilt(tilt)
                        except ValueError:
                            _LOGGER.warning("Invalid cover tilt value: %s", message)
                    else:
                        _LOGGER.debug("Cover %s does not support tilt control", device_id)
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

        if msg_type == "modbus" and command == "set_polling":
            target_device = self.modbus.get_all_coordinators().get(device_id)
            if target_device and isinstance(message, str):
                enabled = message.upper() == ON
                target_device.set_polling_enabled(enabled)
                _LOGGER.info(
                    "Modbus polling for %s set to %s via MQTT",
                    device_id,
                    "enabled" if enabled else "disabled",
                )
            else:
                _LOGGER.debug("Modbus coordinator not found: %s", device_id)
            return

        if msg_type == "modbus" and command == "set":
            target_device = self.modbus.get_all_coordinators().get(device_id)
            if target_device and isinstance(message, str):
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
