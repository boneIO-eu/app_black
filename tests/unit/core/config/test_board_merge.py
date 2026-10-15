"""Config checks leave a malformed entry for the schema to report, instead of raising."""

from __future__ import annotations

import pytest

from boneio.core.config.yaml_util import merge_board_config

BONEIO = {"config_version": 7, "name": "t", "version": 1.1, "device_type": "24x16A"}


@pytest.mark.parametrize("value", [None, 7, ["OUT_01"]])
def test_an_output_named_by_a_non_string_is_left_alone(value):
    # .lower() on it raised AttributeError, at start-up as much as on a save.
    config = merge_board_config({"boneio": dict(BONEIO), "output": [{"boneio_output": value}]})
    assert config["output"] == [{"boneio_output": value}]


def test_an_output_named_by_a_string_is_still_mapped():
    config = merge_board_config({"boneio": dict(BONEIO), "output": [{"boneio_output": "OUT_01"}]})
    assert "kind" in config["output"][0]


@pytest.mark.parametrize("actions", [None, [], "x", 7, {"on_turn_on": True}, {"on_turn_off": "x"}])
def test_a_virtual_switch_whose_actions_are_not_a_dict_is_reported_not_a_crash(actions):
    from boneio.core.config.yaml_util import _cerberus_section_errors, _section_document

    doc = _section_document("virtual_switch", [{"name": "Night", "actions": actions}], None)
    errors = _cerberus_section_errors("virtual_switch", doc)
    assert errors and all("actions" in e for e in errors)
