"""The ``remote_outputs`` section: outputs of other devices shown as this one's.

Mirrors boneio/schema/schema.yaml for the section.
"""

from __future__ import annotations

from typing import Literal, Union

from pydantic import Field

from boneio.core.config.models.base import Model, Str, StrPeriod, section


class RemoteOutput(Model):
    # coerce: str turns a null into "None" in Cerberus, so it passes there.
    nullable = frozenset({"id"})

    id: Str | None = Field(None, description="Output ID")
    name: str | None = Field(None, description="Display Name")
    remote_source: Literal["esphome_api", "can", "mqtt", "wled"] = Field(description="Remote Source Protocol")
    device_id: str = Field(description="Remote Device ID")
    output_id: str = Field(description="Output/Entity ID")
    output_type: Literal["switch", "light", "valve", "cover"] = Field("switch", description="Output Type")
    show_in_ha: bool = Field(False, description="Forward to Home Assistant")
    area: str | None = Field(None, description="Area (for HA)")
    on_disconnect: Literal["ignore", "turn_off"] = Field("ignore", description="On Disconnect Behavior")
    momentary_turn_on: StrPeriod | None = Field(None, description="Momentary Turn On")
    momentary_turn_off: StrPeriod | None = Field(None, description="Momentary Turn Off")
    adjustable_duration: bool = Field(False, description="Adjustable Duration")
    duration_default: StrPeriod | None = Field(
        None, description='Default adjustable duration (e.g. "60s", "5min", "1h").'
    )
    duration_min: StrPeriod | None = Field(None, description='Minimum adjustable duration (e.g. "1s", "10s").')
    duration_max: StrPeriod | None = Field(None, description='Maximum adjustable duration (e.g. "3600s", "1h").')
    duration_unit: Literal["s", "min"] = Field("s", description="Unit displayed on Home Assistant duration slider.")
    interlock_group: Union[str, list[str]] = Field(default_factory=list, description="Interlock Groups")
    enforce_interlock: bool = Field(False, description="Enforce Interlock on External Changes")


SECTION_ADAPTERS = {
    "remote_outputs": section(list[RemoteOutput], "Remote outputs from ESPHome, CAN, or other remote devices.")
}
