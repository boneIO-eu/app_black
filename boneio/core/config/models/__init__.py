"""Pydantic models for the config sections that have them.

Importing this package is cheap: the models themselves are built on first
use. Building them takes 1.2 s on a BeagleBone, which a start that finds its
validated config in the cache should not pay.

Start-up and a save read a section through the same model, so what a save
accepts is what the next start loads; tests/unit/core/config/test_config_shape.py
holds that the running objects get it in the shape they always did.
"""

from __future__ import annotations

import importlib
from typing import Any

#: Every config section, and the module holding its model. Only that module is built when its section is checked.
_MODULES = {
    "event": "inputs",
    "binary_sensor": "inputs",
    "output": "outputs",
    "cover": "covers",
    "remote_inputs": "remote_inputs",
    "virtual_switch": "virtual_switches",
    "schedule": "schedules",
    "template": "templates",
    "remote_devices": "remote_devices",
    "remote_outputs": "remote_outputs",
    "output_group": "output_groups",
    "irrigation": "irrigation",
    "web": "system",
    "mqtt": "system",
    "boneio": "system",
    **dict.fromkeys(
        ("sensor", "adc", "ina219", "ina226", "lm75", "mcp9808", "modbus", "modbus_devices", "can",
         "mcp23017", "pcf8575", "pca9685", "virtual_energy_sensor"),
        "sensors",
    ),
    **dict.fromkeys(("oled", "location", "lox_udp", "logger", "areas", "usage_history"), "misc"),
}
SECTIONS = frozenset(_MODULES)


def read(section: str, data: Any, *, at_start: bool = False) -> tuple[Any, list[str]]:
    """Check one section as written, before the board mapping expands it.

    Args:
        section: One of :data:`SECTIONS`.
        data: The section. Not modified.
        at_start: Read config.yaml as start-up does, which lets a few things
            through that a save refuses (a 1-Wire address it cannot parse).

    Returns:
        The section as the running objects read it (coerced, with its
        defaults), and one ``path: message`` line per error; the section is
        None when there are errors.
    """
    from pydantic import ValidationError

    module = importlib.import_module(f"{__name__}.{_MODULES[section]}")
    adapter = module.SECTION_ADAPTERS[section]
    try:
        value = adapter.validate_python(data, context={"at_start": at_start})
    except ValidationError as err:
        tags = getattr(module, "UNION_TAGS", frozenset())
        return None, [f"{_path(section, e['loc'], tags)}: {_message(e)}" for e in err.errors()]
    return adapter.dump_python(value), []


def validate(section: str, data: Any) -> list[str]:
    """The errors :func:`read` finds in a section, as a save checks it."""
    return read(section, data)[1]


def load(section: str, data: Any) -> Any:
    """The section as the running objects read it; ``data`` must be valid."""
    value, errors = read(section, data)
    if errors:
        raise ValueError("; ".join(errors))
    return value


def _message(error: Any) -> str:
    # A message raised by our own validators reads better without the
    # "Value error, " pydantic puts in front of it; a value not among the
    # allowed ones is named, since the line it is on is not.
    message = error["msg"].removeprefix("Value error, ")
    if error["type"] == "literal_error":
        message += f" (got {error['input']!r})"
    return message


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
