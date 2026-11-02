"""The ``remote_inputs`` section: buttons and sensors on other devices.

Mirrors boneio/schema/schema.yaml for the section, with one difference made
on purpose: ``actions`` there is any dictionary, while the runtime runs these
actions exactly as an input's. Here each one is checked by the same models
as the actions of ``event`` and ``binary_sensor``. The click types stay free:
which apply depends on the entry's ``mode``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from boneio.core.config.models.base import Model, Str, section
from boneio.core.config.models.inputs import UNION_TAGS, Action  # noqa: F401 - UNION_TAGS for error paths


class RemoteInput(Model):
    # coerce: str turns a null into "None" in Cerberus, so it passes there.
    nullable = frozenset({"id"})

    id: Str | None = Field(None, description="Input ID")
    name: str | None = Field(None, description="Display Name")
    remote_source: Literal["esphome_api", "can", "mqtt"] = Field(description="Remote Source Protocol")
    device_id: str = Field(description="Remote Device ID")
    input_id: str = Field(description="Input/Sensor ID")
    topic: str | None = Field(None, description="MQTT topic (mqtt source only)")
    mode: Literal["binary_sensor", "event"] = Field("binary_sensor", description="Mode")
    device_class: str | None = Field(None, description="Device Class (for HA)")
    area: str | None = Field(None, description="Area (for HA)")
    show_in_ha: bool = Field(False, description="Forward to Home Assistant")
    inverted: bool = Field(False, description="Invert state")
    double_click_duration: int | None = Field(None, description="Double Click Window (ms)")
    long_press_duration: int | None = Field(None, description="Long Press Threshold (ms)")
    sequence_mode: Literal["immediate", "exclusive"] | None = Field(None, description="Sequence Mode")
    long_press_mqtt_mode: Literal["single", "periodic"] | None = Field(None, description="Long Press MQTT Mode")
    enable_triple_click: bool = Field(False, description="Enable Triple Click")
    actions: dict[str, list[Action]] | None = Field(None, description="Actions")


SECTION_ADAPTERS = {
    "remote_inputs": section(
        list[RemoteInput], "Remote binary sensor inputs from ESPHome, CAN, or other remote devices."
    )
}
