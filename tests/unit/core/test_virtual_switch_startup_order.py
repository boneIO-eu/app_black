"""Actions that target a virtual switch are resolved while the manager is built.

Input actions are parsed as the inputs are built, and a virtual switch's own
actions as the switches are. Both look the target up through
``manager.virtual_switches``. When the switches were built after the inputs,
an input whose action set a virtual switch stopped the controller from
starting at all, with ``'Manager' object has no attribute 'virtual_switches'``;
a switch whose action set another switch did the same from inside its own
constructor.

These build the real ``Manager`` with every other subsystem stubbed, so the
construction order itself is what is under test.
"""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock

import pytest

from boneio.core.manager import manager as manager_module
from boneio.core.manager.manager import Manager
from boneio.core.manager.virtual_switches import VirtualSwitchManager

INPUT_ACTIONS = {
    "single": [
        {"action": "virtual_switch", "boneio_virtual_switch": "away", "action_output": "ON"},
    ]
}


class StateManager:
    def get(self, attr_type, attr, default_value=None):
        return default_value

    def save_attribute(self, attr_type, attribute, value):
        pass


@pytest.fixture
def build(monkeypatch):
    """Build a Manager whose only real parts are the virtual switches and parse_actions."""
    parsed: dict[str, dict] = {}

    class Inputs:
        """Parses an input's actions at construction, as InputManager does."""

        def __init__(self, manager, **_kwargs):
            parsed["input"] = manager.parse_actions("IN_01", INPUT_ACTIONS)

    for name, value in vars(manager_module).items():
        # Every subsystem class the module uses, except the two under test.
        if (
            inspect.isclass(value)
            and value.__module__.startswith("boneio")
            and value not in (Manager, VirtualSwitchManager)
            and not issubclass(value, BaseException)
        ):
            monkeypatch.setattr(manager_module, name, MagicMock(name=name))
    monkeypatch.setattr(manager_module, "InputManager", Inputs)
    monkeypatch.setattr(Manager, "register_remote_outputs", lambda self: None)

    def make(virtual_switch):
        config_helper = MagicMock()
        config_helper.topic_prefix = "boneio/test"
        manager = Manager(
            message_bus=MagicMock(),
            event_bus=MagicMock(),
            state_manager=StateManager(),
            config_helper=config_helper,
            config_file_path="/nonexistent/config.yaml",
            virtual_switch=virtual_switch,
        )
        return manager, parsed

    return make


def test_an_input_action_on_a_virtual_switch_does_not_stop_the_start(build):
    manager, parsed = build([{"id": "away", "name": "Away"}])
    assert manager.virtual_switches.get("away") is not None
    actions = parsed["input"]["single"]
    assert [a["boneio_virtual_switch"] for a in actions] == ["away"]


def test_a_switch_may_set_another_switch(build):
    manager, _ = build(
        [
            {"id": "away", "name": "Away"},
            {
                "id": "night",
                "name": "Night",
                "actions": {
                    "on_turn_on": [
                        {"action": "virtual_switch", "boneio_virtual_switch": "away",
                         "action_output": "ON"},
                    ]
                },
            },
        ]
    )
    assert manager.virtual_switches.get("night") is not None
