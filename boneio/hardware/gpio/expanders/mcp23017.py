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
        
        Raises:
            ValueError: If address is not in valid range (0x20-0x27)
            RuntimeError: If I2C bus cannot be locked
        """
        # Validate I2C address (MCP23017 supports 0x20-0x27 via A0-A2 pins)
        if not 0x20 <= address <= 0x27:
            raise ValueError(f"MCP23017 address must be 0x20-0x27, got 0x{address:02X}")
        
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
            # Disable Sequential Operation (SEQOP) - logic assumes Byte mode
            # IOCON register is at 0x0A and 0x0B (shared in BANK=0)
            # Write to both registers for robustness in case of dirty startup
            self._write_register_unlocked(0x0A, 0x20)  # SEQOP=1 (disabled), BANK=0
            self._write_register_unlocked(0x0B, 0x20)  # Mirror register
            
            # Read current output latch states from hardware to preserve relay states
            # This prevents momentary OFF state during application restart
            self._port_a_state = self._read_register_unlocked(OLATA)
            self._port_b_state = self._read_register_unlocked(OLATB)
            _LOGGER.debug(
                f"MCP23017@0x{address:02X} preserved states: "
                f"A=0b{self._port_a_state:08b}, B=0b{self._port_b_state:08b}"
            )
            
            # Initialize: Set all pins as outputs (IODIR=0x00)
            # This does NOT change the output latch values
            self._write_register_unlocked(IODIRA, 0x00)
            self._write_register_unlocked(IODIRB, 0x00)
            
            _LOGGER.info(f"Initialized MCP23017 at address 0x{address:02X}")
        finally:
            self._i2c.unlock()

    def _write_register_unlocked(self, register: int, value: int) -> None:
        """Write byte to register (caller must hold I2C lock).
        
        Args:
            register: Register address
            value: Byte value to write
        """
        try:
            self._i2c.write_byte_data(self._address, register, value)
        except Exception as e:
            _LOGGER.error(f"Failed to write MCP23017@0x{self._address:02X} register 0x{register:02X}: {e}")
            raise

    def _read_register_unlocked(self, register: int) -> int:
        """Read byte from register (caller must hold I2C lock).
        
        Args:
            register: Register address
            
        Returns:
            Byte value from register
        """
        try:
            return self._i2c.read_byte_data(self._address, register)
        except Exception as e:
            _LOGGER.error(f"Failed to read MCP23017@0x{self._address:02X} register 0x{register:02X}: {e}")
            raise

    def _write_register(self, register: int, value: int) -> None:
        """Write byte to register using direct SMBus call.
        
        Args:
            register: Register address
            value: Byte value to write
        """
        with self._i2c:
            self._write_register_unlocked(register, value)

    def _read_register(self, register: int) -> int:
        """Read byte from register using direct SMBus call with retry.
        
        Args:
            register: Register address
            
        Returns:
            Byte value from register
        """
        retries = 3
        last_error = None
        
        for i in range(retries):
            try:
                with self._i2c:
                    return self._i2c.read_byte_data(self._address, register)
            except Exception as e:
                last_error = e
                # Small delay before retry (outside of I2C lock!)
                time.sleep(0.001 * (i + 1))
        
        _LOGGER.error(f"Failed to read MCP23017@0x{self._address:02X} register 0x{register:02X} after {retries} attempts: {last_error}")
        raise last_error or RuntimeError(f"Failed to read register 0x{register:02X}")

    def _configure_pin_as_output(self, pin_number: int) -> None:
        """Configure a pin as output.
        
        Thread-safe and atomic I2C operation.
        
        Args:
            pin_number: Pin number (0-15)
        """
        with self._lock:
            # ATOMIC Read-Modify-Write for IODIR register
            with self._i2c:
                if pin_number < 8:
                    # Port A (pins 0-7)
                    iodir = self._read_register_unlocked(IODIRA)
                    iodir &= ~(1 << pin_number)  # Clear bit = output
                    self._write_register_unlocked(IODIRA, iodir)
                else:
                    # Port B (pins 8-15)
                    pin_bit = pin_number - 8
                    iodir = self._read_register_unlocked(IODIRB)
                    iodir &= ~(1 << pin_bit)  # Clear bit = output
                    self._write_register_unlocked(IODIRB, iodir)

    def _write_pin(self, pin_number: int, value: bool) -> None:
        """Write value to a pin using ATOMIC hardware Read-Modify-Write.
        
        This implementation performs read and write in a SINGLE I2C transaction block,
        ensuring no other thread can interfere between read and write operations.
        
        Args:
            pin_number: Pin number (0-15)
            value: Output state (True=HIGH, False=LOW)
        """
        with self._lock:
            # Rate limiting: ensure minimum delay between I2C operations
            # Do this BEFORE acquiring I2C lock to avoid blocking other devices
            now = time.monotonic()
            elapsed = now - self._last_operation_time
            if elapsed < I2C_OPERATION_DELAY:
                time.sleep(I2C_OPERATION_DELAY - elapsed)
            
            # Determine register and bit position
            if pin_number < 8:
                reg = OLATA
                bit = pin_number
            else:
                reg = OLATB
                bit = pin_number - 8
            
            try:
                # ATOMIC Read-Modify-Write: Single I2C lock for entire operation
                with self._i2c:
                    # Read current state from hardware
                    current_state = self._read_register_unlocked(reg)
                    
                    # Calculate new state
                    if value:
                        new_state = current_state | (1 << bit)
                    else:
                        new_state = current_state & ~(1 << bit)
                    
                    # Only write if state changed
                    if new_state != current_state:
                        _LOGGER.debug(
                            f"MCP23017@0x{self._address:02X} pin {pin_number} -> {value}: "
                            f"{'OLATA' if pin_number < 8 else 'OLATB'} "
                            f"0b{current_state:08b} -> 0b{new_state:08b}"
                        )
                        self._write_register_unlocked(reg, new_state)
                        
                        # Update cache after successful write
                        if pin_number < 8:
                            self._port_a_state = new_state
                        else:
                            self._port_b_state = new_state
                        
            except Exception as e:
                _LOGGER.error(f"Error writing MCP23017@0x{self._address:02X} pin {pin_number}: {e}")
                raise  # Re-raise to signal error to caller
            
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
        
        with self._lock:
            if pin_number < 8:
                return bool(self._port_a_state & (1 << pin_number))
            else:
                pin_bit = pin_number - 8
                return bool(self._port_b_state & (1 << pin_bit))

    def verify_port_state(self) -> tuple[int, int]:
        """Read actual port states from hardware and compare with cached state.
        
        Returns:
            Tuple of (actual_port_a, actual_port_b) read from hardware
        """
        with self._lock:
            actual_a = self._read_register(OLATA)
            actual_b = self._read_register(OLATB)
            
            if actual_a != self._port_a_state or actual_b != self._port_b_state:
                _LOGGER.warning(
                    f"MCP23017@0x{self._address:02X} state mismatch! "
                    f"Cached: A=0b{self._port_a_state:08b}, B=0b{self._port_b_state:08b} | "
                    f"Actual: A=0b{actual_a:08b}, B=0b{actual_b:08b}"
                )
            return (actual_a, actual_b)

    def __del__(self):
        """Cleanup on deletion."""
        # No cleanup needed - I2C bus is managed by the main bus manager
        pass
