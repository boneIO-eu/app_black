"""Modbus coils: read with FC01, written with FC05.

pymodbus returns coil state in ``bits`` and leaves ``registers`` empty, so a
coil block decoded nothing. Relay modules such as the Waveshare 16CH accept
only FC05 for switching, not FC06.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from pymodbus.pdu import ExceptionResponse
from pymodbus.pdu.bit_message import ReadCoilsResponse

from boneio.modbus.client import FailureLog, Modbus
from boneio.modbus.coordinator import ModbusCoordinator


@pytest.fixture
def modbus():
    # Bypass __init__: it opens a serial client and wants an event loop.
    client = Modbus.__new__(Modbus)
    client._uart = {"id": "/dev/ttyS4"}
    client._failures = FailureLog(logging.getLogger("boneio.modbus.client"))
    client._client = MagicMock()
    client._client.connected = True
    return client


def test_coil_read_gives_one_register_per_coil(modbus):
    # pymodbus pads bits to a whole byte.
    bits = [True, False, True] + [False] * 5
    modbus._client.read_coils.return_value = ReadCoilsResponse(bits=bits)

    result = modbus.read_registers_blocking(unit=1, address=0, count=3, method="coil")

    assert result.registers == [1, 0, 1]
    assert modbus.decode_value(result.registers[2:3], "U_WORD") == 1


def test_refused_coil_read_stays_an_exception_response(modbus):
    modbus._client.read_coils.return_value = ExceptionResponse(1, 2)

    result = modbus.read_registers_blocking(unit=1, address=0, count=3, method="coil")

    assert isinstance(result, ExceptionResponse)
    assert result.registers == []


@pytest.mark.parametrize(("value", "state"), [(1, True), (0, False), (255, True)])
def test_coil_write_uses_fc05(modbus, value, state):
    modbus.write_register_blocking(unit=1, address=3, value=value, coil=True)

    modbus._client.write_coil.assert_called_once_with(address=3, value=state, device_id=1)
    modbus._client.write_register.assert_not_called()


def test_register_write_still_uses_fc06(modbus):
    modbus.write_register_blocking(unit=1, address=3, value=7)

    modbus._client.write_register.assert_called_once_with(address=3, value=7, device_id=1)
    modbus._client.write_coil.assert_not_called()


def _coordinator(registers_base: list) -> ModbusCoordinator:
    # Bypass __init__: it loads a device JSON and wires up the manager.
    coordinator = ModbusCoordinator.__new__(ModbusCoordinator)
    coordinator._id = "relays"
    coordinator._name = "Relays"
    coordinator._model = "Relay 16CH"
    coordinator._area = None
    coordinator._has_custom_id = False
    coordinator._address = 1
    coordinator._db = {"registers_base": registers_base}
    coordinator._modbus_entities = []
    coordinator._additional_entities = []
    coordinator._coil_entities = set()
    coordinator._sensors_filters = {}
    coordinator._entity_labels = {}
    coordinator._message_bus = MagicMock()
    coordinator._send_topic = "boneio/modbus/relays"
    coordinator._event_bus = MagicMock()
    coordinator.manager = MagicMock()
    coordinator._modbus = MagicMock()
    coordinator._modbus.write_register = AsyncMock(return_value=MagicMock())
    coordinator.request_update = MagicMock()
    coordinator.__init_modbus_entities__()
    return coordinator


def _relay(address: int) -> dict:
    return {
        "name": f"Relay {address}",
        "address": address,
        "write_address": address,
        "entity_type": "writeable_binary_sensor_discrete",
        "value_type": "U_WORD",
        "payload_on": "1",
        "payload_off": "0",
    }


@pytest.mark.parametrize(("register_type", "coil"), [("coil", True), ("holding", False)])
async def test_coordinator_writes_coil_blocks_with_fc05(register_type, coil):
    coordinator = _coordinator(
        [{"base": 0, "length": 1, "register_type": register_type, "registers": [_relay(0)]}]
    )
    (entity,) = coordinator._modbus_entities[0].values()

    await coordinator.write_register(value=1, entity=entity)

    coordinator._modbus.write_register.assert_awaited_once_with(
        unit=1, address=0, value=1, coil=coil
    )


def test_waveshare_16ch_relays_are_coils():
    path = Path(__file__).parents[3] / "boneio/modbus/devices/other/waveshare-16ch.json"
    coordinator = _coordinator(json.loads(path.read_text())["registers_base"])

    entities = list(coordinator._modbus_entities[0].values())
    assert len(entities) == 16
    assert set(entities) == coordinator._coil_entities
    assert [e.write_address for e in entities] == list(range(16))
