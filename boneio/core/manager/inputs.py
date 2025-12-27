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
from typing import TYPE_CHECKING, Callable

from boneio.components.input import GpioEventButton, GpioInputBinarySensor
from boneio.const import (
    ACTIONS,
    BINARY_SENSOR,
    DEVICE_CLASS,
    EVENT_ENTITY,
    ID,
    INPUT,
    INPUT_SENSOR,
    PIN,
    PRESSED,
    RELEASED,
    SHOW_HA,
)
from boneio.exceptions import GPIOInputException
from boneio.integration.homeassistant import (
    ha_binary_sensor_availabilty_message,
    ha_event_availabilty_message,
)
from boneio.models.events import InputEvent

if TYPE_CHECKING:
    from boneio.core.manager import Manager
    from boneio.hardware.gpio.input import GpioBaseClass

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
        self._inputs: dict[str, GpioBaseClass] = {}
        self._event_pins = event_pins
        self._binary_pins = binary_pins
        
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
            len(binary_pins)
        )

    def _configure_inputs(self, reload_config: bool = False) -> None:
        """Configure inputs (events and binary sensors).
        
        Args:
            reload_config: If True, reload configuration from file and update existing inputs
        """
        def get_input_id_from_gpio(gpio: dict, pin: str) -> str:
            """Get input ID from gpio config (same logic as in _configure_event_sensor)."""
            if ID in gpio:
                return str(gpio.get(ID))
            elif "boneio_input" in gpio:
                return str(gpio.get("boneio_input", pin))
            return pin
        
        def check_if_input_configured(input_id: str) -> bool:
            """Check if input is already configured (only blocks new configs, not reloads)."""
            if input_id in self._inputs:
                if not reload_config:
                    _LOGGER.warning(
                        "Input %s is already configured. Omitting it.", input_id
                    )
                    return True
                # During reload, we want to update existing inputs - don't block
                return False
            return False

        def configure_single_input(configure_sensor_func: Callable, gpio: dict) -> None:
            """Configure a single input (event or binary sensor)."""
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
            # Get config from ConfigHelper (uses cache, reloads if needed)
            config = self._manager._config_helper.reload_config()
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
                    gpio=gpio
                )
            except GPIOInputException as err:
                _LOGGER.error("Failed to configure event input: %s", err)

        # Configure binary sensors
        for gpio in self._binary_pins:
            try:
                configure_single_input(
                    configure_sensor_func=self._configure_binary_sensor,
                    gpio=gpio
                )
            except GPIOInputException as err:
                _LOGGER.error("Failed to configure binary sensor: %s", err)

    def _configure_event_sensor(
        self,
        gpio: dict,
        pin: str,
        existing_input: GpioEventButton | None = None,
        actions: dict = {},
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
            if ID in gpio:
                input_id: str = str(gpio.pop(ID))
            elif "boneio_input" in gpio:
                input_id = str(gpio.get("boneio_input", pin))
            else:
                input_id = pin
            
            # Get area for HA assignment
            area = gpio.pop("area", None)
            
            # Reload: update existing input's actions and name
            if existing_input:
                
                # Check if HA-relevant fields changed (name, area)
                old_name = existing_input._name if hasattr(existing_input, '_name') else None
                old_area = getattr(existing_input, 'area', None)
                ha_fields_changed = (old_name != name) or (old_area != area)
                
                # Update actions (always - this is internal to the controller)
                existing_input.set_actions(actions=actions)
                
                # Update name if changed
                if hasattr(existing_input, '_name'):
                    existing_input._name = name
                
                # Store area on input
                existing_input.area = area
                
                # Update timing parameters if this is an event button
                existing_input.update_timings(
                    double_click_duration=gpio.get('double_click_duration'),
                    long_press_duration=gpio.get('long_press_duration'),
                    sequence_window_duration=gpio.get('sequence_window_duration'),
                )
                
                # Re-send HA discovery only if HA-relevant fields changed (name, area)
                # Actions are internal to the controller and don't need HA update
                if ha_fields_changed and gpio.get(SHOW_HA, True):
                    _LOGGER.debug(f"HA-relevant fields changed for {input_id}, re-sending discovery")
                    self._manager.send_ha_autodiscovery(
                        id=input_id,
                        name=name,
                        ha_type=EVENT_ENTITY,
                        device_class=gpio.get(DEVICE_CLASS, None),
                        availability_msg_func=ha_event_availabilty_message,
                        area=area,
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
                self._manager.send_ha_autodiscovery(
                    id=input_id,
                    name=name,
                    ha_type=EVENT_ENTITY,
                    device_class=gpio.get(DEVICE_CLASS, None),
                    availability_msg_func=ha_event_availabilty_message,
                    area=area,
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
        actions: dict = {},
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
            if ID in gpio:
                input_id: str = str(gpio.pop(ID))
            else:
                input_id = str(gpio.get("boneio_input", pin))
            
            # Get area for HA assignment
            area = gpio.pop("area", None)

            # Reload: update existing input's actions and name
            if existing_input:
                if not isinstance(existing_input, GpioInputBinarySensor):
                    _LOGGER.warning(
                        "Cannot reconfigure input type for %s. Restart required.", pin
                    )
                    return existing_input
                
                # Check if HA-relevant fields changed (name, area)
                old_name = existing_input._name if hasattr(existing_input, '_name') else None
                old_area = getattr(existing_input, 'area', None)
                ha_fields_changed = (old_name != name) or (old_area != area)
                
                # Update actions (always - this is internal to the controller)
                existing_input.set_actions(actions=actions)
                
                # Update name if changed
                if hasattr(existing_input, '_name'):
                    existing_input._name = name
                
                # Store area on input
                existing_input.area = area
                
                # Re-send HA discovery only if HA-relevant fields changed (name, area)
                # Actions are internal to the controller and don't need HA update
                if ha_fields_changed and gpio.get(SHOW_HA, True):
                    _LOGGER.debug(f"HA-relevant fields changed for {input_id}, re-sending discovery")
                    self._manager.send_ha_autodiscovery(
                        id=input_id,
                        name=name,
                        ha_type=BINARY_SENSOR,
                        device_class=gpio.get(DEVICE_CLASS, None),
                        availability_msg_func=ha_binary_sensor_availabilty_message,
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
                self._manager.send_ha_autodiscovery(
                    id=input_id,
                    name=name,
                    ha_type=BINARY_SENSOR,
                    device_class=gpio.get(DEVICE_CLASS, None),
                    availability_msg_func=ha_binary_sensor_availabilty_message,
                    area=area,
                )
            
            return input_device
            
        except GPIOInputException as err:
            _LOGGER.error("Failed to configure binary sensor on pin %s: %s", pin, err)
            return None

    def get_input(self, pin: str) -> GpioBaseClass | None:
        """Get input by pin.
        
        Args:
            pin: Pin identifier
            
        Returns:
            Input instance or None if not found
        """
        return self._inputs.get(pin)

    def get_all_inputs(self) -> dict[str, GpioBaseClass]:
        """Get all inputs.
        
        Returns:
            Dictionary of all inputs
        """
        return self._inputs

    def get_inputs_list(self) -> list[GpioBaseClass]:
        """Get list of all inputs.
        
        Returns:
            List of all input instances
        """
        return list(self._inputs.values())

    async def reload_inputs(self) -> None:
        """Reload input configuration from file.
        
        This handles:
        - Updating existing inputs (actions, area, name)
        - Removing deleted inputs (from internal state and HA Discovery)
        - Adding inputs that use already-registered GPIO pins (e.g., moving from event to binary_sensor)
        """
        _LOGGER.info("Reloading input configuration")
        
        # Get new config
        config = self._manager._config_helper.reload_config()
        
        # Build map of new inputs from config (input_id -> {pin, area})
        new_input_map: dict[str, dict] = {}
        for gpio in config.get(EVENT_ENTITY, []) + config.get(BINARY_SENSOR, []):
            pin = gpio.get("pin")
            # Determine input ID (same logic as in _configure_event_sensor/_configure_binary_sensor)
            if "id" in gpio:
                input_id = gpio["id"]
            elif "boneio_input" in gpio:
                input_id = gpio["boneio_input"]
            elif pin:
                input_id = pin
            else:
                continue
            new_input_map[input_id] = {"pin": pin, "area": gpio.get("area")}
        
        # Find inputs to remove (in current config but not in new config)
        current_input_ids = set(self._inputs.keys())
        new_input_ids = set(new_input_map.keys())
        
        inputs_to_remove = current_input_ids - new_input_ids
        
        _LOGGER.info(f"Input reload: current={current_input_ids}, new={new_input_ids}, to_remove={inputs_to_remove}")
        
        # Remove deleted inputs from internal state (GPIO pin stays registered - minimal overhead)
        ha_discovery_changed = False
        
        for input_id in inputs_to_remove:
            input_device = self._inputs.get(input_id)
            if input_device:
                old_area = getattr(input_device, 'area', None)
                
                # Remove HA Discovery
                self._remove_input_ha_discovery(input_id, old_area)
                ha_discovery_changed = True
                
                # Remove from internal state (GPIO detector will be replaced by new input class)
                del self._inputs[input_id]
                _LOGGER.info(f"Removed input {input_id}")
        
        # Check for area changes on remaining inputs
        for input_id, input_device in self._inputs.items():
            old_area = getattr(input_device, 'area', None)
            new_area = new_input_map.get(input_id, {}).get("area")
            
            if old_area != new_area:
                ha_discovery_changed = True
                _LOGGER.info(
                    f"Input {input_id} area changed: {old_area} -> {new_area}, "
                    "removing old HA Discovery"
                )
                self._remove_input_ha_discovery(input_id, old_area)
        
        # Wait for HA to process the removal before sending new discovery
        if ha_discovery_changed:
            _LOGGER.debug("Waiting 1s for HA to process discovery removal...")
            await asyncio.sleep(1)
        
        # _configure_inputs with reload_config=True will:
        # - Update existing inputs (actions, area, name)
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
        from boneio.models.events import InputEvent
        
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
                    area=input_.area
                )
                event = InputEvent(
                    entity_id=input_.id,
                    state=input_state,
                    click_type=None,
                    duration=None
                )
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
        _LOGGER.info(f"Looking for autodiscovery topics for input_id={input_id}, old_device_identifier={old_device_identifier}")
        matching_topics = self._manager._config_helper.get_autodiscovery_topics_for_id(
            input_id, old_device_identifier
        )
        _LOGGER.info(f"Found {len(matching_topics)} matching topics: {matching_topics}")
        
        for ha_type, topic in matching_topics:
            _LOGGER.info(f"Removing HA Discovery for input {input_id} (old area: {old_area}): {topic}")
            # Send empty/null payload to remove from HA (HA requires zero-length retained message)
            self._manager.send_message(topic=topic, payload=None, retain=True)
            # Remove from internal cache
            self._manager._config_helper.remove_autodiscovery_msg(ha_type, topic)

    def _publish_input_event_to_mqtt(
        self, input_instance: GpioBaseClass, event: InputEvent
    ) -> None:
        """Publish input event to MQTT for Home Assistant.
        
        For event buttons (input_type=INPUT): sends JSON with event_type
        For binary sensors (input_type=INPUT_SENSOR): sends pressed/released state
        
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
            event_payload: dict[str, str | float | None] = {"event_type": click_type}
            if event.duration is not None:
                event_payload["duration"] = round(event.duration, 3)
            
            self._manager.send_message(
                topic=topic,
                payload=json.dumps(event_payload),
            )
            _LOGGER.debug(
                "Published event to MQTT: topic=%s, payload=%s",
                topic, event_payload
            )
            
        elif input_type == INPUT_SENSOR:
            payload = str(click_type)  # "pressed" or "released"
            
            self._manager.send_message(
                topic=topic,
                payload=payload,
            )
            _LOGGER.debug(
                "Published binary sensor state to MQTT: topic=%s, payload=%s",
                topic, payload
            )

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
            _LOGGER.warning("Entity ID or click type not found in event data")
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
            len(actions)
        )
        
        # Send event to MQTT for Home Assistant
        self._publish_input_event_to_mqtt(input_instance, event)
        
        # Execute actions for this input event (skip if publish_only)
        if actions and not event.publish_only:
            await self._manager.execute_actions(actions=actions)

    async def send_ha_autodiscovery(self) -> None:
        """Send Home Assistant autodiscovery for all inputs.
        
        This is typically handled during input configuration,
        but can be called manually if needed.
        """
        for pin, input_device in self._inputs.items():
            try:
                # Use input_device.id (which is boneio_input or explicit id) instead of pin
                input_id = input_device.id if hasattr(input_device, 'id') else pin
                input_name = input_device.name if hasattr(input_device, 'name') else input_id
                input_area = getattr(input_device, 'area', None)
                
                # Determine input type and send appropriate autodiscovery
                if isinstance(input_device, GpioEventButton):
                    self._manager.send_ha_autodiscovery(
                        id=input_id,
                        name=input_name,
                        ha_type=EVENT_ENTITY,
                        device_class=getattr(input_device, '_device_class', None),
                        availability_msg_func=ha_event_availabilty_message,
                        area=input_area,
                    )
                elif isinstance(input_device, GpioInputBinarySensor):
                    self._manager.send_ha_autodiscovery(
                        id=input_id,
                        name=input_name,
                        ha_type=BINARY_SENSOR,
                        device_class=getattr(input_device, '_device_class', None),
                        availability_msg_func=ha_binary_sensor_availabilty_message,
                        area=input_area,
                    )
            except Exception as err:
                _LOGGER.error(
                    "Failed to send HA discovery for input %s: %s",
                    pin,
                    err
                )
