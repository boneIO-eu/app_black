"""What every section model shares: Cerberus' reading of a value, and its coercions."""

from __future__ import annotations

from typing import Annotated, Any, ClassVar

from pydantic import BaseModel, BeforeValidator, ConfigDict, model_validator
from pydantic_core import PydanticUndefined

from boneio.core.config.yaml_util import CustomValidator
from boneio.core.utils import TimePeriod

# ponytail: the coercions still live on the Cerberus validator; move them to
# plain functions when the last section leaves Cerberus.
_cerberus = CustomValidator({})


def coerce(name: str):
    """A ``coerce:`` rule of the Cerberus schema, as a pydantic validator."""
    method = getattr(_cerberus, f"_normalize_coerce_{name}")

    def run(value: Any) -> Any:
        # Cerberus reports any exception a coercion raises as the field's
        # error, so a coercion fed the wrong type is an error here too.
        try:
            return method(value)
        except Exception as err:  # noqa: BLE001
            raise ValueError(str(err) or type(err).__name__) from None

    return run


_time_period = coerce("positive_time_period")


def _str_time_period(value: Any) -> Any:
    """``coerce: [str, positive_time_period]``."""
    return value if isinstance(value, TimePeriod) else _time_period(str(value))


def str_lower(value: Any) -> Any:
    """``coerce: [str, lower]``."""
    return str(value).lower()


Period = Annotated[TimePeriod, BeforeValidator(_time_period)]
StrPeriod = Annotated[TimePeriod, BeforeValidator(_str_time_period)]
Str = Annotated[str, BeforeValidator(str)]
"""``coerce: str``: anything but a null becomes its string."""


class Model(BaseModel):
    """Strict like the Cerberus schema: no "yes" for a boolean, no 5 for a string."""

    model_config = ConfigDict(extra="ignore", strict=True, arbitrary_types_allowed=True)

    #: Fields whose null Cerberus' coercion turns into a value (str() into
    #: "None", sun_offset into 0); handed to the field's own coercion.
    nullable: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode="before")
    @classmethod
    def _as_cerberus_reads_it(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        fields = cls.model_fields
        refused = []
        for key in [k for k, v in data.items() if v is None and k in fields]:
            # Cerberus fills a null with the field's default, as if it were
            # missing; with no default it is an error - unless a coercion
            # makes something of it.
            if key in cls.nullable:
                continue
            field = fields[key]
            if field.default not in (None, PydanticUndefined) or field.default_factory is not None:
                data = {k: v for k, v in data.items() if k != key}
            else:
                refused.append(key)
        if refused:
            raise ValueError(f"null value not allowed: {', '.join(sorted(refused))}")
        return cls._refuse_forbidden(data)

    @classmethod
    def _refuse_forbidden(cls, data: dict) -> dict:
        """Refuse fields this model may not carry; runs after nulls are read."""
        return data


def unique_explicit_ids(entries: list) -> list:
    """Refuse two entries with the same explicit ``id``; entries without one pass."""
    ids = [e.id for e in entries if e.id]
    if len(ids) != len(set(ids)):
        raise ValueError("Output IDs are not unique.")
    return entries


def unique_resolved_ids(entries: list) -> list:
    """Refuse two entries that resolve to the same identifier (``resolve_id``).

    Identifiers are made from names when no ``id`` is given: two lights both
    called "Salon" in different rooms are an easy thing to write and produce
    one entity, with the second silently dropped at start-up.
    """
    from boneio.core.utils.naming import resolve_id

    seen: dict[str, int] = {}
    for index, entry in enumerate(entries):
        entry_id = resolve_id({"id": entry.id, "name": entry.name})
        if not entry_id:
            raise ValueError(f"Entry {index + 1} has no name to make an identifier from.")
        if entry_id in seen:
            raise ValueError(
                f"Entries {seen[entry_id] + 1} and {index + 1} both resolve to the identifier "
                f"{entry_id!r}. Names do not have to be unique, but what they are turned into "
                "does — give one of them an explicit 'id', or a name that differs by more than "
                "punctuation."
            )
        seen[entry_id] = index
    return entries
