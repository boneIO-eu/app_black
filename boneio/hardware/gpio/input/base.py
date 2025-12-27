"""Base class for GPIO inputs using libgpiod.

This module provides the base class for all GPIO input types.
It handles low-level GPIO operations and event processing.
"""

from __future__ import annotations

import asyncio
import logging
import time

from boneio.const import PRESSED, RELEASED, ClickTypes
from boneio.core.events import EventBus
from boneio.core.utils import TimePeriod
from boneio.hardware.gpio.input.manager import get_gpio_manager
from boneio.models import InputState
from boneio.models.events import InputEvent

_LOGGER = logging.getLogger(__name__)


class GpioBaseClass:
    """Base class for GPIO inputs.
    
    This class provides common functionality for all GPIO input types:
    - Pin configuration and reading
    - Bounce time handling
    - Event publishing to EventBus
    - Action management
    
    Subclasses should implement specific input behavior (binary sensor, event button, etc.)
    
    Args:
        pin: GPIO pin name (e.g., "P8_30")
        name: Human-readable name
        actions: Dictionary of actions for different click types
        input_type: Type of input (e.g., "event", "binary_sensor")
        event_bus: EventBus instance for publishing events
        boneio_input: Optional BoneIO input identifier
        **kwargs: Additional options (bounce_time, etc.)
        
    Example:
        >>> class MyInput(GpioBaseClass):
        ...     def __init__(self, **kwargs):
        ...         super().__init__(input_type="custom", **kwargs)
    """

    def __init__(
        self,
        pin: str,
        name: str,
        actions: dict,
        input_type: str,
        event_bus: EventBus,
        id: str | None = None,
        boneio_input: str = "",
        **kwargs,
    ) -> None:
        """Initialize GPIO input base class."""
        self._pin = pin
        bounce_time: TimePeriod = kwargs.get(
            "bounce_time", TimePeriod(milliseconds=50)
        )
        self._bounce_time = bounce_time.total_in_seconds
        self._loop = asyncio.get_running_loop()
        self._name = name
        self._actions = actions
        self._input_type = input_type
        self._boneio_input = boneio_input
        self._id = id or boneio_input or pin
        self._click_type = (PRESSED, RELEASED)
        self._state = False  # Will be updated by subclass
        self._last_state = "Unknown"
        self._last_timestamp = 0.0
        self._event_bus = event_bus
        self._event_lock = asyncio.Lock()
        self.area: str | None = None  # HA area/room assignment

    @property
    def boneio_input(self) -> str:
        """Get BoneIO input identifier.
        
        Returns:
            BoneIO input identifier string
        """
        return self._boneio_input or ""

    def press_callback(
        self, click_type: ClickTypes, duration: float | None = None, start_time: float | None = None
    ) -> None:
        """Handle press callback - schedule async processing.
        
        This method is called from GpioManager when a GPIO event occurs.
        It schedules async processing to avoid blocking the GPIO event loop.
        
        Args:
            click_type: Type of click (pressed, released, single, double, long)
            duration: Duration of the press in seconds (for long press)
            start_time: Start time of the press (for duration calculation)
        """
        asyncio.create_task(self._handle_press_with_lock(click_type, duration, start_time))
        
    async def _handle_press_with_lock(
        self, 
        click_type: ClickTypes, 
        duration: float | None = None, 
        start_time: float | None = None
    ):
        """Handle press event with a lock to ensure sequential execution.
        
        This method publishes the event to EventBus for any listeners
        (Manager, MQTT, etc.) to process.
        
        Args:
            click_type: Type of click
            duration: Duration of the press
            start_time: Start time of the press
        """
        async with self._event_lock:
            self._last_timestamp = time.time()
            self._last_state = click_type
            
            _LOGGER.debug(
                "Input event: %s on %s (%s), entity_id=%s, duration=%s",
                click_type.upper(),
                self._name,
                self._pin,
                self.id,
                duration,
            )
            
            # Create event state
            event = InputState(
                name=self.name,
                pin=self._pin,
                state=self.last_state,
                type=self.input_type,
                timestamp=self.last_press_timestamp,
                boneio_input=self.boneio_input,
                area=self.area,
            )
            
            self._event_bus.trigger_event(InputEvent(
                entity_id=self.id,
                click_type=click_type,
                duration=duration,
                state=event,
            ))

    def set_actions(self, actions: dict) -> None:
        """Set actions for this input.
        
        Args:
            actions: Dictionary mapping click types to action lists
        """
        self._actions = actions

    def get_actions_of_click(self, click_type: ClickTypes) -> list:
        """Get actions for a specific click type.
        
        Args:
            click_type: Type of click
            
        Returns:
            List of actions for the click type
        """
        return self._actions.get(click_type, [])

    @property
    def name(self) -> str:
        """Get input name.
        
        Returns:
            Human-readable name
        """
        return self._name

    @property
    def pin(self) -> str:
        """Get configured pin.
        
        Returns:
            Pin name (e.g., "P8_30")
        """
        return self._pin

    @property
    def id(self) -> str:
        """Get input ID.
        
        Returns user-defined ID, boneio_input, or pin as fallback.
        
        Returns:
            Input identifier (e.g., "IN_01" or user-defined ID)
        """
        return self._id

    @property
    def last_state(self) -> str:
        """Get last state.
        
        Returns:
            Last click type or "Unknown"
        """
        return self._last_state

    @property
    def input_type(self) -> str:
        """Get input type.
        
        Returns:
            Input type string (e.g., "event", "binary_sensor")
        """
        return self._input_type

    @property
    def last_press_timestamp(self) -> float:
        """Get timestamp of last press.
        
        Returns:
            Unix timestamp
        """
        return self._last_timestamp
