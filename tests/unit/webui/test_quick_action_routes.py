"""Tests for the quick-action routes behind Teach Mode and the quick action.

They had none, and three things were wrong that tests would have caught: a
binary input's actions went to a key the config loader throws away, an edit
dropped every field the flat payload does not name, and the editor's own
action types could not be stored. The routes are called directly with the
config and the background YAML write stubbed out — what matters is what ends
up in the section that would be written.
"""

from __future__ import annotations

import asyncio
import copy
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from boneio.webui.routes import config_actions


def _config() -> dict:
    return {
        "event": [
            {"id": "IN_01", "boneio_input": "in_01", "area": "kitchen"},
            {
                "id": "IN_02",
                "boneio_input": "in_02",
                "actions": {
                    "single": [
                        {
                            "action": "output",
                            "boneio_output": "out_01",
                            "action_output": "TOGGLE",
                            "delay": "2min",
                            "min_duration": 100,
                        }
                    ]
                },
            },
        ],
        "binary_sensor": [
            {"id": "IN_48", "boneio_input": "in_48"},
            {
                "id": "IN_49",
                "boneio_input": "in_49",
                # Where the old quick action put them.
                "actions_on_press": [
                    {"action": "output", "boneio_output": "out_02", "action_output": "ON"}
                ],
            },
        ],
        "virtual_switch": [{"id": "away"}],
    }


@pytest.fixture
def store(monkeypatch):
    """The config the routes read, and what they would write back."""
    state = {"config": _config(), "written": {}}

    def load(_app_state):
        return state["config"]

    def invalidate(section=None, section_data=None):
        state["config"][section] = copy.deepcopy(section_data)
        state["written"][section] = copy.deepcopy(section_data)

    app_state = MagicMock()
    app_state.manager.inputs._inputs = {}
    monkeypatch.setattr(config_actions, "_get_app_state", lambda: app_state)
    monkeypatch.setattr(config_actions, "_load_config_from_cache_or_disk", load)
    monkeypatch.setattr(config_actions, "invalidate_config_cache", invalidate)
    monkeypatch.setattr(config_actions, "update_config_section", lambda *a: {"status": "ok"})
    return state


def run(coro):
    return asyncio.run(coro)


def _entry(store, section: str, entry_id: str) -> dict:
    return next(e for e in store["config"][section] if e["id"] == entry_id)


class TestActionDef:
    def test_a_whole_action_is_stored_with_everything_the_editor_set(self, store):
        action = {
            "action": "output",
            "boneio_output": "out_03",
            "action_output": "ON",
            "delay": "5min",
            "conditions": {"type": "and", "list": [{"type": "state", "entity": "output", "entity_id": "out_04", "state": "OFF"}]},
        }
        run(config_actions.add_quick_action({"entity_id": "IN_01", "click_type": "double", "action_def": action}))
        assert _entry(store, "event", "IN_01")["actions"]["double"] == [action]

    def test_a_virtual_switch_action_is_accepted(self, store):
        """The input editor offers it; the validator used to refuse it."""
        action = {"action": "virtual_switch", "boneio_virtual_switch": "away", "action_output": "ON"}
        run(config_actions.add_quick_action({"entity_id": "IN_01", "click_type": "single", "action_def": action}))
        assert _entry(store, "event", "IN_01")["actions"]["single"] == [action]

    def test_leftovers_from_another_type_and_empty_fields_are_dropped(self, store):
        action = {
            "action": "cover", "boneio_cover": "c1", "action_cover": "OPEN",
            "boneio_output": "out_01", "topic": "", "delay": None,
        }
        run(config_actions.add_quick_action({"entity_id": "IN_01", "click_type": "single", "action_def": action}))
        assert _entry(store, "event", "IN_01")["actions"]["single"] == [
            {"action": "cover", "boneio_cover": "c1", "action_cover": "OPEN"}
        ]

    @pytest.mark.parametrize("action", [
        {"action": "output", "action_output": "ON"},
        {"action": "remote_output", "remote_device": "esp1"},
        {"action": "nope"},
        "output",
    ])
    def test_an_action_without_its_target_is_refused(self, store, action):
        with pytest.raises(HTTPException) as err:
            run(config_actions.add_quick_action({"entity_id": "IN_01", "click_type": "single", "action_def": action}))
        assert err.value.status_code == 422
        assert "actions" not in _entry(store, "event", "IN_01")

    def test_a_sun_condition_without_a_location_is_refused(self, store):
        action = {
            "action": "output", "boneio_output": "out_01", "action_output": "ON",
            "condition": {"type": "sun", "after": "sunset"},
        }
        with pytest.raises(HTTPException) as err:
            run(config_actions.add_quick_action({"entity_id": "IN_01", "click_type": "single", "action_def": action}))
        assert err.value.status_code == 422


class TestDuplicates:
    def test_the_same_action_twice_is_a_409(self, store):
        action = {"action": "output", "boneio_output": "out_03", "action_output": "TOGGLE"}
        payload = {"entity_id": "IN_01", "click_type": "single", "action_def": action}
        run(config_actions.add_quick_action(payload))
        with pytest.raises(HTTPException) as err:
            run(config_actions.add_quick_action(payload))
        assert err.value.status_code == 409

    def test_a_different_action_on_the_same_output_is_allowed(self, store):
        """ON when dark and OFF otherwise is two actions on one relay."""
        base = {"action": "output", "boneio_output": "out_03"}
        run(config_actions.add_quick_action({"entity_id": "IN_01", "click_type": "single", "action_def": {**base, "action_output": "ON"}}))
        run(config_actions.add_quick_action({"entity_id": "IN_01", "click_type": "single", "action_def": {**base, "action_output": "OFF"}}))
        assert len(_entry(store, "event", "IN_01")["actions"]["single"]) == 2


class TestBinaryInputs:
    def test_actions_go_under_actions_pressed_not_the_purged_key(self, store):
        run(config_actions.add_quick_action({
            "entity_id": "IN_48", "click_type": "pressed", "action_type": "output",
            "output_id": "out_05", "action": "ON",
        }))
        entry = _entry(store, "binary_sensor", "IN_48")
        assert entry["actions"]["pressed"] == [{"action": "output", "boneio_output": "out_05", "action_output": "ON"}]
        assert "actions_on_press" not in entry

    def test_legacy_actions_are_listed_and_moved_on_the_next_edit(self, store):
        listed = run(config_actions.get_input_actions("IN_49"))
        assert [(a["click_type"], a["index"], a["target"]) for a in listed["actions"]] == [("pressed", 0, "out_02")]

        run(config_actions.add_quick_action({
            "entity_id": "IN_49", "click_type": "released",
            "action_def": {"action": "output", "boneio_output": "out_02", "action_output": "OFF"},
        }))
        entry = _entry(store, "binary_sensor", "IN_49")
        assert "actions_on_press" not in entry
        assert [a["action_output"] for a in entry["actions"]["pressed"]] == ["ON"]
        assert [a["action_output"] for a in entry["actions"]["released"]] == ["OFF"]

    def test_an_event_click_type_on_a_binary_input_is_refused(self, store):
        with pytest.raises(HTTPException) as err:
            run(config_actions.add_quick_action({
                "entity_id": "IN_48", "click_type": "double",
                "action_def": {"action": "output", "boneio_output": "out_05", "action_output": "ON"},
            }))
        assert err.value.status_code == 422

    def test_single_on_a_binary_input_still_means_pressed(self, store):
        run(config_actions.add_quick_action({
            "entity_id": "IN_48", "click_type": "single",
            "action_def": {"action": "output", "boneio_output": "out_05", "action_output": "ON"},
        }))
        assert "pressed" in _entry(store, "binary_sensor", "IN_48")["actions"]


class TestUpdate:
    def test_a_flat_update_keeps_the_fields_it_does_not_name(self, store):
        """It used to drop delay and min_duration and keep a key that does not exist."""
        run(config_actions.update_quick_action({
            "entity_id": "IN_02", "click_type": "single", "index": 0,
            "action_type": "output", "output_id": "out_07", "action": "ON",
        }))
        assert _entry(store, "event", "IN_02")["actions"]["single"] == [{
            "action": "output", "boneio_output": "out_07", "action_output": "ON",
            "delay": "2min", "min_duration": 100,
        }]

    def test_an_action_def_update_replaces_the_whole_action(self, store):
        action = {"action": "mqtt", "topic": "home/bell", "action_mqtt_msg": "ring"}
        run(config_actions.update_quick_action({
            "entity_id": "IN_02", "click_type": "single", "index": 0, "action_def": action,
        }))
        assert _entry(store, "event", "IN_02")["actions"]["single"] == [action]

    def test_moving_to_another_click_type_leaves_no_empty_list(self, store):
        result = run(config_actions.update_quick_action({
            "entity_id": "IN_02", "click_type": "single", "new_click_type": "long", "index": 0,
            "action_def": {"action": "output", "boneio_output": "out_01", "action_output": "ON", "repeat": True},
        }))
        actions = _entry(store, "event", "IN_02")["actions"]
        assert "single" not in actions
        assert actions["long"][0]["repeat"] is True
        assert result["index"] == 0


class TestDelete:
    def test_deleting_the_last_action_removes_the_container(self, store):
        run(config_actions.delete_quick_action({"entity_id": "IN_02", "click_type": "single", "index": 0}))
        assert "actions" not in _entry(store, "event", "IN_02")

    def test_a_legacy_binary_action_can_be_deleted(self, store):
        run(config_actions.delete_quick_action({"entity_id": "IN_49", "click_type": "pressed", "index": 0}))
        entry = _entry(store, "binary_sensor", "IN_49")
        assert "actions" not in entry
        assert "actions_on_press" not in entry


class TestTimePeriods:
    """The parsed config holds durations as TimePeriod objects."""

    def test_listed_actions_carry_durations_as_the_yaml_spells_them(self, store):
        from boneio.core.utils import TimePeriod

        _entry(store, "event", "IN_02")["actions"]["single"][0]["repeat_interval"] = TimePeriod(milliseconds=800)
        listed = run(config_actions.get_input_actions("IN_02"))
        assert listed["actions"][0]["raw"]["repeat_interval"] == "800ms"

    def test_a_json_encoded_time_period_is_stored_as_a_string(self, store):
        """What an editor sends back if it loaded the object form — a dict the
        config loader refuses, which would keep the device from starting."""
        encoded = {"milliseconds": None, "seconds": 120, "_timedelta": 120.0, "_total_in_seconds": 120.0}
        run(config_actions.add_quick_action({
            "entity_id": "IN_01", "click_type": "long",
            "action_def": {"action": "output", "boneio_output": "out_01", "action_output": "ON",
                           "repeat": True, "repeat_interval": encoded},
        }))
        assert _entry(store, "event", "IN_01")["actions"]["long"][0]["repeat_interval"] == "120s"


class TestRouting:
    """``PUT /config/{section}`` sits on the same router and was matched first:
    an edit from Teach Mode was written into config.yaml as a section named
    ``quick-action`` and the action itself never changed."""

    def test_put_quick_action_reaches_its_own_handler(self):
        from boneio.webui.routes import config  # noqa: F401 — registers every config route
        from boneio.webui.routes.config_core import router

        puts = [r.path for r in router.routes if "PUT" in (getattr(r, "methods", None) or ())]
        assert puts.index("/api/config/quick-action") < puts.index("/api/config/{section}")

    def test_the_section_route_refuses_a_name_that_is_not_a_section(self):
        from boneio.webui.routes.config_core import update_section_content

        with pytest.raises(HTTPException) as err:
            run(update_section_content("quick-action", {"entity_id": "in_05"}))
        assert err.value.status_code == 404
