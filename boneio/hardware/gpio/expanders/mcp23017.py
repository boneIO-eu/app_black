"""MCP23017 I2C GPIO expander driver using smbus2.

MCP23017 is a 16-bit I/O expander with I2C interface.
This implementation is output-only for relay control.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from boneio.hardware.i2c.bus import SMBus2I2C

_LOGGER = logging.getLogger(__name__)

# MCP23017 Registers
IODIRA = 0x00  # I/O direction register for port A (1=input, 0=output)
IODIRB = 0x01  # I/O direction register for port B
GPIOA = 0x12   # GPIO register for port A
GPIOB = 0x13   # GPIO register for port B
OLATA = 0x14   # Output latch register for port A
OLATB = 0x15   # Output latch register for port B

# Minimum delay between I2C operations in seconds
# This prevents bus contention when switching multiple outputs rapidly
I2C_OPERATION_DELAY = 0.002  # 2ms


class MCP23017:
    """MCP23017 16-bit I2C GPIO expander driver.
    
    Output-only implementation for relay control.
    Pins 0-7 are on Port A, pins 8-15 are on Port B.
    
    Args:
        i2c: I2C bus instance
        address: I2C address of the MCP23017 (default 0x20)
    
    Example:
        from boneio.hardware.i2c import SMBus2I2C
        from boneio.hardware.gpio.expanders import MCP23017
        
        i2c = SMBus2I2C(bus_number=2)
        mcp = MCP23017(i2c=i2c, address=0x20)
        pin0 = mcp.get_pin(0)
        pin0.switch_to_output(value=True)
    """

    def __init__(self, i2c: SMBus2I2C, address: int = 0x20, reset: bool = False):
        """Initialize MCP23017.
        
        Args:
            i2c: I2C bus instance (SMBus2I2C)
            address: I2C address of the device (default 0x20)
            reset: Reset flag (unused, for API compatibility with Adafruit library)
        """
        self._i2c = i2c
        self._address = address
        
        # Lock for thread-safe pin operations
        # This prevents race conditions when multiple outputs are switched simultaneously
        self._lock = threading.Lock()
        
        # Track output states (16 pins, 2 bytes)
        self._port_a_state = 0x00  # Pins 0-7
        self._port_b_state = 0x00  # Pins 8-15
        
        # Timestamp of last I2C operation for rate limiting
        self._last_operation_time = 0.0
        
        # Lock the I2C bus for initialization
        if not self._i2c.try_lock():
            raise RuntimeError("Failed to lock I2C bus for MCP23017 initialization")
        
        try:
            # Initialize: Set all pins as outputs (IODIR=0x00)
            self._write_register(IODIRA, 0x00)
            self._write_register(IODIRB, 0x00)
            
            # Clear all outputs
            self._write_register(OLATA, 0x00)
            self._write_register(OLATB, 0x00)
            
            _LOGGER.info(f"Initialized MCP23017 at address 0x{address:02X}")
        finally:
            self._i2c.unlock()

    def _write_register(self, register: int, value: int) -> None:
        """Write byte to register.
        
        Args:
            register: Register address
            value: Byte value to write
        """
        with self._i2c:
            try:
                data = bytes([register, value])
                self._i2c.writeto(self._address, data)
            except Exception as e:
                _LOGGER.error(f"Failed to write MCP23017 register 0x{register:02X}: {e}")
                raise

    def _read_register(self, register: int) -> int:
        """Read byte from register.
        
        Args:
            register: Register address
            
        Returns:
            Byte value from register
        """
        with self._i2c:
            try:
                buffer_out = bytes([register])
                buffer_in = bytearray(1)
                self._i2c.writeto_then_readfrom(self._address, buffer_out, buffer_in)
                return buffer_in[0]
            except Exception as e:
                _LOGGER.error(f"Failed to read MCP23017 register 0x{register:02X}: {e}")
                raise

    def _configure_pin_as_output(self, pin_number: int) -> None:
        """Configure a pin as output.
        
        Args:
            pin_number: Pin number (0-15)
        """
        if pin_number < 8:
            # Port A (pins 0-7)
            iodir = self._read_register(IODIRA)
            iodir &= ~(1 << pin_number)  # Clear bit = output
            self._write_register(IODIRA, iodir)
        else:
            # Port B (pins 8-15)
            pin_bit = pin_number - 8
            iodir = self._read_register(IODIRB)
            iodir &= ~(1 << pin_bit)  # Clear bit = output
            self._write_register(IODIRB, iodir)

    def _write_pin(self, pin_number: int, value: bool) -> None:
        """Write value to a pin.
        
        Thread-safe operation with rate limiting to prevent I2C bus contention.
        
        Args:
            pin_number: Pin number (0-15)
            value: Output state (True=HIGH, False=LOW)
        """
        with self._lock:
            # Rate limiting: ensure minimum delay between I2C operations
            now = time.monotonic()
            elapsed = now - self._last_operation_time
            if elapsed < I2C_OPERATION_DELAY:
                time.sleep(I2C_OPERATION_DELAY - elapsed)
            
            if pin_number < 8:
                # Port A (pins 0-7)
                if value:
                    self._port_a_state |= (1 << pin_number)  # Set bit
                else:
                    self._port_a_state &= ~(1 << pin_number)  # Clear bit
                self._write_register(OLATA, self._port_a_state)
            else:
                # Port B (pins 8-15)
                pin_bit = pin_number - 8
                if value:
                    self._port_b_state |= (1 << pin_bit)  # Set bit
                else:
                    self._port_b_state &= ~(1 << pin_bit)  # Clear bit
                self._write_register(OLATB, self._port_b_state)
            
            self._last_operation_time = time.monotonic()

    def configure_pin_as_output(self, pin_number: int, value: bool = False) -> None:
        """Configure a pin as output and set initial value.
        
        Args:
            pin_number: Pin number (0-15)
            value: Initial output state (True=HIGH, False=LOW)
        """
        if not 0 <= pin_number <= 15:
            raise ValueError(f"Pin number must be 0-15, got {pin_number}")
        
        self._configure_pin_as_output(pin_number)
        self._write_pin(pin_number, value)
        _LOGGER.debug(f"MCP23017 pin {pin_number} configured as output, initial value: {value}")

    def set_pin_value(self, pin_number: int, value: bool) -> None:
        """Set pin output value.
        
        Args:
            pin_number: Pin number (0-15)
            value: Output state (True=HIGH, False=LOW)
        """
        if not 0 <= pin_number <= 15:
            raise ValueError(f"Pin number must be 0-15, got {pin_number}")
        
        self._write_pin(pin_number, value)

    def get_pin_value(self, pin_number: int) -> bool:
        """Get current pin value.
        
        Args:
            pin_number: Pin number (0-15)
            
        Returns:
            Current pin state
        """
        if not 0 <= pin_number <= 15:
            raise ValueError(f"Pin number must be 0-15, got {pin_number}")
        
        if pin_number < 8:
            return bool(self._port_a_state & (1 << pin_number))
        else:
            pin_bit = pin_number - 8
            return bool(self._port_b_state & (1 << pin_bit))

    def __del__(self):
        """Cleanup on deletion."""
        # No cleanup needed - I2C bus is managed by the main bus manager
        pass
