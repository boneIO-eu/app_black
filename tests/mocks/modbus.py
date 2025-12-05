"""Mock Modbus client for testing.

This module provides mock implementations of Modbus client
for testing without real hardware.

Example:
    mock_client = MockModbusClient()
    mock_client.add_device(1, {
        # SDM120 - Voltage register at address 0
        0: [0x43, 0x66, 0x00, 0x00],  # 230.0V as FP32
        # Current register at address 6
        6: [0x3F, 0x80, 0x00, 0x00],  # 1.0A as FP32
    })
    
    result = mock_client.read_input_registers(address=0, count=2, slave=1)
    # result.registers = [0x4366, 0x0000] -> decodes to 230.0
"""

from __future__ import annotations

import logging
import struct
from dataclasses import dataclass, field
from typing import Any

_LOGGER = logging.getLogger(__name__)


@dataclass
class MockModbusResponse:
    """Mock response from Modbus read operation.
    
    Attributes:
        registers: List of 16-bit register values
        isError: Whether this is an error response
    """
    registers: list[int] = field(default_factory=list)
    isError: bool = False
    
    def __bool__(self) -> bool:
        """Return True if not an error."""
        return not self.isError


@dataclass
class MockModbusErrorResponse:
    """Mock error response from Modbus."""
    exception_code: int = 1
    isError: bool = True
    
    def __bool__(self) -> bool:
        """Return False for error responses."""
        return False


class MockModbusSerialClient:
    """Mock ModbusSerialClient for testing.
    
    Simulates pymodbus ModbusSerialClient behavior without real serial port.
    
    Example:
        client = MockModbusSerialClient()
        client.add_device(1, registers={0: 230.0, 6: 1.5})
        
        result = client.read_input_registers(address=0, count=2, slave=1)
    """
    
    def __init__(
        self,
        port: str = "/dev/ttyS1",
        baudrate: int = 9600,
        **kwargs: Any
    ):
        """Initialize mock Modbus client.
        
        Args:
            port: Serial port (ignored in mock)
            baudrate: Baud rate (stored for verification)
            **kwargs: Additional parameters (ignored)
        """
        self._port = port
        self._baudrate = baudrate
        self._connected = False
        
        # Device registers: {slave_id: {address: [bytes]}}
        self._devices: dict[int, dict[int, list[int]]] = {}
        
        # Simulate errors for specific addresses
        self._error_addresses: dict[int, dict[int, int]] = {}  # {slave: {addr: error_code}}
        
        # Simulate timeout for specific slaves
        self._timeout_slaves: set[int] = set()
        
        # Track read/write operations for verification
        self._read_log: list[dict] = []
        self._write_log: list[dict] = []
        
        _LOGGER.debug(f"MockModbusSerialClient initialized for port {port}")
    
    @property
    def connected(self) -> bool:
        """Return connection status."""
        return self._connected
    
    def connect(self) -> bool:
        """Simulate connection.
        
        Returns:
            True (always succeeds in mock)
        """
        self._connected = True
        _LOGGER.debug("MockModbusSerialClient connected")
        return True
    
    def close(self) -> None:
        """Close mock connection."""
        self._connected = False
        _LOGGER.debug("MockModbusSerialClient closed")
    
    def add_device(
        self,
        slave_id: int,
        registers: dict[int, list[int] | float | int] | None = None
    ) -> None:
        """Add a simulated Modbus device.
        
        Args:
            slave_id: Modbus slave address (1-247)
            registers: Dict of address -> value (bytes, float, or int)
                       For float values, they will be encoded as FP32
                       For int values, they will be encoded as U_WORD
        
        Example:
            # Add SDM120 energy meter at address 1
            client.add_device(1, {
                0: 230.5,   # Voltage (FP32)
                6: 1.25,    # Current (FP32)
                12: 287.5,  # Power (FP32)
            })
        """
        if slave_id not in self._devices:
            self._devices[slave_id] = {}
        
        if registers:
            for addr, value in registers.items():
                if isinstance(value, float):
                    # Encode as FP32 (big endian)
                    packed = struct.pack(">f", value)
                    # Convert to list of 16-bit register values
                    self._devices[slave_id][addr] = [
                        (packed[0] << 8) | packed[1],
                        (packed[2] << 8) | packed[3],
                    ]
                elif isinstance(value, int):
                    # Single 16-bit register
                    self._devices[slave_id][addr] = [value & 0xFFFF]
                elif isinstance(value, list):
                    # Raw register values
                    self._devices[slave_id][addr] = value
        
        _LOGGER.debug(f"Added mock Modbus device at slave {slave_id}")
    
    def set_register_float(self, slave_id: int, address: int, value: float) -> None:
        """Set a float value at register address.
        
        Args:
            slave_id: Modbus slave address
            address: Register address
            value: Float value to set
        """
        if slave_id not in self._devices:
            self._devices[slave_id] = {}
        
        packed = struct.pack(">f", value)
        self._devices[slave_id][address] = [
            (packed[0] << 8) | packed[1],
            (packed[2] << 8) | packed[3],
        ]
    
    def set_register_int(self, slave_id: int, address: int, value: int, signed: bool = False) -> None:
        """Set an integer value at register address.
        
        Args:
            slave_id: Modbus slave address
            address: Register address
            value: Integer value to set
            signed: Whether value is signed
        """
        if slave_id not in self._devices:
            self._devices[slave_id] = {}
        
        self._devices[slave_id][address] = [value & 0xFFFF]
    
    def simulate_error(self, slave_id: int, address: int, error_code: int = 1) -> None:
        """Simulate Modbus error for specific address.
        
        Args:
            slave_id: Modbus slave address
            address: Register address that will return error
            error_code: Modbus exception code (1=illegal function, 2=illegal address, etc.)
        """
        if slave_id not in self._error_addresses:
            self._error_addresses[slave_id] = {}
        self._error_addresses[slave_id][address] = error_code
    
    def simulate_timeout(self, slave_id: int) -> None:
        """Simulate timeout for specific slave.
        
        Args:
            slave_id: Modbus slave that will timeout
        """
        self._timeout_slaves.add(slave_id)
    
    def clear_timeout(self, slave_id: int) -> None:
        """Clear timeout simulation for slave."""
        self._timeout_slaves.discard(slave_id)
    
    def read_input_registers(
        self,
        address: int,
        count: int = 1,
        slave: int = 1,
        **kwargs: Any
    ) -> MockModbusResponse | MockModbusErrorResponse | None:
        """Read input registers (function code 0x04).
        
        Args:
            address: Starting register address
            count: Number of registers to read
            slave: Slave address
            
        Returns:
            MockModbusResponse with register values or error
        """
        return self._read_registers(address, count, slave, "input")
    
    def read_holding_registers(
        self,
        address: int,
        count: int = 1,
        slave: int = 1,
        **kwargs: Any
    ) -> MockModbusResponse | MockModbusErrorResponse | None:
        """Read holding registers (function code 0x03).
        
        Args:
            address: Starting register address
            count: Number of registers to read
            slave: Slave address
            
        Returns:
            MockModbusResponse with register values or error
        """
        return self._read_registers(address, count, slave, "holding")
    
    def _read_registers(
        self,
        address: int,
        count: int,
        slave: int,
        method: str
    ) -> MockModbusResponse | MockModbusErrorResponse | None:
        """Internal method to read registers.
        
        Args:
            address: Starting register address
            count: Number of registers to read
            slave: Slave address
            method: "input" or "holding"
            
        Returns:
            MockModbusResponse or error
        """
        # Log the read operation
        self._read_log.append({
            "address": address,
            "count": count,
            "slave": slave,
            "method": method,
        })
        
        # Check for timeout simulation
        if slave in self._timeout_slaves:
            _LOGGER.debug(f"Simulating timeout for slave {slave}")
            return None
        
        # Check for error simulation
        if slave in self._error_addresses and address in self._error_addresses[slave]:
            error_code = self._error_addresses[slave][address]
            _LOGGER.debug(f"Simulating error {error_code} for slave {slave} address {address}")
            return MockModbusErrorResponse(exception_code=error_code)
        
        # Check if device exists
        if slave not in self._devices:
            _LOGGER.debug(f"Slave {slave} not found")
            return MockModbusErrorResponse(exception_code=2)  # Illegal data address
        
        # Read registers
        registers = []
        device = self._devices[slave]
        
        for addr in range(address, address + count):
            if addr in device:
                regs = device[addr]
                registers.extend(regs)
            else:
                # Return 0 for uninitialized registers
                registers.append(0)
        
        # Trim to requested count
        registers = registers[:count]
        
        _LOGGER.debug(f"Read registers from slave {slave} addr {address}: {registers}")
        return MockModbusResponse(registers=registers)
    
    def write_register(
        self,
        address: int,
        value: int,
        slave: int = 1,
        **kwargs: Any
    ) -> MockModbusResponse | MockModbusErrorResponse:
        """Write single register (function code 0x06).
        
        Args:
            address: Register address
            value: Value to write
            slave: Slave address
            
        Returns:
            MockModbusResponse on success
        """
        self._write_log.append({
            "address": address,
            "value": value,
            "slave": slave,
        })
        
        if slave not in self._devices:
            self._devices[slave] = {}
        
        self._devices[slave][address] = [value & 0xFFFF]
        
        return MockModbusResponse(registers=[value])
    
    def get_read_log(self) -> list[dict]:
        """Get log of all read operations.
        
        Returns:
            List of read operation dicts
        """
        return self._read_log.copy()
    
    def get_write_log(self) -> list[dict]:
        """Get log of all write operations.
        
        Returns:
            List of write operation dicts
        """
        return self._write_log.copy()
    
    def clear_logs(self) -> None:
        """Clear read and write logs."""
        self._read_log.clear()
        self._write_log.clear()


# Pre-configured device register maps
class MockSDM120Registers:
    """Pre-configured registers for SDM120 energy meter."""
    
    @staticmethod
    def default(
        voltage: float = 230.0,
        current: float = 1.0,
        power: float = 230.0,
        frequency: float = 50.0,
        energy: float = 100.0,
    ) -> dict[int, float]:
        """Create default SDM120 register values.
        
        Args:
            voltage: Voltage in V
            current: Current in A
            power: Active power in W
            frequency: Frequency in Hz
            energy: Total energy in kWh
            
        Returns:
            Dict of register address -> float value
        """
        return {
            0: voltage,      # Voltage (V)
            6: current,      # Current (A)
            12: power,       # Active Power (W)
            18: power,       # Apparent Power (VA)
            24: power,       # Reactive Power (VAr)
            30: 1.0,         # Power Factor
            36: 0.0,         # Phase Angle
            70: frequency,   # Frequency (Hz)
            72: energy,      # Import Active Energy (kWh)
            74: 0.0,         # Export Active Energy (kWh)
        }


class MockCWTRegisters:
    """Pre-configured registers for CWT current transformer."""
    
    @staticmethod
    def default(
        current_a: float = 10.0,
        current_b: float = 10.0,
        current_c: float = 10.0,
    ) -> dict[int, float]:
        """Create default CWT register values.
        
        Args:
            current_a: Phase A current in A
            current_b: Phase B current in A
            current_c: Phase C current in A
            
        Returns:
            Dict of register address -> float value
        """
        return {
            0: current_a,    # Phase A Current
            2: current_b,    # Phase B Current
            4: current_c,    # Phase C Current
        }
