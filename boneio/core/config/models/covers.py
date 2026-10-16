"""The ``cover`` section: blinds and gates driven by an open and a close relay.

Mirrors boneio/schema/schema.yaml for the section.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BeforeValidator, Field, TypeAdapter

from boneio.core.config.models.base import Model, StrPeriod


class Cover(Model):
    name: str | None = None
    id: Annotated[str, BeforeValidator(str), Field(pattern=r"^[a-z0-9_]+$")] | None = None
    area: str | None = None
    restore_state: bool = False
    open_relay: str
    close_relay: str
    platform: Literal["time_based", "venetian"] = "time_based"
    open_time: StrPeriod
    close_time: StrPeriod
    tilt_duration: StrPeriod | None = None
    actuator_activation_duration: StrPeriod | None = None
    endstop_overrun: Annotated[int, Field(ge=0, le=100)] = 10
    direction_change_wait_time: StrPeriod = Field("500ms", validate_default=True)
    tilt_restore_after_close: bool = False
    device_class: Literal["awning", "blind", "curtain", "damper", "door", "garage", "gate",
                          "shade", "shutter", "window"] | None = None
    show_in_ha: bool = True
    facade_azimuth: Annotated[int, Field(ge=0, le=359)] | None = None
    facade_min_elevation: Annotated[int, Field(ge=0, le=45)] = 0


SECTION_ADAPTERS = {"cover": TypeAdapter(list[Cover])}
