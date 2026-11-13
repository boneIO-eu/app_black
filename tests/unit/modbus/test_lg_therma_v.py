"""LG Therma V R290: the register map is built around addresses that do not answer.

A block read that includes a silent register is rejected whole, so the layout
must skip them, and everything beyond the manual's core set must be optional.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from boneio.modbus.coordinator import ModbusCoordinator
from boneio.modbus.definition import load_definition
from tests.unit.modbus.test_modbus_coils import _coordinator

DEVICE = Path(__file__).parents[3] / "boneio/modbus/devices/hvac/lg-therma-v-r290.json"


def _registers(register_type: str) -> dict:
    d = load_definition("lg-therma-v-r290")
    return {r.decoded_name: r for b in d.registers_base if b.register_type == register_type for r in b.registers}


def _by_name() -> dict:
    d = load_definition("lg-therma-v-r290")
    return {r.decoded_name: r for b in d.registers_base for r in b.registers}


def test_blocks_skip_registers_that_do_not_answer():
    d = load_definition("lg-therma-v-r290")
    inputs = [b for b in d.registers_base if b.register_type == "input"]
    covered = {a for b in inputs for a in range(b.base, b.base + b.length)}
    assert 15 not in covered and 17 not in covered
    assert all(b.optional for b in inputs if b.base != 0)


def test_cooling_flag_is_not_exposed():
    d = load_definition("lg-therma-v-r290")
    di = next(b for b in d.registers_base if b.register_type == "discrete_input")
    assert 8 not in {r.address for r in di.registers}


@pytest.mark.parametrize(
    ("name", "low", "high"),
    [("heatingsetpoint", 5, 60), ("heatingsetpointcircuit2", 20, 40), ("dhwsetpoint", 35, 65)],
)
def test_setpoint_limits(name, low, high):
    r = _by_name()[name]
    assert (r.min, r.max) == (low, high)
    assert r.write_filters == [{"multiply": 10}] and r.filters[0] == {"multiply": 0.1}


def test_curve_offsets_are_signed_and_limited_to_five_kelvin():
    for name in ("curveoffsetcircuit1", "curveoffsetcircuit2"):
        r = _by_name()[name]
        assert (r.value_type, r.min, r.max) == ("S_WORD", -5, 5)


def test_power_limits_sit_in_an_optional_block():
    d = load_definition("lg-therma-v-r290")
    b = next(b for b in d.registers_base if b.register_type == "holding" and b.base == 23)
    assert b.optional
    r = {x.decoded_name: x for x in b.registers}
    assert (r["modulationlimit"].min, r["modulationlimit"].max) == (0, 100)
    assert (r["powerlimit"].min, r["powerlimit"].max) == (0.1, 25)


def test_emergency_stop_is_hidden_and_confirmed():
    stop = _by_name()["emergencystopstate"]
    assert stop.hidden and stop.confirm and stop.address == 4
    assert {n for n, r in _by_name().items() if r.confirm} == {"emergencystopstate", "startemergencyoperation"}
    assert {n for n, r in _by_name().items() if r.hidden} == {"emergencystopstate"}


def test_emergency_stop_switch_is_hidden_and_confirmed_through_its_source():
    coordinator = _coordinator(json.loads(DEVICE.read_text())["registers_base"])
    switch = SimpleNamespace(decoded_name="emergencystop", source_sensor_decoded_name="emergencystopstate")

    assert not coordinator.visible(switch, "panel") and not coordinator.visible(switch, "ha")
    assert coordinator.confirm_required(switch)


def test_triggers_are_buttons():
    coils = _registers("coil")
    assert {n: (r.entity_type, r.address) for n, r in coils.items() if r.entity_type == "button"} == {
        "startdhwdisinfection": ("button", 3),
        "startemergencyoperation": ("button", 5),
    }


def test_mode_values_follow_r290_measurements():
    mode = _by_name()["operatingmodevalue"]
    assert mode.x_mapping == {"0": "Cooling", "3": "Auto", "4": "Heating"}
    d = load_definition("lg-therma-v-r290")
    select = next(a for a in d.additional_entities if a.name == "Operating mode")
    assert select.entity_type == "select" and select.x_mapping == mode.x_mapping


def test_water_flow_one_means_flowing():
    flow = _registers("discrete_input")["waterflow"]
    assert (flow.address, flow.payload_on) == (0, "1")


def _entities() -> dict:
    coordinator = _coordinator(json.loads(DEVICE.read_text())["registers_base"])
    return {name: e for block in coordinator._modbus_entities for name, e in block.items()}


def test_temperatures_are_tenths_of_a_degree():
    entities = _entities()
    assert entities["heatingsetpoint"].encode_value(45.5) == 455
    entities["watersupplytemperature"].set_value(-75, timestamp=1.0)
    assert entities["watersupplytemperature"].get_value() == -7.5


async def test_negative_curve_offset_is_accepted_and_reaches_the_client_unchanged():
    coordinator = _coordinator(json.loads(DEVICE.read_text())["registers_base"])
    entity = next(b for b in coordinator._modbus_entities if "curveoffsetcircuit1" in b)["curveoffsetcircuit1"]

    await ModbusCoordinator.write_register(coordinator, value=-3, entity=entity)

    coordinator._modbus.write_register.assert_awaited_once_with(unit=1, address=4, value=-3, coil=False)
