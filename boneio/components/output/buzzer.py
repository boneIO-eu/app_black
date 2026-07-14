"""Buzzer Output module."""

from __future__ import annotations

import logging
import os
from typing import override

from boneio.components.output.basic import BasicOutput
from boneio.const import OFF, ON, SWITCH

_LOGGER = logging.getLogger(__name__)


class BuzzerOutput(BasicOutput):
    """Represents a buzzer output controlled via sysfs LED interface."""

    def __init__(
        self,
        sysfs_path: str = "/sys/class/leds/boneio:buzzer/brightness",
        output_type: str = SWITCH,
        restored_state: bool = False,
        **kwargs,
    ) -> None:
        """Initialize Buzzer output.

        Args:
            sysfs_path: Path to the brightness file in sysfs.
            output_type: Home Assistant type (default is switch).
            restored_state: Whether to restore state.
            **kwargs: Extra arguments.
        """
        self._sysfs_path = sysfs_path
        super().__init__(**kwargs, output_type=output_type, restored_state=restored_state)

        # Initialize the output state in sysfs
        self.init_state(restored_state)
        _LOGGER.debug("Setup Buzzer output with sysfs path %s", self._sysfs_path)

    def init_state(self, restored_state: bool) -> None:
        """Initialize the state in sysfs."""
        try:
            # Create directory if it doesn't exist (useful for test environments)
            os.makedirs(os.path.dirname(self._sysfs_path), exist_ok=True)
            self._write_brightness(1 if restored_state else 0)
        except Exception as e:
            _LOGGER.warning("Could not initialize buzzer sysfs state: %s", e)

    def _write_brightness(self, value: int) -> None:
        """Write brightness value to sysfs."""
        try:
            with open(self._sysfs_path, "w") as f:
                f.write(str(value))
        except Exception as e:
            _LOGGER.error("Failed to write to buzzer sysfs at %s: %s", self._sysfs_path, e)

    @property
    @override
    def is_active(self) -> bool:
        """Check if the buzzer is active by reading the sysfs file."""
        try:
            if not os.path.exists(self._sysfs_path):
                return self._state == ON
            with open(self._sysfs_path, "r") as f:
                val = f.read().strip()
                return val != "0"
        except Exception as e:
            _LOGGER.warning("Failed to read buzzer state from sysfs: %s", e)
            return self._state == ON

    @override
    def turn_on(self, timestamp=None) -> None:
        """Turn on the buzzer."""
        self._write_brightness(1)
        self._state = ON
        if not timestamp:
            self._execute_momentary_turn(momentary_type=ON)

    @override
    def turn_off(self, timestamp=None) -> None:
        """Turn off the buzzer."""
        self._write_brightness(0)
        self._state = OFF
        if not timestamp:
            self._execute_momentary_turn(momentary_type=OFF)
