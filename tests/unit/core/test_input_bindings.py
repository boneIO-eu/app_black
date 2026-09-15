"""Tests for the first-run wizard's input binding planner."""

from __future__ import annotations

import pytest

from boneio.core.config.input_bindings import (
    COVER_ACTION_DOWN,
    COVER_ACTION_UP,
    cover_relay_ids,
    output_id,
    plan_input_bindings,
    resolve_cover_id,
)

INPUTS = [f"in_{n:02d}" for n in range(1, 50)]


def single_actions(entry):
    """The one action a generated entry carries."""
    return entry["actions"]["single"]


# ------------------------------------------------------------------- id rules


def test_resolve_cover_id_prefers_an_explicit_id():
    assert resolve_cover_id({"id": "salon", "open_relay": "OUT_01"}) == "salon"


def test_resolve_cover_id_derives_from_relays():
    # The shipped cover.yaml files carry no ids, so this is the common case and
    # has to match what CoverManager will register.
    cover = {"name": "Cover01", "open_relay": "01_up", "close_relay": "01_down"}
    assert resolve_cover_id(cover) == "cover_01_up_01_down"


def test_resolve_cover_id_derives_from_relay_names_with_spaces():
    cover = {"open_relay": "OUT 31", "close_relay": "OUT 32"}
    assert resolve_cover_id(cover) == "cover_out_31_out_32"


def test_output_id_prefers_explicit_id():
    assert output_id({"id": "OUT_01", "boneio_output": "OUT_01"}) == "OUT_01"
    assert output_id({"boneio_output": "OUT_07"}) == "OUT_07"
    assert output_id({"name": "nameless"}) == ""


def test_cover_relay_ids_collects_both_ends():
    covers = [
        {"open_relay": "01_up", "close_relay": "01_down"},
        {"open_relay": "OUT_31", "close_relay": "OUT_32"},
    ]
    assert cover_relay_ids(covers) == {"01_up", "01_down", "out_31", "out_32"}


# --------------------------------------------------------------- output mode


def test_outputs_mode_binds_one_input_per_output():
    entries = plan_input_bindings("outputs", INPUTS, set(), ["OUT_01", "OUT_02"], [])
    assert [e["boneio_input"] for e in entries] == ["in_01", "in_02"]
    assert single_actions(entries[0]) == [{"action": "output", "boneio_output": "OUT_01"}]
    assert entries[0]["name"] == "IN_01"


def test_generated_entries_carry_only_a_single_click():
    entries = plan_input_bindings("outputs", INPUTS, set(), ["OUT_01"], [])
    assert list(entries[0]["actions"]) == ["single"]


def test_outputs_mode_skips_inputs_already_used_elsewhere():
    # Events and binary sensors share the physical pins; the shipped config
    # puts IN_48 and IN_49 in binary_sensor.yaml.
    entries = plan_input_bindings(
        "outputs", INPUTS, {"in_01", "IN_02"}, ["OUT_01", "OUT_02"], []
    )
    assert [e["boneio_input"] for e in entries] == ["in_03", "in_04"]


def test_outputs_mode_stops_when_the_board_runs_out_of_inputs():
    entries = plan_input_bindings(
        "outputs", ["in_01", "in_02"], set(), ["OUT_01", "OUT_02", "OUT_03"], []
    )
    assert len(entries) == 2


def test_a_48_output_board_cannot_bind_every_output():
    # 48 relays, 49 inputs, two of them taken: the last outputs go unbound
    # rather than sharing a button.
    outputs = [f"OUT_{n:02d}" for n in range(1, 49)]
    entries = plan_input_bindings("outputs", INPUTS, {"in_48", "in_49"}, outputs, [])
    assert len(entries) == 47
    assert len({e["boneio_input"] for e in entries}) == 47


# ---------------------------------------------------------------- cover mode


def test_covers_mode_spends_two_inputs_per_cover():
    entries = plan_input_bindings("covers", INPUTS, set(), [], ["c1", "c2"])
    assert [e["boneio_input"] for e in entries] == ["in_01", "in_02", "in_03", "in_04"]
    assert single_actions(entries[0])[0]["action_cover"] == COVER_ACTION_UP
    assert single_actions(entries[1])[0]["action_cover"] == COVER_ACTION_DOWN
    assert single_actions(entries[0])[0]["boneio_cover"] == "c1"
    assert single_actions(entries[2])[0]["boneio_cover"] == "c2"


def test_covers_mode_ignores_outputs():
    entries = plan_input_bindings("covers", INPUTS, set(), ["OUT_01"], ["c1"])
    assert len(entries) == 2
    assert all(a["action"] == "cover" for e in entries for a in single_actions(e))


def test_a_cover_never_gets_only_one_button():
    # One input left and a cover still waiting: binding just the up button
    # would leave a shutter that opens and never closes.
    entries = plan_input_bindings("covers", ["in_01", "in_02", "in_03"], set(), [], ["c1", "c2"])
    assert len(entries) == 2
    assert {e["boneio_input"] for e in entries} == {"in_01", "in_02"}


def test_sixteen_covers_fit_on_a_cover_board():
    covers = [f"cover_{n:02d}_up_{n:02d}_down" for n in range(1, 17)]
    entries = plan_input_bindings("covers", INPUTS, {"in_48", "in_49"}, [], covers)
    assert len(entries) == 32
    assert entries[-1]["boneio_input"] == "in_32"


# ------------------------------------------------------------- combined mode


def test_combined_mode_serves_covers_first_then_outputs():
    entries = plan_input_bindings(
        "covers_and_outputs", INPUTS, set(), ["OUT_17", "OUT_18"], ["c1"]
    )
    kinds = [single_actions(e)[0]["action"] for e in entries]
    assert kinds == ["cover", "cover", "output", "output"]
    assert [e["boneio_input"] for e in entries] == ["in_01", "in_02", "in_03", "in_04"]


def test_combined_mode_gives_an_odd_leftover_input_to_an_output():
    # Three inputs, two covers, one relay: the second cover cannot be wired, so
    # the spare input must not be thrown away.
    entries = plan_input_bindings(
        "covers_and_outputs", ["in_01", "in_02", "in_03"], set(), ["OUT_17"], ["c1", "c2"]
    )
    kinds = [single_actions(e)[0]["action"] for e in entries]
    assert kinds == ["cover", "cover", "output"]
    assert entries[-1]["boneio_input"] == "in_03"


def test_a_cover_mix_board_binds_eight_covers_and_sixteen_relays():
    covers = [f"cover_{n:02d}_up_{n:02d}_down" for n in range(1, 9)]
    outputs = [f"OUT_{n:02d}" for n in range(17, 33)]
    entries = plan_input_bindings(
        "covers_and_outputs", INPUTS, {"in_48", "in_49"}, outputs, covers
    )
    assert len(entries) == 16 + 16
    assert len({e["boneio_input"] for e in entries}) == 32


# --------------------------------------------------------------------- misc


def test_none_mode_changes_nothing():
    assert plan_input_bindings("none", INPUTS, set(), ["OUT_01"], ["c1"]) == []


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError, match="Unknown input mode"):
        plan_input_bindings("whatever", INPUTS, set(), [], [])


def test_no_input_is_ever_bound_twice():
    covers = [f"c{n}" for n in range(1, 9)]
    outputs = [f"OUT_{n:02d}" for n in range(1, 17)]
    entries = plan_input_bindings("covers_and_outputs", INPUTS, set(), outputs, covers)
    used = [e["boneio_input"] for e in entries]
    assert len(used) == len(set(used))
