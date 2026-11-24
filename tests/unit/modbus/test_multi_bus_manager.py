"""Each Modbus bus has its own client, and each device polls on its own bus."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from boneio.core.config.config_helper import ConfigHelper
from boneio.core.manager.modbus import ModbusManager
from boneio.modbus.client import Modbus

BUSES = [{"id": "a", "port": "uart4"}, {"id": "b", "port": "/dev/serial/by-id/usb-FTDI-if00"}]
LG = {"address": 1, "model": "lg-therma-v-r290", "id": "lg"}
SDM = {"address": 2, "model": "sdm120", "id": "sdm"}


@pytest.fixture
def sim(monkeypatch):
    monkeypatch.setenv("BONEIO_DEV", "1")
    monkeypatch.setenv("BONEIO_MODBUS_SIM", "1")


@pytest.fixture(autouse=True)
def _no_wait(monkeypatch):
    monkeypatch.setattr("boneio.core.manager.modbus.asyncio.sleep", AsyncMock())


def _manager(buses: list[dict], devices: list[dict]) -> tuple[ModbusManager, dict]:
    helper = ConfigHelper(name="black", serial_override="blk0001")
    config = {"modbus": buses, "modbus_devices": devices}
    helper.get_config = lambda: config
    parent = MagicMock(config_helper=helper, _config_helper=helper)
    return ModbusManager(manager=parent, modbus_config=buses, modbus_devices=devices), config


async def test_devices_land_on_their_bus(sim):
    modbus, _ = _manager(BUSES, [LG, {**SDM, "bus": "b"}])

    assert modbus.bus_ids() == ["a", "b"]
    assert modbus.get_coordinator("sdm")._modbus is modbus.get_modbus_client("b")
    assert modbus.get_coordinator("lg")._modbus is modbus.get_modbus_client("a")
    assert modbus.get_modbus_client("a") is not modbus.get_modbus_client("b")


async def test_device_without_bus_uses_first(sim):
    modbus, _ = _manager(BUSES, [SDM])

    assert modbus.get_coordinator("sdm")._modbus is modbus.get_modbus_client("a")


async def test_same_address_on_two_buses_is_simulated_on_each(sim):
    modbus, _ = _manager(BUSES, [{**SDM, "address": 1}, {**LG, "bus": "b"}])

    on_a = modbus.get_modbus_client("a").client._devices[1].definition
    on_b = modbus.get_modbus_client("b").client._devices[1].definition
    assert on_a.model != on_b.model


async def test_unknown_bus_device_skipped_at_start(sim, caplog):
    caplog.set_level(logging.ERROR)
    modbus, _ = _manager(BUSES, [{**LG, "bus": "nope"}, SDM])

    assert set(modbus.get_all_coordinators()) == {"sdm"}
    (record,) = [r for r in caplog.records if "lg" in r.getMessage()]
    assert record.levelno == logging.ERROR
    assert "nope" in record.getMessage()


async def test_duplicate_device_id_skipped_at_start(sim, caplog):
    caplog.set_level(logging.ERROR)
    modbus, _ = _manager(BUSES, [LG, {**SDM, "id": "lg", "bus": "b"}])

    assert modbus.get_coordinator("lg")._address == 1
    assert modbus.get_coordinator("lg")._modbus is modbus.get_modbus_client("a")
    (record,) = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert "lg" in record.getMessage()


async def test_missing_usb_port_does_not_stop_other_bus(monkeypatch):
    monkeypatch.delenv("BONEIO_DEV", raising=False)
    monkeypatch.delenv("BONEIO_MODBUS_SIM", raising=False)
    buses = [{"id": "a", "port": "uart4"}, {"id": "b", "port": "/dev/serial/by-id/nie-ma"}]

    modbus, _ = _manager(buses, [LG, {**SDM, "bus": "b"}])

    assert modbus.bus_ids() == ["a", "b"]
    assert modbus.get_coordinator("lg")._modbus is modbus.get_modbus_client("a")
    assert modbus.get_modbus_client("a").client.comm_params.host == "/dev/ttyS4"
    assert modbus.get_modbus_client("b").client.comm_params.host == "/dev/serial/by-id/nie-ma"


async def test_a_bus_that_fails_to_build_leaves_the_others(sim, monkeypatch, caplog):
    real = Modbus.__init__

    def init(self, port, **kwargs):
        if port.endswith("if00"):
            raise OSError("no such device")
        real(self, port, **kwargs)

    monkeypatch.setattr(Modbus, "__init__", init)
    modbus, _ = _manager(BUSES, [LG, {**SDM, "bus": "b"}])

    assert modbus.bus_ids() == ["a"]
    assert set(modbus.get_all_coordinators()) == {"lg"}
    assert any("usb-FTDI" in r.getMessage() and r.levelno == logging.ERROR for r in caplog.records)


async def test_reload_moves_device_between_buses(sim):
    modbus, config = _manager(BUSES, [LG])
    old = modbus.get_coordinator("lg")

    config["modbus_devices"] = [{**LG, "bus": "b"}]
    await modbus.reload_modbus_devices()

    new = modbus.get_coordinator("lg")
    assert new is not old
    assert old._stopped
    assert new._modbus is modbus.get_modbus_client("b")
    assert list(modbus.get_all_coordinators()) == ["lg"]


async def test_reload_naming_the_first_bus_keeps_the_device(sim):
    modbus, config = _manager(BUSES, [LG])
    old = modbus.get_coordinator("lg")
    assert old is not None

    config["modbus_devices"] = [{**LG, "bus": "a"}]
    await modbus.reload_modbus_devices()

    assert modbus.get_coordinator("lg") is old


async def test_reload_of_a_duplicate_keeps_the_first(sim):
    devices = [LG, {**SDM, "id": "lg"}]
    modbus, _ = _manager(BUSES, devices)
    old = modbus.get_coordinator("lg")
    assert old._address == 1

    await modbus.reload_modbus_devices()

    assert modbus.get_coordinator("lg") is old


async def test_get_modbus_client_default_and_unknown(sim):
    modbus, _ = _manager(BUSES, [])

    assert modbus.get_modbus_client() is modbus.get_modbus_client("a")
    assert modbus.get_modbus_client("nope") is None


async def test_devices_without_buses_warns(caplog):
    caplog.set_level(logging.WARNING)
    modbus, _ = _manager([], [LG])

    assert modbus.get_all_coordinators() == {}
    assert modbus.get_modbus_client() is None
    assert modbus.bus_ids() == []
    assert any(r.levelno == logging.WARNING and "bus" in r.getMessage() for r in caplog.records)


async def test_duplicate_device_ids_load_and_start_with_one(sim, caplog):
    """Start-up lets two devices with one id through; the manager keeps the first."""
    from boneio.core.config import models
    from boneio.core.config.yaml_util import load_config_from_string

    twins = [{"address": 1, "model": "sdm630"}, {"address": 1, "model": "sdm630"}]
    assert models.validate("modbus_devices", twins)
    config = load_config_from_string(
        "boneio:\n  name: test\nmodbus:\n  - id: a\n    port: uart4\n"
        "modbus_devices:\n  - {address: 1, model: sdm630}\n  - {address: 1, model: sdm630}\n"
    )
    assert len(config["modbus_devices"]) == 2

    caplog.set_level(logging.ERROR)
    modbus, _ = _manager(config["modbus"], config["modbus_devices"])

    assert list(modbus.get_all_coordinators()) == ["1_sdm630"]
    assert any("1_sdm630" in r.getMessage() and "skipped" in r.getMessage() for r in caplog.records)
