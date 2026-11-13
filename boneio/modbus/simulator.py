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
import math
import os
import random
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
from boneio.modbus.heat_pump import ROLE_KINDS, SCHEMES

_LOGGER = logging.getLogger(__name__)

ILLEGAL_ADDRESS = 2
START_TEMPERATURE = 20.0
NOISE_K = 0.1  # sensor noise of devices without a heat pump model
MAX_STEP_S = 60.0  # one read advances the model by at most this much
SUPPLY_TAU_S = 600.0  # supply water approaches its setpoint
IDLE_TAU_S = 1800.0  # supply water relaxes to room temperature with the compressor off
COMPRESSOR_ON_K = 2.0  # compressor starts above this distance from the setpoint
COMPRESSOR_OFF_K = 0.5  # and stops below this one
CIRCUIT_DELTA_K = 5.0  # supply/return spread with the compressor running
IDLE_DELTA_K = 0.5
DHW_HEAT_K_PER_S = 1.0 / 60
DHW_LOSS_K_PER_S = 0.1 / 60
OUTDOOR_MEAN = 2.0
OUTDOOR_SWING_K = 3.0
OUTDOOR_PERIOD_S = 6 * 3600.0
DEFROST_BELOW_OUTDOOR = 3.0
DEFROST_EVERY_S = 40 * 60.0
DEFROST_DURATION_S = 60.0
AUTO_HEATS_BELOW_OUTDOOR = 15.0  # LG "auto" heats below this outdoor temperature, else idles
# Phnix operating_state values: 0 cooling, 1 heating, 2 defrost, 4 hot water.
PHNIX_STATE_COOLING, PHNIX_STATE_HEATING, PHNIX_STATE_DEFROST, PHNIX_STATE_HOT_WATER = 0, 1, 2, 4
# Phnix reports the state of its mode, not compressor activity: raw mode -> operating_state.
PHNIX_STATE_BY_MODE = {0: PHNIX_STATE_HOT_WATER, 1: PHNIX_STATE_HEATING, 2: PHNIX_STATE_COOLING, 3: PHNIX_STATE_HEATING, 4: PHNIX_STATE_COOLING}
DHW_RESUME_BELOW_K = 1.0  # DHW heating stops at the target and resumes this far below it
# LG outdoor unit cycle: 0 stop, 1 cooling, 2 heating.

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


def _decode(register, words: list[int]) -> float:
    """Inverse of :func:`_start_words`."""
    spec = VALUE_TYPES[register.value_type]
    data = b"".join(w.to_bytes(2, "big") for w in words)
    value = struct.unpack(spec["byteorder"] + spec["format"], data)[0]
    for f in register.filters:
        if "multiply" in f:
            value *= f["multiply"]
    return value


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
        self._noisy: list = []
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
                elif reg.device_class == "temperature" and block.register_type in ("input", "holding"):
                    self._noisy.append((bank, reg))
        self._elapsed = 0.0
        self.last_step = time.monotonic()
        self._roles = self._resolve_roles()
        # Physical state in full precision; the banks only hold it rounded.
        self._supply = self._dhw = START_TEMPERATURE
        self._circuit_on = self._defrosting = self._dhw_on = False
        self._since_defrost = self._defrost_left = 0.0
        if self._roles:
            self.step(0)

    def _resolve_roles(self) -> dict[str, tuple[dict[int, int], object]]:
        """Heat pump role -> (bank, register); a switch role resolves to its source register."""
        spec = self.definition.heat_pump
        if spec is None:
            return {}
        registers = {
            r.decoded_name: (self.bank(b.register_type), r)
            for b in self.definition.registers_base
            for r in b.registers
        }
        switches = {
            a.name.replace(" ", "").lower(): a.source
            for a in self.definition.additional_entities
            if a.entity_type == "switch"
        }
        self._power_state = registers.get("powerstate")
        roles = {}
        for role, ref in spec.roles.items():
            key = (ref if isinstance(ref, str) else ref[0]).replace(" ", "").lower()
            if ROLE_KINDS[role] == "switch":
                source = switches[key]
                key = (source if isinstance(source, str) else source[0]).replace(" ", "").lower()
            if key in registers:
                roles[role] = registers[key]
        return roles

    def _get(self, role: str) -> float | None:
        entry = self._roles.get(role)
        if entry is None:
            return None
        bank, reg = entry
        return _decode(reg, [bank[reg.address + i] for i in range(len(_start_words(reg, 0)))])

    def _put(self, role: str, value: float) -> None:
        """Write a measured value or status bit; unmapped roles are skipped."""
        entry = self._roles.get(role)
        if entry is not None:
            bank, reg = entry
            for i, word in enumerate(_start_words(reg, value)):
                bank[reg.address + i] = word

    def _role_values(self) -> dict[str, object]:
        """Role values as the heat pump schemes read them."""
        values = {}
        for role in self._roles:
            v = self._get(role)
            values[role] = ("ON" if v else "OFF") if ROLE_KINDS[role] == "switch" else v
        return values

    def step(self, dt: float) -> None:
        """Advance the model by ``dt`` seconds; the app's writes are inputs, never overwritten."""
        if not self._roles:
            for bank, reg in self._noisy:
                value = START_TEMPERATURE + random.uniform(-NOISE_K, NOISE_K)
                for i, word in enumerate(_start_words(reg, value)):
                    bank[reg.address + i] = word
            return
        self._elapsed += dt
        scheme = SCHEMES[self.definition.heat_pump.scheme]
        outdoor = OUTDOOR_MEAN + OUTDOOR_SWING_K * math.sin(2 * math.pi * self._elapsed / OUTDOOR_PERIOD_S)
        v = self._role_values()
        mode = scheme.hvac_mode(v)
        if mode == "auto":
            mode = "heat" if outdoor < AUTO_HEATS_BELOW_OUTDOOR else "off"
        target = scheme.target(v)
        active = mode in ("heat", "cool") and target is not None
        sign = -1 if mode == "cool" else 1

        distance = sign * (target - self._supply) if active else 0.0
        if not active or distance < COMPRESSOR_OFF_K:
            self._circuit_on = False
        elif distance > COMPRESSOR_ON_K:
            self._circuit_on = True

        dhw_target = v.get("dhw_target")
        dhw_wanted = scheme.dhw_mode(v) == "heat_pump" and dhw_target is not None
        if not dhw_wanted or self._dhw >= dhw_target:
            self._dhw_on = False
        elif self._dhw < dhw_target - DHW_RESUME_BELOW_K:
            self._dhw_on = True
        dhw_heating = self._dhw_on
        running = self._circuit_on or dhw_heating

        # Compressor running time accumulates toward a defrost in the cold.
        if self._defrosting:
            self._defrost_left -= dt
            self._defrosting = self._defrost_left > 0
        elif running and mode == "heat" and outdoor < DEFROST_BELOW_OUTDOOR:
            self._since_defrost += dt
            if self._since_defrost >= DEFROST_EVERY_S:
                self._since_defrost = 0.0
                self._defrosting, self._defrost_left = True, DEFROST_DURATION_S

        if self._circuit_on and not self._defrosting:
            self._supply += (target - self._supply) * (1 - math.exp(-dt / SUPPLY_TAU_S))
        else:
            self._supply += (START_TEMPERATURE - self._supply) * (1 - math.exp(-dt / IDLE_TAU_S))
        if dhw_heating:
            self._dhw = min(self._dhw + DHW_HEAT_K_PER_S * dt, dhw_target)
        else:
            self._dhw = max(self._dhw - DHW_LOSS_K_PER_S * dt, START_TEMPERATURE)

        delta = CIRCUIT_DELTA_K if self._circuit_on else IDLE_DELTA_K
        self._put("supply", self._supply)
        self._put("return", self._supply - sign * delta)
        self._put("dhw_current", self._dhw)
        self._put("outdoor", outdoor)
        self._put("compressor", running)
        self._put("defrost", self._defrosting)
        self._put("dhw_heating", dhw_heating)
        if self._defrosting or self._circuit_on or dhw_heating:
            lg_cycle = 1 if self._circuit_on and mode == "cool" else 2
        else:
            lg_cycle = 0
        self._put("outdoor_cycle", lg_cycle)
        raw_mode = v.get("mode")
        if raw_mode is not None:
            state = PHNIX_STATE_DEFROST if self._defrosting else PHNIX_STATE_BY_MODE.get(int(raw_mode))
            if state is not None:
                self._put("operating_state", state)
        if self._power_state is not None:
            bank, reg = self._power_state
            bank[reg.address] = int(v.get("power") == "ON")

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
        now = time.monotonic()
        device.step(min(now - device.last_step, MAX_STEP_S))
        device.last_step = now
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
