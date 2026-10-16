"""The ``schedule`` section: actions run at a time of day or of the sun.

Mirrors boneio/schema/schema.yaml for the section. Conditions and actions
are the inputs', checked by the same models.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AfterValidator, BeforeValidator, Field, TypeAdapter, model_validator

from boneio.core.config.models.base import Model, Str, coerce, unique_resolved_ids
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

    type: Literal["sun", "time"] = "sun"
    event: str | None = None
    cover: str | None = None
    at: ClockTime | None = None
    offset: SunOffset | None = None
    earliest: ClockTime | None = None
    latest: ClockTime | None = None
    jitter: Seconds = 0
    days: Literal["daily", "weekdays", "weekend", "mon", "tue", "wed", "thu", "fri", "sat",
                  "sun"] = "daily"


class Schedule(Model):
    # coerce: str turns a null into "None" in Cerberus, so it passes there.
    nullable = frozenset({"id"})

    name: str
    description: str | None = None
    id: Str | None = None
    enabled: bool = True
    trigger: Trigger
    on_missed: Literal["skip", "run"] = "skip"
    catch_up: Seconds = 900
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
    "schedule": TypeAdapter(Annotated[list[Schedule], AfterValidator(unique_resolved_ids)]),
}
