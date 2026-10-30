"""A section's schema made from its model reads to the panel as schema.yaml's did.

Each section moved to json_schema.FROM_MODELS is compared with what
schema_converter.py makes of the same section in schema.yaml; the only
differences allowed are the ones listed, each of them deliberate. The test
goes when schema.yaml does.
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

#: What the model says that schema.yaml did not, by section and path.
ADDED = {
    "modbus_devices": {
        "items/properties/entity_labels": {"additionalProperties": {"type": "string"}},
        "items/properties/sensors_filters/properties/temperature/items": _FILTER_ITEM,
        "items/properties/sensors_filters/properties/humidity/items": _FILTER_ITEM,
    },
}


def _without(schema: dict, added: dict) -> dict:
    schema = json.loads(json.dumps(schema))
    for path, keys in added.items():
        node = schema
        for part in path.split("/"):
            node = node[part]
        for key, value in keys.items():
            assert node.pop(key) == value, f"{path}/{key}"
    return schema


@pytest.mark.parametrize("section", sorted(FROM_MODELS))
def test_model_schema_matches_schema_yaml(section):
    converted = convert_cerberus_to_json_schema(load_schema_yaml())["properties"][section]
    assert _without(section_schema(section), ADDED.get(section, {})) == converted


@pytest.mark.parametrize("section", sorted(FROM_MODELS))
def test_model_schema_has_nothing_the_panel_cannot_read(section):
    text = json.dumps(section_schema(section))
    for keyword in ('"$ref"', '"$defs"', '"anyOf"', '"null"'):
        assert keyword not in text


def test_modbus_device_models_are_not_in_the_schema():
    # A new device file must not need a schema rebuild: the model is checked
    # against boneio/modbus/devices/ when the config is validated.
    model = section_schema("modbus_devices")["items"]["properties"]["model"]
    assert "enum" not in model
