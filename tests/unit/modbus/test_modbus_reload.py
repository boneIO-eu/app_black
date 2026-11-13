"""A reload builds a Modbus device again whenever its coordinator config changed.

Read only, visibility, model and interval are taken when the coordinator is
built, so a change to any of them must give a new coordinator, and the old
one must stop polling so it never announces its entities again.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from boneio.core.config.config_helper import ConfigHelper
from boneio.core.manager.modbus import ModbusManager
from boneio.core.utils.timeperiod import TimePeriod

SETPOINT_TOPIC = "homeassistant/number/blk0001/lg_heatingsetpoint/config"


def _modbus_manager(devices: list[dict]) -> tuple[ModbusManager, dict]:
    helper = ConfigHelper(name="black", serial_override="blk0001")
    config = {"modbus_devices": devices}
    helper.get_config = lambda: config
    manager = MagicMock(config_helper=helper, _config_helper=helper)
    modbus = ModbusManager.__new__(ModbusManager)
    modbus._manager = manager
    modbus._modbus = MagicMock(read_and_decode=AsyncMock(return_value=None))
    modbus._coordinator_built_from = {}
    modbus._modbus_coordinators = modbus._configure_modbus_coordinators(devices)
    return modbus, config


@pytest.fixture(autouse=True)
def _no_wait(monkeypatch):
    monkeypatch.setattr("boneio.core.manager.modbus.asyncio.sleep", AsyncMock())


async def test_turning_read_only_on_rebuilds_the_device_without_controls():
    modbus, config = _modbus_manager(
        [{"address": 1, "model": "lg-therma-v-r290", "id": "lg", "update_interval": TimePeriod(seconds=30)}]
    )
    old = modbus.get_coordinator("lg")
    old._send_discovery_for_all_registers()
    assert SETPOINT_TOPIC in {topic for _, topic in old.discovery_topics()}

    config["modbus_devices"] = [{"address": 1, "model": "lg-therma-v-r290", "id": "lg", "read_only": True}]
    await modbus.reload_modbus_devices()

    new = modbus.get_coordinator("lg")
    assert new is not old
    assert old._stopped
    removed = [
        c.kwargs["topic"] for c in modbus._manager.send_message.call_args_list if c.kwargs["payload"] is None
    ]
    assert SETPOINT_TOPIC in removed
    assert new._read_only
    assert SETPOINT_TOPIC not in {e.discovery_topic for e in new._announced_entities()}
    assert not any(e.entity_type in ("numeric", "select", "switch", "button") for e in new._announced_entities())


@pytest.mark.parametrize(
    "change",
    [
        {"entity_visibility": {"heatingsetpoint": {"ha": False}}},
        {"update_interval": "10s"},
        {"address": 2},
    ],
)
async def test_any_coordinator_setting_rebuilds_the_device(change):
    device = {"address": 1, "model": "lg-therma-v-r290", "id": "lg"}
    modbus, config = _modbus_manager([device])
    old = modbus.get_coordinator("lg")

    config["modbus_devices"] = [{**device, **change}]
    await modbus.reload_modbus_devices()

    assert modbus.get_coordinator("lg") is not old
    assert old._stopped


async def test_the_same_file_after_start_keeps_the_device():
    # At startup the config is validated, defaults filled in; a reload reads raw YAML.
    validated = {"address": 1, "model": "lg-therma-v-r290", "update_interval": TimePeriod(seconds=30), "read_only": False}
    modbus, config = _modbus_manager([validated])
    old = modbus.get_coordinator("1_lg-therma-v-r290")

    config["modbus_devices"] = [
        {"address": 1, "model": "lg-therma-v-r290", "update_interval": "30s", "entity_labels": {"dhw": "Water"}}
    ]
    await modbus.reload_modbus_devices()

    assert modbus.get_coordinator("1_lg-therma-v-r290") is old
    assert not old._stopped


async def test_a_device_from_a_reload_polls_at_its_interval():
    modbus, _ = _modbus_manager([{"address": 1, "model": "lg-therma-v-r290", "update_interval": "10s"}])

    assert modbus.get_coordinator("1_lg-therma-v-r290")._update_interval == TimePeriod(seconds=10)


async def test_a_stopped_updater_returns():
    modbus, _ = _modbus_manager([{"address": 1, "model": "lg-therma-v-r290"}])
    coordinator = modbus.get_coordinator("1_lg-therma-v-r290")
    coordinator.async_update = AsyncMock(return_value=3600)

    coordinator.stop_updates()

    await coordinator._refresh()  # returns instead of sleeping for an hour
    coordinator.async_update.assert_not_awaited()


def test_entity_labels_alone_are_not_a_rebuild():
    modbus, _ = _modbus_manager([])
    device = {"address": 1, "model": "lg-therma-v-r290"}

    assert modbus._coordinator_inputs(device) == modbus._coordinator_inputs({**device, "entity_labels": {"dhw": "x"}})


def test_manager_config_is_not_shared_with_the_snapshot():
    device = {"address": 1, "model": "lg-therma-v-r290", "entity_visibility": {"dhw": {"ha": False}}}
    modbus, _ = _modbus_manager([device])

    device["entity_visibility"]["dhw"]["ha"] = True

    assert modbus._coordinator_built_from["1_lg-therma-v-r290"]["entity_visibility"] == {"dhw": {"ha": False}}



def _as_at_startup(devices: list[dict]) -> list[dict]:
    from boneio.core.config.yaml_util import normalize_section

    return normalize_section("modbus_devices", devices)


@pytest.mark.parametrize(
    "raw",
    [
        # Startup reads a bare number as milliseconds.
        {"address": 1, "model": "lg-therma-v-r290", "update_interval": 30000},
        # Startup lowercases the model; the device file is lowercase.
        {"address": 1, "model": "LG-Therma-V-R290", "id": "lg"},
        # Startup turns lengths with units into metres for the formula.
        {"address": 3, "model": "liquid-sensor", "data": {"width": "50cm", "length": "1m"}},
    ],
)
async def test_a_reload_of_the_unchanged_file_reads_it_as_startup_did(raw):
    modbus, config = _modbus_manager(_as_at_startup([raw]))
    (device_id, old), = modbus._modbus_coordinators.items()

    config["modbus_devices"] = [raw]
    await modbus.reload_modbus_devices()

    assert modbus.get_coordinator(device_id) is old
    assert not old._stopped


async def test_a_device_added_by_a_reload_gets_startup_values():
    modbus, config = _modbus_manager([])

    config["modbus_devices"] = [
        {"address": 3, "model": "Liquid-Sensor", "update_interval": 30000, "data": {"width": "50cm", "length": "1m"}}
    ]
    await modbus.reload_modbus_devices()

    (coordinator,) = modbus._modbus_coordinators.values()
    assert coordinator._update_interval == TimePeriod(milliseconds=30000)
    assert coordinator._additional_data == {"width": 0.5, "length": 1.0}
