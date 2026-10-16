"""The small sections: ``oled``, ``location``, ``lox_udp``, ``logger``, ``areas``.

Mirrors boneio/schema/schema.yaml for these sections.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BeforeValidator, Field, TypeAdapter

from boneio.core.config.models.base import Model, Str, StrPeriod, coerce

Number = Union[float, int]

_lower, _remove_space = coerce("lower"), coerce("remove_space")


def _sensor_ref(value: Any) -> Any:
    """``coerce: [lower, remove_space]``."""
    return _remove_space(_lower(value))


SensorRef = Annotated[str, BeforeValidator(_sensor_ref)]
LogLevel = Annotated[Literal["critical", "error", "warning", "info", "debug"], BeforeValidator(_lower)]

Screen = Literal["uptime", "network", "ina", "ina219", "cpu", "disk", "memory", "swap", "outputs",
                 "inputs", "extra_sensors", "web"]


class ExtraScreenSensor(Model):
    # remove_space is str(value) in Cerberus, so a null becomes "None" there.
    nullable = frozenset({"modbus_id", "sensor_id"})

    sensor_type: Literal["modbus", "dallas"]
    modbus_id: SensorRef | None = None
    sensor_id: SensorRef


class Oled(Model):
    enabled: bool = False
    screens: list[Screen] = Field(
        default_factory=lambda: ["uptime", "network", "ina", "cpu", "disk", "memory", "swap", "outputs"]
    )
    extra_screen_sensors: list[ExtraScreenSensor] | None = None
    screensaver_timeout: StrPeriod = Field("60s", validate_default=True)


class Location(Model):
    latitude: Annotated[Number, Field(ge=-90, le=90)]
    longitude: Annotated[Number, Field(ge=-180, le=180)]
    elevation: Annotated[Number, Field(ge=-500, le=9000)] = 0


class UsageHistory(Model):
    enabled: bool = False
    days: Annotated[int, Field(ge=7, le=90)] = 30


_HOST = (
    r"^(((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)"
    r"|([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)$"
)


class LoxUdp(Model):
    enabled: bool = False
    host: Annotated[str, Field(pattern=_HOST)]
    send_port: int = 4444
    listen_port: int = 4445


class Logger(Model):
    default: LogLevel | None = None
    logs: dict[str, LogLevel] | None = None


class Area(Model):
    # coerce: str turns a null into "None" in Cerberus, so it passes there.
    nullable = frozenset({"id"})

    id: Str
    name: str


SECTION_ADAPTERS = {
    # Required with a default: a null section is the default one.
    "oled": TypeAdapter(Oled | None),
    "location": TypeAdapter(Location),
    "usage_history": TypeAdapter(UsageHistory),
    "lox_udp": TypeAdapter(LoxUdp),
    "logger": TypeAdapter(Logger),
    "areas": TypeAdapter(list[Area]),
}
