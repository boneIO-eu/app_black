"""The ``virtual_switch`` section: flags that conditions read and actions set.

Mirrors boneio/schema/schema.yaml for the section. Its actions are the
inputs' actions, checked by the same models.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator, Field, model_validator

from boneio.core.config.models.base import Model, Str, section, unique_resolved_ids
from boneio.core.config.models.inputs import UNION_TAGS, Action  # noqa: F401 - UNION_TAGS for error paths
from boneio.core.utils.naming import resolve_id


class SwitchActions(Model):
    on_turn_on: list[Action] | None = None
    on_turn_off: list[Action] | None = None


class VirtualSwitch(Model):
    # coerce: str turns a null into "None" in Cerberus, so it passes there.
    nullable = frozenset({"id"})

    name: str = Field(description="Name")
    description: str | None = Field(None, description="What this flag is for.")
    id: Str | None = Field(None, description="Identifier, if the one made from the name will not do.")
    area: str | None = Field(None, description="Area/room for Home Assistant grouping.")
    icon: str | None = Field(None, description="Home Assistant icon, e.g. `mdi:weather-night`.")
    restore_state: bool = Field(True, description="Remember the state across a restart.")
    initial: bool = Field(False, description="State to start in when there is nothing to restore.")
    show_in_ha: bool = Field(True, description="Announce this switch to Home Assistant.")
    actions: SwitchActions | None = Field(None, description="Actions to run when this switch changes.")

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
    "virtual_switch": section(
        Annotated[list[VirtualSwitch], AfterValidator(unique_resolved_ids)],
        "Virtual switches — an on/off flag with no relay behind it.",
    ),
}
