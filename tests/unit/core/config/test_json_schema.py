"""The panel's JSON Schema, as the section models make it, reads to the panel.

The panel's forms and the config editor read one dialect (see json_schema),
and an agent reads the same files through MCP.
"""

from __future__ import annotations

import json

import pytest

from boneio.core.config import models
from boneio.core.config.json_schema import section_schema
from boneio.core.config.models.base import details


@pytest.mark.parametrize("section", sorted(models.SECTIONS))
def test_model_schema_has_nothing_the_panel_cannot_read(section):
    node, defs = section_schema(section)
    text = json.dumps([node, defs])
    # A null only where the model marks one, in a list of types.
    for keyword in ('"anyOf"', '{"type": "null"}', '"type": "null"', '"ge"', '"le"', '"enum": []'):
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


def test_an_action_type_refuses_another_types_fields():
    _, defs = section_schema("event")
    refused = defs["OutputAction"]["propertyNames"]["not"]["enum"]
    assert {"topic", "action_mqtt_msg", "boneio_id"} <= set(refused)
    # Start-up fills action_cover: TOGGLE into every action; the model takes it.
    assert "action_cover" not in refused


def test_modbus_device_models_are_not_in_the_schema():
    # A new device file must not need a schema rebuild: the model is checked
    # against boneio/modbus/devices/ when the config is validated.
    node, _ = section_schema("modbus_devices")
    assert "enum" not in node["items"]["properties"]["model"]


def test_every_longer_explanation_is_of_a_field_that_exists():
    import importlib
    import inspect

    classes = {
        name: cls
        for module in set(models._MODULES.values())
        for name, cls in inspect.getmembers(importlib.import_module(f"boneio.core.config.models.{module}"), inspect.isclass)
    }
    for key in details()["fields"]:
        name, field = key.split(".")
        assert field in classes[name].model_fields, key
    assert set(details()["sections"]) <= models.SECTIONS


def test_the_longer_explanation_reaches_the_schema():
    node, _ = section_schema("web")
    text = node["properties"]["auth"]["properties"]["allow_anonymous"]["markdownDescription"]
    assert text.startswith("Allow unauthenticated access") and "DANGEROUS" in text
    _, defs = section_schema("event")
    assert "cancel" in defs["OutputAction"]["properties"]["delay"]["markdownDescription"]
