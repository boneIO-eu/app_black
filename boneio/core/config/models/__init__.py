"""Pydantic models for the config sections that have them.

Importing this package is cheap: the models themselves are built on first
use. Building them takes 1.2 s on a BeagleBone, which a start that finds its
validated config in the cache should not pay.

While start-up still validates config.yaml with Cerberus, a model may be
stricter than the Cerberus schema for its section but never more lenient: a
section the model accepts is written to the file as posted, and must load.
tests/unit/core/config/test_models_match_cerberus.py holds that.
"""

from __future__ import annotations

import importlib
from typing import Any

#: Sections validated by a model instead of the Cerberus schema, and the
#: module holding it. Only that module is built when its section is checked.
_MODULES = {
    "event": "inputs",
    "binary_sensor": "inputs",
    "output": "outputs",
    "cover": "covers",
    "remote_inputs": "remote_inputs",
    "virtual_switch": "virtual_switches",
}
SECTIONS = frozenset(_MODULES)


def validate(section: str, data: Any) -> list[str]:
    """Check one section as written, before the board mapping expands it.

    Args:
        section: One of :data:`SECTIONS`.
        data: The section. Not modified.

    Returns:
        One ``path: message`` line per error; empty when the section is valid.
    """
    from pydantic import ValidationError

    module = importlib.import_module(f"{__name__}.{_MODULES[section]}")
    tags = getattr(module, "UNION_TAGS", frozenset())
    try:
        module.SECTION_ADAPTERS[section].validate_python(data)
    except ValidationError as err:
        # A message raised by our own validators reads better without the
        # "Value error, " pydantic puts in front of it.
        return [
            f"{_path(section, e['loc'], tags)}: {e['msg'].removeprefix('Value error, ')}"
            for e in err.errors()
        ]
    return []


def _path(section: str, loc: tuple, tags: frozenset[str]) -> str:
    """``event[0].actions.single[1].boneio_output`` from a pydantic location.

    A tagged union member's location carries its tag right after its index
    (an action's type); it is not a field, so it is left out.
    """
    path = section
    previous: Any = None
    for part in loc:
        if isinstance(part, int):
            path += f"[{part}]"
        elif not (isinstance(previous, int) and part in tags):
            path += f".{part}"
        previous = part
    return path
