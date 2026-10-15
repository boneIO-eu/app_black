"""The ``output`` section: relays, lights, valves and what drives them.

Mirrors boneio/schema/schema.yaml for the section. The board mapping fills in
``kind``, ``pin`` and the expander id for an output named by
``boneio_output``; the model checks the entry as written, before that.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import AfterValidator, BeforeValidator, TypeAdapter

from boneio.core.config.models.base import Model, Str, StrPeriod


def _lower(value: Any) -> Any:
    return value.lower() if isinstance(value, str) else value


class Output(Model):
    # coerce: str turns a null into "None" in Cerberus, so it passes there.
    nullable = frozenset({"name", "id"})

    name: Str | None = None
    id: Str | None = None
    boneio_output: str | None = None
    area: str | None = None
    kind: Literal["gpio", "mcp", "pca", "pcf", "buzzer"] | None = None
    sysfs_path: str | None = None
    mcp_id: str | None = None
    pca_id: str | None = None
    pcf_id: str | None = None
    pin: int | None = None
    momentary_turn_on: StrPeriod | None = None
    momentary_turn_off: StrPeriod | None = None
    adjustable_duration: bool = False
    duration_default: StrPeriod | None = None
    duration_min: StrPeriod | None = None
    duration_max: StrPeriod | None = None
    duration_unit: Literal["s", "min"] = "s"
    restore_state: bool = True
    interlock_group: Union[str, list] | None = None
    percentage_default_brightness: int | None = None
    output_type: Annotated[
        Literal["switch", "light", "cover", "valve", "none"], BeforeValidator(_lower)
    ]


def _unique_ids(outputs: list[Output]) -> list[Output]:
    ids = [o.id for o in outputs if o.id]
    if len(ids) != len(set(ids)):
        raise ValueError("Output IDs are not unique.")
    return outputs


SECTION_ADAPTERS = {
    "output": TypeAdapter(Annotated[list[Output], AfterValidator(_unique_ids)]),
}
