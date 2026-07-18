import logging
import math
import re
from collections import OrderedDict
from datetime import timedelta
from typing import Any

_LOGGER = logging.getLogger(__name__)

def is_approximately_integer(value):
    if isinstance(value, int):
        return True
    return abs(value - round(value)) < 0.001


class TimePeriod:
    def __init__(
        self,
        microseconds=None,
        milliseconds=None,
        seconds=None,
        minutes=None,
        hours=None,
        days=None,
    ) -> None:
        if days is not None:
            if not is_approximately_integer(days):
                frac_days, days = math.modf(days)
                hours = (hours or 0) + frac_days * 24
            self.days = int(round(days))
        else:
            self.days = None

        if hours is not None:
            if not is_approximately_integer(hours):
                frac_hours, hours = math.modf(hours)
                minutes = (minutes or 0) + frac_hours * 60
            self.hours = int(round(hours))
        else:
            self.hours = None

        if minutes is not None:
            if not is_approximately_integer(minutes):
                frac_minutes, minutes = math.modf(minutes)
                seconds = (seconds or 0) + frac_minutes * 60
            self.minutes = int(round(minutes))
        else:
            self.minutes = None

        if seconds is not None:
            if not is_approximately_integer(seconds):
                frac_seconds, seconds = math.modf(seconds)
                milliseconds = (milliseconds or 0) + frac_seconds * 1000
            self.seconds = int(round(seconds))
        else:
            self.seconds = None

        if milliseconds is not None:
            if not is_approximately_integer(milliseconds):
                frac_milliseconds, milliseconds = math.modf(milliseconds)
                microseconds = (microseconds or 0) + frac_milliseconds * 1000
            self.milliseconds = int(round(milliseconds))
        else:
            self.milliseconds = None

        if microseconds is not None:
            if not is_approximately_integer(microseconds):
                raise ValueError("Maximum precision is microseconds")
            self.microseconds = int(round(microseconds))
        else:
            self.microseconds = None

        self._timedelta = timedelta(
            days=self.days or 0,
            hours=self.hours or 0,
            minutes=self.minutes or 0,
            seconds=self.seconds or 0,
            milliseconds=self.milliseconds or 0,
            microseconds=self.microseconds or 0,
        )
        self._total_in_seconds = self.total_microseconds / 1000000.0

    @property
    def as_timedelta(self) -> timedelta:
        return self._timedelta

    def as_dict(self) -> OrderedDict:
        out = OrderedDict()
        if self.microseconds is not None:
            out["microseconds"] = self.microseconds
        if self.milliseconds is not None:
            out["milliseconds"] = self.milliseconds
        if self.seconds is not None:
            out["seconds"] = self.seconds
        if self.minutes is not None:
            out["minutes"] = self.minutes
        if self.hours is not None:
            out["hours"] = self.hours
        if self.days is not None:
            out["days"] = self.days
        return out

    def __str__(self) -> str:
        if self.microseconds is not None:
            return f"{self.total_microseconds}us"
        if self.milliseconds is not None:
            return f"{self.total_milliseconds}ms"
        if self.seconds is not None:
            return f"{self.total_seconds}s"
        if self.minutes is not None:
            return f"{self.total_minutes}min"
        if self.hours is not None:
            return f"{self.total_hours}h"
        if self.days is not None:
            return f"{self.total_days}d"
        return "0s"

    def __repr__(self):
        return f"TimePeriod<{self.__str__()}>"

    @property
    def total_in_seconds(self) -> float:
        return self._total_in_seconds

    @property
    def total_microseconds(self):
        return self.total_milliseconds * 1000 + (self.microseconds or 0)

    @property
    def total_milliseconds(self):
        return self.total_seconds * 1000 + (self.milliseconds or 0)

    @property
    def total_seconds(self):
        return self.total_minutes * 60 + (self.seconds or 0)

    @property
    def total_minutes(self):
        return self.total_hours * 60 + (self.minutes or 0)

    @property
    def total_hours(self):
        return self.total_days * 24 + (self.hours or 0)

    @property
    def total_days(self):
        return self.days or 0

    def __eq__(self, other):
        if isinstance(other, TimePeriod):
            return self.total_microseconds == other.total_microseconds
        return NotImplemented

    def __ne__(self, other):
        if isinstance(other, TimePeriod):
            return self.total_microseconds != other.total_microseconds
        return NotImplemented

    def __lt__(self, other):
        if isinstance(other, TimePeriod):
            return self.total_microseconds < other.total_microseconds
        return NotImplemented

    def __gt__(self, other):
        if isinstance(other, TimePeriod):
            return self.total_microseconds > other.total_microseconds
        return NotImplemented

    def __le__(self, other):
        if isinstance(other, TimePeriod):
            return self.total_microseconds <= other.total_microseconds
        return NotImplemented

    def __ge__(self, other):
        if isinstance(other, TimePeriod):
            return self.total_microseconds >= other.total_microseconds
        return NotImplemented


class TimePeriodMicroseconds(TimePeriod):
    pass


class TimePeriodMilliseconds(TimePeriod):
    pass


class TimePeriodSeconds(TimePeriod):
    pass


class TimePeriodMinutes(TimePeriod):
    pass


def parse_time_to_seconds(value: Any, default: float) -> float:
    """Parse a time value to seconds.

    Supports TimePeriod objects and raw numeric values.

    Args:
        value: TimePeriod, int, float, or None.
        default: Default value in seconds.

    Returns:
        Time in seconds as float.
    """
    if value is None:
        return default
    if hasattr(value, "total_in_seconds"):
        return value.total_in_seconds
    try:
        return float(value)
    except (ValueError, TypeError):
        _LOGGER.warning("Invalid time value: %s, using default %.0fs", value, default)
        return default


def parse_time_to_ms(value: Any, default: int | None) -> int | None:
    """Parse a time value to milliseconds.

    Supports TimePeriod objects and raw numeric values.

    Args:
        value: TimePeriod, int, float, or None.
        default: Default value in milliseconds (None = no default).

    Returns:
        Time in milliseconds as int, or None.
    """
    if value is None:
        return default
    if hasattr(value, "total_milliseconds"):
        return int(value.total_milliseconds)
    if hasattr(value, "total_in_seconds"):
        return int(value.total_in_seconds * 1000)
    try:
        return int(float(value))
    except (ValueError, TypeError):
        _LOGGER.warning("Invalid time value: %s, using default %s ms", value, default)
        return default


_TIME_UNIT_MAP = {
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


_TIME_PERIOD_RE = re.compile(r"^([-+]?[0-9]*\.?[0-9]+)\s*([a-zA-Z]+)$")


def ensure_time_period(value: "TimePeriod | str | int | float") -> "TimePeriod":
    """Ensure a value is a TimePeriod object.

    Converts strings like '5s', '1000ms', '2min' and raw numeric values
    (treated as seconds) to TimePeriod. Passes through existing TimePeriod
    objects unchanged. This is the defensive layer for hot-reload scenarios
    where YAML values may arrive as raw strings instead of pre-parsed
    TimePeriod objects.

    Args:
        value: A TimePeriod, time string with unit, or numeric seconds.

    Returns:
        A TimePeriod instance.

    Raises:
        ValueError: If the string format is invalid or the unit is unknown.
    """
    if isinstance(value, TimePeriod):
        return value

    if isinstance(value, (int, float)):
        return TimePeriod(seconds=float(value))

    if not isinstance(value, str):
        raise ValueError(f"Cannot convert {type(value).__name__} to TimePeriod: {value!r}")

    value = value.strip()
    if not value:
        raise ValueError("Empty string cannot be converted to TimePeriod")

    match = _TIME_PERIOD_RE.match(value)
    if match is None:
        raise ValueError(f"Invalid time period format: {value!r}")

    num_str, unit = match.group(1), match.group(2).lower()
    kwarg = _TIME_UNIT_MAP.get(unit)
    if kwarg is None:
        raise ValueError(f"Unknown time unit '{unit}' in: {value!r}")

    return TimePeriod(**{kwarg: float(num_str)})

