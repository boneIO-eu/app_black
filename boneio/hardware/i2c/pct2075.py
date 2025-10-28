"""PCT2075 temperature sensor implementation using SMBus2I2C."""

import logging

_LOGGER = logging.getLogger(__name__)

# PCT2075 registers
TEMP_REG = 0x00  # Temperature register (read-only)
CONF_REG = 0x01  # Configuration register
THYST_REG = 0x02  # Hysteresis register
TOS_REG = 0x03   # Over-temp shutdown threshold register
TIDLE_REG = 0x04  # Temperature conversion idle time register

class PCT2075:
    """PCT2075 and compatible LM75 temperature sensor driver using SMBus2I2C."""
    
    def __init__(self, i2c_bus, address: int = 0x48):
        """Initialize the PCT2075 temperature sensor.
        
        Args:
            i2c_bus: The I2C bus object (SMBus2I2C)
            address: The I2C device address (default 0x48)
        """
        self._i2c = i2c_bus
        self._address = address
        
        # Lock the I2C bus for initialization
        if not self._i2c.try_lock():
            raise RuntimeError("Failed to lock I2C bus for PCT2075 initialization")
        
        try:
            # Set to normal operation mode
            self._write_register(CONF_REG, 0x00)
            _LOGGER.debug("Initialized PCT2075 at address 0x%02X", address)
        finally:
            self._i2c.unlock()
    
    def _read_register(self, register: int, size: int = 2) -> int:
        """Read a register from the device.
        
        Args:
            register: The register address
            size: Number of bytes to read (default 2)
            
        Returns:
            The register value
        """
        with self._i2c:
            try:
                if size == 2:
                    # Read 2 bytes using write-then-read pattern
                    buffer_out = bytes([register])
                    buffer_in = bytearray(2)
                    self._i2c.writeto_then_readfrom(self._address, buffer_out, buffer_in)
                    return int.from_bytes(buffer_in, byteorder='big')
                else:
                    # Read single byte using write-then-read pattern
                    buffer_out = bytes([register])
                    buffer_in = bytearray(1)
                    self._i2c.writeto_then_readfrom(self._address, buffer_out, buffer_in)
                    return buffer_in[0]
            except Exception as e:
                _LOGGER.error(f"Failed to read PCT2075 register 0x{register:02X}: {e}")
                raise
    
    def _write_register(self, register: int, value: int, size: int = 1) -> None:
        """Write to a register on the device.
        
        Args:
            register: The register address
            value: The value to write
            size: Number of bytes to write (default 1)
        """
        with self._i2c:
            try:
                if size == 1:
                    # Single byte write
                    data = bytes([register, value])
                else:
                    # 2-byte write (big-endian)
                    data = bytes([register, (value >> 8) & 0xFF, value & 0xFF])
                
                self._i2c.writeto(self._address, data)
            except Exception as e:
                _LOGGER.error(f"Failed to write PCT2075 register 0x{register:02X}: {e}")
                raise
    
    @property
    def temperature(self):
        """Read the temperature value in degrees Celsius."""
        raw = self._read_register(TEMP_REG)
        # Convert from raw value to temperature
        # PCT2075 returns a 16-bit value with the temperature in the upper 11 bits
        # Each bit represents 0.125°C, and the value is signed
        if raw & 0x8000:  # Check if negative (sign bit set)
            raw = -((~raw & 0xFFFF) + 1)  # Two's complement
        return (raw >> 5) * 0.125  # Shift right by 5 bits and multiply by 0.125°C
    
    def set_high_temp_threshold(self, temp_c):
        """Set the high temperature threshold in degrees Celsius."""
        # Convert temperature to raw value (8 bits for whole part, 7 bits for fraction)
        raw = int(temp_c / 0.125) << 5
        self._write_register(TOS_REG, raw, size=2)
    
    def set_hysteresis(self, temp_c):
        """Set the hysteresis temperature in degrees Celsius."""
        # Convert temperature to raw value
        raw = int(temp_c / 0.125) << 5
        self._write_register(THYST_REG, raw, size=2)
    
    def shutdown(self):
        """Put the device in shutdown mode to save power."""
        # Set shutdown bit in configuration register
        conf = self._read_register(CONF_REG, size=1)
        self._write_register(CONF_REG, conf | 0x01)
    
    def wake(self):
        """Wake the device from shutdown mode."""
        # Clear shutdown bit in configuration register
        conf = self._read_register(CONF_REG, size=1)
        self._write_register(CONF_REG, conf & ~0x01)
