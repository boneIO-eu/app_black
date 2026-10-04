"""Hashing plain alarm PIN codes rewrites them in the file's own section.

The migration wrote back the running config's template list, which has the
schema's defaults filled in, so they all landed in the user's file.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import yaml

from boneio.components.template.alarm_panel import AlarmPinCode
from boneio.core.manager.templates.alarm import AlarmManager


def test_only_the_codes_change_in_the_file(tmp_path):
    panel = {"platform": "alarm_control_panel", "id": "dom", "codes": [{"name": "Ja", "code": "1234"}]}
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.safe_dump({"template": [panel]}), encoding="utf-8")

    running = {"template": [{**panel, "codes": [dict(panel["codes"][0])], "arming_time": 30, "delay_time": 30}]}
    alarm = AlarmManager.__new__(AlarmManager)
    alarm._manager = MagicMock()
    alarm._manager._config_helper.get_config.return_value = running
    alarm._manager._config_helper._config_file_path = str(config_file)

    alarm._migrate_codes_to_hashes([])

    hashed = AlarmPinCode.hash_code("1234")
    written = yaml.safe_load(config_file.read_text(encoding="utf-8"))
    assert written["template"] == [{**panel, "codes": [{"name": "Ja", "code": hashed}]}]
    assert running["template"][0]["codes"][0]["code"] == hashed
