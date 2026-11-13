"""A heat pump shows in Home Assistant as a thermostat and a water heater.

Both sit in the Modbus device next to its plain entities. Their state is one
JSON on ``…/modbus/<id>/heat_pump``; their commands come back on
``…/cmd/modbus/<id>/heat_pump/<field>/set`` and are written through the same
checks as any other write, all of them before the first reaches the bus.
"""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from boneio.core.config.config_helper import ConfigHelper
from boneio.core.manager import Manager
from boneio.core.manager.modbus import ModbusManager
from boneio.modbus.coordinator import ModbusCoordinator, ModbusWriteFailed, ModbusWriteRejected
from boneio.modbus.definition import load_definition

PREFIX = "boneio/blk0001"
CLIMATE_TOPIC = "homeassistant/climate/blk0001/lg_heat_pump/config"
WATER_HEATER_TOPIC = "homeassistant/water_heater/blk0001/lg_dhw/config"


def _coordinator(
    model="lg-therma-v-r290", read_only=False, visibility=None, device_id="lg", config_helper=None
) -> ModbusCoordinator:
    # Bypass __init__: it wires up the manager, but the entities are built as usual.
    c = ModbusCoordinator.__new__(ModbusCoordinator)
    c._id, c._name, c._area, c._has_custom_id = device_id, "LG", None, False
    c._read_only, c._address, c._polling_enabled = read_only, 1, True
    c._definition = load_definition(model)
    c._model = c._definition.model
    c._modbus_entities, c._additional_entities = [], []
    c._additional_entities_by_name, c._additional_entities_by_source_name = {}, {}
    c._additional_data, c._coil_entities = {}, set()
    c._sensors_filters, c._entity_labels = {}, {}
    c._entity_visibility = visibility or {}
    c._heat_pump_lock = asyncio.Lock()
    c._message_bus, c._event_bus = MagicMock(), MagicMock()
    c._send_topic = f"{PREFIX}/modbus/lg"
    c.manager = MagicMock(
        config_helper=config_helper or ConfigHelper(name="black", serial_override="blk0001")
    )
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


def test_climate_limits_come_from_the_target_registers():
    c = _coordinator()
    registers = c._registers_by_name
    registers["heatingsetpoint"] = registers["heatingsetpoint"].model_copy(
        update={"min": 15, "max": 55, "step": 1}
    )

    c._send_discovery_for_all_registers()

    [climate] = _sent(c, CLIMATE_TOPIC)
    assert (climate["payload"]["min_temp"], climate["payload"]["max_temp"]) == (15, 55)
    assert climate["payload"]["temp_step"] == 1


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
    assert _sent(c, topic) == []  # nothing read yet: no made-up state is retained

    _heating_lg(c)
    await c.async_update(2.0)
    await c.async_update(3.0)

    sent = _sent(c, topic)
    assert len(sent) == 1
    assert sent[0]["retain"] is True
    assert sent[0]["payload"] == {
        "mode": "heat",
        "action": "heating",  # outdoor unit cycle fed as its raw value 2, not "Heating"
        "current_temperature": 40.2,
        "target_temperature": 45.0,
        "dhw_mode": "heat_pump",
        "dhw_current": 48.0,
        "dhw_target": 50.0,
    }


async def test_an_unknown_mode_is_published_as_null():
    c = _coordinator()
    _heating_lg(c)
    _read(c, operatingmodevalue=1)  # not a mode LG documents

    c._publish_heat_pump_state()

    [sent] = _sent(c, f"{PREFIX}/modbus/lg/heat_pump")
    assert sent["payload"]["mode"] is None


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
    [
        ("temperature", "61"),
        ("temperature", "nan"),
        ("dhw_temperature", "70"),
        ("dhw_temperature", "abc"),
        ("dhw_temperature", "30"),
    ],
)
async def test_out_of_range_target_writes_nothing(field, value):
    c = _coordinator()
    _heating_lg(c)

    with pytest.raises(ModbusWriteRejected):
        await c.set_heat_pump(field, value)

    c._modbus.write_register.assert_not_awaited()


def _known_phnix():
    c = _coordinator("kaisai-phnix")
    _read(c, power=1, mode=1)
    return c


@pytest.mark.parametrize(
    ("field", "value"),
    [("mode", "auto"), ("temperature", "nan"), ("temperature", "61"), ("dhw_temperature", "4"), ("swing", "on")],
)
async def test_phnix_rejects_what_it_cannot_do(field, value):
    c = _known_phnix()

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


@pytest.mark.parametrize(
    ("model", "field", "value"),
    [
        ("kaisai-phnix", "dhw_mode", "heat_pump"),
        ("kaisai-phnix", "mode", "heat"),
        ("kaisai-phnix", "temperature", "40"),
        ("lg-therma-v-r290", "mode", "heat"),
    ],
)
async def test_nothing_is_written_before_power_and_mode_are_known(model, field, value):
    c = _coordinator(model)

    with pytest.raises(ModbusWriteRejected, match="not known yet"):
        await c.set_heat_pump(field, value)

    c._modbus.write_register.assert_not_awaited()


async def test_a_failed_bus_write_stops_the_command():
    c = _coordinator()
    _heating_lg(c)
    _read(c, heatingcoolingstate=0, operatingmodevalue=0)
    c._publish_heat_pump_state()
    c._message_bus.send_message.reset_mock()
    c._modbus.write_register = AsyncMock(return_value=None)  # timeout, exception response, suspended

    with pytest.raises(ModbusWriteFailed):
        await c.set_heat_pump("mode", "heat")

    c._modbus.write_register.assert_awaited_once()  # the power write never went out
    assert c.get_entity_by_name("operatingmodevalue").get_value() == 0
    c._message_bus.send_message.assert_not_called()


async def test_a_failed_bus_write_reaches_mqtt_as_a_warning(caplog):
    c = _coordinator()
    c._modbus.write_register = AsyncMock(return_value=None)

    with caplog.at_level(logging.WARNING):
        await _manager(c).receive_message(
            f"{PREFIX}/cmd/modbus/lg/set", '{"device": "heatingsetpoint", "value": "40"}'
        )

    assert "Modbus write failed" in caplog.text
    assert c.get_entity_by_name("heatingsetpoint").get_value() is None


def test_removing_a_device_leaves_other_entities_alone():
    helper = ConfigHelper(name="black", serial_override="blk0001")
    heat = _coordinator(device_id="heat", config_helper=helper)
    heat._send_discovery_for_all_registers()
    native = [
        "homeassistant/climate/blk0001/heating_floor/config",
        "homeassistant/climate/blk0001/heat_floor/config",
        "homeassistant/switch/blk0001/heat_relay/config",
    ]
    for topic in native:
        helper.add_autodiscovery_msg(ha_type=topic.split("/")[1], topic=topic, payload={})
    owned = [topic for _, topic in heat.discovery_topics() if helper.is_topic_in_autodiscovery(topic)]
    assert "homeassistant/climate/blk0001/heat_heat_pump/config" in owned
    modbus = ModbusManager.__new__(ModbusManager)
    modbus._manager = SimpleNamespace(_config_helper=helper, send_message=MagicMock())
    modbus._modbus_coordinators = {"heat": heat}

    modbus._remove_modbus_ha_discovery_for_id("heat")

    removed = {c.kwargs["topic"] for c in modbus._manager.send_message.call_args_list}
    assert removed == set(owned)
    assert all(helper.is_topic_in_autodiscovery(topic) for topic in native)
    assert not any(helper.is_topic_in_autodiscovery(topic) for topic in owned)


async def test_a_failed_bus_write_is_a_bad_gateway_for_the_panel():
    from fastapi import HTTPException

    from boneio.webui.routes.modbus import set_modbus_value

    c = _coordinator()
    c._modbus.write_register = AsyncMock(return_value=None)
    manager = SimpleNamespace(modbus=SimpleNamespace(get_all_coordinators=lambda: {"lg": c}))

    with pytest.raises(HTTPException) as err:
        await set_modbus_value("lg", "heatingsetpoint", {"value": 40}, manager)

    assert err.value.status_code == 502


@pytest.mark.parametrize(
    ("entity", "value"),
    [("operatingmode", "Heat"), ("operatingmode", "1"), ("heatingcooling", "on"), ("dhw", "maybe")],
)
async def test_a_value_the_mapping_does_not_name_writes_nothing(entity, value):
    c = _coordinator()

    with pytest.raises(ModbusWriteRejected, match="is not one of"):
        await c.write_register(value, c.get_additional_entity_by_name(entity))

    c._modbus.write_register.assert_not_awaited()


@pytest.mark.parametrize(("entity", "value", "word"), [("operatingmode", "Heating", 4), ("heatingcooling", "ON", 1)])
async def test_a_mapped_value_is_written(entity, value, word):
    c = _coordinator()

    await c.write_register(value, c.get_additional_entity_by_name(entity))

    assert c._modbus.write_register.await_args.kwargs["value"] == word


@pytest.mark.parametrize(("register", "value"), [("operatingmodevalue", 5), ("controlmethodvalue", 3)])
async def test_raw_mode_registers_take_only_known_values(register, value):
    c = _coordinator()

    with pytest.raises(ModbusWriteRejected, match="outside the allowed range"):
        await c.write_register(value, c.get_entity_by_name(register))

    c._modbus.write_register.assert_not_awaited()


async def test_a_heat_pump_role_without_a_write_address_writes_nothing():
    c = _coordinator()
    _heating_lg(c)
    _read(c, heatingcoolingstate=0, operatingmodevalue=0)
    c.get_entity_by_name("heatingcoolingstate")._write_address = None  # power, the second write

    with pytest.raises(ModbusWriteRejected, match="no write address"):
        await c.set_heat_pump("mode", "heat")

    c._modbus.write_register.assert_not_awaited()


async def test_a_button_without_a_write_address_is_an_error():
    c = _coordinator()
    button = c.get_entity_by_name("startdhwdisinfection")
    button._write_address = None

    with pytest.raises(ModbusWriteRejected, match="no write address"):
        await c.write_register(1, button)

    c._modbus.write_register.assert_not_awaited()


async def test_heat_pump_commands_run_one_at_a_time():
    # Phnix keeps hot water and mode in one register: each command must
    # build on the value the previous one wrote, not on the same old read.
    c = _known_phnix()  # power on, heating (mode 1)
    written = []

    async def slow_write(unit, address, value, coil):
        await asyncio.sleep(0)
        written.append(value)
        return MagicMock()

    c._modbus.write_register = AsyncMock(side_effect=slow_write)

    await asyncio.gather(c.set_heat_pump("dhw_mode", "heat_pump"), c.set_heat_pump("mode", "cool"))

    assert written == [3, 4]  # hot water + heating, then hot water + cooling
