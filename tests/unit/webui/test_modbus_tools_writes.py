"""Tools writes: raw register writes from the panel's Modbus helper.

A value that does not fit one register is refused before the bus, with a
reason the helper can show.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from boneio.webui.routes.modbus import ModbusSetRequest, modbus_set


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
