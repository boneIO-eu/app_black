"""The Modbus helper names a port it cannot open instead of blaming the device.

With an unplugged USB adapter every read, write and scan fails, and "no
response from device" sends the user to check the device and its address.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from boneio.modbus.client import Modbus
from boneio.webui.routes.modbus import (
    ModbusGetRequest,
    ModbusSetMultipleRequest,
    ModbusSetRequest,
    modbus_get,
    modbus_search_stream,
    modbus_set,
    modbus_set_multiple,
)

PORT = "/dev/ttyUSB7"


def _manager(port_open: bool):
    client = MagicMock(
        port=PORT,
        port_open=port_open,
        read_registers_direct=AsyncMock(return_value=None),
        write_register_direct=AsyncMock(return_value=None),
        write_registers_direct=AsyncMock(return_value=None),
        scan_device=AsyncMock(return_value=False),
    )
    modbus = SimpleNamespace(get_modbus_client=lambda bus=None: client, get_all_coordinators=dict)
    return SimpleNamespace(modbus=modbus)


CALLS = [
    lambda m: modbus_get(ModbusGetRequest(address=1, register_address=0), m),
    lambda m: modbus_set(ModbusSetRequest(address=1, register_address=0, value=4), m),
    lambda m: modbus_set_multiple(ModbusSetMultipleRequest(address=1, register_address=0, values=[4]), m),
]


@pytest.mark.parametrize("call", CALLS)
async def test_a_closed_port_is_named(call):
    result = await call(_manager(port_open=False))
    assert result == {"success": False, "error_key": "port_not_open", "error_params": {"port": PORT}}


@pytest.mark.parametrize("call", CALLS)
async def test_an_open_port_still_blames_the_device(call):
    result = await call(_manager(port_open=True))
    assert result["success"] is False
    assert "no response" in result["error"].lower()


async def _events(manager) -> list[dict]:
    response = await modbus_search_stream(1, 247, 0, "input", 0.1, None, manager)
    return [json.loads(chunk[len("data: "):]) async for chunk in response.body_iterator]


async def test_a_scan_stops_at_once_on_a_closed_port():
    manager = _manager(port_open=False)
    events = await _events(manager)
    assert events[-1] == {"type": "error", "error_key": "port_not_open", "error_params": {"port": PORT}}
    assert manager.modbus.get_modbus_client().scan_device.await_count == 1


def test_port_open_follows_the_serial_client():
    client = Modbus.__new__(Modbus)
    client._port = PORT
    client._client = MagicMock(connected=False)
    assert client.port == PORT
    assert not client.port_open
    client._client.connected = True
    assert client.port_open
    client._client = None
    assert not client.port_open
