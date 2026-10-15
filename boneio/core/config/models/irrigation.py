"""The ``irrigation`` section: valves run in turn, from water sources, on a timetable.

Mirrors boneio/schema/schema.yaml for the section. Water sources and runs
are the irrigation template's, checked by the same models.
"""

from __future__ import annotations

from typing import Annotated, Union

from pydantic import Field, TypeAdapter

from boneio.core.config.models.base import Model, StrPeriod
from boneio.core.config.models.templates import Run, WaterSource


class Zone(Model):
    id: str | None = None
    name: str | None = None
    valve_id: str
    run_duration: StrPeriod
    enabled: bool = True
    run_every_n: Annotated[int, Field(ge=1)] = 1


class Irrigation(Model):
    id: str | None = None
    name: str | None = None
    water_sources: list[WaterSource] | None = None
    standby: bool = False
    valve_open_delay: StrPeriod | None = None
    valve_overlap: StrPeriod | None = None
    multiplier: Union[float, int] = 1.0
    repeat: int = 0
    auto_advance: bool = True
    reverse: bool = False
    pause_timeout: StrPeriod | None = None
    schedule: list[Run] | None = None
    zones: list[Zone]


SECTION_ADAPTERS = {"irrigation": TypeAdapter(list[Irrigation])}
