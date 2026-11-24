"""Saving Modbus buses or devices cannot lose or move a device."""

from __future__ import annotations

import pytest

from boneio.webui.routes import config_core

A = {"id": "a", "port": "uart4"}
B = {"id": "b", "port": "uart2"}
DEV = {"id": "meter", "address": 1, "model": "x"}


@pytest.fixture
def stored(monkeypatch):
    """Set what the app holds per section; None means it cannot be read."""
    sections: dict = {}

    async def fake(section):
        return sections.get(section)

    monkeypatch.setattr(config_core, "_stored_section", fake)
    return sections


async def test_device_with_unknown_bus_refused(stored):
    stored["modbus"] = [A]
    errors = await config_core._section_errors("modbus_devices", [{**DEV, "bus": "zzz"}])
    assert any("meter" in e and "zzz" in e for e in errors)


async def test_device_naming_bus_with_no_buses_refused(stored):
    stored["modbus"] = []
    assert await config_core._section_errors("modbus_devices", [{**DEV, "bus": "a"}])
    assert not await config_core._section_errors("modbus_devices", [DEV])


async def test_delete_used_bus_refused(stored):
    stored["modbus"] = [A, B]
    stored["modbus_devices"] = [{**DEV, "bus": "b"}]
    errors = await config_core._section_errors("modbus", [A])
    assert any("meter" in e for e in errors)


async def test_rename_used_bus_refused(stored):
    stored["modbus"] = [A]
    stored["modbus_devices"] = [DEV]
    assert await config_core._section_errors("modbus", [{**A, "id": "renamed"}])


async def test_reorder_that_moves_implicit_devices_refused(stored):
    stored["modbus"] = [A, B]
    stored["modbus_devices"] = [DEV]
    errors = await config_core._section_errors("modbus", [B, A])
    assert any("meter" in e for e in errors)


async def test_add_second_bus_allowed(stored):
    stored["modbus"] = [A]
    stored["modbus_devices"] = [DEV]
    assert await config_core._section_errors("modbus", [A, B]) == []


async def test_unreadable_stored_section_skips_check(stored):
    assert await config_core._section_errors("modbus_devices", [{**DEV, "bus": "zzz"}]) == []
    stored["modbus"] = [A]
    assert await config_core._section_errors("modbus", [B]) == []


async def test_malformed_entries_do_not_crash(stored):
    stored["modbus"] = [A, "junk", {"port": "x"}]
    stored["modbus_devices"] = [DEV, None]
    assert await config_core._section_errors("modbus_devices", [None, "x", {"bus": "q"}]) == [
        "Modbus device '_' is on bus 'q', which is not configured."
    ]
    assert await config_core._section_errors("modbus", ["junk", {"id": None}, A]) == []
