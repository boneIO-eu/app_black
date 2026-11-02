"""The panel's JSON Schema for a section, made from the section's model.

The panel reads one dialect, the one schema_converter.py writes from
schema.yaml: no ``anyOf`` (the forms read ``type``), ``"string"`` beside every
type (a value may be an ``!include``), a boolean as a ``oneOf`` with the YAML
words for it, and a time period as ``x-timeperiod``. pydantic's own output is
rewritten into that.

A definition used once is written in place, so the forms find the fields
where they look for them. One used more than once (an action type, used by
every click of every input) stays a ``$ref`` to ``#/$defs/<name>`` — written
in place it would be repeated in every list of actions. Every document the
schema is served in carries the ``$defs`` at its root: config.schema.json,
each ``<section>.schema.json``, and the config editor adds them to the
section schemas it hands monaco.
"""

from __future__ import annotations

import importlib
import json
from collections import Counter
from typing import Any

from pydantic.json_schema import GenerateJsonSchema

from boneio.core.config.models import _MODULES
from boneio.core.utils import TimePeriod

#: Sections whose schema comes from the model; the rest still from schema.yaml.
FROM_MODELS = frozenset({
    "modbus_devices", "event", "binary_sensor",
    "modbus", "can", "location", "lox_udp", "logger", "usage_history", "oled", "areas",
})

_BOOLEAN = [
    {"type": "boolean"},
    {"type": "string", "enum": ["yes", "no", "true", "false", "on", "off"], "x-yaml-boolean": True},
]


_BOUNDS = {"ge": "minimum", "le": "maximum", "gt": "exclusiveMinimum", "lt": "exclusiveMaximum"}


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


def section_schema(section: str) -> tuple[dict, dict]:
    """The schema of one section as the panel reads it.

    Returns:
        The section's schema, and the definitions its ``$ref``s point to.
    """
    module = importlib.import_module(f"boneio.core.config.models.{_MODULES[section]}")
    raw = module.SECTION_ADAPTERS[section].json_schema(schema_generator=_Generator)
    defs = raw.get("$defs", {})
    uses = Counter(ref.rsplit("/", 1)[1] for ref in _refs(raw))
    shared = {name for name, count in uses.items() if count > 1}
    node = _panel(raw, defs, shared, section)
    kept = {name: _panel(defs[name], defs, shared, name) for name in sorted(shared)}
    return node, kept


def _refs(node: Any):
    if isinstance(node, dict):
        if "$ref" in node:
            yield node["$ref"]
        for value in node.values():
            yield from _refs(value)
    elif isinstance(node, list):
        for value in node:
            yield from _refs(value)


def _panel(node: dict, defs: dict, shared: set, name: str | None = None) -> dict:
    ref = None
    if "$ref" in node:
        target = node["$ref"].rsplit("/", 1)[1]
        if target in shared:
            ref = target
            node = {k: v for k, v in node.items() if k != "$ref"}
        else:
            # Keys beside the reference (a field's description, default) win.
            node = {**defs[target], **node}
            del node["$ref"]
    node = {k: v for k, v in node.items() if k not in ("$defs", "title")}
    # pydantic leaves Field(ge=..., le=...) on a union under its own names.
    for bound, keyword in _BOUNDS.items():
        if bound in node:
            node[keyword] = node.pop(bound)
    if node.get("items") == {}:
        del node["items"]  # a plain ``list``
    if isinstance(node.get("default"), dict) and None in node["default"].values():
        # A model's default instance, with every field it leaves unset as null.
        node["default"] = {k: v for k, v in node["default"].items() if v is not None}
        if not node["default"]:
            del node["default"]
    if "default" in node and node["default"] is None:
        del node["default"]

    if node.pop("x-any-case", False):
        # Read in any case (the model lowers or uppers it), so the editor must
        # not flag IN_01 or toggle_open; the spellings schema.yaml's converter
        # listed for coerce: lower.
        values = node.pop("enum", None) or [node.pop("const")]
        node["enum"] = sorted({c for v in values for c in (v, v.lower(), v.upper(), v.title())})

    if "anyOf" in node:
        # An optional field is one that may be left out, not one that may be null.
        branches = [b for b in node.pop("anyOf") if b != {"type": "null"}]
        if len(branches) == 1:
            return _panel({**branches[0], **node}, defs, shared, name)
        if not all(set(b) == {"type"} for b in branches):
            raise ValueError(f"{name}: a union the panel cannot read")
        node["type"] = [b["type"] for b in branches]
    if "oneOf" in node:
        # A tagged union (an action of one of its types); each member is
        # written like any other schema.
        node["oneOf"] = [_panel(branch, defs, shared, name) for branch in node["oneOf"]]

    kind = node.get("type")
    if kind == "boolean":
        del node["type"]
        node = {"oneOf": _BOOLEAN, **node}
    elif kind is not None:
        kinds = sorted({kind, "string"} if isinstance(kind, str) else {*kind, "string"})
        node["type"] = kinds[0] if len(kinds) == 1 else kinds

    if "properties" in node:
        node["properties"] = {k: _panel(v, defs, shared, k) for k, v in node["properties"].items()}
    if "items" in node:
        node["items"] = _panel(node["items"], defs, shared)
    if isinstance(node.get("additionalProperties"), dict):
        node["additionalProperties"] = _panel(node["additionalProperties"], defs, shared)
    if "description" in node and name:
        node["title"] = name.replace("_", " ").capitalize()
    if ref:
        node = {"$ref": f"#/$defs/{ref}", **node}
    return node


def merge_defs(into: dict, defs: dict, section: str) -> None:
    """Add a section's definitions to a document's, refusing a clash.

    Sections share a definition by name (``event`` and ``binary_sensor`` both
    use the action types), which is only right while it says the same thing.
    """
    for name, schema in defs.items():
        if name in into and json.dumps(into[name], sort_keys=True) != json.dumps(schema, sort_keys=True):
            raise ValueError(f"{section}: definition {name!r} differs from another section's")
        into[name] = schema
