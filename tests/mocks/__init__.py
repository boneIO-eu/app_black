"""Mock objects for testing BoneIO hardware."""

from .i2c import MockSMBus, MockSMBus2I2C
from .modbus import (
    MockModbusSerialClient,
    MockModbusResponse,
    MockModbusErrorResponse,
    MockSDM120Registers,
    MockCWTRegisters,
)

__all__ = [
    "MockSMBus",
    "MockSMBus2I2C",
    "MockModbusSerialClient",
    "MockModbusResponse",
    "MockModbusErrorResponse",
    "MockSDM120Registers",
    "MockCWTRegisters",
]
