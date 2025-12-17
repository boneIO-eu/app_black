"""I2C wrapper for Python 3.13+ on BeagleBone Black.

This module provides a compatibility layer between smbus2 and Adafruit CircuitPython I2C API.
Required because Adafruit Blinka depends on Adafruit_BBIO which doesn't support Python 3.13.
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

from smbus2 import SMBus, i2c_msg

_LOGGER = logging.getLogger(__name__)


class SMBus2I2C:
    """Wrapper around smbus2 to provide Adafruit CircuitPython I2C-like API.
    
    This class mimics the busio.I2C interface used by Adafruit CircuitPython libraries,
    allowing them to work with smbus2 on Python 3.13+.
    
    It uses low-level i2c_msg and i2c_rdwr for correct transaction handling
    (Repeated Start, raw reads/writes).
    
    Args:
        bus_number: I2C bus number (typically 2 for BeagleBone Black)
    """

    def __init__(self, bus_number: int = 2):
        """Initialize I2C bus wrapper.  
        
        Args:
            bus_number: I2C bus number (default 2 for BBB I2C-2)
        """
        self._bus_number = bus_number
        self._bus: Optional[SMBus] = None
        self._lock = threading.RLock()  # Reentrant lock for thread safety
        self._open_bus()
        _LOGGER.info("Initialized I2C wrapper on bus %d (smbus2)", bus_number)

    def _open_bus(self) -> None:
        """Open I2C bus if not already open."""
        if self._bus is None:
            try:
                self._bus = SMBus(self._bus_number)
                _LOGGER.debug("Opened I2C bus %d", self._bus_number)
            except OSError as e:
                _LOGGER.error(f"Failed to open I2C bus {self._bus_number}: {e}")
                raise

    def __enter__(self):
        """Context manager entry - acquire bus lock."""
        self._lock.acquire()
        # Ensure bus is open
        if self._bus is None:
            self._open_bus()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - release bus lock (but keep bus open)."""
        self._lock.release()

    def try_lock(self) -> bool:
        """Try to acquire the I2C bus lock.
        
        Returns:
            True if lock was acquired, False otherwise
        """
        acquired = self._lock.acquire(blocking=False)
        if acquired:
            # Ensure bus is open
            if self._bus is None:
                try:
                    self._open_bus()
                except OSError:
                    self._lock.release()
                    return False
        return acquired

    def unlock(self) -> None:
        """Release the I2C bus lock (but keep bus open)."""
        try:
            self._lock.release()
        except RuntimeError:
            # Lock was not held
            pass

    def readfrom_into(self, address: int, buffer: bytearray, *, start: int = 0, end: Optional[int] = None) -> None:
        """Read from I2C device into a buffer.
        
        Args:
            address: I2C device address (7-bit)
            buffer: Buffer to read data into
            start: Starting index in buffer
            end: Ending index in buffer (None = end of buffer)
        """
        if not self._bus:
            raise RuntimeError("I2C bus not locked. Call try_lock() first.")
        
        if end is None:
            end = len(buffer)
        
        length = end - start
        if length <= 0:
            return
            
        try:
            # Use i2c_msg for raw read
            msg = i2c_msg.read(address, length)
            self._bus.i2c_rdwr(msg)
            # Copy data from message to buffer
            buffer[start:end] = bytes(msg)
        except OSError as e:
            _LOGGER.error(f"I2C read error on address 0x{address:02X}: {e}")
            raise

    def writeto(self, address: int, buffer: bytes, *, start: int = 0, end: Optional[int] = None) -> None:
        """Write data to I2C device.
        
        This method writes raw bytes to the device without treating the first byte
        as a register address. This is compatible with devices like PCF8575 that
        don't use register-based addressing.
        
        Args:
            address: I2C device address (7-bit)
            buffer: Data to write
            start: Starting index in buffer
            end: Ending index in buffer (None = end of buffer)
        """
        if not self._bus:
            raise RuntimeError("I2C bus not locked. Call try_lock() first.")
        
        if end is None:
            end = len(buffer)
        
        data = buffer[start:end]
        if len(data) == 0:
            return
            
        try:
            # Use i2c_msg for raw write
            # We need to construct the message with the data
            msg = i2c_msg.write(address, list(data))
            self._bus.i2c_rdwr(msg)
        except OSError as e:
            _LOGGER.error(f"I2C write error on address 0x{address:02X}: {e}")
            raise

    def writeto_then_readfrom(
        self,
        address: int,
        buffer_out: bytes,
        buffer_in: bytearray,
        *,
        out_start: int = 0,
        out_end: Optional[int] = None,
        in_start: int = 0,
        in_end: Optional[int] = None
    ) -> None:
        """Write data to I2C device then read response using Repeated Start.
        
        Args:
            address: I2C device address (7-bit)
            buffer_out: Data to write
            buffer_in: Buffer to read response into
            out_start: Starting index in output buffer
            out_end: Ending index in output buffer
            in_start: Starting index in input buffer
            in_end: Ending index in input buffer
        """
        if not self._bus:
            raise RuntimeError("I2C bus not locked. Call try_lock() first.")
        
        if out_end is None:
            out_end = len(buffer_out)
        if in_end is None:
            in_end = len(buffer_in)
            
        out_len = out_end - out_start
        in_len = in_end - in_start
        
        if out_len == 0 and in_len == 0:
            return
            
        if out_len == 0:
            self.readfrom_into(address, buffer_in, start=in_start, end=in_end)
            return
            
        if in_len == 0:
            self.writeto(address, buffer_out, start=out_start, end=out_end)
            return
        
        try:
            # Create two messages for i2c_rdwr
            # This ensures a Repeated Start condition between write and read
            msg_write = i2c_msg.write(address, list(buffer_out[out_start:out_end]))
            msg_read = i2c_msg.read(address, in_len)
            
            # Execute combined transaction
            self._bus.i2c_rdwr(msg_write, msg_read)
            
            # Copy result to input buffer
            buffer_in[in_start:in_end] = bytes(msg_read)
        except OSError as e:
            _LOGGER.error(f"I2C write-then-read error on address 0x{address:02X}: {e}")
            raise

    def scan(self) -> list[int]:
        """Scan I2C bus for devices.
        
        Returns:
            List of I2C addresses that responded
        """
        if not self._bus:
            # Temporarily open bus for scanning
            with SMBus(self._bus_number) as bus:
                devices = []
                for addr in range(0x03, 0x78):  # Valid I2C address range
                    try:
                        bus.read_byte(addr)
                        devices.append(addr)
                        _LOGGER.debug("Found I2C device at 0x%02X", addr)
                    except OSError:
                        pass
                return devices
        else:
            devices = []
            for addr in range(0x03, 0x78):
                try:
                    self._bus.read_byte(addr)
                    devices.append(addr)
                    _LOGGER.debug("Found I2C device at 0x%02X", addr)
                except OSError:
                    pass
            return devices

    # ========== Direct SMBus methods for low-level device access ==========
    # These methods provide direct access to SMBus operations for devices
    # like DS2482 that need byte-level control.

    def write_byte(self, address: int, value: int) -> None:
        """Write a single byte to I2C device (no register).
        
        Args:
            address: I2C device address (7-bit)
            value: Byte value to write
        """
        if not self._bus:
            raise RuntimeError("I2C bus not open")
        self._bus.write_byte(address, value)

    def read_byte(self, address: int) -> int:
        """Read a single byte from I2C device (no register).
        
        Args:
            address: I2C device address (7-bit)
            
        Returns:
            Byte value read from device
        """
        if not self._bus:
            raise RuntimeError("I2C bus not open")
        return self._bus.read_byte(address)

    def write_byte_data(self, address: int, register: int, value: int) -> None:
        """Write a byte to a specific register.
        
        Args:
            address: I2C device address (7-bit)
            register: Register address
            value: Byte value to write
        """
        if not self._bus:
            raise RuntimeError("I2C bus not open")
        self._bus.write_byte_data(address, register, value)

    def read_byte_data(self, address: int, register: int) -> int:
        """Read a byte from a specific register.
        
        Args:
            address: I2C device address (7-bit)
            register: Register address
            
        Returns:
            Byte value read from register
        """
        if not self._bus:
            raise RuntimeError("I2C bus not open")
        return self._bus.read_byte_data(address, register)

    def write_i2c_block_data(self, address: int, register: int, data: list[int]) -> None:
        """Write a block of bytes to a register.
        
        Args:
            address: I2C device address (7-bit)
            register: Register address
            data: List of bytes to write
        """
        if not self._bus:
            raise RuntimeError("I2C bus not open")
        self._bus.write_i2c_block_data(address, register, data)

    def read_i2c_block_data(self, address: int, register: int, length: int) -> list[int]:
        """Read a block of bytes from a register.
        
        Args:
            address: I2C device address (7-bit)
            register: Register address
            length: Number of bytes to read
            
        Returns:
            List of bytes read from device
        """
        if not self._bus:
            raise RuntimeError("I2C bus not open")
        return self._bus.read_i2c_block_data(address, register, length)

    @property
    def frequency(self) -> int:
        """Get I2C bus frequency.
        
        Note: smbus2 doesn't provide frequency control, returns default.
        
        Returns:
            Default I2C frequency (100000 Hz)
        """
        return 100000  # Default I2C frequency

    @frequency.setter
    def frequency(self, value: int) -> None:
        """Set I2C bus frequency.
        
        Note: smbus2 doesn't support changing frequency at runtime.
        This is a no-op for compatibility.
        
        Args:
            value: Desired frequency (ignored)
        """
        _LOGGER.debug("I2C frequency setting not supported with smbus2 (requested: %d Hz)", value)

    def close(self) -> None:
        """Close the I2C bus."""
        with self._lock:
            if self._bus:
                try:
                    self._bus.close()
                    self._bus = None
                    _LOGGER.debug("Closed I2C bus %d", self._bus_number)
                except Exception as e:
                    _LOGGER.warning(f"Error closing I2C bus: {e}")

    def __del__(self):
        """Cleanup on deletion."""
        self.close()
