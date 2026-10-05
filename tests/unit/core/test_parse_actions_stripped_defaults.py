"""Actions saved without their default action value still parse.

The file keeps only what the user wrote, so ``action_output: toggle`` and
``action_cover: toggle`` are dropped on save, and a hot reload reads the file
without filling schema defaults back in. A remote MQTT output or cover action
then had no action value, ``None.upper()`` raised, and the whole event section
failed to reload.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

mock_gpiod = MagicMock()
sys.modules.setdefault("gpiod", mock_gpiod)
sys.modules.setdefault("gpiod.line", mock_gpiod.line)

from boneio.core.manager.manager import Manager  # noqa: E402


def _parse(action: dict) -> list:
    manager = Manager.__new__(Manager)
    manager.sun = None
    return manager.parse_actions("P9_16", {"single": [action]})["single"]


def test_output_over_mqtt_without_action_output_toggles() -> None:
    parsed = _parse({"action": "output_over_mqtt", "boneio_id": "other", "boneio_output": "out_01"})
    assert parsed and parsed[0]["action_output"] == "TOGGLE"


def test_cover_over_mqtt_without_action_cover_toggles() -> None:
    parsed = _parse({"action": "cover_over_mqtt", "boneio_id": "other", "boneio_cover": "cov_01"})
    assert parsed and parsed[0]["action_cover"] == "TOGGLE"
