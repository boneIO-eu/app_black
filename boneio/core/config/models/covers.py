"""The ``cover`` section: blinds and gates driven by an open and a close relay.

Mirrors boneio/schema/schema.yaml for the section.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BeforeValidator, Field

from boneio.core.config.models.base import Model, StrPeriod, section


class Cover(Model):
    name: str | None = Field(None, description="Display Name")
    id: Annotated[str, BeforeValidator(str), Field(pattern=r"^[a-z0-9_]+$")] | None = Field(
        None, description="Cover ID"
    )
    area: str | None = Field(None, description="Area/Room")
    restore_state: bool = Field(False, description="Restore saved state of boneio.")
    open_relay: str = Field(description="ID of open relay of output.")
    close_relay: str = Field(description="ID of close relay of output.")
    platform: Literal["time_based", "venetian"] = Field("time_based", description="Platform to use for cover.")
    open_time: StrPeriod = Field(description="Time to open cover. Example 30s. Minimum is 1s.")
    close_time: StrPeriod = Field(description="Time to close cover. Example 30s. Minimum is 1s.")
    tilt_duration: StrPeriod | None = Field(None, description="Time to tilt cover. Example 2s. Minimum is 10ms.")
    actuator_activation_duration: StrPeriod | None = Field(
        None,
        description="Time from switching the relay on until the motor starts moving, added to every movement. "
        "Example 200ms for Somfy J4 WT, which ignores shorter orders. Default 0ms.",
    )
    endstop_overrun: Annotated[int, Field(ge=0, le=100)] = Field(
        10,
        description="Extra relay time when the cover moves to fully open or fully closed, as a percent of "
        "open_time/close_time. The cover runs into its endstop, so the time-based position is exact again at "
        "0% and 100%. 0 disables it.",
    )
    direction_change_wait_time: StrPeriod = Field(
        "500ms",
        validate_default=True,
        description="Pause before the cover is driven in the opposite direction, so the motor stops before it "
        "reverses. 0ms disables it.",
    )
    tilt_restore_after_close: bool = Field(
        False, description="Restore tilt position after closing venetian blinds."
    )
    device_class: Literal["awning", "blind", "curtain", "damper", "door", "garage", "gate",
                          "shade", "shutter", "window"] | None = Field(None, description="Device class to use in HA")
    show_in_ha: bool = Field(True, description="If you want you can disable discovering this input in HA.")
    facade_azimuth: Annotated[int, Field(ge=0, le=359)] | None = Field(
        None,
        description="Which way the window faces, in degrees clockwise from north (90 east, 180 south, 270 "
        "west). With it and the location set, the controller knows when the sun shines on the window: a "
        '"sun on" binary sensor in Home Assistant, and schedules that run when the sun reaches or leaves the '
        "window.",
    )
    facade_min_elevation: Annotated[int, Field(ge=0, le=45)] = Field(
        0,
        description="The sun counts as on the window only above this many degrees over the horizon - raise it "
        "when a neighbouring house or trees shade the window while the sun is low.",
    )


SECTION_ADAPTERS = {
    "cover": section(
        list[Cover],
        "https://boneio.eu/docs/black/configuration/cover \n Cover section of boneIO Black. It enables cover "
        "entities in HA. You'd need output config to use it first.",
    )
}
