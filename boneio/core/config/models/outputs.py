"""The ``output`` section: relays, lights, valves and what drives them.

Mirrors boneio/schema/schema.yaml for the section. The board mapping fills in
``kind``, ``pin`` and the expander id for an output named by
``boneio_output``; the model checks the entry as written, before that.
Since the map may also supply ``output_type``, the model leaves it optional
and ``yaml_util`` requires it once the map is applied.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import AfterValidator, BeforeValidator, Field

from boneio.core.config.models.base import ANY_CASE, Model, Str, StrPeriod, section, unique_explicit_ids


def _lower(value: Any) -> Any:
    return value.lower() if isinstance(value, str) else value


class Output(Model):
    # coerce: str turns a null into "None" in Cerberus, so it passes there.
    nullable = frozenset({"name", "id"})

    name: Str | None = Field(None, description="Display Name")
    id: Str | None = Field(None, description="Output ID")
    boneio_output: str | None = Field(None, description="BoneIO Output")
    area: str | None = Field(None, description="Area/Room")
    kind: Literal["gpio", "mcp", "pca", "pcf", "buzzer"] | None = Field(
        None, description="Output kind (mcp, gpio, buzzer, etc)"
    )
    sysfs_path: str | None = Field(None, description="Sysfs path for buzzer/led")
    mcp_id: str | None = Field(None, description="MCP ID reference")
    pca_id: str | None = Field(None, description="PCA ID to connect")
    pcf_id: str | None = Field(None, description="PCF ID to connect")
    pin: int | None = Field(None, description="Pin number")
    momentary_turn_on: StrPeriod | None = Field(
        None, description='How long can this relay be on. Can\'t be used if output_type is "none".'
    )
    momentary_turn_off: StrPeriod | None = Field(
        None, description='How long can this relay be off. Can\'t be used if output_type is "none".'
    )
    adjustable_duration: bool = Field(
        False,
        description="Enable an HA number entity (slider) to dynamically set the on-timer. When ON is pressed, "
        "auto-OFF after this duration.",
    )
    duration_default: StrPeriod | None = Field(
        None, description='Default adjustable duration (e.g. "60s", "5min", "1h").'
    )
    duration_min: StrPeriod | None = Field(None, description='Minimum adjustable duration (e.g. "1s", "10s").')
    duration_max: StrPeriod | None = Field(None, description='Maximum adjustable duration (e.g. "3600s", "1h").')
    duration_unit: Literal["s", "min"] = Field("s", description="Unit displayed on Home Assistant duration slider.")
    restore_state: bool = True
    interlock_group: Union[str, list] | None = Field(None, description="Interlock group name or list")
    percentage_default_brightness: int | None = Field(
        None,
        description="When the brightness is not set in ha, and we switch led to turn this value will be used",
    )
    output_type: Annotated[
        Literal["switch", "light", "cover", "valve", "none"] | None, BeforeValidator(_lower)
    ] = Field(
        None,
        description="Taken from the board when boneio_output names an output it maps; required otherwise. If HA "
        "discovery is used device if relay is light or switch. Cover if this output will be used for cover. "
        "If None is declared then any state is not published to MQTT (used for cover).",
        json_schema_extra=ANY_CASE,
    )


SECTION_ADAPTERS = {
    "output": section(
        Annotated[list[Output], AfterValidator(unique_explicit_ids)],
        "https://boneio.eu/docs/black/configuration/output \n List of outputs to define.",
    ),
}
