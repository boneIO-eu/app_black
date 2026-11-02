"""The ``irrigation`` section: valves run in turn, from water sources, on a timetable.

Mirrors boneio/schema/schema.yaml for the section. Water sources and runs
are the irrigation template's, checked by the same models.
"""

from __future__ import annotations

from typing import Annotated, Union

from pydantic import Field

from boneio.core.config.models.base import Model, StrPeriod, section
from boneio.core.config.models.templates import Run, WaterSource

# schema.yaml's shared id.yaml, whatever the id is of.
_ID = "Id of I2C to use in pin config"


class Zone(Model):
    id: str | None = Field(None, description=_ID)
    name: str | None = Field(None, description="Display name for the zone.")
    valve_id: str = Field(description="Output ID of the valve relay to control.")
    run_duration: StrPeriod = Field(description="How long to run this zone. Example 5min or 300s.")
    enabled: bool = Field(True, description="Whether this zone is active.")
    run_every_n: Annotated[int, Field(ge=1)] = Field(
        1, description="Run zone every Nth scheduled cycle. 1 = every time."
    )


class Irrigation(Model):
    id: str | None = Field(None, description=_ID)
    name: str | None = Field(None, description="Display name for the irrigation controller in Home Assistant.")
    water_sources: list[WaterSource] | None = Field(
        None, description="Water sources — each defines outputs to activate and per-source pump timing."
    )
    standby: bool = Field(False, description="When enabled, the controller will not start any valves.")
    valve_open_delay: StrPeriod | None = Field(
        None, description="Delay between valve switching. May not be used with valve_overlap."
    )
    valve_overlap: StrPeriod | None = Field(
        None,
        description="Time that current and next valve run simultaneously. May not be used with valve_open_delay.",
    )
    multiplier: Union[float, int] = Field(
        1.0, description="Duration multiplier applied to all zone run times. 1.0 = 100%."
    )
    repeat: int = Field(0, description="Number of times to repeat the full cycle. 0 = run once.")
    auto_advance: bool = Field(
        True, description="Automatically advance to the next zone. Disable for single-zone manual mode."
    )
    reverse: bool = Field(False, description="Run zones in reverse order.")
    pause_timeout: StrPeriod | None = Field(
        None, description="Auto-shutdown after being paused for this duration. Default 30min. Set 0 to disable."
    )
    schedule: list[Run] | None = Field(None, description="Scheduled start times for this controller.")
    zones: list[Zone] = Field(description="Irrigation zones — each zone controls a single valve output.")


SECTION_ADAPTERS = {
    "irrigation": section(
        list[Irrigation],
        "Irrigation controllers — manage watering zones with schedules, per-zone intervals, and master valve "
        "support.",
    )
}
