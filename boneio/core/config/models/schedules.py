"""The ``schedule`` section: actions run at a time of day or of the sun.

Mirrors boneio/schema/schema.yaml for the section. Conditions and actions
are the inputs', checked by the same models.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AfterValidator, BeforeValidator, Field, model_validator

from boneio.core.config.models.base import Model, Str, coerce, section, unique_resolved_ids
from boneio.core.config.models.inputs import (  # noqa: F401 - UNION_TAGS for error paths
    UNION_TAGS,
    Action,
    Conditions,
    ShapedCondition,
    SunOffset,
)
from boneio.core.config.yaml_util import schedule_shape_errors

ClockTime = Annotated[str, Field(pattern=r"^([01]?[0-9]|2[0-3]):[0-5][0-9]$")]
Seconds = Annotated[float, BeforeValidator(coerce("sun_offset")), Field(ge=0, le=21600)]


class Trigger(Model):
    # sun_offset turns a null into 0, so Cerberus takes it.
    nullable = frozenset({"offset"})

    type: Literal["sun", "time"] = Field("sun", description="Trigger type")
    event: str | None = Field(None, description="Sun event (sun triggers only)")
    cover: str | None = Field(None, description="Cover whose window the Sun reaches or leaves (facade events only)")
    at: ClockTime | None = Field(None, description="Clock time in HH:MM (time triggers only)")
    offset: SunOffset | None = Field(None, description="Shift the moment")
    earliest: ClockTime | None = Field(None, description="Not before this clock time (sun triggers only)")
    latest: ClockTime | None = Field(None, description="Not after this clock time (sun triggers only)")
    jitter: Seconds = Field(0, description="Random spread")
    days: Literal["daily", "weekdays", "weekend", "mon", "tue", "wed", "thu", "fri", "sat",
                  "sun"] = Field("daily", description="Days this schedule is active.")


class Schedule(Model):
    # coerce: str turns a null into "None" in Cerberus, so it passes there.
    nullable = frozenset({"id"})

    name: str = Field(description="Name")
    description: str | None = Field(None, description="What this schedule is for.")
    id: Str | None = Field(None, description="Identifier, if the one made from the name will not do.")
    enabled: bool = Field(True, description="Whether this schedule is armed.")
    trigger: Trigger = Field(description="When this schedule fires.")
    on_missed: Literal["skip", "run"] = Field(
        "skip", description="What to do about a firing missed while the device was off."
    )
    catch_up: Seconds = Field(900, description="How late a missed firing may still run (on_missed - run).")
    condition: ShapedCondition | None = None
    conditions: Conditions | None = None
    actions: list[Action] | None = None

    @model_validator(mode="after")
    def _trigger_fits_its_type(self) -> Schedule:
        errors = schedule_shape_errors(
            {"trigger": self.trigger.model_dump(exclude_none=True), "actions": self.actions}
        )
        if errors:
            raise ValueError(" ".join(errors))
        return self


SECTION_ADAPTERS = {
    "schedule": section(
        Annotated[list[Schedule], AfterValidator(unique_resolved_ids)],
        "Time and sun driven schedules — run actions without anyone pressing anything.",
    ),
}
