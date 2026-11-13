"""In-process stand-in for pymodbus' ``ModbusSerialClient``, for development.

Active only with ``BONEIO_DEV`` and ``BONEIO_MODBUS_SIM`` both set. Every
answer is a genuine pymodbus response object, so :class:`boneio.modbus.client.Modbus`
and the coordinators run their real code paths against simulated devices.

Invariants: a read touching an address outside the device definition's blocks
of that register type is refused with ILLEGAL_ADDRESS, as a real unit refuses
such a block; an unknown slave id gives no response at all.
``BONEIO_MODBUS_SIM_MISSING`` (``exception`` or ``timeout``), read once at
construction, makes every optional block of every device unavailable.
"""

from __future__ import annotations

import logging
import os
import struct
import time
from types import SimpleNamespace
from typing import Callable

from pymodbus.exceptions import ModbusIOException
from pymodbus.pdu import ExceptionResponse
from pymodbus.pdu.bit_message import (
    ReadCoilsResponse,
    ReadDiscreteInputsResponse,
    WriteSingleCoilResponse,
)
from pymodbus.pdu.register_message import (
    ReadHoldingRegistersResponse,
    ReadInputRegistersResponse,
    WriteMultipleRegistersResponse,
    WriteSingleRegisterResponse,
)

from boneio.modbus.client import VALUE_TYPES
from boneio.modbus.definition import DeviceDefinition

_LOGGER = logging.getLogger(__name__)

ILLEGAL_ADDRESS = 2
START_TEMPERATURE = 20.0

# register_type of a definition block -> device bank name
_BANKS = {"input": "input", "holding": "holding", "coil": "coil", "discrete_input": "discrete"}


def simulator_enabled() -> bool:
    return bool(os.environ.get("BONEIO_DEV")) and bool(os.environ.get("BONEIO_MODBUS_SIM"))


def _start_words(register, value: float) -> list[int]:
    """Raw words that decode to ``value`` once the register's ``multiply`` filters are applied."""
    for f in register.filters:
        if "multiply" in f:
            value /= f["multiply"]
    spec = VALUE_TYPES[register.value_type]
    fmt = spec["byteorder"] + spec["format"]
    raw = value if register.value_type.startswith("FP") else round(value)
    data = struct.pack(fmt, raw)
    return [int.from_bytes(data[i : i + 2], "big") for i in range(0, len(data), 2)]


class SimulatedDevice:
    """Register banks of one simulated slave, laid out by its definition."""

    def __init__(self, definition: DeviceDefinition, missing: set[int] | None = None) -> None:
        self.definition = definition
        self.holding: dict[int, int] = {}
        self.input: dict[int, int] = {}
        self.coil: dict[int, int] = {}
        self.discrete: dict[int, int] = {}
        # Indices of definition blocks that do not answer.
        self.missing: set[int] = missing or set()
        self._writable = {
            "holding": set(),
            "coil": set(),
        }
        for block in definition.registers_base:
            bank = self.bank(block.register_type)
            for address in range(block.base, block.base + block.length):
                bank.setdefault(address, 0)
            if block.register_type in self._writable:
                self._writable[block.register_type].update(range(block.base, block.base + block.length))
            for reg in block.registers:
                if reg.device_class == "temperature":
                    for i, word in enumerate(_start_words(reg, START_TEMPERATURE)):
                        bank[reg.address + i] = word
                write_address = getattr(reg, "write_address", None)
                if write_address is not None and block.register_type in self._writable:
                    self._writable[block.register_type].add(write_address)

    def bank(self, register_type: str) -> dict[int, int]:
        return getattr(self, _BANKS[register_type])

    def block_index(self, register_type: str, address: int) -> int | None:
        for i, b in enumerate(self.definition.registers_base):
            if b.register_type == register_type and b.base <= address < b.base + b.length:
                return i
        return None

    def can_write(self, register_type: str, address: int) -> bool:
        return address in self._writable[register_type]


class SimulatedClient:
    """The subset of ``ModbusSerialClient`` that ``Modbus`` calls."""

    def __init__(self, timeout: float = 1.5) -> None:
        self.connected = True
        self.retries = 2
        self.comm_params = SimpleNamespace(timeout_connect=timeout)
        self._timeout = timeout
        self._missing_profile = os.environ.get("BONEIO_MODBUS_SIM_MISSING", "")
        self._devices: dict[int, SimulatedDevice] = {}
        _LOGGER.warning("Modbus simulator active: no serial port is used")

    def connect(self) -> bool:
        self.connected = True
        return True

    def close(self) -> None:
        self.connected = False

    def add_device(self, slave: int, definition: DeviceDefinition) -> SimulatedDevice:
        missing = (
            {i for i, b in enumerate(definition.registers_base) if b.optional}
            if self._missing_profile
            else set()
        )
        device = self._devices[int(slave)] = SimulatedDevice(definition, missing)
        return device

    def _device(self, device_id: int) -> SimulatedDevice:
        device = self._devices.get(int(device_id))
        if device is None:
            raise ModbusIOException(f"No response received from simulated slave {device_id}")
        return device

    def _read(self, fc: int, register_type: str, response, address: int, count: int, device_id: int):
        device = self._device(device_id)
        indices = [device.block_index(register_type, a) for a in range(address, address + count)]
        if None in indices:
            return ExceptionResponse(fc, ILLEGAL_ADDRESS)
        if device.missing.intersection(indices):
            if self._missing_profile == "timeout":
                time.sleep(self._timeout)
                raise ModbusIOException("No response received (simulated timeout)")
            return ExceptionResponse(fc, ILLEGAL_ADDRESS)
        bank = device.bank(register_type)
        values = [bank.get(a, 0) for a in range(address, address + count)]
        if register_type in ("coil", "discrete_input"):
            # pymodbus pads bits to a whole byte.
            return response(bits=[bool(v) for v in values] + [False] * (-count % 8))
        return response(registers=values)

    def read_input_registers(self, address: int, count: int = 1, device_id: int = 0, **_):
        return self._read(4, "input", ReadInputRegistersResponse, address, count, device_id)

    def read_holding_registers(self, address: int, count: int = 1, device_id: int = 0, **_):
        return self._read(3, "holding", ReadHoldingRegistersResponse, address, count, device_id)

    def read_coils(self, address: int, count: int = 1, device_id: int = 0, **_):
        return self._read(1, "coil", ReadCoilsResponse, address, count, device_id)

    def read_discrete_inputs(self, address: int, count: int = 1, device_id: int = 0, **_):
        return self._read(2, "discrete_input", ReadDiscreteInputsResponse, address, count, device_id)

    def _write(self, fc: int, register_type: str, address: int, values: list[int], device_id: int):
        device = self._device(device_id)
        if not all(device.can_write(register_type, a) for a in range(address, address + len(values))):
            return ExceptionResponse(fc, ILLEGAL_ADDRESS)
        bank = device.bank(register_type)
        for i, v in enumerate(values):
            bank[address + i] = v
        return None

    def write_register(self, address: int, value: int, device_id: int = 0, **_):
        refused = self._write(6, "holding", address, [value & 0xFFFF], device_id)
        return refused or WriteSingleRegisterResponse(address=address, registers=[value & 0xFFFF])

    def write_coil(self, address: int, value: bool, device_id: int = 0, **_):
        refused = self._write(5, "coil", address, [int(bool(value))], device_id)
        return refused or WriteSingleCoilResponse(address=address, bits=[bool(value)])

    def write_registers(self, address: int, values: list[int], device_id: int = 0, **_):
        words = [v & 0xFFFF for v in values]
        refused = self._write(16, "holding", address, words, device_id)
        return refused or WriteMultipleRegistersResponse(address=address, count=len(words))
