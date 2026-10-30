"""The panel's JSON Schema for a section, made from the section's model.

The panel reads one dialect, the one schema_converter.py writes from
schema.yaml: no ``$ref`` (the config editor hands each section's subtree to
monaco-yaml on its own, without the root's ``$defs``), no ``anyOf`` (the forms
read ``type``), ``"string"`` beside every type (a value may be an
``!include``), a boolean as a ``oneOf`` with the YAML words for it, and a
time period as ``x-timeperiod``. pydantic's own output is rewritten into that.
"""

from __future__ import annotations

import importlib
from typing import Any

from pydantic.json_schema import GenerateJsonSchema, NoDefault

from boneio.core.config.models import _MODULES
from boneio.core.utils import TimePeriod

#: Sections whose schema comes from the model; the rest still from schema.yaml.
FROM_MODELS = frozenset({"modbus_devices"})

_BOOLEAN = [
    {"type": "boolean"},
    {"type": "string", "enum": ["yes", "no", "true", "false", "on", "off"], "x-yaml-boolean": True},
]


class _Generator(GenerateJsonSchema):
    def is_instance_schema(self, schema: Any) -> dict:
        if schema["cls"] is TimePeriod:
            return {"type": "number", "x-timeperiod": True}
        return super().is_instance_schema(schema)

    def get_default_value(self, schema: Any) -> Any:
        factory = schema.get("default_factory")
        if factory and not schema.get("default_factory_takes_data"):
            return factory()
        return super().get_default_value(schema)


def section_schema(section: str) -> dict:
    """The schema of one section as the panel reads it."""
    module = importlib.import_module(f"boneio.core.config.models.{_MODULES[section]}")
    raw = module.SECTION_ADAPTERS[section].json_schema(schema_generator=_Generator)
    return _panel(raw, raw.get("$defs", {}), section)


def _panel(node: dict, defs: dict, name: str | None = None) -> dict:
    if "$ref" in node:
        # Keys beside the reference (a field's description, default) win.
        node = {**defs[node["$ref"].rsplit("/", 1)[1]], **node}
        del node["$ref"]
    node = {k: v for k, v in node.items() if k not in ("$defs", "title")}
    if "default" in node and node["default"] is None:
        del node["default"]

    if "anyOf" in node:
        # An optional field is one that may be left out, not one that may be null.
        branches = [b for b in node.pop("anyOf") if b != {"type": "null"}]
        if len(branches) == 1:
            return _panel({**branches[0], **node}, defs, name)
        if not all(set(b) == {"type"} for b in branches):
            raise ValueError(f"{name}: a union the panel cannot read")
        node["type"] = [b["type"] for b in branches]

    kind = node.get("type")
    if kind == "boolean":
        del node["type"]
        node = {"oneOf": _BOOLEAN, **node}
    elif kind is not None:
        kinds = sorted({kind, "string"} if isinstance(kind, str) else {*kind, "string"})
        node["type"] = kinds[0] if len(kinds) == 1 else kinds

    if "properties" in node:
        node["properties"] = {k: _panel(v, defs, k) for k, v in node["properties"].items()}
    if "items" in node:
        node["items"] = _panel(node["items"], defs)
    if isinstance(node.get("additionalProperties"), dict):
        node["additionalProperties"] = _panel(node["additionalProperties"], defs)
    if "description" in node and name:
        node["title"] = name.replace("_", " ").capitalize()
    return node
