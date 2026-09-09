"""Tests for action field validation in the WebUI config route.

Covers _validate_action_fields and _validate_section_actions to ensure
that hybrid action configs (e.g. remote_output + boneio_id) are rejected
before being written to disk.
"""

import pytest
from boneio.webui.action_validation import (
    clean_action_fields as _clean_action_fields,
    validate_action_fields as _validate_action_fields,
    validate_section_actions as _validate_section_actions,
)


# ---------------------------------------------------------------------------
# _validate_action_fields
# ---------------------------------------------------------------------------

class TestValidateActionFields:
    """Unit tests for _validate_action_fields."""

    # --- missing / unknown action type ---

    def test_missing_action_field_returns_error(self):
        assert _validate_action_fields({}) is not None

    def test_unknown_action_type_returns_error(self):
        err = _validate_action_fields({"action": "teleport"})
        assert err is not None
        assert "teleport" in err

    # --- output ---

    def test_valid_output_action(self):
        assert _validate_action_fields({
            "action": "output",
            "boneio_output": "OUT_01",
            "action_output": "TOGGLE",
        }) is None

    def test_output_with_boneio_id_returns_error(self):
        """output action must not carry boneio_id (belongs to output_over_mqtt)."""
        err = _validate_action_fields({
            "action": "output",
            "boneio_output": "OUT_01",
            "boneio_id": "boneio_remote",
        })
        assert err is not None
        assert "boneio_id" in err

    def test_output_with_remote_device_returns_error(self):
        err = _validate_action_fields({
            "action": "output",
            "boneio_output": "OUT_01",
            "remote_device": "esphome_garage",
        })
        assert err is not None

    # --- cover ---

    def test_valid_cover_action(self):
        assert _validate_action_fields({
            "action": "cover",
            "boneio_cover": "blind_01",
            "action_cover": "TOGGLE",
        }) is None

    # --- mqtt ---

    def test_valid_mqtt_action(self):
        assert _validate_action_fields({
            "action": "mqtt",
            "topic": "home/light/set",
            "action_mqtt_msg": "ON",
        }) is None

    # --- output_over_mqtt ---

    def test_valid_output_over_mqtt_action(self):
        assert _validate_action_fields({
            "action": "output_over_mqtt",
            "boneio_id": "boneio_led",
            "boneio_output": "OUT_03",
            "action_output": "ON",
        }) is None

    def test_output_over_mqtt_with_remote_device_returns_error(self):
        """output_over_mqtt must not carry remote_device (belongs to remote_output)."""
        err = _validate_action_fields({
            "action": "output_over_mqtt",
            "boneio_id": "boneio_led",
            "boneio_output": "OUT_03",
            "remote_device": "some_esp",
        })
        assert err is not None
        assert "remote_device" in err

    # --- remote_output (the main bug scenario) ---

    def test_valid_remote_output_action(self):
        assert _validate_action_fields({
            "action": "remote_output",
            "remote_device": "boneio_led",
            "output_id": "chr_02",
            "action_output": "TOGGLE",
            "brightness": 200,
            "transition": "1s",
        }) is None

    def test_remote_output_with_boneio_id_returns_error(self):
        """The primary bug: user switched from output_over_mqtt to remote_output,
        boneio_id was left in the action object."""
        err = _validate_action_fields({
            "action": "remote_output",
            "remote_device": "boneio_led",
            "output_id": "chr_02",
            "boneio_id": "boneio_led",   # stale field from output_over_mqtt
        })
        assert err is not None
        assert "boneio_id" in err

    def test_remote_output_with_boneio_output_returns_error(self):
        err = _validate_action_fields({
            "action": "remote_output",
            "remote_device": "boneio_led",
            "output_id": "chr_02",
            "boneio_output": "OUT_01",   # stale field from output action
        })
        assert err is not None
        assert "boneio_output" in err

    def test_remote_output_with_topic_returns_error(self):
        err = _validate_action_fields({
            "action": "remote_output",
            "remote_device": "boneio_led",
            "output_id": "chr_02",
            "topic": "home/light/set",   # stale field from mqtt
        })
        assert err is not None

    # --- remote_cover ---

    def test_valid_remote_cover_action(self):
        assert _validate_action_fields({
            "action": "remote_cover",
            "remote_device": "esp_home",
            "cover_id": "blinds_01",
            "action_cover": "TOGGLE",
        }) is None

    def test_remote_cover_with_boneio_id_returns_error(self):
        err = _validate_action_fields({
            "action": "remote_cover",
            "remote_device": "esp_home",
            "cover_id": "blinds_01",
            "boneio_id": "boneio_remote",
        })
        assert err is not None

    # --- shared fields always allowed ---

    def test_shared_fields_preserved_for_all_types(self):
        for action_type, extra in [
            ("output",           {"boneio_output": "OUT_01"}),
            ("remote_output",    {"remote_device": "d", "output_id": "o"}),
            ("output_over_mqtt", {"boneio_id": "x", "boneio_output": "OUT_01"}),
        ]:
            action = {
                "action": action_type,
                "min_duration": 500,
                "max_duration": 2000,
                "repeat": True,
                "repeat_interval": "800ms",
                **extra,
            }
            assert _validate_action_fields(action) is None, (
                f"Shared fields should be valid for action type '{action_type}'"
            )

    # --- case insensitive action type ---

    def test_action_type_is_case_insensitive(self):
        assert _validate_action_fields({
            "action": "OUTPUT",
            "boneio_output": "OUT_01",
        }) is None


# ---------------------------------------------------------------------------
# _validate_section_actions
# ---------------------------------------------------------------------------

class TestValidateSectionActions:
    """Tests for _validate_section_actions (full section validation)."""

    def test_empty_section_returns_no_errors(self):
        assert _validate_section_actions("event", []) == []

    def test_valid_event_section_returns_no_errors(self):
        data = [
            {
                "name": "Button_01",
                "boneio_input": "IN_01",
                "actions": {
                    "single": [{"action": "output", "boneio_output": "OUT_01"}],
                    "double": [{"action": "remote_output", "remote_device": "led", "output_id": "ch1"}],
                },
            }
        ]
        assert _validate_section_actions("event", data) == []

    def test_hybrid_action_in_event_section_auto_cleaned(self):
        """Stale fields are auto-stripped by validate_section_actions."""
        action = {
            "action": "remote_output",
            "remote_device": "boneio_led",
            "output_id": "chr_02",
            "action_output": "TOGGLE",
            "boneio_id": "boneio_led",   # stale field
            "brightness": 255,
            "transition": "1s",
        }
        data = [
            {
                "name": "Potrojny_prawy_kuchnia",
                "boneio_input": "IN_48",
                "actions": {"single": [action]},
            }
        ]
        errors = _validate_section_actions("event", data)
        assert len(errors) == 0
        # Stale field should have been removed from the action dict
        assert "boneio_id" not in action

    def test_multiple_stale_fields_auto_cleaned(self):
        """Multiple actions with stale fields are all auto-cleaned."""
        action1 = {"action": "remote_output", "remote_device": "d", "output_id": "o", "boneio_id": "x"}
        action2 = {"action": "output", "boneio_output": "OUT_01", "remote_device": "x"}
        action3 = {"action": "output_over_mqtt", "boneio_id": "y", "boneio_output": "OUT_02", "topic": "bad"}
        data = [
            {
                "name": "Btn_A",
                "boneio_input": "IN_01",
                "actions": {"single": [action1, action2]},
            },
            {
                "name": "Btn_B",
                "boneio_input": "IN_02",
                "actions": {"double": [action3]},
            },
        ]
        errors = _validate_section_actions("event", data)
        assert len(errors) == 0
        assert "boneio_id" not in action1
        assert "remote_device" not in action2
        assert "topic" not in action3

    def test_valid_binary_sensor_section(self):
        data = [
            {
                "name": "Sensor_01",
                "boneio_input": "IN_10",
                "actions": {
                    "pressed": [{"action": "output", "boneio_output": "OUT_05"}],
                    "released": [{"action": "mqtt", "topic": "home/t", "action_mqtt_msg": "OFF"}],
                },
            }
        ]
        assert _validate_section_actions("binary_sensor", data) == []

    def test_hybrid_action_in_binary_sensor_section_auto_cleaned(self):
        """Stale fields in binary_sensor section are auto-stripped."""
        action = {
            "action": "cover_over_mqtt",
            "boneio_id": "main",
            "boneio_cover": "blind",
            "remote_device": "stale",   # stale from remote_cover
        }
        data = [
            {
                "name": "PIR_01",
                "boneio_input": "IN_20",
                "actions": {"pressed": [action]},
            }
        ]
        errors = _validate_section_actions("binary_sensor", data)
        assert len(errors) == 0
        assert "remote_device" not in action

    def test_entity_without_actions_key_returns_no_errors(self):
        """Entities with no actions block should not cause errors."""
        data = [{"name": "In_46", "boneio_input": "IN_46"}]
        assert _validate_section_actions("event", data) == []

    def test_entity_with_empty_actions_returns_no_errors(self):
        data = [{"name": "In_47", "boneio_input": "IN_47", "actions": {}}]
        assert _validate_section_actions("event", data) == []

    def test_self_reference_single_condition_rejected(self):
        """Binary sensor referencing its own state in a condition should be rejected."""
        data = [
            {
                "name": "IN_48",
                "boneio_input": "IN_48",
                "actions": {
                    "pressed": [{
                        "action": "output",
                        "boneio_output": "OUT_01",
                        "condition": {
                            "type": "state",
                            "entity": "binary_sensor",
                            "entity_id": "IN_48",
                            "state": "is_on",
                        },
                    }],
                },
            }
        ]
        errors = _validate_section_actions("binary_sensor", data)
        assert len(errors) == 1
        assert "Self-referencing" in errors[0]

    def test_self_reference_in_conditions_list_rejected(self):
        """Self-reference in conditions list (multi-condition) should be rejected."""
        data = [
            {
                "name": "IN_48",
                "boneio_input": "IN_48",
                "actions": {
                    "released": [{
                        "action": "output",
                        "boneio_output": "OUT_02",
                        "conditions": {
                            "mode": "and",
                            "list": [
                                {"type": "time", "after": "08:00", "before": "22:00"},
                                {
                                    "type": "state",
                                    "entity": "binary_sensor",
                                    "entity_id": "IN_48",
                                    "state": "is_off",
                                },
                            ],
                        },
                    }],
                },
            }
        ]
        errors = _validate_section_actions("binary_sensor", data)
        assert len(errors) == 1
        assert "Self-referencing" in errors[0]

    def test_different_entity_id_no_self_reference(self):
        """Referencing a different binary sensor should not be flagged."""
        data = [
            {
                "name": "IN_48",
                "boneio_input": "IN_48",
                "actions": {
                    "pressed": [{
                        "action": "output",
                        "boneio_output": "OUT_01",
                        "condition": {
                            "type": "state",
                            "entity": "binary_sensor",
                            "entity_id": "IN_10",
                            "state": "is_on",
                        },
                    }],
                },
            }
        ]
        errors = _validate_section_actions("binary_sensor", data)
        assert len(errors) == 0

    def test_event_section_no_self_reference_check(self):
        """Event entities should not be checked for self-reference (only binary_sensor)."""
        data = [
            {
                "name": "IN_48",
                "boneio_input": "IN_48",
                "actions": {
                    "single": [{
                        "action": "output",
                        "boneio_output": "OUT_01",
                        "condition": {
                            "type": "state",
                            "entity": "binary_sensor",
                            "entity_id": "IN_48",
                            "state": "is_on",
                        },
                    }],
                },
            }
        ]
        errors = _validate_section_actions("event", data)
        assert len(errors) == 0


# ---------------------------------------------------------------------------
# Delayed execution fields (delay / delay_cancel_on)
# ---------------------------------------------------------------------------

class TestDelayFieldsPreserved:
    """Delay fields are shared fields and must survive save/sanitize.

    Regression: SHARED_FIELDS was missing 'delay' and 'delay_cancel_on', so
    clean_action_fields silently stripped them from every saved action and the
    UI's "delayed execution" setting never reached the YAML.
    """

    def test_clean_keeps_delay_fields(self):
        action = {
            "action": "output",
            "boneio_output": "OUT_24",
            "action_output": "OFF",
            "delay": "2min",
            "delay_cancel_on": ["pressed"],
        }
        removed = _clean_action_fields(action)
        assert removed == []
        assert action["delay"] == "2min"
        assert action["delay_cancel_on"] == ["pressed"]

    def test_validate_accepts_delay_fields(self):
        action = {
            "action": "output",
            "boneio_output": "OUT_24",
            "action_output": "OFF",
            "delay": "2min",
            "delay_cancel_on": ["pressed"],
        }
        assert _validate_action_fields(action) is None

    def test_section_save_keeps_delay_fields(self):
        data = [
            {
                "name": "Czujka_Bosh_1",
                "boneio_input": "in_46",
                "actions": {
                    "released": [{
                        "action": "output",
                        "boneio_output": "OUT_24",
                        "action_output": "OFF",
                        "delay": "2min",
                        "delay_cancel_on": ["pressed"],
                    }],
                },
            }
        ]
        errors = _validate_section_actions("binary_sensor", data)
        assert errors == []
        saved = data[0]["actions"]["released"][0]
        assert saved["delay"] == "2min"
        assert saved["delay_cancel_on"] == ["pressed"]

    @pytest.mark.parametrize("action_type,extra", [
        ("cover", {"boneio_cover": "cover1", "action_cover": "TILT"}),
        ("remote_cover", {"remote_device": "dev1", "cover_id": "c1", "action_cover": "TILT"}),
    ])
    def test_clean_keeps_restore_tilt(self, action_type, extra):
        action = {"action": action_type, "restore_tilt": True, **extra}
        assert _clean_action_fields(action) == []
        assert action["restore_tilt"] is True
