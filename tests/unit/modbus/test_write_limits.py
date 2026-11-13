"""A setpoint outside the manufacturer's range never reaches the bus.

Whatever the source (Home Assistant over MQTT, the panel, other API), a write
goes through ModbusCoordinator.write_register, which refuses out-of-range
values and every write to a read-only device before touching the bus.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from boneio.core.config.config_helper import ConfigHelper
from boneio.core.manager import Manager
from boneio.modbus.coordinator import ModbusCoordinator, ModbusWriteRejected
from tests.unit.modbus.test_modbus_coils import _coordinator as _bare_coordinator


def _setpoint(**extra) -> dict:
    return {
        "name": "Setpoint",
        "address": 10,
        "write_address": 10,
        "entity_type": "writeable_sensor",
        "value_type": "S_WORD",
        "write_filters": [{"multiply": 10}],
        "min": 20,
        "max": 60,
        **extra,
    }


def _coordinator(read_only: bool = False, **setpoint) -> ModbusCoordinator:
    coordinator = _bare_coordinator(
        [{"base": 0, "length": 1, "register_type": "holding", "registers": [_setpoint(**setpoint)]}]
    )
    coordinator._read_only = read_only
    return coordinator


def _entity(coordinator):
    return coordinator._modbus_entities[0]["setpoint"]


async def test_value_above_max_is_rejected_before_the_bus():
    coordinator = _coordinator()

    with pytest.raises(ModbusWriteRejected):
        await coordinator.write_register(value=61, entity=_entity(coordinator))

    coordinator._modbus.write_register.assert_not_awaited()


async def test_value_below_min_and_non_numbers_are_rejected():
    coordinator = _coordinator()

    for bad in (19.9, "abc"):
        with pytest.raises(ModbusWriteRejected):
            await coordinator.write_register(value=bad, entity=_entity(coordinator))

    coordinator._modbus.write_register.assert_not_awaited()


async def test_values_that_are_not_finite_are_rejected():
    coordinator = _coordinator()

    for bad in ("nan", "inf", "-inf", float("nan")):
        with pytest.raises(ModbusWriteRejected):
            await coordinator.write_register(value=bad, entity=_entity(coordinator))

    coordinator._modbus.write_register.assert_not_awaited()


async def test_value_within_range_is_written_scaled():
    coordinator = _coordinator()

    await coordinator.write_register(value="45.5", entity=_entity(coordinator))

    coordinator._modbus.write_register.assert_awaited_once()
    assert coordinator._modbus.write_register.await_args.kwargs["value"] == 455


async def test_register_without_limits_is_unrestricted():
    coordinator = _coordinator(min=None, max=None)

    await coordinator.write_register(value=1000, entity=_entity(coordinator))

    coordinator._modbus.write_register.assert_awaited_once()


async def test_read_only_device_writes_nothing():
    coordinator = _coordinator(read_only=True, min=None, max=None)

    with pytest.raises(ModbusWriteRejected):
        await coordinator.write_register(value=30, entity=_entity(coordinator))

    coordinator._modbus.write_register.assert_not_awaited()


async def test_mqtt_set_out_of_range_is_rejected(caplog):
    coordinator = _coordinator()
    manager = Manager.__new__(Manager)
    manager._config_helper = SimpleNamespace(
        ha_discovery_prefix="homeassistant",
        receive_boneio_autodiscovery=False,
        cmd_topic_prefix="boneio/cmd/",
    )
    manager.modbus = SimpleNamespace(get_all_coordinators=lambda: {"relays": coordinator})
    coordinator.find_entity = lambda name: _entity(coordinator)

    with caplog.at_level(logging.WARNING):
        await manager.receive_message(
            "boneio/cmd/modbus/relays/set", '{"device": "setpoint", "value": "99"}'
        )

    coordinator._modbus.write_register.assert_not_awaited()
    assert "rejected" in caplog.text


def test_number_discovery_carries_min_and_max():
    coordinator = _coordinator()
    coordinator.manager.config_helper = ConfigHelper(name="black", serial_override="blk0001")
    entity = _entity(coordinator)
    entity._config_helper = coordinator.manager.config_helper

    payload = entity.discovery_message()

    assert (payload["min"], payload["max"]) == (20, 60)


def _with_controls(read_only: bool):
    config_helper = ConfigHelper(name="black", serial_override="blk0001")
    coordinator = _coordinator(read_only=read_only)
    coordinator.manager.config_helper = config_helper
    coordinator._polling_enabled = True
    entity = _entity(coordinator)
    entity._config_helper = config_helper
    entity._message_bus = coordinator._message_bus
    coordinator._modbus_entities[0]["readout"] = MagicMock(entity_type="sensor")
    return coordinator, entity


@pytest.mark.parametrize(("read_only", "announced"), [(False, True), (True, False)])
def test_read_only_device_reserves_no_command_entities(read_only, announced):
    coordinator, entity = _with_controls(read_only)
    coordinator._send_polling_switch_discovery = MagicMock()
    coordinator._polling_switch_discovery = MagicMock(return_value=("t", {}))
    coordinator.manager.config_helper.reserve_autodiscovery_msg = MagicMock()
    entity.reserve_ha_discovery = MagicMock()
    entity.send_ha_discovery = MagicMock()
    sensor = coordinator._modbus_entities[0]["readout"]

    coordinator._reserve_discovery_for_all_registers()
    coordinator._send_discovery_for_all_registers()

    assert entity.reserve_ha_discovery.called is announced
    assert entity.send_ha_discovery.called is announced
    sensor.reserve_ha_discovery.assert_called_once()
    sensor.send_ha_discovery.assert_called_once()
