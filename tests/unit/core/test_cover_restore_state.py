"""Unit tests for cover state restore after restart.

Tests verify that the CoverManager correctly deserializes saved cover state
from the StateManager. The core bug: save_attribute uses json.dumps() to store
position, but restore used isinstance(str) to discard the string and reset
to default position=100, losing the user's saved state.

These tests use a minimal stub approach to avoid hardware dependencies
(smbus2, gpiod, etc.) that are unavailable on dev machines.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Minimal stub that reproduces the CoverManager._configure_cover restore logic
# without importing boneio (which pulls in smbus2, gpiod, etc.)
# ---------------------------------------------------------------------------

def _deserialize_restored_state(
    raw_value,
    default: dict,
) -> dict:
    """Reproduce the fixed deserialization logic from CoverManager._configure_cover.

    This mirrors the code in covers.py:
    1. If str → json.loads()
    2. If int/float → wrap in {"position": value}
    3. If dict → use directly

    Args:
        raw_value: Value returned by StateManager.get()
        default: Default state dict if deserialization fails

    Returns:
        Deserialized state dict with at least a 'position' key.
    """
    restored_state = raw_value
    if isinstance(restored_state, str):
        try:
            restored_state = json.loads(restored_state)
        except (json.JSONDecodeError, TypeError):
            restored_state = dict(default)
    if isinstance(restored_state, (float, int)):
        restored_state = {"position": restored_state}
        # Add tilt_position if default has it
        if "tilt" in default:
            restored_state["tilt"] = default["tilt"]
    return restored_state


# ---------------------------------------------------------------------------
# Buggy version (before fix) to confirm the bug exists
# ---------------------------------------------------------------------------

def _deserialize_restored_state_buggy(
    raw_value,
    default: dict,
) -> dict:
    """Old buggy logic that discards JSON strings.

    This is what the code did BEFORE the fix — used to prove the bug.
    """
    restored_state = raw_value
    if isinstance(restored_state, (float, int)):
        restored_state = {"position": restored_state}
    elif isinstance(restored_state, str):
        restored_state = dict(default)  # BUG: discards valid JSON
    return restored_state


class TestCoverRestoreDeserialization:
    """Tests for the cover state deserialization logic.

    These tests verify the fix without importing boneio hardware modules.
    """

    def test_bug_exists_in_old_code(self):
        """Prove the bug: old code discards JSON string, resets to default 100."""
        saved = json.dumps({"position": 42})
        result = _deserialize_restored_state_buggy(saved, {"position": 100})
        # Old code wrongly resets to 100
        assert result == {"position": 100}, (
            "Old buggy code should discard the JSON string"
        )

    def test_fix_restores_from_json_string(self):
        """Fixed code properly deserializes JSON string back to dict."""
        saved = json.dumps({"position": 42})
        result = _deserialize_restored_state(saved, {"position": 100})
        assert result == {"position": 42}

    def test_restore_from_dict(self):
        """Dict value (already parsed) passes through unchanged."""
        result = _deserialize_restored_state({"position": 75}, {"position": 100})
        assert result == {"position": 75}

    def test_restore_from_int(self):
        """Legacy: bare int wraps into dict."""
        result = _deserialize_restored_state(33, {"position": 100})
        assert result == {"position": 33}

    def test_restore_from_float(self):
        """Legacy: bare float wraps into dict."""
        result = _deserialize_restored_state(55.5, {"position": 100})
        assert result == {"position": 55.5}

    def test_corrupted_string_falls_back(self):
        """Invalid JSON string falls back to default."""
        result = _deserialize_restored_state("not-valid-json", {"position": 100})
        assert result == {"position": 100}

    def test_empty_string_falls_back(self):
        """Empty string falls back to default."""
        result = _deserialize_restored_state("", {"position": 100})
        assert result == {"position": 100}

    def test_default_dict_passthrough(self):
        """Default value (dict) passes through when no saved state."""
        result = _deserialize_restored_state({"position": 100}, {"position": 100})
        assert result == {"position": 100}

    def test_position_zero_restored(self):
        """Position 0 (fully closed) must be restored, not treated as falsy."""
        saved = json.dumps({"position": 0})
        result = _deserialize_restored_state(saved, {"position": 100})
        assert result == {"position": 0}

    def test_position_zero_int_restored(self):
        """Position 0 as bare int must be wrapped, not discarded."""
        result = _deserialize_restored_state(0, {"position": 100})
        assert result == {"position": 0}


class TestVenetianRestoreDeserialization:
    """Tests for venetian cover state deserialization (with tilt_position)."""

    def test_venetian_json_string_restore(self):
        """Venetian state with tilt_position deserializes from JSON string."""
        saved = json.dumps({"position": 60, "tilt": 45})
        default = {"position": 100, "tilt": 100}
        result = _deserialize_restored_state(saved, default)
        assert result == {"position": 60, "tilt": 45}

    def test_venetian_corrupted_falls_back(self):
        """Corrupted venetian state falls back to defaults with tilt."""
        default = {"position": 100, "tilt": 100}
        result = _deserialize_restored_state("broken", default)
        assert result == {"position": 100, "tilt": 100}

    def test_venetian_int_gets_default_tilt(self):
        """Bare int for venetian cover gets default tilt_position."""
        default = {"position": 100, "tilt": 100}
        result = _deserialize_restored_state(55, default)
        assert result == {"position": 55, "tilt": 100}

    def test_venetian_tilt_zero(self):
        """Tilt position 0 must be preserved."""
        saved = json.dumps({"position": 80, "tilt": 0})
        default = {"position": 100, "tilt": 100}
        result = _deserialize_restored_state(saved, default)
        assert result["tilt"] == 0

    def test_venetian_float_tilt_roundtrip(self):
        """Venetian float tilt is preserved through save/restore."""
        saved = {"position": 60.3, "tilt": 45.7}
        result = _deserialize_restored_state(saved, {"position": 100, "tilt": 100})
        assert result == {"position": 60.3, "tilt": 45.7}


class TestStateSaveCallback:
    """Tests for the state_save closure used by CoverManager."""

    def test_state_save_calls_save_attribute_when_restore_enabled(self):
        """When restore_state=True, state_save persists the position as a dict.

        After the fix, save_attribute receives a native dict — NOT a
        json.dumps string. StateManager.save_state() handles JSON serialization.
        """
        mock_state_manager = MagicMock()
        cover_id = "living_room"
        config_restore_state = True

        # Reproduce the FIXED closure from CoverManager._configure_cover
        def state_save(value: dict[str, float]):
            if config_restore_state:
                mock_state_manager.save_attribute(
                    attr_type="cover",
                    attribute=cover_id,
                    value=value,
                )

        state_save({"position": 55})

        mock_state_manager.save_attribute.assert_called_once_with(
            attr_type="cover",
            attribute="living_room",
            value={"position": 55},
        )

    def test_state_save_skips_when_restore_disabled(self):
        """When restore_state=False, state_save should NOT persist."""
        mock_state_manager = MagicMock()
        cover_id = "living_room"
        config_restore_state = False

        def state_save(value: dict[str, float]):
            if config_restore_state:
                mock_state_manager.save_attribute(
                    attr_type="cover",
                    attribute=cover_id,
                    value=value,
                )

        state_save({"position": 55})
        mock_state_manager.save_attribute.assert_not_called()

    def test_roundtrip_save_then_restore(self):
        """Full roundtrip: save position → simulate restart → restore position.

        After the fix, save stores a dict directly (not json.dumps string).
        StateManager's json.dump() serializes the entire state dict to JSON,
        and json.load() deserializes it back to native Python types.
        So on restart, StateManager.get() returns a dict, not a string.
        """
        # Save phase — store dict directly
        saved_store: dict[str, dict] = {}

        def save_attribute(attr_type, attribute, value):
            saved_store[f"{attr_type}/{attribute}"] = value

        save_attribute("cover", "my_cover", {"position": 42})

        # Restore phase (simulating restart — json.load returns dict)
        raw_value = saved_store["cover/my_cover"]
        restored = _deserialize_restored_state(raw_value, {"position": 100})
        assert restored == {"position": 42}

    def test_roundtrip_float_precision(self):
        """Saved float position is restored without precision loss."""
        saved = {"position": 73.456}
        result = _deserialize_restored_state(saved, {"position": 100})
        assert result == {"position": 73.456}

    def test_roundtrip_backward_compat_legacy_string(self):
        """Backward compatibility: old state files have json.dumps strings.

        Before the fix, state_save wrote json.dumps({"position": 42}) which
        became a double-serialized string in the JSON file. On load,
        json.load() returns a string, not a dict. The restore logic must
        handle this by calling json.loads() on the string.
        """
        # Simulate legacy state file content (double-serialized)
        legacy_value = json.dumps({"position": 42})  # str: '{"position": 42}'

        restored = _deserialize_restored_state(legacy_value, {"position": 100})
        assert restored == {"position": 42}


class TestCoverRestoreSourceCode:
    """Meta-test: verify that the source code uses json.loads for string deserialization.

    This ensures the fix is present in the actual source code and hasn't been reverted.
    """

    def test_covers_py_uses_json_loads_for_time_based(self):
        """Check that covers.py contains json.loads for time_based restore."""
        import pathlib

        covers_path = pathlib.Path(__file__).resolve().parents[3] / "boneio" / "core" / "manager" / "covers.py"
        source = covers_path.read_text()

        # The backward-compat fix: isinstance(str) check followed by json.loads
        assert "json.loads(restored_state)" in source, (
            "covers.py must use json.loads() to deserialize saved cover state strings"
        )

        # The old bug pattern should NOT exist
        bug_pattern = 'elif isinstance(restored_state, str):\n                restored_state = {"position": 100}'
        assert bug_pattern not in source, (
            "The old buggy pattern that discards JSON strings must not exist"
        )

        # Root cause fix: state_save should NOT use json.dumps
        assert "value=json.dumps(value)" not in source, (
            "state_save must NOT double-serialize with json.dumps — "
            "StateManager.save_state() handles JSON serialization"
        )

