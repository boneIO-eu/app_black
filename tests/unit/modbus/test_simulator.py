"""The simulated client behind the real ``Modbus`` wrapper and coordinator."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest
from pymodbus.pdu import ExceptionResponse

from boneio.modbus.client import Modbus
from boneio.modbus.coordinator import ModbusCoordinator
from boneio.modbus.definition import load_definition
from boneio.modbus.simulator import SimulatedClient, simulator_enabled
from tests.unit.modbus.definitions import definition

LG = "lg-therma-v-r290"
UART = {"id": "/dev/sim", "rx": "x", "tx": "y"}


@pytest.fixture
def sim(monkeypatch):
    monkeypatch.setenv("BONEIO_DEV", "1")
    monkeypatch.setenv("BONEIO_MODBUS_SIM", "1")


def _modbus(timeout: float = 0.1) -> Modbus:
    modbus = Modbus(uart=UART, timeout=timeout, inter_device_delay=0)
    assert isinstance(modbus.client, SimulatedClient)
    return modbus


def test_simulator_off_without_boneio_dev(monkeypatch):
    monkeypatch.delenv("BONEIO_DEV", raising=False)
    monkeypatch.setenv("BONEIO_MODBUS_SIM", "1")
    assert simulator_enabled() is False


def test_write_then_read_returns_written_value(sim):
    modbus = _modbus()
    modbus.client.add_device(
        3,
        definition(
            [
                {"base": 0, "length": 2, "register_type": "holding", "registers": []},
                {"base": 0, "length": 2, "register_type": "coil", "registers": []},
            ]
        ),
    )

    assert modbus.write_register_blocking(unit=3, address=1, value=-5) is not None
    assert modbus.read_registers_blocking(unit=3, address=0, count=2, method="holding").registers == [0, 0xFFFB]
    assert modbus.write_registers_blocking(unit=3, address=0, values=[7, 8]) is not None
    assert modbus.read_registers_blocking(unit=3, address=0, count=2, method="holding").registers == [7, 8]

    assert modbus.write_register_blocking(unit=3, address=1, value=1, coil=True) is not None
    assert modbus.read_registers_blocking(unit=3, address=0, count=2, method="coil").registers == [0, 1]


def test_address_outside_blocks_is_refused(sim):
    modbus = _modbus()
    modbus.client.add_device(1, load_definition(LG))

    # LG input register 15 is deliberately not covered by any block.
    result = modbus.read_registers_blocking(unit=1, address=15, count=1, method="input")
    assert isinstance(result, ExceptionResponse)
    assert result.exception_code == 2
    assert modbus.write_register_blocking(unit=1, address=999, value=1) is None


def test_unknown_slave_gives_no_response(sim):
    modbus = _modbus()
    assert modbus.read_registers_blocking(unit=9, address=0, count=1, method="input") is None


def test_missing_timeout_profile_times_out_optional_blocks(sim, monkeypatch):
    monkeypatch.setenv("BONEIO_MODBUS_SIM_MISSING", "timeout")
    modbus = _modbus(timeout=0.2)
    d = load_definition(LG)
    modbus.client.add_device(1, d)
    optional = next(b for b in d.registers_base if b.optional and b.register_type == "input")
    required = next(b for b in d.registers_base if not b.optional and b.register_type == "input")

    start = time.perf_counter()
    assert modbus.read_registers_blocking(unit=1, address=optional.base, count=1, method="input") is None
    assert time.perf_counter() - start >= 0.2
    assert modbus.read_registers_blocking(unit=1, address=required.base, count=1, method="input").registers


def test_missing_exception_profile_refuses_optional_blocks(sim, monkeypatch):
    monkeypatch.setenv("BONEIO_MODBUS_SIM_MISSING", "exception")
    modbus = _modbus()
    d = load_definition(LG)
    modbus.client.add_device(1, d)
    optional = next(b for b in d.registers_base if b.optional and b.register_type == "input")

    result = modbus.read_registers_blocking(unit=1, address=optional.base, count=1, method="input")
    assert isinstance(result, ExceptionResponse)


async def test_coordinator_polls_lg_through_simulator(sim):
    modbus = _modbus()
    manager = MagicMock()
    manager.config_helper.topic_prefix = "boneio"
    coordinator = ModbusCoordinator(
        modbus=modbus, address="1", model=LG, sensors_filters={}, manager=manager, id="lg", name="LG"
    )
    modbus.client.add_device(1, coordinator._definition)

    await coordinator.async_update(timestamp=1.0)

    entity = coordinator.get_entity_by_name("watersupplytemperature")
    assert entity.state == pytest.approx(20.0)
