"""The seam a presence simulation rests on entirely.

A schedule fires; its condition asks whether a virtual switch is on; the
actions run or they do not. Both halves have their own tests — the scheduler
arms and fires, the switch holds and publishes a state — but nothing joined
them, and the join is the whole mechanism: every schedule the presence wizard
writes carries exactly this condition.

Nothing is stubbed between the two. The condition goes through the real
pre-compiler and the real ``Manager._resolve_entity_state``, against a real
``VirtualSwitchManager``.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from boneio.core.manager.action_conditions import (
    precompile_conditions,
    should_execute_action,
)
from boneio.core.manager.manager import Manager
from boneio.core.manager.virtual_switches import VirtualSwitchManager


class FakeStateManager:
    """The bits of StateManager a virtual switch touches."""

    def __init__(self) -> None:
        self.saved: dict[str, dict] = {}

    def get(self, attr_type, attr, default_value=None):
        return self.saved.get(attr_type, {}).get(attr, default_value)

    def save_attribute(self, attr_type, attribute, value) -> None:
        self.saved.setdefault(attr_type, {})[attribute] = value


ARMED_ONLY = {
    "type": "state",
    "entity": "virtual_switch",
    "entity_id": "presence_away",
    "state": "is_on",
}


@pytest.fixture
def manager():
    """A manager stub with a real virtual switch manager behind it."""
    fake = MagicMock()
    fake._message_bus.send_message = lambda **kwargs: None
    fake._event_bus.trigger_event = lambda event: None
    fake._topic_prefix = "boneio/blk"
    fake._state_manager = FakeStateManager()
    fake.parse_actions = lambda pin, actions: {
        key: list(value) for key, value in actions.items()
    }
    fake.execute_actions = None
    fake.virtual_switches = VirtualSwitchManager(
        manager=fake, config=[{"name": "Presence away", "id": "presence_away"}]
    )
    # The real resolver, so the condition walks the path it walks on device.
    fake._resolve_entity_state = lambda entity_type, entity_id: Manager._resolve_entity_state(
        fake, entity_type, entity_id
    )
    return fake


def _would_run(manager, now=None) -> bool:
    """Evaluate a schedule's gate the way execute_actions does."""
    from datetime import datetime

    compiled = precompile_conditions({"condition": ARMED_ONLY})
    return should_execute_action(
        compiled,
        now or datetime.now().astimezone(),
        manager._resolve_entity_state,
    )


@pytest.mark.asyncio
async def test_the_flag_off_stops_the_schedule(manager):
    assert manager.virtual_switches.get("presence_away").is_active is False
    assert _would_run(manager) is False


@pytest.mark.asyncio
async def test_the_flag_on_lets_the_schedule_through(manager):
    await manager.virtual_switches.get("presence_away").async_turn_on()
    assert _would_run(manager) is True


@pytest.mark.asyncio
async def test_turning_it_off_again_closes_the_gate(manager):
    switch = manager.virtual_switches.get("presence_away")
    await switch.async_turn_on()
    assert _would_run(manager) is True
    await switch.async_turn_off()
    assert _would_run(manager) is False, "the gate stayed open after disarming"


@pytest.mark.asyncio
async def test_a_condition_naming_a_missing_switch_FAILS_OPEN(manager):
    """Pins the runtime behaviour, which is still the dangerous direction —
    and is now unreachable from a configuration.

    A condition whose entity cannot be resolved lets the action run:
    ``action_conditions`` logs "not found, allowing action" and returns True.
    For most conditions that is defensible — a broken reference should not
    silently stop the lights working. For "only while nobody is home" it is
    backwards, because one typo would fire every step of a presence simulation
    while somebody is in the house.

    The runtime is unchanged, because flipping it would silently stop actions
    in every existing config with a stale reference. The reference is caught
    one level up instead: ``_check_virtual_switch_references`` refuses to load
    a config naming a virtual switch that is not defined, so nothing dangling
    reaches this code any more (see test_identity_rules.py). This test stays as
    the statement of what would happen if one did.
    """
    from datetime import datetime

    compiled = precompile_conditions(
        {"condition": {**ARMED_ONLY, "entity_id": "presence_awya"}}
    )
    ran = should_execute_action(
        compiled, datetime.now().astimezone(), manager._resolve_entity_state
    )
    assert ran is True, (
        "fail-open changed — if this is now False, the load-time check for "
        "dangling condition references should replace this test"
    )


@pytest.mark.asyncio
async def test_the_gate_survives_a_config_reload(manager):
    """Saving the page rebuilds every switch. A schedule armed before the save
    must still be armed after it — the state is handed to the new instance."""
    switch = manager.virtual_switches.get("presence_away")
    await switch.async_turn_on()

    await manager.virtual_switches.reload(
        [{"name": "Presence away", "id": "presence_away", "description": "edited"}]
    )

    assert manager.virtual_switches.get("presence_away").is_active is True
    assert _would_run(manager) is True
