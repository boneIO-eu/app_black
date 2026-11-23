"""The panel's JSON Schema, made from the section models.

The panel reads one dialect: no ``anyOf`` (the forms read ``type``), ``"string"`` beside every
type (a value may be an ``!include``), a boolean as a ``oneOf`` with the YAML
words for it, and a time period as ``x-timeperiod``. pydantic's own output is
rewritten into that; a ``null`` is offered only where the model marks it.

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
import os
from collections import Counter
from typing import Any

from pydantic import BaseModel
from pydantic.json_schema import GenerateJsonSchema, NoDefault

from boneio.core.config.models import _MODULES
from boneio.core.config.models.base import details
from boneio.core.utils import TimePeriod

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
            value = factory()
        else:
            value = super().get_default_value(schema)
        if isinstance(value, BaseModel):
            # A model's default instance, as start-up gives it; one that sets
            # nothing is no default worth showing.
            return value.model_dump() or NoDefault
        return value


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
    text = details()["sections"].get(section)
    if text:
        node["markdownDescription"] = f"{node['description']}\n\n{text.rstrip()}"
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
    if "default" in node and node["default"] is None:
        del node["default"]

    if "anyOf" in node:
        # An optional field is one that may be left out, not one that may be null.
        # A plain ``list`` in a union says nothing of its items.
        branches = [{k: v for k, v in b.items() if (k, v) != ("items", {})}
                    for b in node.pop("anyOf") if b != {"type": "null"}]
        if len(branches) == 1:
            return _panel({**branches[0], **node}, defs, shared, name)
        if not all(set(b) <= {"type", "items"} for b in branches):
            raise ValueError(f"{name}: a union the panel cannot read")
        node["type"] = [b["type"] for b in branches]
        # ``items`` only applies to the list the value may also be.
        node.update(b for branch in branches for b in branch.items() if b[0] == "items")

    if node.pop("x-any-case", False):
        # Read in any case (the model lowers or uppers it), so the editor must
        # not flag IN_01 or toggle_open.
        values = node.pop("enum", None) or [node.pop("const")]
        node["enum"] = sorted({c for v in values for c in (v, v.lower(), v.upper(), v.title())})

    if "oneOf" in node:
        # A tagged union (an action of one of its types); each member is
        # written like any other schema.
        node["oneOf"] = [_panel(branch, defs, shared, name) for branch in node["oneOf"]]

    # Only where the model marks it: a null that start-up reads as the
    # field's default is still flagged, as it always was.
    may_be_null = node.pop("x-null", False)
    kind = node.get("type")
    if kind == "boolean":
        del node["type"]
        node = {"oneOf": _BOOLEAN, **node}
    elif kind is not None:
        kinds = {kind, "string"} if isinstance(kind, str) else {*kind, "string"}
        kinds = sorted(kinds | {"null"} if may_be_null else kinds)
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


def build_schemas() -> dict[str, dict[str, Any]]:
    """Every JSON Schema file the panel is served, by file name.

    A section's shared definitions go to the root of config.schema.json and
    of the section's own file.
    """
    config: dict[str, Any] = {"$schema": _DRAFT, "type": "object", "properties": {}}
    schemas = {"config.schema.json": config}
    all_defs: dict[str, Any] = {}
    for name in _MODULES:
        node, defs = section_schema(name)
        config["properties"][name] = node
        merge_defs(all_defs, defs, name)
        schemas[f"{name}.schema.json"] = {
            "$schema": _DRAFT,
            "type": "object",
            "properties": {name: node},
            **({"$defs": defs} if defs else {}),
        }
    config["$defs"] = dict(sorted(all_defs.items()))
    return schemas


_DRAFT = "https://json-schema.org/draft/2020-12/schema"

#: Where the panel's schema files live, committed and served as static files.
OUTPUT_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "webui", "schema"))


def main() -> None:
    """Write the schema files the panel is served: python -m boneio.core.config.json_schema."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for name, schema in build_schemas().items():
        path = os.path.join(OUTPUT_DIR, name)
        with open(path, "w") as f:
            json.dump(schema, f, indent=2)
        print(f"Schema written to {path}")


if __name__ == "__main__":
    main()
