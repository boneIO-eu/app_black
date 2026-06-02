"""Input manager - handles all input devices.

This module manages all input devices including:
- Event buttons (single, double, long press)
- Binary sensors (on/off states)
- Input actions and callbacks
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from boneio.components.input import (
    GpioEventButton,
    GpioInputBinarySensor,
    RemoteInputBase,
)
from boneio.const import (
    ACTIONS,
    BINARY_SENSOR,
    DEVICE_CLASS,
    EVENT_ENTITY,
    ID,
    INPUT,
    INPUT_SENSOR,
    LONG,
    PIN,
    SHOW_HA,
)
from boneio.core.manager.remote_input_registrar import RemoteInputRegistrar
from boneio.exceptions import GPIOInputException
from boneio.integration.homeassistant import (
    ha_binary_sensor_availabilty_message,
    ha_event_availabilty_message,
)
from boneio.models.events import InputEvent

if TYPE_CHECKING:
    from boneio.core.manager import Manager

_LOGGER = logging.getLogger(__name__)


class InputManager:
    """Manages all inputs (event buttons, binary sensors).

    This manager handles:
    - Event buttons with multiclick detection
    - Binary sensors with state tracking
    - Input actions and callbacks
    - Dynamic input reconfiguration
    - Home Assistant autodiscovery

    Args:
        manager: Parent Manager instance
        event_pins: List of event button configurations
        binary_pins: List of binary sensor configurations
    """

    def __init__(
        self,
        manager: Manager,
        event_pins: list[dict],
        binary_pins: list[dict],
    ):
        """Initialize input manager."""
        self._manager = manager
        self._inputs: dict[str, GpioEventButton | GpioInputBinarySensor | RemoteInputBase] = {}
        self._event_pins = event_pins
        self._binary_pins = binary_pins
        # Remote input helper — handles ESPHome / CAN / MQTT input registration
        self._remote_registrar = RemoteInputRegistrar(
            manager,
            ha_discovery_fn=self._publish_input_ha_discovery,
        )

        # Track inputs that already had first long press published to MQTT (for single mode)
        # Maps input_id -> timestamp of last long press MQTT publish
        self._long_press_mqtt_last_ts: dict[str, float] = {}

        # Configure inputs
        self._configure_inputs()

        # Register global input event listener
        # This catches all input events (entity_id="" means all entities)
        self._manager._event_bus.add_event_listener(
            event_type="input",
            entity_id="",
            listener_id="input_manager",
            target=self.handle_input_event,
        )

        _LOGGER.info(
            "InputManager initialized with %d inputs (%d events, %d binary sensors)",
            len(self._inputs),
            len(event_pins),
            len(binary_pins),
        )

    def _configure_inputs(self, reload_config: bool = False) -> None:
        """Configure inputs (events and binary sensors).

        Args:
            reload_config: If True, reload configuration from file and update existing inputs
        """

        def get_input_id_from_gpio(gpio: dict, pin: str) -> str:
            """Get input ID from gpio config (same logic as in _configure_event_sensor).

            Note: boneio_input is normalized to lowercase to match yaml_util.py behavior.
            """
            if ID in gpio:
                return str(gpio.get(ID))
            elif "boneio_input" in gpio:
                # Normalize to lowercase (consistent with yaml_util.py input_mapping lookup)
                return str(gpio.get("boneio_input", pin)).lower()
            return pin

        def check_if_input_configured(input_id: str) -> bool:
            """Check if input is already configured (only blocks new configs, not reloads)."""
            if input_id in self._inputs:
                if not reload_config:
                    _LOGGER.warning("Input %s is already configured. Omitting it.", input_id)
                    return True
                # During reload, we want to update existing inputs - don't block
                return False
            return False

        def configure_single_input(
            configure_sensor_func: Callable, gpio: dict, expected_class: type
        ) -> None:
            """Configure a single input (event or binary sensor).

            Args:
                configure_sensor_func: The _configure_event_sensor or _configure_binary_sensor method.
                gpio: GPIO configuration dictionary.
                expected_class: The expected class type (GpioEventButton or GpioInputBinarySensor).
            """
            # Work on a copy to avoid modifying the cached config
            gpio_copy = gpio.copy()

            try:
                pin = gpio_copy.pop(PIN)
            except (AttributeError, KeyError) as err:
                _LOGGER.error("PIN is required for input configuration: %s", err)
                return

            # Get input_id to check if already configured (uses same logic as _configure_*_sensor)
            input_id = get_input_id_from_gpio(gpio_copy, pin)

            if check_if_input_configured(input_id):
                return

            existing_input = self._inputs.get(input_id, None) if reload_config else None

            # Guard: if the existing input is a different class (type changed,
            # e.g. event → binary_sensor), do NOT pass it as existing_input.
            # A new object with the correct detector must be created instead.
            if existing_input is not None and not isinstance(existing_input, expected_class):
                _LOGGER.info(
                    "Input %s type changed from %s to %s, creating new input object",
                    input_id,
                    type(existing_input).__name__,
                    expected_class.__name__,
                )
                existing_input = None

            input_device = configure_sensor_func(
                gpio=gpio_copy,
                pin=pin,
                existing_input=existing_input,
                actions=self._manager.parse_actions(pin, gpio_copy.pop(ACTIONS, {})),
            )

            if input_device:
                self._inputs[input_device.id] = input_device

        # Reload configuration if requested
        if reload_config:
            # Get config from ConfigHelper (already reloaded by Manager)
            config = self._manager._config_helper.get_config()
            if config:
                self._event_pins = config.get(EVENT_ENTITY, [])
                self._binary_pins = config.get(BINARY_SENSOR, [])
                self._manager._config_helper.clear_autodiscovery_type(ha_type=EVENT_ENTITY)
                self._manager._config_helper.clear_autodiscovery_type(ha_type=BINARY_SENSOR)

        # Configure event buttons
        for gpio in self._event_pins:
            try:
                configure_single_input(
                    configure_sensor_func=self._configure_event_sensor,
                    gpio=gpio,
                    expected_class=GpioEventButton,
                )
            except GPIOInputException as err:
                _LOGGER.error("Failed to configure event input: %s", err)

        # Configure binary sensors
        for gpio in self._binary_pins:
            try:
                configure_single_input(
                    configure_sensor_func=self._configure_binary_sensor,
                    gpio=gpio,
                    expected_class=GpioInputBinarySensor,
                )
            except GPIOInputException as err:
                _LOGGER.error("Failed to configure binary sensor: %s", err)

    def _configure_event_sensor(
        self,
        gpio: dict,
        pin: str,
        existing_input: GpioEventButton | None = None,
        actions: dict | None = None,
    ) -> GpioEventButton | None:
        """Configure event input sensor with multiclick detection.

        Args:
            gpio: GPIO configuration dictionary
            pin: Pin name (e.g., "P8_30")
            existing_input: Existing input instance (for reload)
            actions: Dictionary of actions for different click types

        Returns:
            Configured GpioEventButton instance or None on error
        """
        actions = actions or {}
        try:
            # Determine display name (ensure it's always a string)
            if "name" in gpio:
                name: str = str(gpio.pop("name"))
            elif ID in gpio:
                name = str(gpio.get(ID, pin))
            elif "boneio_input" in gpio:
                name = str(gpio.get("boneio_input", pin))
            else:
                name = pin

            # ID strategy: explicit 'id' > 'boneio_input' > 'pin'
            # Note: boneio_input is normalized to lowercase to match yaml_util.py behavior
            if ID in gpio:
                input_id: str = str(gpio.pop(ID))
            elif "boneio_input" in gpio:
                input_id = str(gpio.get("boneio_input", pin)).lower()
            else:
                input_id = pin

            # Get area for HA assignment
            area = gpio.pop("area", None)

            # Reload: update existing input's actions and name
            if existing_input:
                # Check if HA-relevant fields changed (name, area, mqtt_sequences)
                old_name = existing_input._name if hasattr(existing_input, "_name") else None
                old_area = getattr(existing_input, "area", None)
                old_mqtt_sequences = existing_input.mqtt_sequences if hasattr(existing_input, "mqtt_sequences") else {}
                new_mqtt_sequences = gpio.get("mqtt_sequences", {})
                ha_fields_changed = (
                    (old_name != name) or (old_area != area) or (old_mqtt_sequences != new_mqtt_sequences)
                )

                # Update actions (always - this is internal to the controller)
                existing_input.set_actions(actions=actions)

                # Update name if changed
                if hasattr(existing_input, "_name"):
                    existing_input._name = name

                # Store area on input
                existing_input.area = area

                # Update device_class from new config
                existing_input._device_class = gpio.get(DEVICE_CLASS)

                # Update mqtt_sequences configuration
                if hasattr(existing_input, "_mqtt_sequences"):
                    existing_input._mqtt_sequences = new_mqtt_sequences

                # Update timing parameters if this is an event button
                existing_input.update_timings(
                    double_click_duration=gpio.get("double_click_duration"),
                    long_press_duration=gpio.get("long_press_duration"),
                    sequence_window_duration=gpio.get("sequence_window_duration"),
                    sequence_mode=gpio.get("sequence_mode"),
                    actions=actions,
                    mqtt_sequences=new_mqtt_sequences,
                    enable_triple_click=gpio.get("enable_triple_click"),
                    long_press_mqtt_mode=gpio.get("long_press_mqtt_mode"),
                    max_long_press_duration=gpio.get("max_long_press_duration"),
                )

                # Re-send HA discovery only if HA-relevant fields changed (name, area, mqtt_sequences)
                # Actions are internal to the controller and don't need HA update
                if ha_fields_changed and gpio.get(SHOW_HA, True):
                    _LOGGER.debug(f"HA-relevant fields changed for {input_id}, re-sending discovery")
                    self._publish_input_ha_discovery(
                        ha_type=EVENT_ENTITY,
                        input_id=input_id,
                        name=name,
                        device_class=existing_input.device_class,
                        area=area,
                        mqtt_sequences=gpio.get("mqtt_sequences"),
                        enable_triple_click=gpio.get("enable_triple_click", False),
                    )
                return existing_input

            # Create new event input
            input_device = GpioEventButton(
                pin=pin,
                name=name,
                id=input_id,
                input_type=INPUT,
                actions=actions,
                event_bus=self._manager._event_bus,
                **gpio,
            )

            # Store area on input
            input_device.area = area

            # Register with Home Assistant
            if gpio.get(SHOW_HA, True):
                self._publish_input_ha_discovery(
                    ha_type=EVENT_ENTITY,
                    input_id=input_id,
                    name=name,
                    device_class=input_device.device_class,
                    area=area,
                    mqtt_sequences=gpio.get("mqtt_sequences"),
                    enable_triple_click=gpio.get("enable_triple_click", False),
                )

            return input_device

        except GPIOInputException as err:
            _LOGGER.error("Failed to configure event input on pin %s: %s", pin, err)
            return None

    def _configure_binary_sensor(
        self,
        gpio: dict,
        pin: str,
        existing_input: GpioInputBinarySensor | None = None,
        actions: dict | None = None,
    ) -> GpioInputBinarySensor | None:
        """Configure binary sensor input with state detection.

        Args:
            gpio: GPIO configuration dictionary
            pin: Pin name (e.g., "P8_30")
            existing_input: Existing input instance (for reload)
            actions: Dictionary of actions for different states

        Returns:
            Configured GpioInputBinarySensor instance or None on error
        """
        actions = actions or {}
        try:
            # Determine display name (ensure it's always a string)
            if "name" in gpio:
                name: str = str(gpio.pop("name"))
            elif ID in gpio:
                name = str(gpio.get(ID, pin))
            elif "boneio_input" in gpio:
                name = str(gpio.get("boneio_input", pin))
            else:
                name = pin

            # ID strategy: explicit 'id' > 'boneio_input' > 'pin'
            # Note: boneio_input is normalized to lowercase to match yaml_util.py behavior
            if ID in gpio:
                input_id: str = str(gpio.pop(ID))
            else:
                input_id = str(gpio.get("boneio_input", pin)).lower()

            # Get area for HA assignment
            area = gpio.pop("area", None)

            # Reload: update existing input's actions and name
            if existing_input:
                # Check if HA-relevant fields changed (name, area)
                old_name = existing_input._name if hasattr(existing_input, "_name") else None
                old_area = getattr(existing_input, "area", None)
                ha_fields_changed = (old_name != name) or (old_area != area)

                # Update actions (always - this is internal to the controller)
                existing_input.set_actions(actions=actions)

                # Update name if changed
                if hasattr(existing_input, "_name"):
                    existing_input._name = name

                # Store area on input
                existing_input.area = area

                # Update device_class from new config
                existing_input._device_class = gpio.get(DEVICE_CLASS)

                # Re-send HA discovery only if HA-relevant fields changed (name, area)
                # Actions are internal to the controller and don't need HA update
                if ha_fields_changed and gpio.get(SHOW_HA, True):
                    _LOGGER.debug(f"HA-relevant fields changed for {input_id}, re-sending discovery")
                    self._publish_input_ha_discovery(
                        ha_type=BINARY_SENSOR,
                        input_id=input_id,
                        name=name,
                        device_class=existing_input.device_class,
                        area=area,
                    )

                # Send current state if initial_send is enabled (so user doesn't need to restart)
                if gpio.get("initial_send", False):
                    _LOGGER.debug(f"Sending current state for {input_id} after reload (initial_send=True)")
                    existing_input.send_current_state()

                return existing_input

            # Create new binary sensor input
            input_device = GpioInputBinarySensor(
                pin=pin,
                name=name,
                id=input_id,
                actions=actions,
                input_type=INPUT_SENSOR,
                event_bus=self._manager._event_bus,
                **gpio,
            )

            # Store area on input
            input_device.area = area

            # Register with Home Assistant
            if gpio.get(SHOW_HA, True):
                self._publish_input_ha_discovery(
                    ha_type=BINARY_SENSOR,
                    input_id=input_id,
                    name=name,
                    device_class=input_device.device_class,
                    area=area,
                )

            return input_device

        except GPIOInputException as err:
            _LOGGER.error("Failed to configure binary sensor on pin %s: %s", pin, err)
            return None

    def get_input(self, pin: str) -> GpioEventButton | GpioInputBinarySensor | RemoteInputBase | None:
        """Get input by pin.

        Args:
            pin: Pin identifier

        Returns:
            Input instance or None if not found
        """
        return self._inputs.get(pin)

    def get_all_inputs(self) -> dict[str, GpioEventButton | GpioInputBinarySensor | RemoteInputBase]:
        """Get all inputs.

        Returns:
            Dictionary of all inputs
        """
        return self._inputs

    def get_inputs_list(self) -> list[GpioEventButton | GpioInputBinarySensor | RemoteInputBase]:
        """Get list of all inputs.

        Returns:
            List of all input instances
        """
        return list(self._inputs.values())

    def send_current_state_for_input(self, input_id: str) -> bool:
        """Schedule sending current GPIO state for a specific input.

        Registers a callback on the GPIO manager so that send_current_state()
        runs after GPIO lines are fully configured. If the GPIO manager is
        already running, the callback executes immediately.

        Args:
            input_id: Input entity ID (boneio_input).

        Returns:
            True if the input was found and callback registered, False otherwise.
        """
        from boneio.hardware.gpio.input import get_gpio_manager

        inp = self._inputs.get(input_id)
        if inp is None:
            _LOGGER.warning("send_current_state_for_input: input '%s' not found", input_id)
            return False
        if not isinstance(inp, GpioInputBinarySensor):
            _LOGGER.warning("send_current_state_for_input: input '%s' is not a binary sensor", input_id)
            return False

        gpio_manager = get_gpio_manager(loop=inp._loop)
        gpio_manager.register_on_start_callback(inp.send_current_state)
        _LOGGER.debug("send_current_state_for_input: registered on-start callback for '%s'", input_id)
        return True

    async def reload_inputs(self) -> None:
        """Reload input configuration from file.

        This handles:
        - Updating existing inputs (actions, area, name)
        - Removing deleted inputs (from internal state and HA Discovery)
        - Adding inputs that use already-registered GPIO pins (e.g., moving from event to binary_sensor)
        """
        _LOGGER.info("Reloading input configuration")

        # Get config from ConfigHelper (already reloaded by Manager)
        config = self._manager._config_helper.get_config()

        # Build map of new inputs from config (input_id -> {pin, area, ha_type})
        # Note: boneio_input is normalized to lowercase to match yaml_util.py behavior
        new_input_map: dict[str, dict] = {}
        for ha_type, gpio_list in [
            (EVENT_ENTITY, config.get(EVENT_ENTITY, [])),
            (BINARY_SENSOR, config.get(BINARY_SENSOR, [])),
        ]:
            for gpio in gpio_list:
                pin = gpio.get("pin")
                # Determine input ID (same logic as in _configure_event_sensor/_configure_binary_sensor)
                if "id" in gpio:
                    input_id = gpio["id"]
                elif "boneio_input" in gpio:
                    input_id = gpio["boneio_input"].lower()
                elif pin:
                    input_id = pin
                else:
                    continue
                new_input_map[input_id] = {"pin": pin, "area": gpio.get("area"), "ha_type": ha_type}

        # Find inputs to remove (in current config but not in new config)
        current_input_ids = set(self._inputs.keys())
        new_input_ids = set(new_input_map.keys())

        inputs_to_remove = current_input_ids - new_input_ids

        _LOGGER.info("Input reload: current=%s, new=%s, to_remove=%s", current_input_ids, new_input_ids, inputs_to_remove)

        # Detect inputs whose type changed (event <-> binary_sensor).
        # These must be removed and re-created with the correct detector class.
        inputs_type_changed: set[str] = set()
        for input_id, new_info in new_input_map.items():
            existing = self._inputs.get(input_id)
            if existing is None:
                continue
            new_ha_type = new_info["ha_type"]
            # GpioEventButton has input_type=INPUT, GpioInputBinarySensor has input_type=INPUT_SENSOR
            if new_ha_type == EVENT_ENTITY and not isinstance(existing, GpioEventButton):
                inputs_type_changed.add(input_id)
            elif new_ha_type == BINARY_SENSOR and not isinstance(existing, GpioInputBinarySensor):
                inputs_type_changed.add(input_id)

        if inputs_type_changed:
            _LOGGER.info("Input type changed for: %s — will recreate with new detector", inputs_type_changed)

        # Remove deleted inputs from internal state (GPIO pin stays registered - minimal overhead)
        ha_discovery_changed = False

        for input_id in inputs_to_remove | inputs_type_changed:
            input_device = self._inputs.get(input_id)
            if input_device:
                old_area = getattr(input_device, "area", None)

                # Remove HA Discovery
                self._remove_input_ha_discovery(input_id, old_area)
                ha_discovery_changed = True

                # Remove from internal state (GPIO detector will be replaced by new input class)
                del self._inputs[input_id]
                _LOGGER.info("Removed input %s (type_changed=%s)", input_id, input_id in inputs_type_changed)

        # Check for area changes on remaining inputs
        for input_id, input_device in self._inputs.items():
            old_area = getattr(input_device, "area", None)
            new_area = new_input_map.get(input_id, {}).get("area")

            if old_area != new_area:
                ha_discovery_changed = True
                _LOGGER.info("Input %s area changed: %s -> %s, removing old HA Discovery", input_id, old_area, new_area)
                self._remove_input_ha_discovery(input_id, old_area)

        # Wait for HA to process the removal before sending new discovery
        if ha_discovery_changed:
            _LOGGER.debug("Waiting 1s for HA to process discovery removal...")
            await asyncio.sleep(1)

        # _configure_inputs with reload_config=True will:
        # - Update existing inputs (actions, area, name)
        # - Create new inputs for type-changed entries (old objects removed above)
        # - Add new inputs if their GPIO pin is already registered
        self._configure_inputs(reload_config=True)

        # Broadcast all input states to WebSocket clients
        # Global listeners will receive these events for all inputs (including new ones)
        self._broadcast_all_input_states()

    def _broadcast_all_input_states(self) -> None:
        """Broadcast current state of all inputs via WebSocket.

        This is called after reload to ensure frontend receives
        the updated input list immediately.
        """
        import time

        from boneio.models import InputState

        timestamp = time.time()

        for input_ in self._inputs.values():
            try:
                input_state = InputState(
                    name=input_.name,
                    state=input_.last_state,
                    type=input_.input_type,
                    pin=input_.pin,
                    timestamp=timestamp,
                    boneio_input=input_.boneio_input,
                    area=input_.area,
                    remote=isinstance(input_, RemoteInputBase),
                )
                event = InputEvent(entity_id=input_.id, state=input_state, click_type=None, duration=None)
                self._manager._event_bus.trigger_event(event)
            except Exception as e:
                _LOGGER.debug("Error broadcasting input state %s: %s", input_.id, e)

    def _remove_input_ha_discovery(self, input_id: str, old_area: str | None = None) -> None:
        """Remove HA Discovery entries for an input.

        This sends empty payloads to all discovery topics for the input,
        which removes the entity from Home Assistant. This is needed when
        an input's area changes (different area = different device identifier).

        Args:
            input_id: ID of the input to remove from HA Discovery
            old_area: The previous area of the input (used to construct old device identifier)
        """
        # Construct the old device identifier based on the old area
        topic_prefix = self._manager._config_helper.topic_prefix
        if old_area:
            old_device_identifier = f"{topic_prefix}_{old_area}"
        else:
            old_device_identifier = topic_prefix  # If no area was set, it used the main device identifier

        # Find all autodiscovery topics for this input ID with the old device identifier
        _LOGGER.info(
            f"Looking for autodiscovery topics for input_id={input_id}, old_device_identifier={old_device_identifier}"
        )
        matching_topics = self._manager._config_helper.get_autodiscovery_topics_for_id(input_id, old_device_identifier)
        _LOGGER.info(f"Found {len(matching_topics)} matching topics: {matching_topics}")

        for ha_type, topic in matching_topics:
            _LOGGER.info(f"Removing HA Discovery for input {input_id} (old area: {old_area}): {topic}")
            # Send empty/null payload to remove from HA (HA requires zero-length retained message)
            self._manager.send_message(topic=topic, payload=None, retain=True)
            # Remove from internal cache
            self._manager._config_helper.remove_autodiscovery_msg(ha_type, topic)

    # Sequence click types that require mqtt_sequences configuration
    SEQUENCE_CLICK_TYPES = {"double_then_long", "single_then_long", "double_then_single"}

    def _publish_input_event_to_mqtt(
        self, input_instance: GpioEventButton | GpioInputBinarySensor | RemoteInputBase, event: InputEvent
    ) -> None:
        """Publish input event to MQTT for Home Assistant.

        For event buttons (input_type=INPUT): sends JSON with event_type
        For binary sensors (input_type=INPUT_SENSOR): sends pressed/released state

        Sequence events (double_then_long, single_then_long, double_then_single) are only
        published if explicitly enabled in mqtt_sequences configuration.

        Args:
            input_instance: The input device instance
            event: The input event data
        """
        topic_prefix = self._manager._config_helper.topic_prefix
        input_id = input_instance.id
        input_type = input_instance.input_type
        click_type = event.click_type
        topic = f"{topic_prefix}/input/{input_id}"

        if input_type == INPUT:
            # Check if this is a sequence event that requires mqtt_sequences config
            if click_type in self.SEQUENCE_CLICK_TYPES:
                _LOGGER.debug(
                    "Sequence event %s on %s, mqtt_sequences=%s, should_publish=%s",
                    click_type,
                    input_id,
                    input_instance.mqtt_sequences,
                    input_instance.should_publish_sequence_to_mqtt(click_type),
                )
                if not input_instance.should_publish_sequence_to_mqtt(click_type):
                    _LOGGER.debug(
                        "Skipping MQTT publish for sequence %s on %s (not enabled in mqtt_sequences)",
                        click_type,
                        input_id,
                    )
                    return

            # Long press MQTT mode filtering:
            # In 'single' mode, only publish the first long press event per press cycle.
            # Periodic updates (with growing duration) are skipped to avoid
            # triggering repeated actions in Node-RED or other MQTT consumers.
            # A new press cycle is detected when duration resets (new duration < last duration).
            if click_type == LONG:
                mqtt_mode = getattr(input_instance, "long_press_mqtt_mode", "single")
                if mqtt_mode == "single":
                    current_duration = event.duration or 0.0
                    last_duration = self._long_press_mqtt_last_ts.get(input_id, 0.0)
                    if current_duration > last_duration and last_duration > 0.0:
                        # Duration is growing — this is a periodic update, skip it
                        _LOGGER.debug(
                            "Skipping periodic long press MQTT for %s (mode=single, duration=%.3f > last=%.3f)",
                            input_id,
                            current_duration,
                            last_duration,
                        )
                        self._long_press_mqtt_last_ts[input_id] = current_duration
                        return
                    # New press cycle (duration reset) or first long press — publish
                    self._long_press_mqtt_last_ts[input_id] = current_duration
            else:
                # Any non-long event clears the tracking
                self._long_press_mqtt_last_ts.pop(input_id, None)

            event_payload: dict[str, str | float | None] = {"event_type": click_type}
            if event.duration is not None:
                event_payload["duration"] = round(event.duration, 3)

            self._manager.send_message(
                topic=topic,
                payload=json.dumps(event_payload),
            )
            _LOGGER.debug("Published event to MQTT: topic=%s, payload=%s", topic, event_payload)

        elif input_type == INPUT_SENSOR:
            payload = str(click_type)  # "pressed" or "released"

            self._manager.send_message(
                topic=topic,
                payload=payload,
            )
            _LOGGER.debug("Published binary sensor state to MQTT: topic=%s, payload=%s", topic, payload)

    async def handle_input_event(self, event: InputEvent) -> None:
        """Handle input event from EventBus.

        Called when an input (event or binary_sensor) triggers.
        This is the central handler for all input events.

        Args:
            event_data: Event data containing:
                - entity_id: Input identifier
                - click_type: Type of click (pressed, released, single, double, long)
                - duration: Duration of the event
                - event_state: Input state information
        """

        if not event.entity_id or not event.click_type:
            # State-sync events (e.g. from _broadcast_all_input_states after reload)
            # have click_type=None — this is expected, not an error.
            _LOGGER.debug(
                "Ignoring input event without click_type (state sync): entity_id=%s",
                event.entity_id,
            )
            return
        # Get the input instance and retrieve actions for this click type
        input_instance = self._inputs.get(event.entity_id)
        if not input_instance:
            _LOGGER.warning("Input %s not found for event handling", event.entity_id)
            return

        actions = input_instance.get_actions_of_click(event.click_type)

        _LOGGER.debug(
            "Handling input event: entity_id=%s, click_type=%s, actions=%d",
            event.entity_id,
            event.click_type,
            len(actions),
        )

        # Send event to MQTT for Home Assistant
        self._publish_input_event_to_mqtt(input_instance, event)

        # Route to template entities (gate covers, alarm panels)
        # This must happen before the publish_only check so initial state
        # sync events reach gate covers and alarm panels.
        self._manager.templates.on_input_event(event.entity_id, event.click_type)

        # If publish_only is set, skip action execution (used for initial state sync)
        if event.publish_only:
            _LOGGER.debug("Skipping action execution for %s (publish_only=True)", event.entity_id)
            return

        # Cancel pending delayed actions if this event matches delay_cancel_on
        # Check ALL click types' actions for delay_cancel_on (not just current click_type)
        self._cancel_delayed_if_matching(input_instance, event.entity_id, event.click_type)

        # Execute actions with duration threshold support
        if actions and event.click_type == LONG:
            # Get executed_actions and repeat times from detector state
            detector = getattr(input_instance, "_detector", None)
            executed_actions = getattr(detector._state, "executed_long_actions", set()) if detector else set()
            last_repeat_times = getattr(detector._state, "last_repeat_times", {}) if detector else {}

            # Lazy evaluation: Check if there are any pending actions
            duration_ms = (event.duration or 0) * 1000
            has_pending_actions = False
            for idx, action in enumerate(actions):
                is_repeat = action.get("repeat", False)
                if is_repeat:
                    # Repeat actions are always potentially pending (throttled in execute_actions)
                    repeat_interval_ms = action.get("repeat_interval", 1000)
                    last_time = last_repeat_times.get(idx, 0.0)
                    if last_time == 0 or (duration_ms - last_time) >= repeat_interval_ms:
                        has_pending_actions = True
                        break
                    continue
                if idx in executed_actions:
                    continue  # Already executed
                min_dur = action.get("min_duration")
                max_dur = action.get("max_duration")
                if min_dur is not None or max_dur is not None:
                    # Has duration thresholds - might need to execute
                    has_pending_actions = True
                    break
                elif not executed_actions:
                    # No thresholds and nothing executed yet - first event
                    has_pending_actions = True
                    break

            # Skip execute_actions if no pending actions (optimization for periodic events)
            if not has_pending_actions:
                _LOGGER.debug(
                    "Skipping execute_actions for %s - no pending actions (executed=%s)",
                    event.entity_id,
                    executed_actions,
                )
            else:
                # Execute actions with duration checking
                new_executed = await self._manager.execute_actions(
                    actions=actions,
                    duration=event.duration,
                    executed_actions=executed_actions,
                    last_repeat_times=last_repeat_times,
                    input_id=event.entity_id,
                )

                # Update detector state
                if detector:
                    detector._state.executed_long_actions = new_executed
                    detector._state.last_repeat_times = last_repeat_times
        elif actions:
            # Non-long events - execute all actions normally
            await self._manager.execute_actions(actions=actions, input_id=event.entity_id)

    def _cancel_delayed_if_matching(
        self,
        input_instance: GpioEventButton | GpioInputBinarySensor | RemoteInputBase,
        entity_id: str,
        click_type: str,
    ) -> None:
        """Cancel pending delayed actions if this event matches delay_cancel_on.

        Scans ALL click types' actions (not just the current) to find
        any with ``delay_cancel_on`` containing the current ``click_type``.
        If a match is found and there are pending delayed tasks for this
        input, they are cancelled.

        Args:
            input_instance: The input that triggered the event
            entity_id: Input entity ID
            click_type: The event type that just occurred (e.g. 'pressed')
        """
        # Quick check: any pending tasks for this input?
        if entity_id not in self._manager._pending_delayed_actions:
            return

        # Check all click types for delay_cancel_on matching current event
        all_actions = input_instance._actions
        should_cancel = False
        for _ct, action_list in all_actions.items():
            for action_def in action_list:
                cancel_events = action_def.get("delay_cancel_on", [])
                if click_type in cancel_events:
                    should_cancel = True
                    break
            if should_cancel:
                break

        if should_cancel:
            self._manager.cancel_delayed_actions(entity_id)

    async def send_ha_autodiscovery(self) -> None:
        """Send Home Assistant autodiscovery for all inputs.

        This is typically handled during input configuration,
        but can be called manually if needed.
        """
        for pin, input_device in self._inputs.items():
            try:
                input_id = input_device.id if hasattr(input_device, "id") else pin
                input_name = input_device.name if hasattr(input_device, "name") else input_id
                input_area = getattr(input_device, "area", None)

                # Determine HA type from input class/mode
                if isinstance(input_device, GpioEventButton):
                    self._publish_input_ha_discovery(
                        ha_type=EVENT_ENTITY,
                        input_id=input_id,
                        name=input_name,
                        device_class=input_device.device_class,
                        area=input_area,
                        mqtt_sequences=input_device.mqtt_sequences,
                        enable_triple_click=getattr(
                            input_device._detector,
                            "_enable_triple_click",
                            False,
                        ),
                    )
                elif isinstance(input_device, RemoteInputBase):
                    ha_type = EVENT_ENTITY if input_device.mode == "event" else BINARY_SENSOR
                    self._publish_input_ha_discovery(
                        ha_type=ha_type,
                        input_id=input_id,
                        name=input_name,
                        device_class=input_device.device_class,
                        area=input_area,
                        mqtt_sequences=getattr(input_device, "mqtt_sequences", None),
                        enable_triple_click=getattr(
                            getattr(input_device, "_detector", None),
                            "_enable_triple_click",
                            False,
                        ),
                    )
                elif isinstance(input_device, GpioInputBinarySensor):
                    self._publish_input_ha_discovery(
                        ha_type=BINARY_SENSOR,
                        input_id=input_id,
                        name=input_name,
                        device_class=input_device.device_class,
                        area=input_area,
                    )
            except Exception as err:
                _LOGGER.error("Failed to send HA discovery for input %s: %s", pin, err)

    def register_remote_inputs(
        self,
        remote_device_manager: Any,
        remote_inputs_config: list[dict[str, Any]] | None = None,
    ) -> None:
        """Register remote inputs — delegates to :class:`RemoteInputRegistrar`.

        Args:
            remote_device_manager: Initialized :class:`RemoteDeviceManager`.
            remote_inputs_config: List of remote input dicts from
                ``config['remote_inputs']``.
        """
        self._remote_registrar.register_all(self._inputs, remote_device_manager, remote_inputs_config)

    # Keep backward-compatible alias
    register_esphome_binary_sensors = register_remote_inputs

    def unregister_remote_inputs(self) -> None:
        """Remove all remote (virtual) input instances.

        Used during remote device reload to clean up before re-registering.
        """
        self._remote_registrar.unregister_all(self._inputs)

    # Keep backward-compatible alias
    unregister_esphome_binary_sensors = unregister_remote_inputs

    # ------------------------------------------------------------------
    # HA Discovery helpers
    # ------------------------------------------------------------------

    def _publish_input_ha_discovery(
        self,
        *,
        ha_type: str,
        input_id: str,
        name: str,
        device_class: str | None = None,
        area: str | None = None,
        mqtt_sequences: dict | None = None,
        enable_triple_click: bool = False,
    ) -> None:
        """Build and publish HA autodiscovery payload for an input.

        Handles both ``EVENT_ENTITY`` and ``BINARY_SENSOR`` types.
        This is the single entry point for all HA discovery calls in
        :class:`InputManager`, avoiding code duplication.

        Args:
            ha_type: HA entity type constant (EVENT_ENTITY or BINARY_SENSOR).
            input_id: Unique input identifier.
            name: Human-readable name.
            device_class: Optional HA device class (e.g. "motion", "door").
            area: Optional area name.
            mqtt_sequences: Event-mode only — MQTT sequence definitions.
            enable_triple_click: Event-mode only — whether triple click is on.
        """
        if ha_type == EVENT_ENTITY:
            payload = ha_event_availabilty_message(
                id=input_id,
                name=name,
                config_helper=self._manager._config_helper,
                device_class=device_class,
                area=area,
                mqtt_sequences=mqtt_sequences,
                enable_triple_click=enable_triple_click,
            )
        else:
            payload = ha_binary_sensor_availabilty_message(
                id=input_id,
                name=name,
                config_helper=self._manager._config_helper,
                device_class=device_class,
                area=area,
            )
        self._manager.publish_ha_discovery(
            id=input_id,
            ha_type=ha_type,
            payload=payload,
        )
