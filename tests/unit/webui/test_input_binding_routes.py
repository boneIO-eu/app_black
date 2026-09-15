"""Tests for the wizard's input-binding routes.

The helpers are exercised against configs shaped like the ones flashed at
assembly, because the interesting mistakes are board-specific: a cover board
has no plain relays, and a cover_mix board has both kinds on one board.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest
import yaml


def _relay_board(count: int = 32) -> dict:
    """A 32x10-style config: plain relays, no covers."""
    return {
        "boneio": {"device_type": "32x10A", "version": "0.8"},
        "output": [
            {"name": f"OUT {n:02d}", "boneio_output": f"OUT_{n:02d}", "output_type": "light"}
            for n in range(1, count + 1)
        ],
        "binary_sensor": [
            {"name": "IN_48", "boneio_input": "in_48"},
            {"name": "IN_49", "boneio_input": "in_49"},
        ],
    }


def _cover_board() -> dict:
    """A cover-board config: every pin is half a shutter."""
    return {
        "boneio": {"device_type": "cover", "version": "0.8"},
        "output": [
            {"name": f"cover_{n:02d}_{d}", "boneio_output": f"{n:02d}_{d}"}
            for n in range(1, 17)
            for d in ("up", "down")
        ],
        # As shipped: named, but with no explicit id.
        "cover": [
            {"name": f"Cover{n:02d}", "open_relay": f"{n:02d}_up", "close_relay": f"{n:02d}_down"}
            for n in range(1, 17)
        ],
    }


def _cover_mix_board() -> dict:
    """A cover_mix config: eight shutters plus sixteen relays."""
    return {
        "boneio": {"device_type": "cover_mix", "version": "0.8"},
        "output": [
            {"boneio_output": f"{n:02d}_{d}"} for n in range(1, 9) for d in ("up", "down")
        ]
        + [{"boneio_output": f"OUT_{n:02d}"} for n in range(17, 33)],
        "cover": [
            {"name": f"Cover{n:02d}", "open_relay": f"{n:02d}_up", "close_relay": f"{n:02d}_down"}
            for n in range(1, 9)
        ],
    }


# --------------------------------------------------------------- what to bind


class TestBindableTargets:
    def test_relay_board_offers_every_relay_and_no_covers(self):
        from boneio.core.config.input_bindings import bindable_targets

        outputs, covers = bindable_targets(_relay_board())
        assert len(outputs) == 32
        assert outputs[0] == "OUT_01"
        assert covers == []

    def test_cover_board_offers_covers_and_no_free_relays(self):
        # The whole point: binding a button straight to 01_up would fight the
        # cover logic that already owns that relay.
        from boneio.core.config.input_bindings import bindable_targets

        outputs, covers = bindable_targets(_cover_board())
        assert outputs == []
        assert len(covers) == 16
        assert covers[0] == "cover_01_up_01_down"

    def test_cover_mix_board_offers_both_without_overlap(self):
        from boneio.core.config.input_bindings import bindable_targets

        outputs, covers = bindable_targets(_cover_mix_board())
        assert len(covers) == 8
        assert len(outputs) == 16
        assert outputs == [f"OUT_{n:02d}" for n in range(17, 33)]

    def test_a_relay_paired_into_a_cover_stops_being_an_output(self):
        from boneio.core.config.input_bindings import bindable_targets

        config = _relay_board()
        config["cover"] = [{"id": "brama", "open_relay": "OUT_31", "close_relay": "OUT_32"}]
        outputs, covers = bindable_targets(config)
        assert covers == ["brama"]
        assert "OUT_31" not in outputs and "OUT_32" not in outputs
        assert len(outputs) == 30

    def test_malformed_entries_are_ignored(self):
        from boneio.core.config.input_bindings import bindable_targets

        config = {"output": ["!include other.yaml", {"boneio_output": "OUT_01"}, {}]}
        outputs, covers = bindable_targets(config)
        assert outputs == ["OUT_01"]
        assert covers == []


class TestTakenInputs:
    def test_binary_sensor_pins_are_off_limits(self):
        from boneio.core.config.input_bindings import taken_inputs

        assert taken_inputs(_relay_board()) == {"in_48", "in_49"}

    def test_case_is_normalised(self):
        from boneio.core.config.input_bindings import taken_inputs

        assert taken_inputs({"binary_sensor": [{"boneio_input": "IN_07"}]}) == {"in_07"}

    def test_missing_section_means_nothing_taken(self):
        from boneio.core.config.input_bindings import taken_inputs

        assert taken_inputs({}) == set()


class TestBoardInputs:
    def test_reads_the_real_board_input_map(self):
        # Ships with the package, so this is the genuine 49-input map.
        from boneio.webui.routes.config_actions import _board_inputs

        inputs = _board_inputs({"boneio": {"version": "0.8"}})
        assert len(inputs) == 49
        assert inputs[0] == "in_01"
        assert inputs[-1] == "in_49"

    def test_unknown_board_version_is_a_client_error(self):
        from fastapi import HTTPException

        from boneio.webui.routes.config_actions import _board_inputs

        with pytest.raises(HTTPException) as err:
            _board_inputs({"boneio": {"version": "42.9"}})
        assert err.value.status_code == 400


# ------------------------------------------------------------------- applying


class TestApplyInputBindings:
    """Drives the route against a throwaway config on disk."""

    def _run(self, tmp_path, config: dict, body: dict):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.safe_dump(config), encoding="utf-8")

        app_state = MagicMock()
        app_state.yaml_config_file = str(config_file)

        from boneio.webui.routes import config_actions

        with (
            patch.object(config_actions, "_get_app_state", return_value=app_state),
            patch.object(config_actions, "invalidate_config_cache"),
            patch.object(config_actions, "load_config_from_file", return_value=config),
        ):
            result = asyncio.run(config_actions.apply_input_bindings(body))

        written = yaml.safe_load(config_file.read_text(encoding="utf-8"))
        return result, written

    def test_relay_board_gets_one_input_per_relay(self, tmp_path):
        result, written = self._run(tmp_path, _relay_board(), {"mode": "outputs"})

        assert result["status"] == "success"
        assert result["written"]["event"] == 32
        events = written["event"]
        assert events[0]["boneio_input"] == "in_01"
        assert events[0]["actions"]["single"][0]["boneio_output"] == "OUT_01"
        # IN_48/IN_49 belong to binary_sensor and must not be reused.
        assert {"in_48", "in_49"}.isdisjoint({e["boneio_input"] for e in events})

    def test_cover_board_gets_two_inputs_per_shutter(self, tmp_path):
        result, written = self._run(tmp_path, _cover_board(), {"mode": "covers"})

        assert result["written"]["event"] == 32
        first, second = written["event"][0], written["event"][1]
        assert first["actions"]["single"][0]["action_cover"] == "TOGGLE_OPEN"
        assert second["actions"]["single"][0]["action_cover"] == "TOGGLE_CLOSE"
        assert first["actions"]["single"][0]["boneio_cover"] == "cover_01_up_01_down"

    def test_none_leaves_the_event_section_alone(self, tmp_path):
        config = _relay_board()
        config["event"] = [{"name": "MOJE", "boneio_input": "in_01"}]
        result, written = self._run(tmp_path, config, {"mode": "none"})

        assert result["written"] == {}
        assert written["event"] == [{"name": "MOJE", "boneio_input": "in_01"}]

    def test_restore_state_is_applied_to_relays_and_covers(self, tmp_path):
        config = _cover_mix_board()
        result, written = self._run(tmp_path, config, {"mode": "none", "restore_state": True})

        assert result["written"] == {"output": 32, "cover": 8}
        assert all(o["restore_state"] is True for o in written["output"])
        assert all(c["restore_state"] is True for c in written["cover"])

    def test_restore_state_can_be_turned_off(self, tmp_path):
        config = _relay_board(2)
        _, written = self._run(tmp_path, config, {"mode": "none", "restore_state": False})

        assert all(o["restore_state"] is False for o in written["output"])

    def test_restore_state_is_untouched_when_not_asked_for(self, tmp_path):
        config = _relay_board(2)
        config["output"][0]["restore_state"] = True
        _, written = self._run(tmp_path, config, {"mode": "outputs"})

        assert written["output"][0].get("restore_state") is True
        assert "restore_state" not in written["output"][1]

    def test_unknown_mode_is_rejected(self, tmp_path):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as err:
            self._run(tmp_path, _relay_board(), {"mode": "wszystko"})
        assert err.value.status_code == 400

    def test_non_boolean_restore_state_is_rejected(self, tmp_path):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as err:
            self._run(tmp_path, _relay_board(), {"mode": "none", "restore_state": "yes"})
        assert err.value.status_code == 400
