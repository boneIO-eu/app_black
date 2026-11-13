"""Tools writes: raw register writes from the panel's Modbus helper.

A value that does not fit one register, or a write to the unit of a device
configured read only, is refused before the bus, with a reason the helper
can show.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from boneio.webui.routes.modbus import (
    ModbusSetMultipleRequest,
    ModbusSetRequest,
    modbus_set,
    modbus_set_multiple,
)


def _manager(coordinators=None):
    client = MagicMock(write_register_direct=AsyncMock(return_value=MagicMock()))
    modbus = SimpleNamespace(
        get_modbus_client=lambda: client,
        get_all_coordinators=lambda: coordinators or {},
    )
    return SimpleNamespace(modbus=modbus), client


@pytest.mark.parametrize("value", [70000, -40000])
async def test_a_value_wider_than_a_register_is_refused(value):
    manager, client = _manager()

    with pytest.raises(HTTPException) as err:
        await modbus_set(ModbusSetRequest(address=1, register_address=0, value=value), manager)

    assert err.value.status_code == 400
    assert "-32768..65535" in err.value.detail
    client.write_register_direct.assert_not_awaited()
    client.suspend.assert_not_called()


async def test_a_negative_value_in_range_is_written():
    manager, client = _manager()

    result = await modbus_set(ModbusSetRequest(address=1, register_address=0, value=-3), manager)

    assert result["success"]
    client.write_register_direct.assert_awaited_once_with(unit=1, address=0, value=-3, coil=False)


async def test_a_coil_takes_any_value():
    manager, client = _manager()

    await modbus_set(ModbusSetRequest(address=1, register_address=0, value=70000, register_type="coil"), manager)

    client.write_register_direct.assert_awaited_once()


def _pump(read_only, address="1"):
    return SimpleNamespace(read_only=read_only, address=address, name="LG")


@pytest.mark.parametrize(
    "write",
    [
        lambda m: modbus_set(ModbusSetRequest(address=1, register_address=0, value=4), m),
        lambda m: modbus_set(ModbusSetRequest(address=1, register_address=0, value=1, register_type="coil"), m),
        lambda m: modbus_set_multiple(ModbusSetMultipleRequest(address=1, register_address=0, values=[4]), m),
    ],
)
async def test_a_read_only_device_takes_no_raw_write(write):
    manager, client = _manager({"lg": _pump(read_only=True)})

    with pytest.raises(HTTPException) as err:
        await write(manager)

    assert err.value.status_code == 400
    assert "LG" in err.value.detail and "read only" in err.value.detail
    client.write_register_direct.assert_not_awaited()
    client.write_registers_direct.assert_not_called()
    client.suspend.assert_not_called()


@pytest.mark.parametrize("pump", [_pump(read_only=False), _pump(read_only=True, address=2)])
async def test_other_units_and_writeable_devices_still_take_raw_writes(pump):
    manager, client = _manager({"lg": pump})

    result = await modbus_set(ModbusSetRequest(address=1, register_address=0, value=4), manager)

    assert result["success"]
    client.write_register_direct.assert_awaited_once()
