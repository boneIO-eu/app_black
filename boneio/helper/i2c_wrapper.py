"""I2C wrapper for Python 3.13+ on BeagleBone Black.

This module provides a compatibility layer between smbus2 and Adafruit CircuitPython I2C API.
Required because Adafruit Blinka depends on Adafruit_BBIO which doesn't support Python 3.13.
"""

from __future__ import annotations

import logging
from typing import Optional

from smbus2 import SMBus

_LOGGER = logging.getLogger(__name__)


class SMBus2I2CWrapper:
    """Wrapper around smbus2 to provide Adafruit CircuitPython I2C-like API.
    
    This class mimics the busio.I2C interface used by Adafruit CircuitPython libraries,
    allowing them to work with smbus2 on Python 3.13+.
    
    Args:
        bus_number: I2C bus number (typically 2 for BeagleBone Black)
    
    Example:
        i2c = SMBus2I2CWrapper(bus_number=2)
        # Now can be used with Adafruit libraries that expect busio.I2C
    """

    def __init__(self, bus_number: int = 2):
        """Initialize I2C bus wrapper.  
        
        Args:
            bus_number: I2C bus number (default 2 for BBB I2C-2)
        """
        self._bus_number = bus_number
        self._bus: Optional[SMBus] = None
        self._locked = False
        _LOGGER.info("Initialized I2C wrapper on bus %d (smbus2)", bus_number)

    def __enter__(self):
        """Context manager entry - acquire bus lock."""
        if not self._locked:
            self._bus = SMBus(self._bus_number)
            self._locked = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - release bus lock."""
        if self._locked and self._bus:
            self._bus.close()
            self._bus = None
            self._locked = False

    def try_lock(self) -> bool:
        """Try to acquire the I2C bus lock.
        
        Returns:
            True if lock was acquired, False otherwise
        """
        if not self._locked:
            self._bus = SMBus(self._bus_number)
            self._locked = True
            return True
        return False

    def unlock(self) -> None:
        """Release the I2C bus lock."""
        if self._locked and self._bus:
            self._bus.close()
            self._bus = None
            self._locked = False

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
        data = self._bus.read_i2c_block_data(address, 0, length)
        buffer[start:end] = data

    def writeto(self, address: int, buffer: bytes, *, start: int = 0, end: Optional[int] = None) -> None:
        """Write data to I2C device.
        
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
        
        data = list(buffer[start:end])
        if len(data) > 0:
            # First byte is typically the register, rest is data
            register = data[0]
            if len(data) > 1:
                self._bus.write_i2c_block_data(address, register, data[1:])
            else:
                self._bus.write_byte(address, register)

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
        """Write data to I2C device then read response.
        
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
        
        # Write phase
        out_data = list(buffer_out[out_start:out_end])
        register = out_data[0] if out_data else 0
        
        # Read phase
        in_length = in_end - in_start
        data = self._bus.read_i2c_block_data(address, register, in_length)
        buffer_in[in_start:in_end] = data

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

    def __del__(self):
        """Cleanup on deletion."""
        if self._locked and self._bus:
            try:
                self._bus.close()
            except Exception:
                pass
