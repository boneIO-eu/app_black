"""The ``output_group`` section: outputs switched together as one.

Mirrors boneio/schema/schema.yaml for the section.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BeforeValidator, Field

from boneio.core.config.models.base import ANY_CASE, Model, Str, section, unique_explicit_ids


def _lower(value: Any) -> Any:
    return value.lower() if isinstance(value, str) else value


class OutputGroup(Model):
    # coerce: str turns a null into "None" in Cerberus, so it passes there.
    nullable = frozenset({"id", "name"})

    id: Str = Field(description="Group ID")
    name: Str | None = Field(None, description="Display Name")
    outputs: list = Field(description="Output IDs")
    all_on_behaviour: bool = Field(
        False,
        description="Behaviour if set true toggle when all outputs are on, otherwise if any is on then group is on.",
    )
    output_type: Annotated[Literal["switch", "light"], BeforeValidator(_lower)] = Field(
        "switch", description="If HA discovery is used device if relay is light or switch.", json_schema_extra=ANY_CASE
    )


SECTION_ADAPTERS = {
    "output_group": section(
        Annotated[list[OutputGroup], AfterValidator(unique_explicit_ids)],
        "https://boneio.eu/docs/black/configuration/output_group \n List of grouped outputs to define. Output "
        "has to be defined first in output section!",
    ),
}
