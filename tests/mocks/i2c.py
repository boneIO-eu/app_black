"""Mock I2C bus for testing without real hardware.

These mocks simulate SMBus and SMBus2I2C behavior for unit testing
GPIO expanders (MCP23017, PCF8575, PCA9685) and sensors.
"""

from __future__ import annotations

import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)


class MockSMBus:
    """Mock SMBus for testing without hardware.
    
    Simulates smbus2.SMBus interface with in-memory register storage.
    
    Example:
        bus = MockSMBus(2)
        bus.write_byte_data(0x20, 0x00, 0xFF)
        value = bus.read_byte_data(0x20, 0x00)  # Returns 0xFF
    """
    
    def __init__(self, bus_number: int = 2):
        """Initialize mock SMBus.
        
        Args:
            bus_number: I2C bus number (ignored, for API compatibility)
        """
        self.bus_number = bus_number
        self._registers: dict[int, dict[int, int]] = {}  # addr -> {reg: value}
        self._closed = False
        _LOGGER.debug(f"MockSMBus initialized for bus {bus_number}")
    
    def _ensure_device(self, addr: int) -> None:
        """Ensure device exists in register map."""
        if addr not in self._registers:
            self._registers[addr] = {}
    
    def write_byte(self, addr: int, value: int) -> None:
        """Write single byte to device."""
        self._ensure_device(addr)
        self._registers[addr][0] = value & 0xFF
    
    def read_byte(self, addr: int) -> int:
        """Read single byte from device."""
        self._ensure_device(addr)
        return self._registers[addr].get(0, 0)
    
    def write_byte_data(self, addr: int, register: int, value: int) -> None:
        """Write byte to specific register."""
        self._ensure_device(addr)
        self._registers[addr][register] = value & 0xFF
        _LOGGER.debug(f"MockSMBus: write 0x{value:02X} to addr=0x{addr:02X} reg=0x{register:02X}")
    
    def read_byte_data(self, addr: int, register: int) -> int:
        """Read byte from specific register."""
        self._ensure_device(addr)
        value = self._registers[addr].get(register, 0)
        _LOGGER.debug(f"MockSMBus: read 0x{value:02X} from addr=0x{addr:02X} reg=0x{register:02X}")
        return value
    
    def write_word_data(self, addr: int, register: int, value: int) -> None:
        """Write 16-bit word to register (little-endian)."""
        self._ensure_device(addr)
        self._registers[addr][register] = value & 0xFF
        self._registers[addr][register + 1] = (value >> 8) & 0xFF
    
    def read_word_data(self, addr: int, register: int) -> int:
        """Read 16-bit word from register (little-endian)."""
        self._ensure_device(addr)
        low = self._registers[addr].get(register, 0)
        high = self._registers[addr].get(register + 1, 0)
        return low | (high << 8)
    
    def write_i2c_block_data(self, addr: int, register: int, data: list[int]) -> None:
        """Write block of bytes starting at register."""
        self._ensure_device(addr)
        for i, byte in enumerate(data):
            self._registers[addr][register + i] = byte & 0xFF
    
    def read_i2c_block_data(self, addr: int, register: int, length: int) -> list[int]:
        """Read block of bytes starting at register."""
        self._ensure_device(addr)
        return [self._registers[addr].get(register + i, 0) for i in range(length)]
    
    def close(self) -> None:
        """Close the bus."""
        self._closed = True
    
    # Helper methods for testing
    
    def add_device(self, addr: int, initial_registers: dict[int, int] | None = None) -> None:
        """Add a device with optional initial register values.
        
        Args:
            addr: I2C address
            initial_registers: Dict of register -> value
        """
        self._registers[addr] = initial_registers or {}
    
    def get_register(self, addr: int, register: int) -> int:
        """Get register value (for test assertions)."""
        return self._registers.get(addr, {}).get(register, 0)
    
    def set_register(self, addr: int, register: int, value: int) -> None:
        """Set register value (for test setup)."""
        self._ensure_device(addr)
        self._registers[addr][register] = value & 0xFF


class MockSMBus2I2C:
    """Mock SMBus2I2C wrapper for testing.
    
    Simulates the boneio.hardware.i2c.bus.SMBus2I2C interface.
    Uses MockSMBus internally for register storage.
    
    Example:
        i2c = MockSMBus2I2C(bus_number=2)
        i2c.add_device(0x20)  # Add MCP23017
        
        mcp = MCP23017(i2c=i2c, address=0x20)
        mcp.set_pin_value(0, True)
        
        # Verify register was written
        assert i2c.get_register(0x20, 0x14) & 0x01 == 0x01
    """
    
    def __init__(self, bus_number: int = 2):
        """Initialize mock I2C wrapper.
        
        Args:
            bus_number: I2C bus number (for API compatibility)
        """
        self._bus = MockSMBus(bus_number)
        self._locked = False
        self._bus_number = bus_number
        _LOGGER.debug(f"MockSMBus2I2C initialized for bus {bus_number}")
    
    def try_lock(self) -> bool:
        """Try to acquire I2C bus lock.
        
        Returns:
            True if lock acquired, False if already locked
        """
        if self._locked:
            return False
        self._locked = True
        return True
    
    def unlock(self) -> None:
        """Release I2C bus lock."""
        self._locked = False
    
    def __enter__(self) -> MockSMBus2I2C:
        """Context manager entry - acquire lock."""
        self.try_lock()
        return self
    
    def __exit__(self, *args: Any) -> None:
        """Context manager exit - release lock."""
        self.unlock()
    
    def writeto(self, address: int, buffer: bytes, *, start: int = 0, end: int | None = None) -> None:
        """Write bytes to device.
        
        Args:
            address: I2C device address
            buffer: Bytes to write
            start: Starting index in buffer
            end: Ending index in buffer
        """
        if end is None:
            end = len(buffer)
        data = buffer[start:end]
        
        if len(data) == 0:
            return
        elif len(data) == 1:
            self._bus.write_byte(address, data[0])
        elif len(data) == 2:
            self._bus.write_byte_data(address, data[0], data[1])
        else:
            # First byte is register, rest is data
            register = data[0]
            for i, byte in enumerate(data[1:]):
                self._bus.write_byte_data(address, register + i, byte)
    
    def readfrom_into(self, address: int, buffer: bytearray, *, start: int = 0, end: int | None = None) -> None:
        """Read bytes from device into buffer.
        
        Args:
            address: I2C device address
            buffer: Buffer to read into
            start: Starting index in buffer
            end: Ending index in buffer
        """
        if end is None:
            end = len(buffer)
        for i in range(end - start):
            buffer[start + i] = self._bus.read_byte_data(address, i)
    
    def writeto_then_readfrom(
        self, 
        address: int, 
        buffer_out: bytes, 
        buffer_in: bytearray,
        *,
        out_start: int = 0,
        out_end: int | None = None,
        in_start: int = 0,
        in_end: int | None = None
    ) -> None:
        """Write then read (combined transaction).
        
        Args:
            address: I2C device address
            buffer_out: Bytes to write (typically register address)
            buffer_in: Buffer to read into
            out_start: Starting index in output buffer
            out_end: Ending index in output buffer
            in_start: Starting index in input buffer
            in_end: Ending index in input buffer
        """
        if out_end is None:
            out_end = len(buffer_out)
        if in_end is None:
            in_end = len(buffer_in)
            
        out_data = buffer_out[out_start:out_end]
        register = out_data[0] if len(out_data) > 0 else 0
        
        for i in range(in_end - in_start):
            buffer_in[in_start + i] = self._bus.read_byte_data(address, register + i)
    
    def scan(self) -> list[int]:
        """Scan for devices on the bus.
        
        Returns:
            List of device addresses found
        """
        return list(self._bus._registers.keys())
    
    # ========== Direct SMBus methods (matching real SMBus2I2C) ==========
    
    def write_byte(self, address: int, value: int) -> None:
        """Write a single byte to I2C device."""
        self._bus.write_byte(address, value)
    
    def read_byte(self, address: int) -> int:
        """Read a single byte from I2C device."""
        return self._bus.read_byte(address)
    
    def write_byte_data(self, address: int, register: int, value: int) -> None:
        """Write a byte to a specific register."""
        self._bus.write_byte_data(address, register, value)
    
    def read_byte_data(self, address: int, register: int) -> int:
        """Read a byte from a specific register."""
        return self._bus.read_byte_data(address, register)
    
    def write_i2c_block_data(self, address: int, register: int, data: list[int]) -> None:
        """Write a block of bytes to a register."""
        self._bus.write_i2c_block_data(address, register, data)
    
    def read_i2c_block_data(self, address: int, register: int, length: int) -> list[int]:
        """Read a block of bytes from a register."""
        return self._bus.read_i2c_block_data(address, register, length)
    
    @property
    def frequency(self) -> int:
        """Get I2C bus frequency (mock returns default)."""
        return 100000
    
    @frequency.setter
    def frequency(self, value: int) -> None:
        """Set I2C bus frequency (no-op in mock)."""
        pass
    
    def close(self) -> None:
        """Close the I2C bus (no-op in mock)."""
        pass
    
    # Helper methods for testing
    
    def add_device(self, addr: int, initial_registers: dict[int, int] | None = None) -> None:
        """Add a device with optional initial register values.
        
        Args:
            addr: I2C address
            initial_registers: Dict of register -> value
        """
        self._bus.add_device(addr, initial_registers)
    
    def get_register(self, addr: int, register: int) -> int:
        """Get register value (for test assertions).
        
        Args:
            addr: I2C address
            register: Register address
            
        Returns:
            Register value
        """
        return self._bus.get_register(addr, register)
    
    def set_register(self, addr: int, register: int, value: int) -> None:
        """Set register value (for test setup).
        
        Args:
            addr: I2C address
            register: Register address
            value: Value to set
        """
        self._bus.set_register(addr, register, value)


# Pre-configured device mocks

class MockMCP23017Registers:
    """Pre-configured registers for MCP23017 simulation."""
    
    IODIRA = 0x00
    IODIRB = 0x01
    GPIOA = 0x12
    GPIOB = 0x13
    OLATA = 0x14
    OLATB = 0x15
    
    @staticmethod
    def default() -> dict[int, int]:
        """Get default register values (all inputs, all low)."""
        return {
            0x00: 0xFF,  # IODIRA - all inputs
            0x01: 0xFF,  # IODIRB - all inputs
            0x12: 0x00,  # GPIOA
            0x13: 0x00,  # GPIOB
            0x14: 0x00,  # OLATA
            0x15: 0x00,  # OLATB
        }


class MockPCF8575Registers:
    """Pre-configured registers for PCF8575 simulation."""
    
    @staticmethod
    def default() -> dict[int, int]:
        """Get default register values (all high - quasi-bidirectional)."""
        return {
            0: 0xFF,  # Port 0 (pins 0-7)
            1: 0xFF,  # Port 1 (pins 8-15)
        }


class MockPCA9685Registers:
    """Pre-configured registers for PCA9685 simulation."""
    
    MODE1 = 0x00
    MODE2 = 0x01
    PRESCALE = 0xFE
    LED0_ON_L = 0x06
    
    @staticmethod
    def default() -> dict[int, int]:
        """Get default register values."""
        registers = {
            0x00: 0x11,  # MODE1 - sleep mode
            0x01: 0x04,  # MODE2 - totem pole
            0xFE: 0x1E,  # PRESCALE - ~200Hz
        }
        # Initialize all 16 channels to off
        for ch in range(16):
            base = 0x06 + (ch * 4)
            registers[base] = 0x00      # ON_L
            registers[base + 1] = 0x00  # ON_H
            registers[base + 2] = 0x00  # OFF_L
            registers[base + 3] = 0x10  # OFF_H (full off)
        return registers
