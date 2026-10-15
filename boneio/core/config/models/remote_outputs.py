"""The ``remote_outputs`` section: outputs of other devices shown as this one's.

Mirrors boneio/schema/schema.yaml for the section.
"""

from __future__ import annotations

from typing import Literal, Union

from pydantic import Field, TypeAdapter

from boneio.core.config.models.base import Model, Str, StrPeriod


class RemoteOutput(Model):
    # coerce: str turns a null into "None" in Cerberus, so it passes there.
    nullable = frozenset({"id"})

    id: Str | None = None
    name: str | None = None
    remote_source: Literal["esphome_api", "can", "mqtt", "wled"]
    device_id: str
    output_id: str
    output_type: Literal["switch", "light", "valve", "cover"] = "switch"
    show_in_ha: bool = False
    area: str | None = None
    on_disconnect: Literal["ignore", "turn_off"] = "ignore"
    momentary_turn_on: StrPeriod | None = None
    momentary_turn_off: StrPeriod | None = None
    adjustable_duration: bool = False
    duration_default: StrPeriod | None = None
    duration_min: StrPeriod | None = None
    duration_max: StrPeriod | None = None
    duration_unit: Literal["s", "min"] = "s"
    interlock_group: Union[str, list[str]] = Field(default_factory=list)
    enforce_interlock: bool = False


SECTION_ADAPTERS = {"remote_outputs": TypeAdapter(list[RemoteOutput])}
