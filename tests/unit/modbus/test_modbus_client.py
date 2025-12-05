"""Unit tests for Modbus client.

Tests cover:
- Reading registers (input and holding)
- Decoding values (FP32, U_WORD, S_WORD, etc.)
- Error handling (timeout, invalid address)
- Device simulation (SDM120, CWT)
"""

import struct
import pytest
from unittest.mock import patch, MagicMock

from tests.mocks.modbus import (
    MockModbusSerialClient,
    MockModbusResponse,
    MockModbusErrorResponse,
    MockSDM120Registers,
    MockCWTRegisters,
)


class TestMockModbusClient:
    """Test MockModbusSerialClient functionality."""
    
    def test_connect(self):
        """Client should connect successfully."""
        client = MockModbusSerialClient()
        assert not client.connected
        
        result = client.connect()
        
        assert result is True
        assert client.connected
    
    def test_close(self):
        """Client should close connection."""
        client = MockModbusSerialClient()
        client.connect()
        
        client.close()
        
        assert not client.connected
    
    def test_add_device_with_float(self):
        """Adding device with float values should encode as FP32."""
        client = MockModbusSerialClient()
        client.add_device(1, {0: 230.0})
        
        result = client.read_input_registers(address=0, count=2, slave=1)
        
        assert result is not None
        assert not result.isError
        assert len(result.registers) == 2
        
        # Decode FP32 from registers
        packed = struct.pack(">HH", result.registers[0], result.registers[1])
        value = struct.unpack(">f", packed)[0]
        assert abs(value - 230.0) < 0.01
    
    def test_add_device_with_int(self):
        """Adding device with int values should encode as U_WORD."""
        client = MockModbusSerialClient()
        client.add_device(1, {0: 1234})
        
        result = client.read_input_registers(address=0, count=1, slave=1)
        
        assert result is not None
        assert result.registers == [1234]
    
    def test_read_nonexistent_slave(self):
        """Reading from nonexistent slave should return error."""
        client = MockModbusSerialClient()
        
        result = client.read_input_registers(address=0, count=1, slave=99)
        
        assert result is not None
        assert result.isError
        assert result.exception_code == 2  # Illegal data address


class TestModbusReadOperations:
    """Test Modbus read operations."""
    
    @pytest.fixture
    def client_with_sdm120(self):
        """Create client with SDM120 device."""
        client = MockModbusSerialClient()
        client.add_device(1, MockSDM120Registers.default(
            voltage=230.5,
            current=1.25,
            power=288.125,
            frequency=50.0,
        ))
        return client
    
    def test_read_voltage(self, client_with_sdm120):
        """Should read voltage from SDM120."""
        result = client_with_sdm120.read_input_registers(address=0, count=2, slave=1)
        
        assert result is not None
        assert not result.isError
        
        # Decode FP32
        packed = struct.pack(">HH", result.registers[0], result.registers[1])
        voltage = struct.unpack(">f", packed)[0]
        
        assert abs(voltage - 230.5) < 0.01
    
    def test_read_current(self, client_with_sdm120):
        """Should read current from SDM120."""
        result = client_with_sdm120.read_input_registers(address=6, count=2, slave=1)
        
        assert result is not None
        
        packed = struct.pack(">HH", result.registers[0], result.registers[1])
        current = struct.unpack(">f", packed)[0]
        
        assert abs(current - 1.25) < 0.01
    
    def test_read_holding_registers(self, client_with_sdm120):
        """Should read holding registers."""
        result = client_with_sdm120.read_holding_registers(address=0, count=2, slave=1)
        
        assert result is not None
        assert not result.isError
    
    def test_read_log(self, client_with_sdm120):
        """Should log all read operations."""
        client_with_sdm120.read_input_registers(address=0, count=2, slave=1)
        client_with_sdm120.read_input_registers(address=6, count=2, slave=1)
        
        log = client_with_sdm120.get_read_log()
        
        assert len(log) == 2
        assert log[0]["address"] == 0
        assert log[1]["address"] == 6


class TestModbusErrorHandling:
    """Test Modbus error handling."""
    
    def test_simulate_timeout(self):
        """Should simulate timeout for slave."""
        client = MockModbusSerialClient()
        client.add_device(1, {0: 230.0})
        client.simulate_timeout(1)
        
        result = client.read_input_registers(address=0, count=2, slave=1)
        
        assert result is None
    
    def test_clear_timeout(self):
        """Should clear timeout simulation."""
        client = MockModbusSerialClient()
        client.add_device(1, {0: 230.0})
        client.simulate_timeout(1)
        client.clear_timeout(1)
        
        result = client.read_input_registers(address=0, count=2, slave=1)
        
        assert result is not None
        assert not result.isError
    
    def test_simulate_error(self):
        """Should simulate error for specific address."""
        client = MockModbusSerialClient()
        client.add_device(1, {0: 230.0})
        client.simulate_error(1, 0, error_code=3)  # Illegal data value
        
        result = client.read_input_registers(address=0, count=2, slave=1)
        
        assert result is not None
        assert result.isError
        assert result.exception_code == 3
    
    def test_read_uninitialized_register(self):
        """Reading uninitialized register should return 0."""
        client = MockModbusSerialClient()
        client.add_device(1, {0: 230.0})  # Only register 0 initialized
        
        result = client.read_input_registers(address=100, count=1, slave=1)
        
        assert result is not None
        assert not result.isError
        assert result.registers == [0]


class TestModbusWriteOperations:
    """Test Modbus write operations."""
    
    def test_write_register(self):
        """Should write single register."""
        client = MockModbusSerialClient()
        client.add_device(1, {})
        
        result = client.write_register(address=0, value=1234, slave=1)
        
        assert result is not None
        assert not result.isError
        
        # Verify written value
        read_result = client.read_input_registers(address=0, count=1, slave=1)
        assert read_result.registers == [1234]
    
    def test_write_log(self):
        """Should log all write operations."""
        client = MockModbusSerialClient()
        client.add_device(1, {})
        
        client.write_register(address=0, value=100, slave=1)
        client.write_register(address=1, value=200, slave=1)
        
        log = client.get_write_log()
        
        assert len(log) == 2
        assert log[0]["value"] == 100
        assert log[1]["value"] == 200


class TestCWTDevice:
    """Test CWT current transformer simulation."""
    
    def test_read_three_phase_current(self):
        """Should read 3-phase current from CWT."""
        client = MockModbusSerialClient()
        client.add_device(1, MockCWTRegisters.default(
            current_a=15.5,
            current_b=14.2,
            current_c=16.8,
        ))
        
        # Read phase A
        result_a = client.read_input_registers(address=0, count=2, slave=1)
        packed = struct.pack(">HH", result_a.registers[0], result_a.registers[1])
        current_a = struct.unpack(">f", packed)[0]
        
        # Read phase B
        result_b = client.read_input_registers(address=2, count=2, slave=1)
        packed = struct.pack(">HH", result_b.registers[0], result_b.registers[1])
        current_b = struct.unpack(">f", packed)[0]
        
        # Read phase C
        result_c = client.read_input_registers(address=4, count=2, slave=1)
        packed = struct.pack(">HH", result_c.registers[0], result_c.registers[1])
        current_c = struct.unpack(">f", packed)[0]
        
        assert abs(current_a - 15.5) < 0.01
        assert abs(current_b - 14.2) < 0.01
        assert abs(current_c - 16.8) < 0.01


class TestModbusValueDecoding:
    """Test value decoding from registers."""
    
    def test_decode_fp32_big_endian(self):
        """Should decode FP32 big endian correctly."""
        # 230.0 as FP32 big endian
        registers = [0x4366, 0x0000]
        
        packed = struct.pack(">HH", registers[0], registers[1])
        value = struct.unpack(">f", packed)[0]
        
        assert abs(value - 230.0) < 0.01
    
    def test_decode_fp32_little_endian(self):
        """Should decode FP32 little endian correctly."""
        # 230.0 as FP32 little endian (reversed registers)
        registers = [0x0000, 0x4366]
        
        packed = struct.pack(">HH", registers[0], registers[1])
        value = struct.unpack("<f", packed)[0]
        
        assert abs(value - 230.0) < 0.01
    
    def test_decode_u_word(self):
        """Should decode unsigned 16-bit word."""
        registers = [0xFFFF]
        value = registers[0]
        
        assert value == 65535
    
    def test_decode_s_word(self):
        """Should decode signed 16-bit word."""
        registers = [0xFFFF]
        packed = struct.pack(">H", registers[0])
        value = struct.unpack(">h", packed)[0]
        
        assert value == -1
    
    def test_decode_u_dword(self):
        """Should decode unsigned 32-bit dword."""
        registers = [0x0001, 0x0000]  # 65536
        
        packed = struct.pack(">HH", registers[0], registers[1])
        value = struct.unpack(">I", packed)[0]
        
        assert value == 65536
