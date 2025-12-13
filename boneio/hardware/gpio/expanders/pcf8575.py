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
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from boneio.hardware.i2c.bus import SMBus2I2C

_LOGGER = logging.getLogger(__name__)

# Minimum delay between I2C operations in seconds
# This prevents bus contention when switching multiple outputs rapidly
I2C_OPERATION_DELAY = 0.002  # 2ms


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
        >>> pcf.configure_pin_as_output(0, value=True)
        >>> pcf.set_pin_value(0, False)
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
        
        # Lock for thread-safe pin operations
        # This prevents race conditions when multiple outputs are switched simultaneously
        self._lock = threading.Lock()
        
        # State tracking for all 16 pins (2 bytes)
        # Bit = 1: HIGH (output) or input with pull-up
        # Bit = 0: LOW (output)
        self._state = 0xFFFF  # All pins HIGH (default state)
        
        # Timestamp of last I2C operation for rate limiting
        self._last_operation_time = 0.0
        
        # Initialize device - write default state
        self._write_state()
        
        _LOGGER.debug(
            "Initialized PCF8575 at address 0x%02X with state 0x%04X",
            address,
            self._state,
        )

    def configure_pin_as_output(self, pin_number: int, value: bool = False) -> None:
        """Configure a pin as output and set initial value.
        
        Args:
            pin_number: Pin number (0-15)
            value: Initial output state (True=HIGH, False=LOW)
        """
        if not 0 <= pin_number <= 15:
            raise ValueError(f"Pin number must be 0-15, got {pin_number}")
        
        self._set_pin_output(pin_number, value)
        _LOGGER.debug(
            "PCF8575 pin %d configured as output, initial value: %s",
            pin_number,
            value,
        )

    def configure_pin_as_input(self, pin_number: int) -> None:
        """Configure a pin as input (enables pull-up).
        
        Args:
            pin_number: Pin number (0-15)
        """
        if not 0 <= pin_number <= 15:
            raise ValueError(f"Pin number must be 0-15, got {pin_number}")
        
        self._set_pin_input(pin_number)
        _LOGGER.debug("PCF8575 pin %d configured as input", pin_number)

    def set_pin_value(self, pin_number: int, value: bool) -> None:
        """Set pin output value.
        
        Args:
            pin_number: Pin number (0-15)
            value: Output state (True=HIGH, False=LOW)
        """
        if not 0 <= pin_number <= 15:
            raise ValueError(f"Pin number must be 0-15, got {pin_number}")
        
        self._set_pin_output(pin_number, value)

    def get_pin_value(self, pin_number: int) -> bool:
        """Get current pin value.
        
        Args:
            pin_number: Pin number (0-15)
            
        Returns:
            Current pin state (True=HIGH, False=LOW)
        """
        if not 0 <= pin_number <= 15:
            raise ValueError(f"Pin number must be 0-15, got {pin_number}")
        
        return self._read_pin(pin_number)

    def _write_state(self) -> None:
        """Write current state to the device (2 bytes)."""
        try:
            # Split 16-bit state into two bytes (P0, P1)
            byte0 = self._state & 0xFF  # Port 0 (pins 0-7)
            byte1 = (self._state >> 8) & 0xFF  # Port 1 (pins 8-15)
            
            # Write 2 bytes to device using SMBus2I2C API
            # PCF8575 expects raw 2-byte write (no register address)
            if self._i2c.try_lock():
                try:
                    self._i2c.writeto(self._address, bytes([byte0, byte1]))
                finally:
                    self._i2c.unlock()
            else:
                raise RuntimeError("Could not acquire I2C bus lock")
            
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
            # Read 2 bytes from device using SMBus2I2C API
            buffer = bytearray(2)
            if self._i2c.try_lock():
                try:
                    self._i2c.readfrom_into(self._address, buffer)
                finally:
                    self._i2c.unlock()
            else:
                raise RuntimeError("Could not acquire I2C bus lock")
            
            # Combine into 16-bit value
            state = buffer[0] | (buffer[1] << 8)
            
            _LOGGER.debug(
                "PCF8575 0x%02X: Read state 0x%04X (P0=0x%02X, P1=0x%02X)",
                self._address,
                state,
                buffer[0],
                buffer[1],
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
        
        Thread-safe operation with rate limiting to prevent I2C bus contention.
        
        Args:
            pin: Pin number (0-15)
            value: Output value (True=HIGH, False=LOW)
        """
        with self._lock:
            # Rate limiting: ensure minimum delay between I2C operations
            now = time.monotonic()
            elapsed = now - self._last_operation_time
            if elapsed < I2C_OPERATION_DELAY:
                time.sleep(I2C_OPERATION_DELAY - elapsed)
            
            if value:
                # Set bit to 1 (HIGH)
                self._state |= (1 << pin)
            else:
                # Clear bit to 0 (LOW)
                self._state &= ~(1 << pin)
            
            self._write_state()
            self._last_operation_time = time.monotonic()

    def _set_pin_input(self, pin: int) -> None:
        """Set a pin to input mode (enables pull-up).
        
        Thread-safe operation with rate limiting.
        
        Args:
            pin: Pin number (0-15)
        """
        with self._lock:
            # Rate limiting: ensure minimum delay between I2C operations
            now = time.monotonic()
            elapsed = now - self._last_operation_time
            if elapsed < I2C_OPERATION_DELAY:
                time.sleep(I2C_OPERATION_DELAY - elapsed)
            
            # Set bit to 1 to enable pull-up for input
            self._state |= (1 << pin)
            self._write_state()
            self._last_operation_time = time.monotonic()

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
