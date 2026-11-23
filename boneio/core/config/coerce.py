"""The coercions a config value goes through, and the shape checks a schema cannot say.

Plain functions: the section models use them, and so does the Cerberus
validator while it still exists.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from boneio.core.utils import TimePeriod
from boneio.exceptions import ConfigurationException

_LOGGER = logging.getLogger(__name__)


def one_of(*values, **kwargs):
    """Validate that the config option is one of the given values.
    :param values: The valid values for this type
    """
    options = ", ".join(f"'{x}'" for x in values)

    def validator(value):
        if value not in values:
            import difflib

            options_ = [str(x) for x in values]
            option = str(value)
            matches = difflib.get_close_matches(option, options_)
            if matches:
                matches_str = ", ".join(f"'{x}'" for x in matches)
                raise ConfigurationException(f"Unknown value '{value}', did you mean {matches_str}?")
            raise ConfigurationException(f"Unknown value '{value}', valid options are {options}.")
        return value

    return validator


def schedule_shape_errors(value: Any) -> list[str]:
    """Why a schedule's trigger does not match its own type; empty when it does.

    A schema can require a dict and check each field on its own, but not "a
    sun trigger needs an event and a time trigger needs a time". Left to
    runtime the symptom is a schedule that quietly never fires, which is the
    hardest kind of misconfiguration to notice. A field of the wrong type is
    the schema's to report and is not compared here.
    """
    if not isinstance(value, dict):
        return []

    errors = []
    trigger = value.get("trigger")
    trigger = trigger if isinstance(trigger, dict) else {}
    kind = trigger.get("type", "sun")

    if kind == "sun":
        from boneio.core.utils.sun import ANCHOR_NAMES, FACADE_EVENTS

        event = trigger.get("event")
        if not event:
            errors.append("A sun trigger needs an 'event', e.g. sunset or civil_dusk.")
        elif event in FACADE_EVENTS:
            if not trigger.get("cover"):
                errors.append(f"{event} needs 'cover': the cover whose window the Sun reaches or leaves.")
        elif event not in ANCHOR_NAMES:
            errors.append(
                f"Unknown sun event {event!r}. "
                f"Expected one of: {', '.join(sorted((*ANCHOR_NAMES, *FACADE_EVENTS)))}."
            )
        elif trigger.get("cover"):
            errors.append(f"'cover' belongs to a facade event, not to {event}.")
        if trigger.get("at"):
            errors.append("'at' belongs to a time trigger, not a sun trigger.")
        earliest, latest = trigger.get("earliest"), trigger.get("latest")
        # String compare is right for zero-padded HH:MM, which the schema's
        # regex holds both to.
        if isinstance(earliest, str) and isinstance(latest, str) and earliest and latest and earliest > latest:
            errors.append(
                f"'earliest' ({earliest}) is after 'latest' ({latest}), "
                "so the window is empty and the schedule can never fire."
            )
    elif kind == "time":
        if not trigger.get("at"):
            errors.append("A time trigger needs 'at' in HH:MM.")
        if trigger.get("event"):
            errors.append("'event' belongs to a sun trigger, not a time trigger.")
        for key in ("earliest", "latest"):
            if trigger.get(key):
                # Clamping a clock time to another clock time is either a
                # no-op or a different time written twice.
                errors.append(
                    f"{key!r} clamps a sun anchor; a time trigger already has a fixed time."
                )

    if not value.get("actions"):
        errors.append("A schedule with no actions would fire and do nothing.")
    return errors


def condition_shape_errors(value: Any) -> list[str]:
    """Why a condition's fields do not match its own type; empty when they do.

    A schema can say "this is a dict of allowed keys" but not "a sun condition
    is one of three shapes and never a mixture". Without this a typo like
    ``type: sun`` with ``after: "05:00"`` reaches runtime, where the only
    symptom is an action that silently never fires.
    """
    if not isinstance(value, dict) or value.get("type") != "sun":
        return []

    from boneio.core.utils.sun import ANCHOR_NAMES, PHASE_NAMES

    window = [key for key in ("after", "before") if value.get(key)]
    phase = value.get("phase")
    elevation = [key for key in ("above", "below") if value.get(key) is not None]

    modes = [bool(window), bool(phase), bool(elevation)]
    if sum(modes) == 0:
        return [
            "A sun condition needs one of: after/before (anchors), "
            "phase, or above/below (elevation in degrees)."
        ]
    if sum(modes) > 1:
        return [
            "A sun condition must use only one of after/before, phase, or "
            "above/below — not a mixture."
        ]

    errors = []
    for key in ("after", "before"):
        anchor = value.get(key)
        if anchor and anchor not in ANCHOR_NAMES:
            errors.append(
                f"Unknown sun anchor {anchor!r} in '{key}'. "
                f"Expected one of: {', '.join(sorted(ANCHOR_NAMES))}."
            )

    for key, other in (("after_offset", "after"), ("before_offset", "before")):
        if value.get(key) and not value.get(other):
            errors.append(f"'{key}' has no effect without '{other}'.")

    if phase and phase not in PHASE_NAMES:
        errors.append(
            f"Unknown sun phase {phase!r}. "
            f"Expected one of: {', '.join(sorted(PHASE_NAMES))}."
        )

    above, below = value.get("above"), value.get("below")
    # A non-number is the schema's to report; compared here it would raise.
    numbers = all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in (above, below))
    if numbers and above >= below:
        errors.append(
            f"'above' ({above}) must be lower than 'below' ({below}); "
            "the pair describes a band of elevations."
        )
    return errors


def lower(value: Any):
    """Convert string to lowercase."""
    if isinstance(value, str):
        return value.lower()
    return value


def remove_space(value: Any):
    return str(value).replace(" ", "")


def length_to_meters(value: Any) -> float | None:
    """
    Convert a length value to meters.
    Accepts:
    - Numeric values (int, float) - assumed to be in meters
    - Strings with units: 'm', 'cm', 'mm'
    Examples:
    5 -> 5.0
    '5m' -> 5.0
    '500cm' -> 5.0
    '2000mm' -> 2.0
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    value = str(value).strip().lower()
    match = re.match(r"^([-+]?[0-9]*\.?[0-9]*)\s*(m|cm|mm)?$", value)
    if not match:
        raise ValueError(f"Invalid length value: {value}")
    num = float(match.group(1))
    unit = match.group(2) or "m"
    if unit == "m":
        multiplier = 1.0
    elif unit == "cm":
        multiplier = 0.01
    elif unit == "mm":
        multiplier = 0.001
    else:
        raise ValueError(f"Unknown unit for length value: {unit}")
    result = num * multiplier
    _LOGGER.debug(f"Parsed length value '{value}' as {result} m")
    return result


def positive_time_period(value: Any) -> TimePeriod:
    """Validate and transform time period with time unit and integer value.

    Bare integers (e.g. ``30``) are treated as **milliseconds** for
    backward compatibility — the frontend and earlier configs sometimes
    omit the unit for bounce_time / duration fields.
    """
    if isinstance(value, (int, float)):
        if value == 0:
            return TimePeriod(seconds=0)
        # Treat bare numbers as milliseconds for backward compatibility
        return TimePeriod(milliseconds=float(value))
    if isinstance(value, TimePeriod):
        value = str(value)
    if not isinstance(value, str):
        raise ConfigurationException("Expected string for time period with unit.")

    # Handle empty string
    if not value or not value.strip():
        raise ConfigurationException(
            "Time period cannot be empty. Expected value with unit like '30s' or '1000ms'."
        )

    unit_to_kwarg = {
        "us": "microseconds",
        "microseconds": "microseconds",
        "ms": "milliseconds",
        "milliseconds": "milliseconds",
        "s": "seconds",
        "sec": "seconds",
        "secs": "seconds",
        "seconds": "seconds",
        "min": "minutes",
        "mins": "minutes",
        "minutes": "minutes",
        "h": "hours",
        "hours": "hours",
        "d": "days",
        "days": "days",
    }

    match = re.match(r"^([-+]?[0-9]*\.?[0-9]*)\s*(\w*)$", value)
    if match is None:
        raise ConfigurationException(f"Expected time period with unit, got {value}")

    unit_str = match.group(2)
    # Bare number without unit (e.g. '30' from coerce: str on int 30)
    # → treat as milliseconds for backward compatibility
    if not unit_str:
        return TimePeriod(milliseconds=float(match.group(1)))

    kwarg = unit_to_kwarg[one_of(*unit_to_kwarg)(unit_str)]
    return TimePeriod(**{kwarg: float(match.group(1))})


def sun_offset(value: Any) -> float:
    """Parse a signed offset from a sun anchor into seconds.

    Unlike ``positive_time_period`` this must accept negative values —
    "half an hour before sunset" is the whole point — and it returns plain
    seconds rather than a TimePeriod, because the only thing that ever
    happens to it is being added to a datetime.

    A bare number means **seconds**, not milliseconds. That differs from
    ``positive_time_period`` deliberately: a sun offset measured in
    milliseconds would be meaningless, and the frontend always sends a unit.

    Args:
        value: ``"-30min"``, ``"1h"``, ``"45s"``, or a number of seconds.

    Returns:
        The offset in seconds, negative for "before".

    Raises:
        ConfigurationException: If the value cannot be read as an offset.
    """
    if value is None or value == "":
        return 0.0
    if isinstance(value, bool):
        raise ConfigurationException(f"Expected a sun offset, got {value!r}")
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip().lower()
    if not text:
        return 0.0

    match = re.match(r"^([-+]?[0-9]*\.?[0-9]+)\s*(\w*)$", text)
    if match is None:
        raise ConfigurationException(
            f"Expected an offset like '-30min', '15m' or '1h', got {value!r}"
        )

    unit_to_seconds = {
        "": 1.0,
        "s": 1.0,
        "sec": 1.0,
        "secs": 1.0,
        "second": 1.0,
        "seconds": 1.0,
        "m": 60.0,
        "min": 60.0,
        "mins": 60.0,
        "minute": 60.0,
        "minutes": 60.0,
        "h": 3600.0,
        "hour": 3600.0,
        "hours": 3600.0,
    }
    unit = match.group(2)
    if unit not in unit_to_seconds:
        raise ConfigurationException(
            f"Unknown unit {unit!r} in sun offset {value!r}. Use s, min or h."
        )
    return float(match.group(1)) * unit_to_seconds[unit]


def power_value_to_watts(value: Any):
    """
    Parse a power or energy value and return it in watts (W).
    Accepts:
    - Numeric values (int, float)
    - Strings with units: 'W', 'kW', 'kWh', 'MW', 'mW', etc.
    - For 'kWh' (kilowatt-hour), returns equivalent average power in W (1kWh = 1000W for 1h)
    - For 'kW', 'MW', etc., converts to W
    Example:
        9 -> 9.0
        '9W' -> 9.0
        '1kW' -> 1000.0
        '1kWh' -> 1000.0
        '2.5MW' -> 2500000.0
    Returns float (watts) or raises ValueError if invalid.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        raise ValueError(f"Unsupported type for power value: {type(value)}")
    value = value.strip().replace(" ", "").lower()
    pattern = r"^([-+]?[0-9]*\.?[0-9]+)([a-z]*)$"
    match = re.match(pattern, value)
    if not match:
        _LOGGER.warning(f"Could not parse power value: {value}")
        raise ValueError(f"Could not parse power value: {value}")
    num = float(match.group(1))
    unit = match.group(2) or "w"
    if unit in ("w", "", "wh"):
        multiplier = 1.0
    elif unit in ("kw", "kwh"):
        multiplier = 1000.0
    elif unit in ("mw", "mwh"):
        multiplier = 1_000_000.0
    elif unit in ("gw", "gwh"):
        multiplier = 1_000_000_000.0
    else:
        _LOGGER.warning(f"Unknown unit for power value: {unit}")
        raise ValueError(f"Unknown unit for power value: {unit}")
    result = num * multiplier
    _LOGGER.debug(f"Parsed power value '{value}' as {result} W")
    return result


def volume_flow_rate_to_lph(value: Any):
    """
    Parse a volume flow rate value and return it in liters per minute (L/min).
    Accepts:
    - Numeric values (int, float)
    - Strings with units: 'L/min', 'L/h', etc.
    Example:
        9 -> 9.0
        '9L/min' -> 9.0
        '1L/h' -> 1000.0
    Returns float (L/h) or raises ValueError if invalid.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        raise ValueError(f"Unsupported type for volume flow rate value: {type(value)}")
    value = value.strip().replace(" ", "").lower()
    pattern = r"^([-+]?[0-9]*\.?[0-9]+)\s*([a-zA-Z/]*)$"
    match = re.match(pattern, value)
    if not match:
        _LOGGER.warning(f"Could not parse volume flow rate value: {value}")
        raise ValueError(f"Could not parse volume flow rate value: {value}")
    num = float(match.group(1))
    unit = match.group(2) or "lph"
    if unit in ("lph", "l/h", ""):
        multiplier = 1.0
    elif unit in ("lpm", "l/min"):
        multiplier = 60.0
    else:
        _LOGGER.warning(f"Unknown unit for volume flow rate value: {unit}")
        raise ValueError(f"Unknown unit for volume flow rate value: {unit}")
    result = num * multiplier
    _LOGGER.debug(f"Parsed volume flow rate value '{value}' as {result} L/h")
    return result
