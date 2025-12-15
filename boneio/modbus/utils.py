"""Modbus utility functions for value conversion.

These functions are used for legacy devices that don't have value_type defined.
New devices should use value_type in their JSON definition instead.

Note: Updated for pymodbus 3.x which uses result.registers[] instead of result.getRegister().
"""
from __future__ import annotations
from struct import unpack


allowed_operations = {"multiply": lambda x, y: x * y if x else x}


def _get_register(result, index: int) -> int:
    """Get register value at index.
    
    Compatible with pymodbus 3.x which uses result.registers[] instead of getRegister().
    
    Args:
        result: Modbus response object with .registers attribute
        index: Index in the registers array
        
    Returns:
        Register value as integer
    """
    return result.registers[index]


def float32(result, base, addr):
    """Read Float value from register.
    
    Args:
        result: Modbus response with .registers attribute
        base: Base address of the register block
        addr: Address of the register to read
        
    Returns:
        Float value decoded from two registers
    """
    low = _get_register(result, addr - base)
    high = _get_register(result, addr - base + 1)
    data = bytearray(4)
    data[0] = high & 0xFF
    data[1] = high >> 8
    data[2] = low & 0xFF
    data[3] = low >> 8
    val = unpack("f", bytes(data))
    return val[0]


def floatsofar(result, base, addr):
    """Read Float value from register (Sofar specific).
    
    Args:
        result: Modbus response with .registers attribute
        base: Base address of the register block
        addr: Address of the register to read
        
    Returns:
        Sum of high and low registers
    """
    low = _get_register(result, addr - base)
    high = _get_register(result, addr - base + 1)
    return high + low


def multiply0_1(result, base, addr):
    """Read register and multiply by 0.1."""
    low = _get_register(result, addr - base)
    return round(low * 0.1, 4)


def multiply0_01(result, base, addr):
    """Read register and multiply by 0.01."""
    low = _get_register(result, addr - base)
    return round(low * 0.01, 4)


def multiply0_001(result, base, addr):
    """Read register and multiply by 0.001."""
    low = _get_register(result, addr - base)
    return round(low * 0.001, 4)


def multiply10(result, base, addr):
    """Read register and multiply by 10."""
    low = _get_register(result, addr - base)
    return round(low * 10, 4)


def multiply100(result, base, addr):
    """Read register and multiply by 100."""
    low = _get_register(result, addr - base)
    return round(low * 100, 4)


def multiply1000(result, base, addr):
    """Read register and multiply by 1000."""
    low = _get_register(result, addr - base)
    return round(low * 1000, 4)


def regular_result(result, base, addr):
    """Read single register value without modification."""
    return _get_register(result, addr - base)


CONVERT_METHODS = {
    "float32": float32,
    "multiply0_1": multiply0_1,
    "multiply0_01": multiply0_01,
    "multiply0_001": multiply0_001,
    "floatsofar": floatsofar,
    "multiply10": multiply10,
    "multiply100": multiply100,
    "multiply1000": multiply1000,
    "regular": regular_result,
}
REGISTERS_BASE = "registers_base"
