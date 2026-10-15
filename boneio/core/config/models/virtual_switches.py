"""The ``virtual_switch`` section: flags that conditions read and actions set.

Mirrors boneio/schema/schema.yaml for the section. Its actions are the
inputs' actions, checked by the same models.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator, TypeAdapter, model_validator

from boneio.core.config.models.base import Model, Str, unique_resolved_ids
from boneio.core.config.models.inputs import UNION_TAGS, Action  # noqa: F401 - UNION_TAGS for error paths
from boneio.core.utils.naming import resolve_id


class SwitchActions(Model):
    on_turn_on: list[Action] | None = None
    on_turn_off: list[Action] | None = None


class VirtualSwitch(Model):
    # coerce: str turns a null into "None" in Cerberus, so it passes there.
    nullable = frozenset({"id"})

    name: str
    description: str | None = None
    id: Str | None = None
    area: str | None = None
    icon: str | None = None
    restore_state: bool = True
    initial: bool = False
    show_in_ha: bool = True
    actions: SwitchActions | None = None

    @model_validator(mode="after")
    def _does_not_set_itself(self) -> VirtualSwitch:
        # The runtime guard stops the recursion by refusing to act, so such a
        # switch would load, look right, and do half of what it says.
        switch_id = resolve_id({"id": self.id, "name": self.name})
        if not switch_id or self.actions is None:
            return self
        for key in ("on_turn_on", "on_turn_off"):
            for action in getattr(self.actions, key) or []:
                if action.action == "virtual_switch" and action.boneio_virtual_switch == switch_id:
                    raise ValueError(
                        f"Virtual switch '{switch_id}' sets itself in '{key}', which cannot "
                        "work: the change that would run the actions is the one they are "
                        "trying to make."
                    )
        return self


SECTION_ADAPTERS = {
    "virtual_switch": TypeAdapter(Annotated[list[VirtualSwitch], AfterValidator(unique_resolved_ids)]),
}
