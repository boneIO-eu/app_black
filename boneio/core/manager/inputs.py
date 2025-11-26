"""Input manager - handles all input devices.

This module manages all input devices including:
- Event buttons (single, double, long press)
- Binary sensors (on/off states)
- Input actions and callbacks
"""

from __future__ import annotations

import asyncio
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
            reload_config: If True, reload configuration from file
        """
        def check_if_pin_configured(pin: str) -> bool:
            """Check if pin is already configured."""
            if pin in self._inputs:
                if not reload_config:
                    _LOGGER.warning(
                        "PIN %s is already configured. Omitting it.", pin
                    )
                    return True
            return False

        def configure_single_input(configure_sensor_func: Callable, gpio: dict) -> None:
            """Configure a single input (event or binary sensor)."""
            try:
                pin = gpio.pop(PIN)
            except (AttributeError, KeyError) as err:
                _LOGGER.error("PIN is required for input configuration: %s", err)
                return
            
            if check_if_pin_configured(pin):
                return
            
            input_device = configure_sensor_func(
                gpio=gpio,
                pin=pin,
                existing_input=self._inputs.get(pin, None),  # For reload actions
                actions=self._manager.parse_actions(pin, gpio.pop(ACTIONS, {})),
            )
            
            if input_device:
                self._inputs[input_device.pin] = input_device

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
            # Determine display name
            if "name" in gpio:
                name = gpio.pop("name")
            elif ID in gpio:
                name = gpio.get(ID)
            elif "boneio_input" in gpio:
                name = gpio.get("boneio_input")
            else:
                name = pin

            # ID strategy: explicit 'id' > 'boneio_input' > 'pin'
            if ID in gpio:
                input_id = gpio.pop(ID)
            elif "boneio_input" in gpio:
                input_id = gpio.get("boneio_input")
            else:
                input_id = pin
            
            # Reload: update existing input's actions
            if existing_input:
                if not isinstance(existing_input, GpioEventButton):
                    _LOGGER.warning(
                        "Cannot reconfigure input type for %s. Restart required.", pin
                    )
                    return existing_input
                existing_input.set_actions(actions=actions)
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
            
            # Register with Home Assistant
            if gpio.get(SHOW_HA, True):
                self._manager.send_ha_autodiscovery(
                    id=pin,
                    name=name,
                    ha_type=EVENT_ENTITY,
                    device_class=gpio.get(DEVICE_CLASS, None),
                    availability_msg_func=ha_event_availabilty_message,
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
            # Determine display name
            if "name" in gpio:
                name = gpio.pop("name")
            elif ID in gpio:
                name = gpio.get(ID)
            elif "boneio_input" in gpio:
                name = gpio.get("boneio_input")
            else:
                name = pin

            # ID strategy: explicit 'id' > 'boneio_input' > 'pin'
            if ID in gpio:
                input_id = gpio.pop(ID)
            elif "boneio_input" in gpio:
                input_id = gpio.get("boneio_input")
            else:
                input_id = pin

            # Reload: update existing input's actions
            if existing_input:
                if not isinstance(existing_input, GpioInputBinarySensor):
                    _LOGGER.warning(
                        "Cannot reconfigure input type for %s. Restart required.", pin
                    )
                    return existing_input
                existing_input.set_actions(actions=actions)
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
            
            # Register with Home Assistant
            if gpio.get(SHOW_HA, True):
                self._manager.send_ha_autodiscovery(
                    id=pin,
                    name=name,
                    ha_type=BINARY_SENSOR,
                    device_class=gpio.get(DEVICE_CLASS, None),
                    availability_msg_func=ha_binary_sensor_availabilty_message,
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

    def reload_inputs(self) -> None:
        """Reload input configuration from file.
        
        This clears existing inputs and reconfigures them from the config file.
        """
        _LOGGER.info("Reloading input configuration")
        self._inputs.clear()
        self._configure_inputs(reload_config=True)

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
        
        # Execute actions for this input event
        if actions:
            await self._manager.execute_actions(actions=actions)

    def get_tasks(self) -> dict[str, asyncio.Task]:
        """Get all input-related tasks.
        
        Returns:
            Dictionary of tasks
        """
        # Inputs don't have background tasks currently
        # GPIO manager handles the event loop
        return {}

    async def send_ha_autodiscovery(self) -> None:
        """Send Home Assistant autodiscovery for all inputs.
        
        This is typically handled during input configuration,
        but can be called manually if needed.
        """
        for pin, input_device in self._inputs.items():
            if hasattr(input_device, 'send_ha_discovery'):
                try:
                    await input_device.send_ha_discovery()
                except Exception as err:
                    _LOGGER.error(
                        "Failed to send HA discovery for input %s: %s",
                        pin,
                        err
                    )
