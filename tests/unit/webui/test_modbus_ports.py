"""Serial port list and bus choice in the Modbus helper routes."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from boneio.modbus.ports import list_serial_ports
from boneio.webui.routes.modbus import (
    ModbusConfigureDeviceRequest,
    ModbusGetRequest,
    modbus_get,
    modbus_ports,
)


def test_list_ports_reads_by_id(tmp_path):
    (tmp_path / "usb-FTDI_FT232R_USB_UART_A10K1234-if00-port0").symlink_to("/dev/null")
    ports = list_serial_ports(["uart4"], by_id_dir=str(tmp_path))
    assert {"port": "uart4", "label": "RS485 (uart4)", "kind": "builtin"} in ports
    usb = [p for p in ports if p["kind"] == "usb"]
    assert usb == [
        {
            "port": f"{tmp_path}/usb-FTDI_FT232R_USB_UART_A10K1234-if00-port0",
            "label": "FTDI_FT232R_USB_UART_A10K1234",
            "kind": "usb",
        }
    ]


def test_list_ports_without_by_id_dir(tmp_path):
    ports = list_serial_ports(["uart1", "/dev/ttyUSB0"], by_id_dir=str(tmp_path / "none"))
    assert [p["port"] for p in ports] == ["uart4", "uart1"]
    assert {p["kind"] for p in ports} == {"builtin"}


def _manager():
    clients = {
        n: MagicMock(read_registers_direct=AsyncMock(return_value=None)) for n in ("a", "b")
    }
    modbus = SimpleNamespace(
        get_modbus_client=lambda bus=None: clients[bus or "a"] if (bus or "a") in clients else None,
        bus_ids=lambda: ["a", "b"],
        bus_ports=lambda: ["uart4", "uart1"],
    )
    return SimpleNamespace(modbus=modbus), clients


async def test_get_uses_requested_bus():
    manager, clients = _manager()

    await modbus_get(ModbusGetRequest(address=1, register_address=0, bus="b"), manager)

    clients["b"].read_registers_direct.assert_awaited_once()
    clients["a"].read_registers_direct.assert_not_awaited()


async def test_unknown_bus_is_404():
    manager, _ = _manager()

    with pytest.raises(HTTPException) as err:
        await modbus_get(ModbusGetRequest(address=1, register_address=0, bus="x"), manager)

    assert err.value.status_code == 404
    assert err.value.detail == "Unknown Modbus bus: x"


async def test_ports_route_lists_ports_and_buses():
    manager, _ = _manager()

    result = await modbus_ports(manager)

    assert result["buses"] == ["a", "b"]
    assert [p["port"] for p in result["ports"] if p["kind"] == "builtin"] == ["uart4", "uart1"]


def test_configure_device_ignores_legacy_uart_field():
    request = ModbusConfigureDeviceRequest(
        device="x", uart="uart4", current_address=1, current_baudrate=9600
    )
    assert request.bus is None


def test_used_addresses_name_each_device_bus():
    from boneio.webui.routes.modbus import get_used_addresses

    manager = MagicMock()
    manager.config_helper.get_config.return_value = {
        "modbus": [{"id": "a", "port": "uart4"}, {"id": "b", "port": "/dev/ttyUSB0"}],
        "modbus_devices": [
            {"address": 1, "model": "sdm630"},
            {"address": 1, "model": "sdm630", "id": "pump", "bus": "b"},
        ],
    }
    result = asyncio.run(get_used_addresses(manager))
    assert [(u["bus"], u["address"]) for u in result["used_addresses"]] == [("a", 1), ("b", 1)]


def test_used_addresses_without_buses_name_none():
    from boneio.webui.routes.modbus import get_used_addresses

    manager = MagicMock()
    manager.config_helper.get_config.return_value = {"modbus_devices": [{"address": 3, "model": "sdm630"}]}
    assert asyncio.run(get_used_addresses(manager))["used_addresses"][0]["bus"] is None
