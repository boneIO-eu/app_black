"""The board mapping leaves a malformed entry for the schema to report."""

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
