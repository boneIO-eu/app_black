"""Tests for action field validation in the WebUI config route.

Covers _validate_action_fields and _validate_section_actions to ensure
that hybrid action configs (e.g. remote_output + boneio_id) are rejected
before being written to disk.
"""

import pytest
from boneio.webui.action_validation import validate_action_fields as _validate_action_fields, validate_section_actions as _validate_section_actions


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

    def test_hybrid_action_in_event_section_returns_error(self):
        """The exact scenario from the bug report."""
        data = [
            {
                "name": "Potrojny_prawy_kuchnia",
                "boneio_input": "IN_45",
                "actions": {
                    "single": [{
                        "action": "remote_output",
                        "remote_device": "boneio_led",
                        "output_id": "chr_02",
                        "boneio_id": "boneio_led",   # stale field
                        "brightness": 255,
                        "transition": "1s",
                    }],
                },
            }
        ]
        errors = _validate_section_actions("event", data)
        assert len(errors) == 1
        assert "Potrojny_prawy_kuchnia" in errors[0]
        assert "boneio_id" in errors[0]

    def test_multiple_errors_reported(self):
        data = [
            {
                "name": "Btn_A",
                "boneio_input": "IN_01",
                "actions": {
                    "single": [
                        {"action": "remote_output", "remote_device": "d", "output_id": "o", "boneio_id": "x"},
                        {"action": "output", "boneio_output": "OUT_01", "remote_device": "x"},
                    ],
                },
            },
            {
                "name": "Btn_B",
                "boneio_input": "IN_02",
                "actions": {
                    "double": [
                        {"action": "output_over_mqtt", "boneio_id": "y", "boneio_output": "OUT_02", "topic": "bad"},
                    ],
                },
            },
        ]
        errors = _validate_section_actions("event", data)
        assert len(errors) == 3

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

    def test_hybrid_action_in_binary_sensor_section(self):
        data = [
            {
                "name": "PIR_01",
                "boneio_input": "IN_20",
                "actions": {
                    "pressed": [{
                        "action": "cover_over_mqtt",
                        "boneio_id": "main",
                        "boneio_cover": "blind",
                        "remote_device": "stale",   # stale from remote_cover
                    }],
                },
            }
        ]
        errors = _validate_section_actions("binary_sensor", data)
        assert len(errors) == 1
        assert "PIR_01" in errors[0]

    def test_entity_without_actions_key_returns_no_errors(self):
        """Entities with no actions block should not cause errors."""
        data = [{"name": "In_46", "boneio_input": "IN_46"}]
        assert _validate_section_actions("event", data) == []

    def test_entity_with_empty_actions_returns_no_errors(self):
        data = [{"name": "In_47", "boneio_input": "IN_47", "actions": {}}]
        assert _validate_section_actions("event", data) == []
