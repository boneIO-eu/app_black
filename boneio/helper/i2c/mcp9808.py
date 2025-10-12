"""MCP9808 temperature sensor implementation using smbus2."""

from smbus2 import SMBus

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
    """MCP9808 temperature sensor driver using smbus2."""
    
    def __init__(self, i2c_bus, address=0x18):
        """Initialize the MCP9808 temperature sensor.
        
        Args:
            i2c_bus: The I2C bus object
            address: The I2C device address (default 0x18)
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
            
        # Verify device
        try:
            manuf_id = self._read_register(REG_MANUF_ID)
            device_id = self._read_register(REG_DEVICE_ID)
            if manuf_id != 0x0054 or (device_id & 0xFF00) != 0x0400:
                raise RuntimeError(f"Failed to find MCP9808! Manufacturer ID: {manuf_id:04x}, Device ID: {device_id:04x}")
        except Exception as e:
            raise RuntimeError(f"Failed to communicate with MCP9808: {e}")
    
    def _read_register(self, register):
        """Read a 16-bit register from the device.
        
        Args:
            register: The register address
            
        Returns:
            The 16-bit register value
        """
        if self.smbus:
            # Read 16-bit value (big-endian)
            data = self.smbus.read_word_data(self.address, register)
            # Convert from little-endian to big-endian
            return ((data & 0xFF) << 8) | ((data >> 8) & 0xFF)
        else:
            # Fallback to using the provided bus object
            result = bytearray(2)
            self.bus.readfrom_into(self.address, result, start=register)
            return (result[0] << 8) | result[1]
    
    def _write_register(self, register, value):
        """Write to a 16-bit register on the device.
        
        Args:
            register: The register address
            value: The 16-bit value to write
        """
        if self.smbus:
            # Convert from big-endian to little-endian for SMBus
            value_le = ((value & 0xFF) << 8) | ((value >> 8) & 0xFF)
            self.smbus.write_word_data(self.address, register, value_le)
        else:
            # Fallback to using the provided bus object
            data = bytes([register, (value >> 8) & 0xFF, value & 0xFF])
            self.bus.write(self.address, data)
    
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
