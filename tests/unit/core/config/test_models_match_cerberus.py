"""The Pydantic models never accept a section the Cerberus schema refuses.

Start-up still validates config.yaml with Cerberus, while a save of a section
that has a model is checked by the model and written as posted. A section the
model let through and Cerberus refuses would stop the controller at its next
start. So every factory config, and thousands of mutations of a valid entry
— each field of each level set to a wrong value or removed — go through both,
and the model must refuse whatever Cerberus refuses.

The model may refuse more. What it refuses on purpose is listed in
STRICTER_ON_PURPOSE; anything else it refuses that Cerberus accepts fails here
too, so a difference is always a decision rather than an accident.
"""

from __future__ import annotations

import copy
import glob
import re
from typing import Any

import pytest

from boneio.core.config import models
from boneio.core.config.yaml_util import (
    _cerberus_section_errors,
    _get_schema,
    _run_config_migrations,
    _section_document,
    load_yaml_file,
    validate_section,
)

BONEIO = {"config_version": 7, "name": "t", "version": 1.1, "device_type": "24x16A"}

#: Fields the board mapping looks up; a wrong one fails the whole list.
MAPPED = {("boneio_input",), ("boneio_output",)}

#: Sections whose entries must resolve to distinct identifiers (from id, else
#: name). Batched, the copies of one entry would all collide; each gets an id
#: of its own instead, and mutations of id and name run alone.
RESOLVED_IDS = {"virtual_switch", "schedule", "output_group"}
IDENTITY = {("id",), ("name",)}

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
    mutated with another base, and every case costs a Cerberus validation.
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
        ("sensor", {"id": "t1", "name": "Floor", "area": "hall", "address": "28-0000", "show_in_ha": False,
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
        ("modbus", {"uart": "uart4", "baudrate": 19200, "stopbits": 2, "bytesize": 7, "parity": "E",
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


def _mutations(value: Any, rule: dict, path: tuple = ()):
    """Every (path, mutant) the schema rule for ``value`` reaches."""
    if rule.get("type") == "dict" and isinstance(rule.get("schema"), dict) and isinstance(value, dict):
        for field, field_rule in rule["schema"].items():
            for mutant in MUTANTS:
                if mutant is REMOVED and field not in value:
                    continue
                yield path + (field,), mutant
            if field in value and isinstance(field_rule, dict):
                yield from _mutations(value[field], field_rule, path + (field,))
    elif rule.get("type") == "list" and isinstance(rule.get("schema"), dict) and isinstance(value, list):
        for i, item in enumerate(value):
            for mutant in MUTANTS[1:]:
                yield path + (i,), mutant
            yield from _mutations(item, rule["schema"], path + (i,))


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


def _verdicts(section: str, entries: list) -> tuple[list[str], list[str]]:
    cerberus = _cerberus_section_errors(section, _section_document(section, entries, BONEIO))
    model = validate_section(section, entries, BONEIO)
    return cerberus, model


_INDEX = re.compile(r"^\w+\[(\d+)\]|index (\d+)")


def _by_entry(errors: list[str]) -> dict[int, list[str]] | None:
    """Errors keyed by the entry they are about; None if one names no entry."""
    found: dict[int, list[str]] = {}
    for error in errors:
        match = _INDEX.search(error)
        if match is None:
            return None
        found.setdefault(int(match.group(1) or match.group(2)), []).append(error)
    return found


def _verdicts_each(section: str, entries: list) -> list[tuple[list[str], list[str]]]:
    """``_verdicts`` for every entry, validated as one list where that is safe.

    A Cerberus validation costs about the same for one entry as for fifty, so
    the entries go through together and the errors are split by index. When
    an error names no entry (the board mapping refusing the whole list), each
    entry is validated on its own instead.
    """
    cerberus, model = (_by_entry(e) for e in _verdicts(section, entries))
    if cerberus is None or model is None:
        return [_verdicts(section, [entry]) for entry in entries]
    return [(cerberus.get(i, []), model.get(i, [])) for i in range(len(entries))]


#: Where the model refuses what Cerberus lets through, and why that is right:
#: (end of the error's path, or "" for any; text in the error message).
STRICTER_ON_PURPOSE = [
    # required_if in the Cerberus schema only runs for a field that is
    # present, so an action missing what its type needs passes there.
    ("", "Field required"),
    # An action without `action` passes Cerberus (nothing requires it) and
    # does nothing at runtime; the model cannot tell which action it is.
    ("", "Unable to extract tag using discriminator"),
    # Cerberus takes True for an integer (bool is an int in Python).
    ("", "Input should be a valid integer"),
    ("", "Input should be a valid number"),
    # With boneio_input set, Cerberus checks the pin the board mapping wrote
    # over the one in the entry; the model checks what was written.
    (".pin", ""),
    ("", "null value not allowed: pin"),
    # min: 1s in the schema never ran (TimePeriod against a string).
    (".update_interval", "at least 1s"),
]


def _on_purpose(errors: list[str]) -> bool:
    def explained(error: str) -> bool:
        where, _, message = error.partition(": ")
        # A string-or-integer field reports each member of the union; True is
        # refused as an integer (above), and so as a string too.
        if where.endswith(".str") and "Input should be a valid string" in message:
            return any(e.startswith(where[:-4] + ".int: Input should be a valid integer") for e in errors)
        return any(where.endswith(end) and text in message for end, text in STRICTER_ON_PURPOSE)

    return all(explained(e) for e in errors)


def test_every_factory_config_gets_the_same_verdict():
    checked = 0
    for path in sorted(glob.glob("boneio/factory_config/*/*/config.yaml")):
        raw, _ = _run_config_migrations(load_yaml_file(path), config_file=None)
        for section in models.SECTIONS & raw.keys():
            cerberus, model = _verdicts(section, raw[section])
            assert (not cerberus) == (not model), (path, section, cerberus, model)
            checked += 1
    assert checked > 20


def _name(section: str, base: dict, focus: tuple, typed_only: bool) -> str:
    part = base
    for key in focus:
        part = part[key]
    kind = part.get("action") or part.get("type") if isinstance(part, dict) else None
    return "-".join(str(x) for x in (section, *focus, kind) if x is not None and x != 0)


def test_what_get_api_config_serves_is_accepted():
    """The panel saves a section as it was served: normalized, board-merged."""
    import json

    from fastapi.encoders import jsonable_encoder

    from boneio.core.config.yaml_util import CustomValidator, merge_board_config
    from boneio.core.utils.timeperiod import plain_time_periods

    checked = 0
    for path in sorted(glob.glob("boneio/factory_config/*/*/config.yaml")):
        raw, _ = _run_config_migrations(load_yaml_file(path), config_file=None)
        validator = CustomValidator(_get_schema(), purge_unknown=True)
        doc = merge_board_config(validator.normalized(raw, always_return_document=True))
        served = json.loads(json.dumps(jsonable_encoder(plain_time_periods(doc))))
        for section in models.SECTIONS & served.keys():
            assert validate_section(section, served[section], served["boneio"]) == [], (path, section)
            checked += 1
    assert checked > 20


def _is_list(section: str) -> bool:
    return _get_schema()[section]["type"] == "list"


def _data(section: str, entry: dict) -> object:
    """A list section holds entries; a dict section is the entry itself."""
    return [entry] if _is_list(section) else entry


@pytest.mark.parametrize(
    "section, base, focus, typed_only", [pytest.param(*b, id=_name(*b)) for b in _bases()]
)
def test_the_model_refuses_whatever_cerberus_refuses(section, base, focus, typed_only):
    assert _verdicts(section, _data(section, base)) == ([], []), "the base must be valid for both"
    rule = _get_schema()[section]["schema"] if _is_list(section) else _get_schema()[section]
    lenient, stricter = [], []
    mutations = [(p, m) for p, m in _mutations(base, rule) if _in_focus(p, focus, typed_only)]
    assert len(mutations) > 20
    # Mutating what the board mapping looks up breaks it for the whole list;
    # a dict section has no list to batch into.
    solo = MAPPED | (IDENTITY if section in RESOLVED_IDS else set())
    if not _is_list(section):
        solo = {p for p, _ in mutations}
    alone = [(p, m) for p, m in mutations if p in solo]
    together = [(p, m) for p, m in mutations if p not in solo]
    batch = [_apply(base, p, m) for p, m in together]
    if section in RESOLVED_IDS:
        for i, entry in enumerate(batch):
            entry["id"] = f"batch_{i}"
    verdicts = _verdicts_each(section, batch) if batch else []
    verdicts += [_verdicts(section, _data(section, _apply(base, p, m))) for p, m in alone]
    for (path, mutant), (cerberus, model) in zip(together + alone, verdicts):
        if cerberus and not model:
            lenient.append((path, mutant, cerberus))
        elif model and not cerberus and not _on_purpose(model):
            stricter.append((path, mutant, model))
    assert not lenient, f"model accepts what Cerberus refuses: {lenient[:5]}"
    assert not stricter, f"model refuses what Cerberus accepts: {stricter[:5]}"


def test_duplicate_output_ids_are_refused_by_both():
    entries = [{"id": "lamp", "kind": "gpio", "pin": 5, "output_type": "light"},
               {"id": "lamp", "kind": "gpio", "pin": 6, "output_type": "switch"}]
    cerberus, model = _verdicts("output", entries)
    assert cerberus == model == ["output: Output IDs are not unique."]


def test_remote_input_actions_are_checked_though_cerberus_takes_any():
    """Stricter on purpose: Cerberus takes any dictionary of actions here."""
    entry = {"remote_source": "mqtt", "device_id": "shelly", "input_id": "in0",
             "actions": {"pressed": [{"action": "output"}]}}
    cerberus, model = _verdicts("remote_inputs", [entry])
    assert cerberus == []
    assert model == ["remote_inputs[0].actions.pressed[0].boneio_output: Field required"]


def test_a_virtual_switch_setting_itself_is_refused_by_both():
    entry = {"name": "Night", "actions": {"on_turn_on": [
        {"action": "virtual_switch", "boneio_virtual_switch": "night"}]}}
    cerberus, model = _verdicts("virtual_switch", [entry])
    assert cerberus and model


def test_virtual_switches_resolving_to_one_id_are_refused_by_both():
    cerberus, model = _verdicts("virtual_switch", [{"name": "Salon"}, {"name": "salon!"}])
    assert cerberus and model


@pytest.mark.parametrize("section, base", [pytest.param(b[0], b[1], id=_name(*b)) for b in _bases()])
def test_each_base_entry_as_get_serves_it_is_accepted(section, base):
    """What the panel posts back after a read, for sections the factory configs lack."""
    import json

    from fastapi.encoders import jsonable_encoder

    from boneio.core.config.yaml_util import CustomValidator, merge_board_config
    from boneio.core.utils.timeperiod import plain_time_periods

    schema = {k: _get_schema()[k] for k in (section, "boneio")}
    validator = CustomValidator(schema, purge_unknown=True)
    doc = {"boneio": dict(BONEIO), section: _data(section, copy.deepcopy(base))}
    doc = validator.normalized(doc, always_return_document=True)
    served = json.loads(json.dumps(jsonable_encoder(plain_time_periods(merge_board_config(doc)))))
    assert validate_section(section, served[section], served["boneio"]) == []


def test_a_protocol_block_on_another_protocol_is_refused_by_both():
    entry = {"id": "esp", "name": "ESP", "protocol": "esphome_api", "wled": {"host": "h"}}
    cerberus, model = _verdicts("remote_devices", [entry])
    assert cerberus and model


def test_duplicate_output_group_ids_are_refused_by_both():
    groups = [{"id": "all", "outputs": ["OUT_01"]}, {"id": "all", "outputs": ["OUT_02"]}]
    assert _verdicts("output_group", groups) == (["output_group: Output IDs are not unique."],) * 2


def test_a_certificate_without_its_key_is_refused_by_both():
    mqtt = {"host": "b", "tls": {"enabled": True, "certfile": "/cert"}}
    cerberus, model = _verdicts("mqtt", mqtt)
    assert cerberus and model


def test_web_may_be_null_for_both():
    assert _verdicts("web", None) == ([], [])


@pytest.mark.parametrize(
    "section, entry",
    [
        ("modbus_devices", {"address": 1, "model": "liquid-sensor", "sensors_filters": {}}),
        ("modbus_devices", {"address": 1, "model": "cwt", "data": {"width": 1}}),
        ("virtual_energy_sensor", {"name": "n", "output_id": "o", "sensor_type": "water", "power_usage": 5}),
        ("virtual_energy_sensor", {"name": "n", "output_id": "o", "sensor_type": "power", "flow_rate": 5}),
    ],
)
def test_a_block_for_another_type_is_refused_by_both(section, entry):
    cerberus, model = _verdicts(section, [entry])
    assert cerberus and model


def test_the_modbus_update_interval_minimum_holds_on_save_only():
    """min: 1s compares a TimePeriod with a string; Cerberus swallows the TypeError."""
    entry = {"address": 1, "model": "cwt", "update_interval": "500ms"}
    cerberus, model = _verdicts("modbus_devices", [entry])
    assert cerberus == []  # start-up still loads a config that has it
    assert len(model) == 1 and "update_interval" in model[0] and "at least 1s" in model[0]
    assert _verdicts("modbus_devices", [{**entry, "update_interval": "1s"}]) == ([], [])
