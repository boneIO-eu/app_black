"""GPIO helper module using libgpiod for BeagleBone GPIO control."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

from boneio.const import (
    PRESSED,
    RELEASED,
    ClickTypes,
)
from boneio.core.events import EventBus
from boneio.core.utils import TimePeriod
from boneio.input.gpio_manager import get_gpio_manager
from boneio.models import InputState

_LOGGER = logging.getLogger(__name__)


def add_event_detect(pin: str, edge: str) -> None:
    """Compatibility function - event detection handled by GpioManager."""
    pass


def add_event_callback(pin: str, callback: Callable) -> None:
    """Compatibility function - callbacks registered via GpioManager."""
    pass


def read_input(pin: str) -> bool:
    """Read current value of a GPIO pin.
    
    Args:
        pin: Pin name (e.g., "P8_30")
        
    Returns:
        True if pin is high, False if low
    """
    try:
        gpio_manager = get_gpio_manager()
        return gpio_manager.read_value(pin)
    except Exception as exc:
        _LOGGER.error("Error reading pin %s: %s", pin, exc)
        return False



class GpioBaseClass:
    """Base class for initialize GPIO"""

    def __init__(
        self,
        pin: str,
        name: str,
        actions: dict,
        input_type: str,
        event_bus: EventBus,
        boneio_input: str = "",
        **kwargs,
    ) -> None:
        """Setup GPIO Input Button.
        
        Args:
            pin: GPIO pin name (e.g., "P8_30")
            name: Human-readable name
            actions: Dictionary of actions for different click types
            input_type: Type of input (e.g., "event", "binary_sensor")
            event_bus: EventBus instance for publishing events
            boneio_input: Optional BoneIO input identifier
            **kwargs: Additional options (bounce_time, etc.)
        """
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
        self._click_type = (PRESSED, RELEASED)
        self._state = False  # Will be updated by subclass
        self._last_state = "Unknown"
        self._last_timestamp = 0.0
        self._event_bus = event_bus
        self._event_lock = asyncio.Lock()

    @property
    def boneio_input(self) -> str:
        return self._boneio_input or ""

    def press_callback(
        self, click_type: ClickTypes, duration: float | None = None, start_time: float | None = None
    ) -> None:
        """Handle press callback - schedule async processing.
        
        Note: This is called from GpioManager which runs in the event loop,
        so we can safely create a task without run_coroutine_threadsafe.
        """
        asyncio.create_task(self._handle_press_with_lock(click_type, duration, start_time))
        
        
    async def _handle_press_with_lock(self, click_type: ClickTypes, duration: float | None = None, start_time: float | None = None):
        """Handle press event with a lock to ensure sequential execution.
        
        Publishes event to EventBus for any listeners (Manager, MQTT, etc.)
        """
        async with self._event_lock:
            self._last_timestamp = time.time()
            self._last_state = click_type
            
            _LOGGER.debug(
                "Input event: %s on %s (%s), duration=%s",
                click_type,
                self._name,
                self._pin,
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
            )
            
            # Publish to EventBus - Manager will subscribe to this
            self._event_bus.trigger_event({
                "event_type": "input",
                "entity_id": self.id,
                "click_type": click_type,
                "duration": duration,
                "actions": self._actions.get(click_type, []),
                "event_state": event,
                "input_instance": self,
            })


    def set_actions(self, actions: dict) -> None:
        self._actions = actions

    def get_actions_of_click(self, click_type: ClickTypes) -> dict:
        return self._actions.get(click_type, [])

    @property
    def name(self) -> str:
        """Name of the GPIO visible in HA/MQTT."""
        return self._name

    @property
    def pin(self) -> str:
        """Return configured pin."""
        return self._pin

    @property
    def id(self) -> str:
        return self._pin

    @property
    def last_state(self) -> str:
        return self._last_state

    @property
    def input_type(self) -> str:
        return self._input_type

    @property
    def last_press_timestamp(self) -> float:
        return self._last_timestamp
