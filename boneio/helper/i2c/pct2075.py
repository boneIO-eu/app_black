"""PCT2075 temperature sensor implementation using smbus2."""

from smbus2 import SMBus

# PCT2075 registers
TEMP_REG = 0x00  # Temperature register (read-only)
CONF_REG = 0x01  # Configuration register
THYST_REG = 0x02  # Hysteresis register
TOS_REG = 0x03   # Over-temp shutdown threshold register
TIDLE_REG = 0x04  # Temperature conversion idle time register

class PCT2075:
    """PCT2075 and compatible LM75 temperature sensor driver using smbus2."""
    
    def __init__(self, i2c_bus, address=0x48):
        """Initialize the PCT2075 temperature sensor.
        
        Args:
            i2c_bus: The I2C bus object
            address: The I2C device address (default 0x48)
        """
        self.bus = i2c_bus
        self.address = address
        self.bus_num = None
        
        # Extract bus number from I2C object if available
        if hasattr(i2c_bus, '_i2c_bus'):
            self.bus_num = i2c_bus._i2c_bus
        elif hasattr(i2c_bus, '_i2c_device'):
            self.bus_num = i2c_bus._i2c_device.bus
            
        # If we have a bus number, use SMBus directly
        if self.bus_num is not None:
            self.smbus = SMBus(self.bus_num)
        else:
            # Otherwise, we'll try to use the provided bus object
            self.smbus = None
            
        # Set to normal operation mode
        self._write_register(CONF_REG, 0x00)
    
    def _read_register(self, register, size=2):
        """Read a register from the device.
        
        Args:
            register: The register address
            size: Number of bytes to read (default 2)
            
        Returns:
            The register value
        """
        if self.smbus:
            if size == 2:
                return self.smbus.read_word_data(self.address, register)
            else:
                return self.smbus.read_byte_data(self.address, register)
        else:
            # Fallback to using the provided bus object
            result = bytearray(size)
            self.bus.readfrom_into(self.address, result, start=register)
            return int.from_bytes(result, byteorder='big')
    
    def _write_register(self, register, value, size=1):
        """Write to a register on the device.
        
        Args:
            register: The register address
            value: The value to write
            size: Number of bytes to write (default 1)
        """
        if self.smbus:
            if size == 2:
                self.smbus.write_word_data(self.address, register, value)
            else:
                self.smbus.write_byte_data(self.address, register, value)
        else:
            # Fallback to using the provided bus object
            if size == 1:
                data = bytes([register, value])
            else:
                data = bytes([register, (value >> 8) & 0xFF, value & 0xFF])
            self.bus.write(self.address, data)
    
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
