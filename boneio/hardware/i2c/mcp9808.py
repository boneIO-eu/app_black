"""MCP9808 temperature sensor implementation using SMBus2I2C."""

import logging

_LOGGER = logging.getLogger(__name__)

# MCP9808 registers
REG_CONFIG = 0x01
REG_TEMP = 0x05
REG_MANUF_ID = 0x06  # Should be 0x0054
REG_DEVICE_ID = 0x07  # Should be 0x0400

# Config register bits
CONFIG_SHUTDOWN = 0x0100
CONFIG_CRITLOCKED = 0x0080
CONFIG_WINLOCKED = 0x0040
CONFIG_INTCLR = 0x0020
CONFIG_ALERTSTAT = 0x0010
CONFIG_ALERTCTRL = 0x0008
CONFIG_ALERTSEL = 0x0004
CONFIG_ALERTPOL = 0x0002
CONFIG_ALERTMODE = 0x0001

class MCP9808:
    """MCP9808 temperature sensor driver using SMBus2I2C."""
    
    def __init__(self, i2c_bus, address: int = 0x18):
        """Initialize the MCP9808 temperature sensor.
        
        Args:
            i2c_bus: The I2C bus object (SMBus2I2C)
            address: The I2C device address (default 0x18)
        """
        self._i2c = i2c_bus
        self._address = address
        
        # Lock the I2C bus for initialization
        if not self._i2c.try_lock():
            raise RuntimeError("Failed to lock I2C bus for MCP9808 initialization")
        
        try:
            # Verify device
            manuf_id = self._read_register(REG_MANUF_ID)
            device_id = self._read_register(REG_DEVICE_ID)
            if manuf_id != 0x0054 or (device_id & 0xFF00) != 0x0400:
                raise RuntimeError(f"Failed to find MCP9808! Manufacturer ID: {manuf_id:04x}, Device ID: {device_id:04x}")
            
            _LOGGER.debug("Initialized MCP9808 at address 0x%02X", address)
        except Exception as e:
            raise RuntimeError(f"Failed to communicate with MCP9808: {e}")
        finally:
            self._i2c.unlock()
    
    def _read_register(self, register: int) -> int:
        """Read a 16-bit register from the device.
        
        Args:
            register: The register address
            
        Returns:
            The 16-bit register value
        """
        with self._i2c:
            try:
                # Read 16-bit value using write-then-read pattern
                buffer_out = bytes([register])
                buffer_in = bytearray(2)
                self._i2c.writeto_then_readfrom(self._address, buffer_out, buffer_in)
                # MCP9808 uses big-endian format
                return (buffer_in[0] << 8) | buffer_in[1]
            except Exception as e:
                _LOGGER.error(f"Failed to read MCP9808 register 0x{register:02X}: {e}")
                raise
    
    def _write_register(self, register: int, value: int) -> None:
        """Write to a 16-bit register on the device.
        
        Args:
            register: The register address
            value: The 16-bit value to write
        """
        with self._i2c:
            try:
                # Write 16-bit value (big-endian format)
                data = bytes([register, (value >> 8) & 0xFF, value & 0xFF])
                self._i2c.writeto(self._address, data)
            except Exception as e:
                _LOGGER.error(f"Failed to write MCP9808 register 0x{register:02X}: {e}")
                raise
    
    @property
    def temperature(self):
        """Read the temperature value in degrees Celsius."""
        # Read temperature register
        raw = self._read_register(REG_TEMP)
        
        # Extract temperature value
        # Upper 4 bits [15:12] are flags/sign
        # Bits [11:4] are the 8-bit temperature value
        # Bits [3:2] are the fractional component (0.25°C resolution)
        # Bits [1:0] are reserved
        
        # Check if negative (sign bit set)
        if raw & 0x1000:
            # Clear flag bits and sign bit
            raw &= 0x0FFF
            # Two's complement for negative value
            raw = -((~raw & 0x0FFF) + 1)
        else:
            # Clear flag bits
            raw &= 0x0FFF
        
        # Convert to temperature (0.0625°C resolution)
        return raw * 0.0625
    
    def shutdown(self):
        """Put the device in low-power shutdown mode."""
        config = self._read_register(REG_CONFIG)
        self._write_register(REG_CONFIG, config | CONFIG_SHUTDOWN)
    
    def wake(self):
        """Wake the device from shutdown mode."""
        config = self._read_register(REG_CONFIG)
        self._write_register(REG_CONFIG, config & ~CONFIG_SHUTDOWN)
