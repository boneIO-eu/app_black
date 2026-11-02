"""The small sections: ``oled``, ``location``, ``lox_udp``, ``logger``, ``areas``.

Mirrors boneio/schema/schema.yaml for these sections.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BeforeValidator, Field, TypeAdapter

from boneio.core.config.models.base import ANY_CASE, Model, Str, StrPeriod, coerce

Number = Union[float, int]

_lower, _remove_space = coerce("lower"), coerce("remove_space")


def _sensor_ref(value: Any) -> Any:
    """``coerce: [lower, remove_space]``."""
    return _remove_space(_lower(value))


SensorRef = Annotated[str, BeforeValidator(_sensor_ref)]
LogLevel = Annotated[
    Literal["critical", "error", "warning", "info", "debug"], BeforeValidator(_lower), Field(json_schema_extra=ANY_CASE)
]

Screen = Literal["uptime", "network", "ina", "ina219", "cpu", "disk", "memory", "swap", "outputs",
                 "inputs", "extra_sensors", "web"]


class ExtraScreenSensor(Model):
    # remove_space is str(value) in Cerberus, so a null becomes "None" there.
    nullable = frozenset({"modbus_id", "sensor_id"})

    sensor_type: Literal["modbus", "dallas"]
    modbus_id: SensorRef | None = Field(None, description="Only needed if sensor type is modbus.")
    sensor_id: SensorRef


class Oled(Model):
    enabled: bool = Field(False, description="Turn the built-in screen on.")
    screens: list[Screen] = Field(
        default_factory=lambda: ["uptime", "network", "ina", "cpu", "disk", "memory", "swap", "outputs"]
    )
    extra_screen_sensors: list[ExtraScreenSensor] | None = Field(None, description="Extra sensors")
    screensaver_timeout: StrPeriod = Field(
        "60s",
        validate_default=True,
        description="How many seconds to wait to enable screensaver. 0 means disable screensaver.",
    )


class Location(Model):
    latitude: Annotated[Number, Field(ge=-90, le=90, description="Latitude")]
    longitude: Annotated[Number, Field(ge=-180, le=180, description="Longitude")]
    elevation: Annotated[Number, Field(ge=-500, le=9000, description="Elevation above sea level (m)")] = 0


class UsageHistory(Model):
    enabled: bool = Field(False, description="Collect usage history")
    days: Annotated[int, Field(ge=7, le=90, description="Days kept")] = 30


_HOST = (
    r"^(((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)"
    r"|([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)$"
)


class LoxUdp(Model):
    enabled: bool = Field(False, description="Enable Lox UDP protocol")
    host: Annotated[str, Field(pattern=_HOST, description="Target host")]
    send_port: int = Field(4444, description="Port to send UDP messages")
    listen_port: int = Field(4445, description="Port to listen for incoming UDP messages")


class Logger(Model):
    default: LogLevel | None = Field(None, description="Module which you want logger to set. Default for app logger.")
    logs: dict[str, LogLevel] | None = None


class Area(Model):
    # coerce: str turns a null into "None" in Cerberus, so it passes there.
    nullable = frozenset({"id"})

    id: Str = Field(description="Area ID")
    name: str = Field(description="Area Name")


def _section(model: Any, description: str, **extra: Any) -> TypeAdapter:
    """The section's adapter, with schema.yaml's description of it."""
    return TypeAdapter(Annotated[model, Field(description=description, json_schema_extra=extra or None)])


SECTION_ADAPTERS = {
    # Required with a default: a null section is the default one.
    "oled": _section(
        Oled | None,
        "https://boneio.eu/docs/black/configuration/oled \n Oled section of boneIO Black. It enables oled "
        "screen. You'd need enabled: true to make it work.",
        default={},
    ),
    "location": _section(
        Location,
        "Geographic location of the controller. Required for sun-based conditions and for the sunrise/sunset "
        "times shown in the panel.",
    ),
    "usage_history": _section(
        UsageHistory,
        "Hourly counts of how outputs, covers and inputs are used, kept on the controller, for an AI assistant "
        "to suggest automations from. Off unless turned on; turning it off deletes what was collected.",
    ),
    "lox_udp": _section(LoxUdp, "Lox UDP Messaging"),
    "logger": _section(
        Logger,
        "https://boneio.eu/docs/black/configuration/logger \n Logger section of boneIO Black. It enables logging "
        "level. If run as systemd service, then it will log to journal. If not, then it will log to "
        "/tmp/boneio.log",
    ),
    "areas": _section(
        list[Area],
        "Define areas/rooms for organizing entities in Home Assistant. Each area creates a sub-device linked to "
        "the main BoneIO device.",
    ),
}
