"""PCF8575 I2C GPIO expander driver using smbus2.

This module provides a native implementation of the PCF8575 16-bit I/O expander
using smbus2, replacing the Adafruit CircuitPython library.

The PCF8575 is a 16-bit quasi-bidirectional I/O expander with:
- 16 I/O pins (P00-P07, P10-P17)
- I2C interface
- 2-byte read/write protocol
- Quasi-bidirectional I/O (pins can be used as inputs or outputs)
- Internal pull-up resistors

Protocol:
- Write: Send 2 bytes (P0 port, P1 port)
- Read: Read 2 bytes (P0 port, P1 port)
- Output: Write 0 to pin (LOW), write 1 to pin (HIGH)
- Input: Write 1 to pin (enables pull-up), then read

For BoneIO, we use PCF8575 primarily for output (relay control).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from boneio.hardware.i2c.bus import SMBus2I2C

_LOGGER = logging.getLogger(__name__)


class PCF8575DigitalInOut:
    """Digital I/O pin for PCF8575.
    
    This class provides an API compatible with Adafruit's DigitalInOut
    for controlling individual pins on the PCF8575.
    """

    def __init__(self, pin_number: int, pcf: PCF8575) -> None:
        """Initialize a digital I/O pin.
        
        Args:
            pin_number: Pin number (0-15)
            pcf: Parent PCF8575 instance
        """
        self._pin = pin_number
        self._pcf = pcf
        self._output = False
        self._value = False

    def switch_to_output(self, value: bool = False) -> None:
        """Switch pin to output mode.
        
        Args:
            value: Initial output value (True=HIGH, False=LOW)
        """
        self._output = True
        self._value = value
        self._pcf._set_pin_output(self._pin, value)

    def switch_to_input(self) -> None:
        """Switch pin to input mode (enables pull-up)."""
        self._output = False
        self._pcf._set_pin_input(self._pin)

    @property
    def value(self) -> bool:
        """Get or set the pin value.
        
        Returns:
            Current pin value (True=HIGH, False=LOW)
        """
        if self._output:
            return self._value
        return self._pcf._read_pin(self._pin)

    @value.setter
    def value(self, val: bool) -> None:
        """Set the pin value (only works in output mode).
        
        Args:
            val: Value to set (True=HIGH, False=LOW)
        """
        if not self._output:
            raise RuntimeError("Pin must be configured as output")
        self._value = val
        self._pcf._set_pin_output(self._pin, val)


class PCF8575:
    """PCF8575 16-bit I2C GPIO expander.
    
    This implementation uses smbus2 for direct I2C communication,
    replacing the Adafruit CircuitPython library.
    
    The PCF8575 has 16 I/O pins organized as two 8-bit ports:
    - Port 0: Pins 0-7 (P00-P07)
    - Port 1: Pins 8-15 (P10-P17)
    
    Example:
        >>> from boneio.hardware.i2c.bus import SMBus2I2C
        >>> from boneio.hardware.gpio.expanders import PCF8575
        >>> 
        >>> i2c = SMBus2I2C(bus_num=2)
        >>> pcf = PCF8575(i2c=i2c, address=0x20, reset=False)
        >>> pin = pcf.get_pin(0)
        >>> pin.switch_to_output(value=True)
        >>> pin.value = False
    """

    def __init__(self, i2c: SMBus2I2C, address: int, reset: bool = False) -> None:
        """Initialize PCF8575.
        
        Args:
            i2c: I2C bus instance (SMBus2I2C)
            address: I2C address of the device (typically 0x20-0x27)
            reset: Reset flag (unused, for API compatibility with Adafruit)
        """
        self._i2c = i2c
        self._address = address
        
        # State tracking for all 16 pins (2 bytes)
        # Bit = 1: HIGH (output) or input with pull-up
        # Bit = 0: LOW (output)
        self._state = 0xFFFF  # All pins HIGH (default state)
        
        # Initialize device - write default state
        self._write_state()
        
        _LOGGER.debug(
            "Initialized PCF8575 at address 0x%02X with state 0x%04X",
            address,
            self._state,
        )

    def get_pin(self, pin: int) -> PCF8575DigitalInOut:
        """Get a digital I/O pin object.
        
        Args:
            pin: Pin number (0-15)
            
        Returns:
            PCF8575DigitalInOut object for the specified pin
            
        Raises:
            ValueError: If pin number is out of range
        """
        if not 0 <= pin <= 15:
            raise ValueError(f"Pin must be 0-15, got {pin}")
        return PCF8575DigitalInOut(pin, self)

    def _write_state(self) -> None:
        """Write current state to the device (2 bytes)."""
        try:
            # Split 16-bit state into two bytes (P0, P1)
            byte0 = self._state & 0xFF  # Port 0 (pins 0-7)
            byte1 = (self._state >> 8) & 0xFF  # Port 1 (pins 8-15)
            
            # Write 2 bytes to device
            self._i2c.write_i2c_block_data(self._address, byte0, [byte1])
            
            _LOGGER.debug(
                "PCF8575 0x%02X: Wrote state 0x%04X (P0=0x%02X, P1=0x%02X)",
                self._address,
                self._state,
                byte0,
                byte1,
            )
        except Exception as e:
            _LOGGER.error(
                "Failed to write to PCF8575 at 0x%02X: %s",
                self._address,
                e,
            )
            raise

    def _read_state(self) -> int:
        """Read current state from the device (2 bytes).
        
        Returns:
            16-bit state value
        """
        try:
            # Read 2 bytes from device
            data = self._i2c.read_i2c_block_data(self._address, 0, 2)
            
            # Combine into 16-bit value
            state = data[0] | (data[1] << 8)
            
            _LOGGER.debug(
                "PCF8575 0x%02X: Read state 0x%04X (P0=0x%02X, P1=0x%02X)",
                self._address,
                state,
                data[0],
                data[1],
            )
            
            return state
        except Exception as e:
            _LOGGER.error(
                "Failed to read from PCF8575 at 0x%02X: %s",
                self._address,
                e,
            )
            raise

    def _set_pin_output(self, pin: int, value: bool) -> None:
        """Set a pin to output mode with specified value.
        
        Args:
            pin: Pin number (0-15)
            value: Output value (True=HIGH, False=LOW)
        """
        if value:
            # Set bit to 1 (HIGH)
            self._state |= (1 << pin)
        else:
            # Clear bit to 0 (LOW)
            self._state &= ~(1 << pin)
        
        self._write_state()

    def _set_pin_input(self, pin: int) -> None:
        """Set a pin to input mode (enables pull-up).
        
        Args:
            pin: Pin number (0-15)
        """
        # Set bit to 1 to enable pull-up for input
        self._state |= (1 << pin)
        self._write_state()

    def _read_pin(self, pin: int) -> bool:
        """Read the current value of a pin.
        
        Args:
            pin: Pin number (0-15)
            
        Returns:
            Pin value (True=HIGH, False=LOW)
        """
        state = self._read_state()
        return bool(state & (1 << pin))

    @property
    def gpio(self) -> int:
        """Get current GPIO state (all 16 pins).
        
        Returns:
            16-bit state value
        """
        return self._state

    @gpio.setter
    def gpio(self, value: int) -> None:
        """Set GPIO state (all 16 pins at once).
        
        Args:
            value: 16-bit state value
        """
        self._state = value & 0xFFFF
        self._write_state()
