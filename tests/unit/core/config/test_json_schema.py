"""A section's schema made from its model reads to the panel as schema.yaml's did.

Each section moved to json_schema.FROM_MODELS is compared with what
schema_converter.py makes of the same section in schema.yaml; the only
differences allowed are the ones listed, each of them deliberate. The test
goes when schema.yaml does.

Two readings make the model's schema comparable: its ``$ref``s are resolved,
and an action union is read as the one object schema.yaml describes — every
field any action type has, each the same in every type that has it.
"""

from __future__ import annotations

import json

import pytest

from boneio.core.config.json_schema import FROM_MODELS, section_schema
from boneio.core.config.schema_converter import convert_cerberus_to_json_schema, load_schema_yaml

_FILTER_ITEM = {
    "additionalProperties": True,
    "propertyNames": {
        "enum": ["offset", "round", "multiply", "filter_out", "filter_out_greater", "filter_out_lower"]
    },
}

_ACTION = "items/properties/actions/properties/*/items/properties"
_CONDITION_BOUNDS = {
    "above": {"minimum": -90, "maximum": 90},
    "below": {"minimum": -90, "maximum": 90},
    "after_offset": {"minimum": -43200, "maximum": 43200},
    "before_offset": {"minimum": -43200, "maximum": 43200},
}


def _any_case(values: list[str]) -> list[str]:
    return sorted({c for v in values for c in (v, v.lower(), v.upper(), v.title())})


_OUTPUT_COMMANDS = ["TOGGLE", "ON", "OFF", "BRIGHTNESS_UP", "BRIGHTNESS_DOWN", "BRIGHTNESS_UP_CYCLE",
                    "BRIGHTNESS_DOWN_CYCLE", "SET_BRIGHTNESS", "CYCLE_COLOR", "CYCLE_PRESET"]
_COVER_COMMANDS = ["TOGGLE", "OPEN", "CLOSE", "STOP", "TOGGLE_OPEN", "TOGGLE_CLOSE", "SMART_TOGGLE",
                   "SET_POSITION", "TILT", "TILT_OPEN", "TILT_CLOSE"]


def _input_added() -> dict:
    """What the models say about inputs and actions that schema.yaml did not."""
    added = {
        # Ranges the models check, which schema.yaml left to the validators.
        f"{_ACTION}/brightness": {"minimum": 0, "maximum": 255},
        f"{_ACTION}/brightness_step": {"minimum": 1, "maximum": 50},
        f"{_ACTION}/probability": {"minimum": 0, "maximum": 1, "type": ["integer", "number", "string"]},
        f"{_ACTION}/data/properties/position": {"minimum": 0, "maximum": 100},
        f"{_ACTION}/data/properties/always_open_till": {"minimum": 0, "maximum": 100},
        # Read in any case; schema.yaml listed upper case only, so the editor
        # flagged the factory configs' own "toggle_open".
        f"{_ACTION}/action_output": {"enum": _any_case(_OUTPUT_COMMANDS)},
        f"{_ACTION}/action_cover": {"enum": _any_case(_COVER_COMMANDS)},
    }
    for field, bounds in _CONDITION_BOUNDS.items():
        added[f"{_ACTION}/condition/properties/{field}"] = bounds
        added[f"{_ACTION}/conditions/properties/list/items/properties/{field}"] = bounds
    return added


#: What the model says that schema.yaml did not, by section and path.
ADDED = {
    "modbus_devices": {
        "items/properties/entity_labels": {"additionalProperties": {"type": "string"}},
        "items/properties/sensors_filters/properties/temperature/items": _FILTER_ITEM,
        "items/properties/sensors_filters/properties/humidity/items": _FILTER_ITEM,
    },
    "event": _input_added(),
    "binary_sensor": {
        **_input_added(),
        # Read at start-up as the entity's name; schema.yaml never listed it.
        "items/properties": {"name": {"type": "string", "description": "Name to use in HA.", "title": "Name"}},
    },
}

#: What schema.yaml said that the model does not, by section and path.
REMOVED = {
    "event": {
        f"{_ACTION}/probability": {"type": ["number", "string"]},
        f"{_ACTION}/data": {"default": {}},
        f"{_ACTION}/action_output": {"enum": _OUTPUT_COMMANDS},
        f"{_ACTION}/action_cover": {"enum": _COVER_COMMANDS},
    },
}
REMOVED["binary_sensor"] = REMOVED["event"]


def _nodes(schema: dict, path: str):
    """Every node at ``path``; a ``*`` part matches each key at its level."""
    nodes = [schema]
    for part in path.split("/"):
        nodes = [child for node in nodes for key, child in node.items() if part in ("*", key)]
    return nodes


def _without(schema: dict, keys_by_path: dict) -> dict:
    schema = json.loads(json.dumps(schema))
    for path, keys in keys_by_path.items():
        nodes = _nodes(schema, path)
        assert nodes, path
        for node in nodes:
            for key, value in keys.items():
                found = node.pop(key)
                assert found == value, f"{path}/{key}"
    return schema


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


def _without_examples(node):
    """schema.yaml's ``examples`` only repeat the first allowed value."""
    if isinstance(node, dict):
        return {k: _without_examples(v) for k, v in node.items() if k != "examples"}
    if isinstance(node, list):
        return [_without_examples(v) for v in node]
    return node


@pytest.mark.parametrize("section", sorted(FROM_MODELS))
def test_model_schema_matches_schema_yaml(section):
    converted = convert_cerberus_to_json_schema(load_schema_yaml())["properties"][section]
    converted = _without(_without_examples(converted), REMOVED.get(section, {}))
    node, defs = section_schema(section)
    model = _flat_actions(_resolved(node, defs))
    assert _without(model, ADDED.get(section, {})) == converted


@pytest.mark.parametrize("section", sorted(FROM_MODELS))
def test_model_schema_has_nothing_the_panel_cannot_read(section):
    node, defs = section_schema(section)
    text = json.dumps([node, defs])
    for keyword in ('"anyOf"', '"null"', '"ge"', '"le"'):
        assert keyword not in text
    assert '"$defs"' not in json.dumps(node)
    # Every reference points to a definition served at the document's root.
    for ref in (line.split('"')[0] for line in text.split('"$ref": "')[1:]):
        assert ref.startswith("#/$defs/") and ref.removeprefix("#/$defs/") in defs


def test_an_action_type_lists_only_its_own_fields():
    _, defs = section_schema("event")
    mqtt = defs["MqttAction"]
    assert {"topic", "action_mqtt_msg"} <= set(mqtt["properties"])
    assert not {"action_output", "action_cover", "boneio_id"} & set(mqtt["properties"])
    assert set(mqtt["required"]) == {"action", "topic", "action_mqtt_msg"}
    # A field the type makes required keeps the description it has on every type.
    assert defs["OutputAction"]["properties"]["boneio_output"]["description"] == "Output ID"


def test_modbus_device_models_are_not_in_the_schema():
    # A new device file must not need a schema rebuild: the model is checked
    # against boneio/modbus/devices/ when the config is validated.
    node, _ = section_schema("modbus_devices")
    assert "enum" not in node["items"]["properties"]["model"]
