from __future__ import annotations
import asyncio
import logging
from datetime import datetime
try:
    from Adafruit_BBIO import GPIO
except ModuleNotFoundError:

    class GPIO:
        PUD_OFF = "poff"
        PUD_UP = "poff"
        PUD_DOWN = "poff"

        def __init__(self):
            pass

    pass

import subprocess
from typing import Callable, Awaitable, List

from boneio.const import CONFIG_PIN, FALLING
from boneio.const import GPIO as GPIO_STR
from boneio.const import GPIO_MODE, LOW, ClickTypes, Gpio_Edges, Gpio_States, InputTypes
from boneio.helper.exceptions import GPIOInputException
from boneio.helper.timeperiod import TimePeriod
from concurrent.futures import ThreadPoolExecutor

_LOGGER = logging.getLogger(__name__)


def configure_pin(pin: str, mode: str = GPIO_STR) -> None:
    pin = f"{pin[0:3]}0{pin[3]}" if len(pin) == 4 else pin
    _LOGGER.debug(f"Configuring pin {pin} for mode {mode}.")
    subprocess.run(
        [CONFIG_PIN, pin, mode],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
        timeout=1,
    )


def setup_output(pin: str) -> None:
    """Set up a GPIO as output."""

    GPIO.setup(pin, GPIO.OUT, pull_up_down=GPIO.PUD_DOWN)


gpio_modes = {
    "gpio": GPIO.PUD_OFF,
    "gpio_pu": GPIO.PUD_UP,
    "gpio_pd": GPIO.PUD_DOWN,
    "gpio_input": GPIO.PUD_OFF,
}


def setup_input(pin: str, pull_mode: str = "gpio") -> None:
    """Set up a GPIO as input."""
    gpio_mode = gpio_modes.get(pull_mode, GPIO.PUD_OFF)
    try:
        GPIO.setup(pin, GPIO.IN, gpio_mode)
    except (ValueError, SystemError) as err:
        raise GPIOInputException(err)


def write_output(pin: str, value: str) -> None:
    """Write a value to a GPIO."""

    GPIO.output(pin, value)


def read_input(pin: str, on_state: Gpio_States = LOW) -> bool:
    """Read a value from a GPIO."""
    return GPIO.input(pin) is on_state


def edge_detect(
    pin: str, callback: Callable, bounce: int = 0, edge: Gpio_Edges = FALLING
) -> None:
    """Add detection for RISING and FALLING events."""
    try:
        GPIO.add_event_detect(gpio=pin, edge=edge, callback=callback, bouncetime=bounce)
    except RuntimeError as err:
        raise GPIOInputException(err)


def add_event_detect(pin: str, edge: Gpio_Edges = FALLING) -> None:
    """Add detection for RISING and FALLING events."""
    try:
        GPIO.add_event_detect(gpio=pin, edge=edge)
    except RuntimeError as err:
        raise GPIOInputException(err)


def add_event_callback(pin: str, callback: Callable) -> None:
    """Add detection for RISING and FALLING events."""
    try:
        GPIO.add_event_callback(gpio=pin, callback=callback)
    except RuntimeError as err:
        raise GPIOInputException(err)


class GpioBaseClass:
    """Base class for initialize GPIO"""

    def __init__(
        self,
        pin: str,
        press_callback: Callable[
            [ClickTypes, str, List, InputTypes, bool, float | None], Awaitable[None]
        ],
        name: str,
        actions: dict,
        input_type,
        empty_message_after: bool,
        **kwargs,
    ) -> None:
        """Setup GPIO Input Button"""
        self._pin = pin
        gpio_mode = kwargs.get(GPIO_MODE, GPIO_STR)
        bounce_time: TimePeriod = kwargs.get("bounce_time", TimePeriod(milliseconds=50))
        self._bounce_time = bounce_time.total_in_seconds
        self._loop = asyncio.get_running_loop()
        self._press_callback = press_callback
        self._name = name
        setup_input(pin=self._pin, pull_mode=gpio_mode)
        self.executor = ThreadPoolExecutor()
        self._actions = actions
        self._input_type = input_type
        self._empty_message_after = empty_message_after

    def press_callback(self, click_type: ClickTypes, duration: float | None = None) -> None:
        actions = self._actions.get(click_type, [])
        self._loop.create_task(self.async_press_callback(click_type, duration, actions))

    async def async_press_callback(
        self, click_type: ClickTypes, duration: float | None = None, actions: List = []
    ) -> None:
        _LOGGER.warn("press callback %s", datetime.now())
        await self._press_callback(
            click_type,
            self._pin,
            actions,
            self._input_type,
            self._empty_message_after,
            duration,
        )

    def set_actions(self, actions: dict) -> None:
        self._actions = actions

    @property
    def is_pressed(self) -> bool:
        """Is button pressed."""
        return read_input(self._pin)

    @property
    def name(self) -> str:
        """Name of the GPIO visible in HA/MQTT."""
        return self._name

    @property
    def pin(self) -> str:
        """Return configured pin."""
        return self._pin
