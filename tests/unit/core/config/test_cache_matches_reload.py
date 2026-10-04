"""After a section save the config cache holds what a reload would read.

The cache used to get the section exactly as it was sent: inputs without the
pin the board supplies, empty fields the file never got. Anything reading the
cache before the next reload saw a different config than the one on disk.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from boneio.core.config.config_helper import ConfigHelper
from boneio.core.config.yaml_util import load_yaml_file, merge_board_config, update_config_section


@pytest.fixture
def config_file(tmp_path: Path) -> str:
    (tmp_path / "config.yaml").write_text(
        "boneio:\n"
        "  name: test\n"
        "  device_type: 32x10A\n"
        "  version: '0.8'\n"
        "event: !include event.yaml\n"
        "output:\n"
        "  - id: lamp\n"
        "    boneio_output: out_01\n",
        encoding="utf-8",
    )
    (tmp_path / "event.yaml").write_text("- id: hall\n  boneio_input: in_01\n", encoding="utf-8")
    return str(tmp_path / "config.yaml")


def _reloaded(config_file: str, section: str):
    return merge_board_config(load_yaml_file(config_file))[section]


@pytest.mark.parametrize(
    ("section", "data"),
    [
        (
            "event",
            [
                {
                    "id": "hall",
                    "boneio_input": "in_01",
                    "area": "",
                    "actions": {"single": [{"action": "output", "boneio_output": "out_01", "action_output": "TOGGLE"}]},
                },
                {"id": "door", "boneio_input": "in_02"},
            ],
        ),
        ("output", [{"id": "lamp", "boneio_output": "out_01", "output_type": "switch"}]),
    ],
)
def test_cache_after_save_equals_a_fresh_reload(config_file, section, data):
    helper = ConfigHelper(name="black", serial_override="blk0001", config_file_path=config_file)
    helper.reload_config()

    assert update_config_section(config_file, section, data)["status"] == "success"
    helper.update_config_section(section, data)

    assert helper.get_config()[section] == _reloaded(config_file, section)
    assert helper.get_config()[section][0]["pin"]
