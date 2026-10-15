"""The ``remote_inputs`` section: buttons and sensors on other devices.

Mirrors boneio/schema/schema.yaml for the section, with one difference made
on purpose: ``actions`` there is any dictionary, while the runtime runs these
actions exactly as an input's. Here each one is checked by the same models
as the actions of ``event`` and ``binary_sensor``. The click types stay free:
which apply depends on the entry's ``mode``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import TypeAdapter

from boneio.core.config.models.base import Model, Str
from boneio.core.config.models.inputs import UNION_TAGS, Action  # noqa: F401 - UNION_TAGS for error paths


class RemoteInput(Model):
    # coerce: str turns a null into "None" in Cerberus, so it passes there.
    nullable = frozenset({"id"})

    id: Str | None = None
    name: str | None = None
    remote_source: Literal["esphome_api", "can", "mqtt"]
    device_id: str
    input_id: str
    topic: str | None = None
    mode: Literal["binary_sensor", "event"] = "binary_sensor"
    device_class: str | None = None
    area: str | None = None
    show_in_ha: bool = False
    inverted: bool = False
    double_click_duration: int | None = None
    long_press_duration: int | None = None
    sequence_mode: Literal["immediate", "exclusive"] | None = None
    long_press_mqtt_mode: Literal["single", "periodic"] | None = None
    enable_triple_click: bool = False
    actions: dict[str, list[Action]] | None = None


SECTION_ADAPTERS = {"remote_inputs": TypeAdapter(list[RemoteInput])}
