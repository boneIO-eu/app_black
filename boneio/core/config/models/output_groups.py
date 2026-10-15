"""The ``output_group`` section: outputs switched together as one.

Mirrors boneio/schema/schema.yaml for the section.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BeforeValidator, TypeAdapter

from boneio.core.config.models.base import Model, Str, unique_explicit_ids


def _lower(value: Any) -> Any:
    return value.lower() if isinstance(value, str) else value


class OutputGroup(Model):
    # coerce: str turns a null into "None" in Cerberus, so it passes there.
    nullable = frozenset({"id", "name"})

    id: Str
    name: Str | None = None
    outputs: list
    all_on_behaviour: bool = False
    output_type: Annotated[Literal["switch", "light"], BeforeValidator(_lower)] = "switch"


SECTION_ADAPTERS = {
    "output_group": TypeAdapter(Annotated[list[OutputGroup], AfterValidator(unique_explicit_ids)]),
}
