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

from typing import Any

#: Sections validated by a model instead of the Cerberus schema.
SECTIONS = frozenset({"event", "binary_sensor"})


def validate(section: str, data: Any) -> list[str]:
    """Check one section as written, before the board mapping expands it.

    Args:
        section: One of :data:`SECTIONS`.
        data: The section. Not modified.

    Returns:
        One ``path: message`` line per error; empty when the section is valid.
    """
    from pydantic import ValidationError

    from boneio.core.config.models.inputs import SECTION_ADAPTERS

    try:
        SECTION_ADAPTERS[section].validate_python(data)
    except ValidationError as err:
        return [f"{_path(section, e['loc'])}: {e['msg']}" for e in err.errors()]
    return []


def _path(section: str, loc: tuple) -> str:
    """``event[0].actions.single[1].boneio_output`` from a pydantic location.

    An action's location carries the tag of the union member it was checked
    against right after its index; it is not a field, so it is left out.
    """
    from boneio.core.config.models.inputs import ACTION_TAGS

    path = section
    previous: Any = None
    for part in loc:
        if isinstance(part, int):
            path += f"[{part}]"
        elif not (isinstance(previous, int) and part in ACTION_TAGS):
            path += f".{part}"
        previous = part
    return path
