"""A heat pump shows in Home Assistant as a thermostat and a water heater.

Both sit in the Modbus device next to its plain entities. Their state is one
JSON on ``…/modbus/<id>/heat_pump``; their commands come back on
``…/cmd/modbus/<id>/heat_pump/<field>/set`` and are written through the same
checks as any other write, all of them before the first reaches the bus.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from boneio.core.config.config_helper import ConfigHelper
from boneio.core.manager import Manager
from boneio.modbus.coordinator import ModbusCoordinator, ModbusWriteRejected
from boneio.modbus.definition import load_definition

PREFIX = "boneio/blk0001"
CLIMATE_TOPIC = "homeassistant/climate/blk0001/lg_heat_pump/config"
WATER_HEATER_TOPIC = "homeassistant/water_heater/blk0001/lg_dhw/config"


def _coordinator(model="lg-therma-v-r290", read_only=False, visibility=None) -> ModbusCoordinator:
    # Bypass __init__: it wires up the manager, but the entities are built as usual.
    c = ModbusCoordinator.__new__(ModbusCoordinator)
    c._id, c._name, c._area, c._has_custom_id = "lg", "LG", None, False
    c._read_only, c._address, c._polling_enabled = read_only, 1, True
    c._definition = load_definition(model)
    c._model = c._definition.model
    c._modbus_entities, c._additional_entities = [], []
    c._additional_entities_by_name, c._additional_entities_by_source_name = {}, {}
    c._additional_data, c._coil_entities = {}, set()
    c._sensors_filters, c._entity_labels = {}, {}
    c._entity_visibility = visibility or {}
    c._message_bus, c._event_bus = MagicMock(), MagicMock()
    c._send_topic = f"{PREFIX}/modbus/lg"
    c.manager = MagicMock(config_helper=ConfigHelper(name="black", serial_override="blk0001"))
    c._modbus = MagicMock()
    c._modbus.write_register = AsyncMock(return_value=MagicMock())
    c.request_update = MagicMock()
    c.__init_modbus_entities__()
    c.__init_derived_sensors__()
    return c


def _read(c: ModbusCoordinator, **raw) -> None:
    """Feed raw register values as a poll would, derived entities included."""
    for name, value in raw.items():
        entity = c.get_entity_by_name(name)
        entity.set_value(value=value, timestamp=1.0)
        for derived in c._additional_entities_by_source_name.get(name, []):
            derived.evaluate_state(entity.get_value(), 1.0)


def _heating_lg(c):
    _read(
        c,
        heatingcoolingstate=1, operatingmodevalue=4, controlmethodvalue=0,
        heatingsetpoint=450, watersupplytemperature=402, dhwstate=1,
        dhwsetpoint=500, dhwtanktemperature=480, compressor=1, defrost=0,
        outdoorunitcycle=2,
    )


def _sent(c, topic):
    return [x.kwargs for x in c._message_bus.send_message.call_args_list if x.kwargs["topic"] == topic]


def _manager(c) -> Manager:
    manager = Manager.__new__(Manager)
    manager._config_helper = SimpleNamespace(
        ha_discovery_prefix="homeassistant",
        receive_boneio_autodiscovery=False,
        cmd_topic_prefix=f"{PREFIX}/cmd/",
    )
    manager.modbus = SimpleNamespace(get_all_coordinators=lambda: {"lg": c})
    return manager


def test_climate_discovery_is_in_modbus_device():
    c = _coordinator()

    c._send_discovery_for_all_registers()

    [climate] = _sent(c, CLIMATE_TOPIC)
    payload = climate["payload"]
    assert climate["retain"] is True
    assert payload["device"]["identifiers"] == ["lg"]
    assert payload["device"]["via_device"] == PREFIX
    assert payload["availability"] == [{"topic": f"{PREFIX}/modbus/lg/state"}]
    assert payload["modes"] == ["off", "heat", "cool", "auto"]
    assert (payload["min_temp"], payload["max_temp"], payload["temp_step"]) == (5, 60, 0.5)
    assert payload["mode_state_topic"] == f"{PREFIX}/modbus/lg/heat_pump"
    assert payload["mode_state_template"] == "{{ value_json.mode }}"
    assert payload["temperature_state_template"] == "{{ value_json.target_temperature }}"
    assert payload["mode_command_topic"] == f"{PREFIX}/cmd/modbus/lg/heat_pump/mode/set"
    assert payload["temperature_command_topic"] == f"{PREFIX}/cmd/modbus/lg/heat_pump/temperature/set"

    [water] = _sent(c, WATER_HEATER_TOPIC)
    payload = water["payload"]
    assert payload["device"]["identifiers"] == ["lg"]
    assert payload["modes"] == ["off", "heat_pump"]
    assert (payload["min_temp"], payload["max_temp"]) == (35, 65)
    assert payload["mode_state_template"] == "{{ value_json.dhw_mode }}"
    assert payload["current_temperature_template"] == "{{ value_json.dhw_current }}"
    assert payload["mode_command_topic"] == f"{PREFIX}/cmd/modbus/lg/heat_pump/dhw_mode/set"
    assert payload["temperature_command_topic"] == f"{PREFIX}/cmd/modbus/lg/heat_pump/dhw_temperature/set"


def test_climate_limits_fall_back_when_the_target_has_none():
    c = _coordinator("kaisai-phnix")

    c._send_discovery_for_all_registers()

    [climate] = _sent(c, CLIMATE_TOPIC)
    payload = climate["payload"]
    assert payload["modes"] == ["off", "heat", "cool"]
    assert (payload["min_temp"], payload["max_temp"], payload["temp_step"]) == (5, 60, 0.5)


@pytest.mark.parametrize(("read_only", "present"), [(False, True), (True, False)])
def test_climate_and_water_heater_are_reserved(read_only, present):
    c = _coordinator(read_only=read_only)
    helper = c.manager.config_helper

    c._reserve_discovery_for_all_registers()

    assert helper.is_topic_in_autodiscovery(CLIMATE_TOPIC) is present
    assert helper.is_topic_in_autodiscovery(WATER_HEATER_TOPIC) is present
    assert _sent(c, CLIMATE_TOPIC) == []

    c._send_discovery_for_all_registers()

    assert bool(_sent(c, CLIMATE_TOPIC)) is present
    assert bool(_sent(c, WATER_HEATER_TOPIC)) is present


async def test_heat_pump_state_published_on_change_only():
    c = _coordinator()
    c._poll = AsyncMock(return_value=60)
    c._published_failing, c._reported_groups = False, set()
    topic = f"{PREFIX}/modbus/lg/heat_pump"

    await c.async_update(1.0)
    [unknown] = _sent(c, topic)
    assert unknown["payload"]["mode"] is None
    assert unknown["retain"] is True

    _heating_lg(c)
    await c.async_update(2.0)
    await c.async_update(3.0)

    sent = _sent(c, topic)
    assert len(sent) == 2
    assert sent[1]["payload"] == {
        "mode": "heat",
        "action": "heating",  # outdoor unit cycle fed as its raw value 2, not "Heating"
        "current_temperature": 40.2,
        "target_temperature": 45.0,
        "dhw_mode": "heat_pump",
        "dhw_current": 48.0,
        "dhw_target": 50.0,
    }


async def test_mqtt_mode_heat_writes_mode_then_power():
    c = _coordinator()
    _heating_lg(c)
    _read(c, heatingcoolingstate=0, operatingmodevalue=0)

    await _manager(c).receive_message(f"{PREFIX}/cmd/modbus/lg/heat_pump/mode/set", "heat")

    assert c._modbus.write_register.await_args_list == [
        call(unit=1, address=0, value=4, coil=False),
        call(unit=1, address=0, value=1, coil=True),
    ]
    assert _sent(c, f"{PREFIX}/modbus/lg/heat_pump")[-1]["payload"]["mode"] == "heat"


async def test_read_only_blocks_both_writes_of_a_mode_change(caplog):
    c = _coordinator(read_only=True)
    _read(c, heatingcoolingstate=0, operatingmodevalue=0)

    with caplog.at_level(logging.WARNING):
        await _manager(c).receive_message(f"{PREFIX}/cmd/modbus/lg/heat_pump/mode/set", "heat")

    c._modbus.write_register.assert_not_awaited()
    assert "rejected" in caplog.text


async def test_a_refused_second_write_stops_the_first():
    c = _coordinator()
    _read(c, heatingcoolingstate=0, operatingmodevalue=0)
    power = c.get_additional_entity_by_name("heatingcooling")
    allowed = c._check_write_allowed

    def refuse_power(value, entity):
        if entity is power:
            raise ModbusWriteRejected("power refused")
        allowed(value, entity)

    c._check_write_allowed = refuse_power

    with pytest.raises(ModbusWriteRejected):
        await c.set_heat_pump("mode", "heat")

    c._modbus.write_register.assert_not_awaited()


@pytest.mark.parametrize(
    ("field", "value"),
    [("temperature", "61"), ("temperature", "nan"), ("dhw_temperature", "70"), ("dhw_temperature", "abc")],
)
async def test_out_of_range_target_writes_nothing(field, value):
    c = _coordinator()
    _heating_lg(c)

    with pytest.raises(ModbusWriteRejected):
        await c.set_heat_pump(field, value)

    c._modbus.write_register.assert_not_awaited()


@pytest.mark.parametrize(("field", "value"), [("mode", "auto"), ("temperature", "nan"), ("swing", "on")])
async def test_phnix_rejects_what_it_cannot_do(field, value):
    c = _coordinator("kaisai-phnix")

    with pytest.raises(ModbusWriteRejected):
        await c.set_heat_pump(field, value)

    c._modbus.write_register.assert_not_awaited()


async def test_heat_pump_works_with_hidden_role_entity():
    hidden = {"heatingsetpoint": {"ha": False, "panel": False}}
    c = _coordinator(visibility=hidden)
    _heating_lg(c)
    setpoint = c.get_entity_by_name("heatingsetpoint")

    assert setpoint not in list(c._announced_entities())
    assert c.heat_pump_state()["target_temperature"] == 45.0

    await c.set_heat_pump("temperature", "40")

    c._modbus.write_register.assert_awaited_once_with(unit=1, address=2, value=400, coil=False)


async def test_plain_modbus_set_still_works():
    c = _coordinator()

    await _manager(c).receive_message(
        f"{PREFIX}/cmd/modbus/lg/set", '{"device": "heatingsetpoint", "value": "40"}'
    )

    c._modbus.write_register.assert_awaited_once_with(unit=1, address=2, value=400, coil=False)
