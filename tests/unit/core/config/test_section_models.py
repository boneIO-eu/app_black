"""What the section models accept, held still.

Every factory config is accepted as written. Beyond them, small valid
entries reach every field between them, and each field of each level is set
to a wrong value of every kind or removed: thousands of cases. Which of them
a model refuses is frozen in config_verdicts.json — written while Cerberus
was still the reference and every difference from it was a listed decision —
so a change in what start-up accepts is always seen, and made on purpose.

Regenerate after a deliberate change:
``python -m tests.unit.core.config.test_section_models``.
"""

from __future__ import annotations

import copy
import functools
import glob
import json
from pathlib import Path
from typing import Any

import pytest

from boneio.core.config import models
from boneio.core.config.json_schema import section_schema
from boneio.core.config.yaml_util import (
    _read_sections,
    _run_config_migrations,
    load_yaml_file,
    merge_board_config,
    validate_section,
)

VERDICTS = Path(__file__).parent / "config_verdicts.json"

BONEIO = {"config_version": 8, "name": "t", "version": 1.1, "device_type": "24x16A"}

#: A wrong value of every kind, and the marker for "field removed".
REMOVED = object()
MUTANTS = [REMOVED, None, True, 7, -1, 1000, 1.5, "x", "TOGGLE", "30s", [], {}]

ACTIONS = [
    {"action": "output", "boneio_output": "out_01", "action_output": "ON",
     "delay": "2s", "delay_cancel_on": ["single", "long"], "brightness": 100},
    {"action": "cover", "boneio_cover": "c1", "action_cover": "SET_POSITION",
     "data": {"position": 50, "tilt_position": 10, "always_open_till": 20}},
    {"action": "mqtt", "topic": "t", "action_mqtt_msg": "m"},
    {"action": "virtual_switch", "boneio_virtual_switch": "v1"},
    {"action": "output_over_mqtt", "boneio_output": "out_01", "action_mqtt_msg": "m", "boneio_id": "b"},
    {"action": "cover_over_mqtt", "boneio_cover": "c1", "action_mqtt_msg": "m", "boneio_id": "b"},
    {"action": "remote_output", "remote_device": "r", "output_id": "o"},
    {"action": "remote_cover", "remote_device": "r", "cover_id": "c"},
]
CONDITIONS = [
    {"type": "time", "after": "05:00", "before": "22:00"},
    {"type": "date", "after": "11-01", "before": "03-31"},
    {"type": "state", "entity": "output", "entity_id": "out_02", "state": "is_on"},
    {"type": "sun", "after": "sunset", "after_offset": "-30min"},
    {"type": "sun", "phase": "night"},
    {"type": "sun", "above": -6, "below": 10},
]


#: The action fields whose rules depend on the action type. The others behave
#: the same on every type and are mutated on one of them.
TYPED_FIELDS = {"action", "boneio_output", "boneio_cover", "boneio_virtual_switch", "topic",
                "action_cover", "action_output", "action_mqtt_msg", "boneio_id", "remote_device",
                "output_id", "cover_id", "transition"}


def _bases() -> list[tuple[str, dict, tuple, bool]]:
    """Small valid entries that between them reach every field.

    Each comes with the part of it that is mutated, and whether only the
    fields that depend on the action type are: what surrounds that part is
    mutated with another base.
    """
    event = {"boneio_input": "in_01", "name": "In 1", "mqtt_sequences": {"double_then_long": True}}
    sensor = {"boneio_input": "in_02", "device_class": "door"}
    bases = [("event", event, (), False), ("binary_sensor", sensor, (), False)]
    for i, action in enumerate(ACTIONS):
        bases.append(("event", {**event, "actions": {"single": [dict(action)]}},
                      ("actions", "single", 0), i > 0))
    bases.append(("event", {**event, "actions": {"triple": [dict(ACTIONS[0])]}}, ("actions",), True))
    bases.append(("binary_sensor", {**sensor, "actions": {"pressed": [dict(ACTIONS[0])]}}, ("actions",), True))
    for condition in CONDITIONS:
        conditioned = {**ACTIONS[0], "condition": dict(condition)}
        bases.append(("event", {**event, "actions": {"double": [conditioned]}},
                      ("actions", "double", 0, "condition"), False))
    grouped = {**ACTIONS[2], "conditions": {"mode": "or", "list": [dict(c) for c in CONDITIONS[:3]]}}
    bases.append(("event", {**event, "actions": {"long": [grouped]}},
                  ("actions", "long", 0, "conditions"), True))
    bases += [
        ("output", {"boneio_output": "OUT_05", "output_type": "light", "name": "Lamp",
                    "percentage_default_brightness": 80, "interlock_group": "g1",
                    "momentary_turn_on": "2s", "momentary_turn_off": "500ms"}, (), False),
        ("output", {"kind": "gpio", "pin": 5, "output_type": "switch", "area": "hall",
                    "adjustable_duration": True, "duration_default": "5min", "duration_min": "1s",
                    "duration_max": "1h", "duration_unit": "min", "restore_state": False,
                    "sysfs_path": "/x", "mcp_id": "m", "pca_id": "p", "pcf_id": "f"}, (), False),
        ("cover", {"open_relay": "OUT_01", "close_relay": "OUT_02", "open_time": "30s",
                   "close_time": "28s"}, (), False),
        ("cover", {"id": "living_blind", "name": "Blind", "area": "living", "restore_state": True,
                   "open_relay": "OUT_03", "close_relay": "OUT_04", "platform": "venetian",
                   "open_time": "40s", "close_time": "38s", "tilt_duration": "1500ms",
                   "actuator_activation_duration": "200ms", "endstop_overrun": 20,
                   "direction_change_wait_time": "1s", "tilt_restore_after_close": True,
                   "device_class": "blind", "show_in_ha": False}, (), False),
        ("remote_inputs", {"remote_source": "esphome_api", "device_id": "hall", "input_id": "button"},
         (), False),
        ("remote_inputs", {"id": "garden_switch", "name": "Garden", "remote_source": "mqtt",
                           "device_id": "shelly", "input_id": "in0", "topic": "shelly/in0",
                           "mode": "event", "device_class": "button", "area": "garden",
                           "show_in_ha": True, "inverted": True, "double_click_duration": 300,
                           "long_press_duration": 600, "sequence_mode": "immediate",
                           "long_press_mqtt_mode": "periodic", "enable_triple_click": True,
                           "actions": {"single": [dict(ACTIONS[0])]}}, (), False),
        ("virtual_switch", {"name": "Away mode"}, (), False),
        ("virtual_switch", {"name": "Night", "id": "night", "description": "d", "area": "house",
                            "icon": "mdi:weather-night", "restore_state": False, "initial": True,
                            "show_in_ha": False,
                            "actions": {"on_turn_on": [dict(ACTIONS[0])],
                                        "on_turn_off": [dict(ACTIONS[3])]}}, (), False),
        ("schedule", {"name": "Dusk lights", "trigger": {"event": "sunset", "offset": "-30min",
                                                        "earliest": "17:00", "latest": "21:30",
                                                        "jitter": "5min", "days": "weekdays"},
                      "actions": [dict(ACTIONS[0])]}, (), False),
        ("schedule", {"name": "Morning", "id": "morning", "description": "d", "enabled": False,
                      "trigger": {"type": "time", "at": "06:30", "days": "mon"},
                      "on_missed": "run", "catch_up": "10min",
                      "condition": {"type": "state", "entity": "output", "entity_id": "out_02",
                                    "state": "is_off"},
                      "actions": [dict(ACTIONS[2])]}, (), False),
        ("schedule", {"name": "Grouped", "trigger": {"event": "sunrise"},
                      "conditions": {"mode": "or", "list": [dict(c) for c in CONDITIONS[:3]]},
                      "actions": [dict(ACTIONS[3])]}, (), False),
        ("template", {"platform": "thermostat", "name": "Living", "id": "living_heat",
                      "area": "living", "sensor_id": "t1", "sensor_ids": ["t1", "t2"],
                      "output_id": "OUT_01", "mode": "off", "target_temperature": 22,
                      "hysteresis": 0.3, "min_temperature": 10, "max_temperature": 30}, (), False),
        ("template", {"platform": "alarm_control_panel", "name": "Alarm",
                      "codes": [{"name": "Me", "code": "1234"}], "code_arm_required": True,
                      "arming_time": "30s", "delay_time": "20s", "trigger_time": "3min",
                      "outputs": [{"id": "OUT_05", "type": "light"}],
                      "zones": [{"name": "Ground", "inputs": ["in_01"], "arm_modes": ["away"],
                                 "entry_delay": True}]}, (), False),
        ("template", {"platform": "gate_cover", "name": "Gate", "control_mode": "separate",
                      "device_class": "garage_door", "pulse_output": "OUT_06",
                      "open_output": "OUT_07", "close_output": "OUT_08", "stop_output": "OUT_09",
                      "pulse_duration": "500ms", "closed_sensor": "in_02",
                      "open_sensor": "in_03"}, (), False),
        ("template", {"platform": "irrigation", "name": "Garden",
                      "water_sources": [{"id": "pump", "name": "Pump", "outputs": ["OUT_10"],
                                         "output_start_delay": "2s", "output_stop_delay": "2s",
                                         "pump_switch_off_during_valve_open_delay": True,
                                         "pump_start_pump_delay": "1s",
                                         "pump_start_valve_delay": "1s",
                                         "pump_stop_pump_delay": "1s",
                                         "pump_stop_valve_delay": "1s"}],
                      "zones": [{"id": "lawn", "name": "Lawn", "valve_id": "OUT_11",
                                 "run_duration": "10min", "enabled": False, "run_every_n": 2}],
                      "standby": True, "valve_open_delay": "3s", "valve_overlap": "5s",
                      "multiplier": 1.5, "repeat": 2, "auto_advance": False, "reverse": True,
                      "pause_timeout": "1h", "schedule": [{"time": "06:00", "days": "weekend"}]},
         (), False),
        ("remote_devices", {"id": "kitchen", "name": "Kitchen", "protocol": "mqtt",
                            "device_type": "boneio_black",
                            "mqtt": {"outputs": [{"id": "out_01", "name": "Lamp"}],
                                     "covers": [{"id": "blind", "name": "Blind"}]}}, (), False),
        ("remote_devices", {"id": "esp", "name": "ESP", "protocol": "esphome_api",
                            "device_type": "esphome",
                            "esphome_api": {"host": "10.0.0.5", "port": 6054, "password": "p",
                                            "encryption_key": "k",
                                            "switches": [{"id": "relay", "name": "R", "key": 1}],
                                            "lights": [{"id": "led", "key": 2, "supports_brightness": True,
                                                        "supports_color_temp": True, "supports_rgb": True,
                                                        "supports_rgbw": True, "min_mireds": 153,
                                                        "max_mireds": 500.5}],
                                            "covers": [{"id": "shade", "key": 3, "supports_position": True,
                                                        "supports_tilt": False}]}}, (), False),
        ("remote_devices", {"id": "strip", "name": "Strip", "protocol": "wled", "device_type": "wled",
                            "wled": {"host": "10.0.0.6", "port": 8080}}, (), False),
        ("remote_outputs", {"remote_source": "mqtt", "device_id": "kitchen", "output_id": "out_01"},
         (), False),
        ("remote_outputs", {"id": "garden_pump", "name": "Pump", "remote_source": "esphome_api",
                            "device_id": "esp", "output_id": "relay", "output_type": "valve",
                            "show_in_ha": True, "area": "garden", "on_disconnect": "turn_off",
                            "momentary_turn_on": "2s", "momentary_turn_off": "1s",
                            "adjustable_duration": True, "duration_default": "5min",
                            "duration_min": "1min", "duration_max": "1h", "duration_unit": "min",
                            "interlock_group": ["pumps"], "enforce_interlock": True}, (), False),
        ("output_group", {"id": "all_lights", "outputs": ["OUT_01", "OUT_02"]}, (), False),
        ("output_group", {"id": "hall", "name": "Hall", "outputs": ["OUT_03"],
                          "all_on_behaviour": True, "output_type": "light"}, (), False),
        ("irrigation", {"id": "garden", "name": "Garden",
                        "water_sources": [{"id": "pump", "outputs": ["OUT_10"],
                                           "output_start_delay": "2s"}],
                        "standby": True, "valve_open_delay": "3s", "valve_overlap": "5s",
                        "multiplier": 1.5, "repeat": 2, "auto_advance": False, "reverse": True,
                        "pause_timeout": "1h", "schedule": [{"time": "06:00", "days": "weekend"}],
                        "zones": [{"id": "lawn", "name": "Lawn", "valve_id": "OUT_11",
                                   "run_duration": "10min", "enabled": False, "run_every_n": 2}]},
         (), False),
        ("web", {"port": 8091, "proxy_port": 8443, "expose": "proxy",
                 "cloud": {"enabled": True, "declined": False, "pwa_name": "Home"},
                 "security": {"map_tiles": True, "frame_ancestors": ["https://ha.local"]},
                 "auth": {"username": "u", "password": "p", "allow_anonymous": False}}, (), False),
        ("mqtt", {"enabled": True, "host": "broker.local", "username": "u", "password": "p",
                  "port": 8883, "ha_discovery": {"enabled": False, "topic_prefix": "ha"},
                  "send_boneio_autodiscovery": False, "receive_boneio_autodiscovery": False,
                  "update_channel": "dev",
                  "tls": {"enabled": True, "ca_certs": "/c", "certfile": "/cert", "keyfile": "/key",
                          "insecure": True}}, (), False),
        ("boneio", {"config_version": 7, "name": "Home", "version": "1.1", "device_type": "24x16A",
                    "ha_child_devices": True, "ha_child_devices_naming": "device_name_area",
                    "serial_override": "blk265f49"}, (), False),
        ("sensor", {"id": "t1", "name": "Floor", "area": "hall", "address": "28-0000098c7df0", "show_in_ha": False,
                    "filters": [{"offset": 0.5}, {"round": 1}], "update_interval": "30s",
                    "unit_of_measurement": "°F"}, (), False),
        ("adc", {"name": "Tank", "id": "tank", "pin": "P9_33", "area": "a", "update_interval": "10s",
                 "show_in_ha": False, "filters": [{"multiply": 2}]}, (), False),
        ("ina219", {"id": "ina", "address": 65, "update_interval": "5s",
                    "sensors": [{"id": "I", "device_class": "current", "filters": [{"round": 3}]}]},
         (), False),
        ("ina226", {"id": "ina", "address": "0x41", "sensors": [{"id": "V", "device_class": "voltage"}]},
         (), False),
        ("lm75", {"id": "board", "address": 73, "update_interval": "2min", "filters": [{"round": 1}],
                  "unit_of_measurement": "°C"}, (), False),
        ("mcp9808", {"id": "mcp", "address": "0x18", "update_interval": "1min"}, (), False),
        ("modbus", {"id": "rs485", "port": "uart4", "baudrate": 19200, "stopbits": 2, "bytesize": 7, "parity": "E",
                    "timeout": "2s", "inter_device_delay": "10ms"}, (), False),
        ("modbus_devices", {"name": "Air", "area": "living", "id": "air_1", "address": 3, "model": "cwt",
                            "update_interval": "1min", "entity_labels": {"temperature": "Temp"},
                            "sensors_filters": {"temperature": [{"offset": -1}],
                                                "humidity": [{"round": 0}]}}, (), False),
        ("modbus_devices", {"address": "4", "model": "liquid-sensor",
                            "data": {"width": "1.2m", "length": 2}}, (), False),
        ("can", {"enabled": True, "channel": "can1", "bitrate": 250000, "node_id": 5, "mode": "slave",
                 "auto_setup": False, "restart_on_error": False}, (), False),
        ("mcp23017", {"id": "mcp1", "address": 32, "init_sleep": "1s", "inverted": True}, (), False),
        ("pcf8575", {"id": "pcf1", "address": 33, "init_sleep": "500ms"}, (), False),
        ("pca9685", {"id": "pca1", "address": 64, "init_sleep": "0s"}, (), False),
        ("virtual_energy_sensor", {"id": "fridge", "name": "Fridge", "output_id": "OUT_01",
                                   "sensor_type": "power", "power_usage": "150W", "area": "kitchen"},
         (), False),
        ("virtual_energy_sensor", {"name": "Garden water", "output_id": "OUT_02", "sensor_type": "water",
                                   "flow_rate": "12 l/min"}, (), False),
        ("oled", {"enabled": True, "screens": ["uptime", "extra_sensors"],
                  "extra_screen_sensors": [{"sensor_type": "modbus", "modbus_id": "Air 1",
                                            "sensor_id": "Temp"}],
                  "screensaver_timeout": "5min"}, (), False),
        ("location", {"latitude": 52.4, "longitude": 16.9, "elevation": 80}, (), False),
        ("lox_udp", {"enabled": True, "host": "10.0.0.10", "send_port": 5000, "listen_port": 5001},
         (), False),
        ("logger", {"default": "INFO", "logs": {"boneio.core": "debug"}}, (), False),
        ("areas", {"id": "living", "name": "Living room"}, (), False),
    ]
    return bases


def _in_focus(path: tuple, focus: tuple, typed_only: bool) -> bool:
    if path[: len(focus)] != focus:
        return False
    if not typed_only:
        return True
    if focus == ("actions",):  # the click lists themselves, not the action again
        return len(path) <= 3
    if focus[-1] == "conditions":  # the group itself; its conditions have their own bases
        return len(path) <= len(focus) + 2
    return len(path) == len(focus) + 1 and path[-1] in TYPED_FIELDS


def _resolved(node, defs: dict):
    if isinstance(node, dict):
        if "$ref" in node:
            node = {**defs[node["$ref"].rsplit("/", 1)[1]], **{k: v for k, v in node.items() if k != "$ref"}}
        return {k: _resolved(v, defs) for k, v in node.items()}
    if isinstance(node, list):
        return [_resolved(v, defs) for v in node]
    return node


def _flat_actions(node):
    """An action union read as one object with every field of every type."""
    if isinstance(node, list):
        return [_flat_actions(v) for v in node]
    if not isinstance(node, dict):
        return node
    node = {k: _flat_actions(v) for k, v in node.items()}
    branches = node.get("oneOf", [])
    if not branches or not all("action" in b.get("properties", {}) for b in branches):
        return node
    fields: dict = {}
    for branch in branches:
        for name, field in branch["properties"].items():
            if name != "action":
                assert fields.setdefault(name, field) == field, f"{name} differs between action types"
    spellings = sorted(v for b in branches for v in b["properties"]["action"]["enum"])
    fields["action"] = {"type": "string", "enum": spellings}
    rest = {k: v for k, v in node.items() if k != "oneOf"}
    return {**rest, "type": ["object", "string"], "properties": fields}


@functools.cache
def _schema(section: str) -> dict:
    node, defs = section_schema(section)
    return _flat_actions(_resolved(node, defs))


def _is_list(section: str) -> bool:
    return "array" in _schema(section)["type"]


def _data(section: str, entry: dict) -> object:
    """A list section holds entries; a dict section is the entry itself."""
    return [entry] if _is_list(section) else entry


def _mutations(value: Any, node: dict, path: tuple = ()):
    """Every (path, mutant) the section's schema reaches from ``value``."""
    if "properties" in node and isinstance(value, dict):
        for field, field_node in node["properties"].items():
            for mutant in MUTANTS:
                if mutant is REMOVED and field not in value:
                    continue
                yield path + (field,), mutant
            if field in value:
                yield from _mutations(value[field], field_node, path + (field,))
    elif "items" in node and isinstance(value, list):
        for i, item in enumerate(value):
            for mutant in MUTANTS[1:]:
                yield path + (i,), mutant
            yield from _mutations(item, node["items"], path + (i,))


def _apply(entry: dict, path: tuple, mutant: Any) -> dict:
    entry = copy.deepcopy(entry)
    parent = entry
    for key in path[:-1]:
        parent = parent[key]
    if mutant is REMOVED:
        del parent[path[-1]]
    else:
        parent[path[-1]] = copy.deepcopy(mutant)
    return entry


def _name(section: str, base: dict, focus: tuple, typed_only: bool) -> str:
    part = base
    for key in focus:
        part = part[key]
    kind = part.get("action") or part.get("type") if isinstance(part, dict) else None
    return "-".join(str(x) for x in (section, *focus, kind) if x is not None and x != 0)


def _cases(section: str, base: dict, focus: tuple, typed_only: bool) -> list[tuple[tuple, Any, object]]:
    rule = _schema(section)
    rule = rule["items"] if _is_list(section) else rule
    out = []
    for path, mutant in _mutations(base, rule):
        if not _in_focus(path, focus, typed_only):
            continue
        out.append((path, mutant, _data(section, _apply(base, path, mutant))))
    return out


def _key(index: int, base: tuple) -> str:
    return f"{index}:{_name(*base)}"


def _verdicts(section: str, base: tuple) -> str:
    """One character per case: 1 when the model refuses it."""
    return "".join("1" if validate_section(section, data, BONEIO) else "0" for _, _, data in _cases(*base))


_BASES = _bases()


@pytest.mark.parametrize("index", range(len(_BASES)), ids=[_name(*b) for b in _BASES])
def test_what_the_models_refuse_has_not_moved(index):
    base = _BASES[index]
    section = base[0]
    assert validate_section(section, _data(section, base[1]), BONEIO) == [], "the base must be valid"
    cases = _cases(*base)
    assert len(cases) > 20
    expected = json.loads(VERDICTS.read_text())[_key(index, base)]
    found = _verdicts(section, base)
    moved = [(path, mutant, "now refused" if now == "1" else "now accepted")
             for (path, mutant, _), was, now in zip(cases, expected, found) if was != now]
    assert len(found) == len(expected) and not moved, moved[:10]


def test_what_get_api_config_serves_is_accepted():
    """The panel saves a section as it was served: read, board-merged."""
    from fastapi.encoders import jsonable_encoder

    from boneio.core.utils.timeperiod import plain_time_periods

    checked = 0
    for path in sorted(glob.glob("boneio/factory_config/*/*/config.yaml")):
        raw, _ = _run_config_migrations(load_yaml_file(path), config_file=None)
        doc = merge_board_config(_read_sections(raw))
        served = json.loads(json.dumps(jsonable_encoder(plain_time_periods(doc))))
        for section in models.SECTIONS & served.keys():
            assert validate_section(section, served[section], served["boneio"]) == [], (path, section)
            checked += 1
    assert checked > 20


@pytest.mark.parametrize("section, base", [pytest.param(b[0], b[1], id=_name(*b)) for b in _BASES])
def test_each_base_entry_as_get_serves_it_is_accepted(section, base):
    """What the panel posts back after a read, for sections the factory configs lack."""
    from fastapi.encoders import jsonable_encoder

    from boneio.core.utils.timeperiod import plain_time_periods

    doc = _read_sections({"boneio": dict(BONEIO), section: _data(section, copy.deepcopy(base))})
    served = json.loads(json.dumps(jsonable_encoder(plain_time_periods(merge_board_config(doc)))))
    assert validate_section(section, served[section], served["boneio"]) == []


def test_duplicate_output_ids_are_refused():
    entries = [{"id": "lamp", "kind": "gpio", "pin": 5, "output_type": "light"},
               {"id": "lamp", "kind": "gpio", "pin": 6, "output_type": "switch"}]
    assert validate_section("output", entries, BONEIO) == ["output: Output IDs are not unique."]


def test_remote_input_actions_are_checked():
    entry = {"remote_source": "mqtt", "device_id": "shelly", "input_id": "in0",
             "actions": {"pressed": [{"action": "output"}]}}
    assert validate_section("remote_inputs", [entry], BONEIO) == [
        "remote_inputs[0].actions.pressed[0].boneio_output: Field required"
    ]


def test_a_virtual_switch_setting_itself_is_refused():
    entry = {"name": "Night", "actions": {"on_turn_on": [
        {"action": "virtual_switch", "boneio_virtual_switch": "night"}]}}
    assert validate_section("virtual_switch", [entry], BONEIO)


def test_virtual_switches_resolving_to_one_id_are_refused():
    assert validate_section("virtual_switch", [{"name": "Salon"}, {"name": "salon!"}], BONEIO)


def test_a_protocol_block_on_another_protocol_is_refused():
    entry = {"id": "esp", "name": "ESP", "protocol": "esphome_api", "wled": {"host": "h"}}
    assert validate_section("remote_devices", [entry], BONEIO)


def test_duplicate_output_group_ids_are_refused():
    groups = [{"id": "all", "outputs": ["OUT_01"]}, {"id": "all", "outputs": ["OUT_02"]}]
    assert validate_section("output_group", groups, BONEIO) == ["output_group: Output IDs are not unique."]


def test_a_certificate_without_its_key_is_refused():
    assert validate_section("mqtt", {"host": "b", "tls": {"enabled": True, "certfile": "/cert"}}, BONEIO)


def test_web_may_be_null():
    assert validate_section("web", None, BONEIO) == []


@pytest.mark.parametrize(
    "section, entry",
    [
        ("modbus_devices", {"address": 1, "model": "liquid-sensor", "sensors_filters": {}}),
        ("modbus_devices", {"address": 1, "model": "cwt", "data": {"width": 1}}),
        ("virtual_energy_sensor", {"name": "n", "output_id": "o", "sensor_type": "water", "power_usage": 5}),
        ("virtual_energy_sensor", {"name": "n", "output_id": "o", "sensor_type": "power", "flow_rate": 5}),
    ],
)
def test_a_block_for_another_type_is_refused(section, entry):
    assert validate_section(section, [entry], BONEIO)


def test_the_modbus_update_interval_is_at_least_a_second():
    # Start-up holds it too; migration v8 raised what was lower.
    entry = {"address": 1, "model": "cwt", "update_interval": "500ms"}
    errors = validate_section("modbus_devices", [entry], BONEIO)
    assert len(errors) == 1 and "update_interval" in errors[0] and "at least 1s" in errors[0]
    assert validate_section("modbus_devices", [{**entry, "update_interval": "1s"}], BONEIO) == []


def test_a_binary_sensor_keeps_its_name():
    # Start-up reads it as the entity's name; a model without the field would
    # drop it with the rest of what it does not know.
    from boneio.core.config.models.inputs import SECTION_ADAPTERS

    adapter = SECTION_ADAPTERS["binary_sensor"]
    entry = {"name": "Kontaktron", "boneio_input": "in_01"}
    assert adapter.dump_python(adapter.validate_python([entry]))[0]["name"] == "Kontaktron"
    assert validate_section("binary_sensor", [entry], BONEIO) == []


def test_every_factory_config_section_is_accepted_as_written():
    """What an agent or a person reads in the file is what a save accepts."""
    checked = 0
    for path in sorted(glob.glob("boneio/factory_config/*/*/config.yaml")):
        raw, _ = _run_config_migrations(load_yaml_file(path), config_file=None)
        for section in models.SECTIONS & raw.keys():
            assert validate_section(section, raw[section], raw["boneio"]) == [], (path, section)
            checked += 1
    assert checked > 20


OLD_BOARD = {"config_version": 7, "name": "t", "version": 0.7, "device_type": "24x16A"}


@pytest.mark.parametrize(
    "entry, boneio, accepted",
    [
        # The cover board's map gives the type.
        ({"boneio_output": "01_up"}, {**BONEIO, "device_type": "cover", "version": 1.0}, True),
        # A 0.7 map does not, so the entry has to.
        ({"boneio_output": "out_01"}, OLD_BOARD, False),
        ({"boneio_output": "out_01", "output_type": "light"}, OLD_BOARD, True),
        # Without a board output nothing else can.
        ({"id": "r1", "kind": "gpio", "pin": 30}, BONEIO, False),
    ],
)
def test_an_output_takes_its_type_from_the_entry_or_the_board(entry, boneio, accepted):
    errors = validate_section("output", [entry], boneio)
    assert errors == ([] if accepted else ["output[0].output_type: required field"])


def test_start_up_refuses_an_output_with_no_type():
    from boneio.core.config.yaml_util import ConfigurationException, load_config_from_string

    config = (
        "boneio:\n  name: t\n  config_version: 7\n  device_type: 24x16A\n  version: 0.7\n"
        "output:\n  - boneio_output: out_01\n"
    )
    with pytest.raises(ConfigurationException, match=r"output\[0\]\.output_type: required field"):
        load_config_from_string(config)
    assert load_config_from_string(config + "    output_type: switch\n")["output"][0]["output_type"] == "switch"


def _write() -> None:
    VERDICTS.write_text(json.dumps(
        {_key(i, base): _verdicts(base[0], base) for i, base in enumerate(_BASES)}, indent=1
    ) + "\n")


if __name__ == "__main__":
    _write()


def test_after_a_downgrade_what_reads_is_kept():
    from boneio.exceptions import ConfigurationException

    doc = {
        "boneio": dict(BONEIO),
        "virtual_switch": [{"name": "Night"}, {"name": 7, "unknown_to_this_version": True}],
        "lox_udp": {"enabled": True},  # no host: the whole section goes
        "location": {"latitude": 52.4, "longitude": 16.9},
    }
    with pytest.raises(ConfigurationException, match="virtual_switch"):
        _read_sections(copy.deepcopy(doc))
    read = _read_sections(copy.deepcopy(doc), downgraded=True)
    assert [s["name"] for s in read["virtual_switch"]] == ["Night"]
    assert "lox_udp" not in read
    assert read["location"]["latitude"] == 52.4
