"""GPIO Manager using libgpiod for BeagleBone GPIO control."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Dict, Tuple

import gpiod
from gpiod import LineSettings
from gpiod.line import Bias, Direction, Edge

from boneio.const import PINS

_LOGGER = logging.getLogger(__name__)


@dataclass
class GpioInputDefinition:
    """Definition of a GPIO input."""
    name: str
    pin: str
    chip: int
    line: int
    bias: Bias
    detector: object  # MultiClickDetector or BinarySensorDetector


class GpioManager:
    """Centralized GPIO manager using libgpiod."""

    def __init__(self, loop: asyncio.AbstractEventLoop, debounce_ms: int = 50):
        """Initialize GPIO manager.
        
        Args:
            loop: Asyncio event loop
            debounce_ms: Debounce time in milliseconds
        """
        self._loop = loop
        self._debounce_ms = debounce_ms
        self._inputs: list[GpioInputDefinition] = []
        self._requests: Dict[int, gpiod.LineRequest] = {}
        self._file_descriptors: list[int] = []
        self._aliases: Dict[Tuple[int, int], str] = {}
        self._detectors: Dict[Tuple[int, int], object] = {}
        self._running = False

    def add_input(
        self,
        name: str,
        pin: str,
        detector: object,  # MultiClickDetector or BinarySensorDetector
        gpio_mode: str = "gpio"
    ) -> None:
        """Add a GPIO input to monitor.
        
        Args:
            name: Name of the input
            pin: Pin name (e.g., "P8_30")
            detector: Detector instance (MultiClickDetector or BinarySensorDetector)
            gpio_mode: GPIO mode (gpio, gpio_pu, gpio_pd)
        """
        if self._running:
            raise RuntimeError("Cannot add inputs while manager is running")

        if pin not in PINS:
            _LOGGER.error("Pin %s not found in PINS mapping", pin)
            return

        pin_info = PINS[pin]
        chip = pin_info["chip"]
        line = pin_info["line"]

        # Map gpio_mode to gpiod.Bias
        bias_map = {
            "gpio": Bias.AS_IS,
            "gpio_pu": Bias.AS_IS,
            "gpio_pd": Bias.PULL_DOWN,
            "gpio_input": Bias.AS_IS,
        }
        bias = bias_map.get(gpio_mode, Bias.AS_IS)

        input_def = GpioInputDefinition(
            name=name,
            pin=pin,
            chip=chip,
            line=line,
            bias=bias,
            detector=detector,
        )
        self._inputs.append(input_def)
        
        # Store detector for later use
        key = (chip, line)
        self._detectors[key] = detector
        self._aliases[key] = f"{name} ({pin})"
        
        _LOGGER.debug(
            "Registered input %s on pin %s (chip%d, line%d) with mode %s",
            name, pin, chip, line, gpio_mode
        )

    async def start(self) -> None:
        """Start monitoring GPIO inputs."""
        if self._running:
            _LOGGER.warning("GPIO manager already running")
            return

        if not self._inputs:
            _LOGGER.warning("No GPIO inputs registered")
            return

        # Group inputs by chip
        grouped_inputs: Dict[int, list[GpioInputDefinition]] = defaultdict(list)
        for input_def in self._inputs:
            grouped_inputs[input_def.chip].append(input_def)

        # Create line requests for each chip
        for chip, chip_definitions in grouped_inputs.items():
            config: Dict[Tuple[int, ...], LineSettings] = {}
            alias_map: Dict[Tuple[int, int], str] = {}
            
            for definition in chip_definitions:
                settings_kwargs = {
                    "direction": Direction.INPUT,
                    "edge_detection": Edge.BOTH,
                    "bias": definition.bias,
                }
                if self._debounce_ms > 0:
                    settings_kwargs["debounce_period"] = timedelta(
                        milliseconds=self._debounce_ms
                    )

                config[(definition.line,)] = LineSettings(**settings_kwargs)
                alias = f"{definition.name} ({definition.pin})"
                key = (chip, definition.line)
                alias_map[key] = alias

            consumer = f"boneio-chip{chip}"
            request = gpiod.request_lines(
                f"/dev/gpiochip{chip}", consumer=consumer, config=config
            )
            self._requests[chip] = request

            summary = ", ".join(
                f"{alias} (line {line})" for (_, line), alias in alias_map.items()
            )
            _LOGGER.info("Monitoring /dev/gpiochip%s on: %s", chip, summary)

        # Register readers in asyncio loop
        for chip, request in self._requests.items():
            fd = request.fileno()
            self._file_descriptors.append(fd)
            self._loop.add_reader(fd, self._handle_gpiod_events, chip, request)

        self._running = True
        _LOGGER.info("GPIO manager started monitoring %d inputs", len(self._inputs))

    def _handle_gpiod_events(self, chip: int, request: gpiod.LineRequest) -> None:
        """Handle GPIO events from libgpiod.
        
        Args:
            chip: GPIO chip number
            request: Line request object
        """
        if not request.read_edge_events():
            return

        for event in request.read_edge_events():
            line = event.line_offset
            key = (chip, line)
            
            if key in self._detectors:
                detector = self._detectors[key]
                alias = self._aliases.get(key, f"chip{chip}/line{line}")
                
                _LOGGER.debug(
                    "GPIO event: %s edge on %s",
                    "rising" if event.event_type == event.Type.RISING_EDGE else "falling",
                    alias,
                )
                
                # Call the detector's handle_event method
                try:
                    detector.handle_event(event)
                except Exception as exc:
                    _LOGGER.error(
                        "Error in GPIO detector for %s: %s",
                        alias,
                        exc,
                        exc_info=True,
                    )

    def read_value(self, pin: str) -> bool:
        """Read current value of a GPIO pin.
        
        Args:
            pin: Pin name (e.g., "P8_30")
            
        Returns:
            True if pin is high, False if low
        """
        if pin not in PINS:
            _LOGGER.error("Pin %s not found in PINS mapping", pin)
            return False

        pin_info = PINS[pin]
        chip = pin_info["chip"]
        line = pin_info["line"]

        if chip not in self._requests:
            _LOGGER.error("Chip %d not initialized", chip)
            return False

        request = self._requests[chip]
        values = request.get_values([line])
        return bool(values[line])

    async def stop(self) -> None:
        """Stop monitoring GPIO inputs and cleanup resources."""
        if not self._running:
            return

        _LOGGER.info("Stopping GPIO manager...")

        # Remove readers from event loop
        for fd in self._file_descriptors:
            self._loop.remove_reader(fd)

        # Release line requests
        for request in self._requests.values():
            request.release()

        self._file_descriptors.clear()
        self._requests.clear()
        self._running = False
        
        _LOGGER.info("GPIO manager stopped")


# Global GPIO manager instance
_gpio_manager: GpioManager | None = None


def get_gpio_manager(
    loop: asyncio.AbstractEventLoop | None = None,
    debounce_ms: int = 50
) -> GpioManager:
    """Get or create the global GPIO manager instance.
    
    Args:
        loop: Asyncio event loop (required on first call)
        debounce_ms: Debounce time in milliseconds
        
    Returns:
        Global GPIO manager instance
    """
    global _gpio_manager
    
    if _gpio_manager is None:
        if loop is None:
            raise ValueError("Event loop required to create GPIO manager")
        _gpio_manager = GpioManager(loop, debounce_ms)
    
    return _gpio_manager


def add_event_detect(pin: str, edge: str) -> None:
    """Compatibility function - not needed with new manager.
    
    This is a no-op placeholder for backward compatibility.
    Actual event detection is handled by GpioManager.
    """
    pass


def add_event_callback(pin: str, callback: Callable) -> None:
    """Compatibility function - not needed with new manager.
    
    This is a no-op placeholder for backward compatibility.
    Actual callbacks are registered via GpioManager.add_input().
    """
    pass
