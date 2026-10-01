"""Remote outputs must survive a reload of the output section.

They are registered into OutputManager from the remote_outputs section, so
rebuilding the local outputs used to drop them: after saving outputs in the
panel, MQTT commands, actions, groups and interlocks no longer found them until
a restart.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

mock_gpiod = MagicMock()
sys.modules.setdefault("gpiod", mock_gpiod)
sys.modules.setdefault("gpiod.line", mock_gpiod.line)

from boneio.core.manager.outputs import OutputManager  # noqa: E402
from boneio.integration.interlock import SoftwareInterlockManager  # noqa: E402


class _Remote:
    """Hashable, like real outputs — the interlock keeps them in sets."""

    is_remote = True
    output_type = "valve"

    def __init__(self, output_id: str, groups: list[str] | None = None):
        self.id = output_id
        self.interlock_groups = groups or []


def _remote(output_id: str, groups: list[str] | None = None) -> _Remote:
    return _Remote(output_id, groups)


def _outputs(existing: dict) -> OutputManager:
    outputs = OutputManager.__new__(OutputManager)
    outputs._manager = SimpleNamespace(_event_bus=MagicMock(), loop=MagicMock())
    outputs._outputs = dict(existing)
    outputs._configured_output_groups = {}
    outputs._interlock_manager = SoftwareInterlockManager()
    outputs._ha_topics = set()
    outputs.grouped_outputs_by_expander = {}
    for output in existing.values():
        if getattr(output, "interlock_groups", None):
            outputs._interlock_manager.register(output, output.interlock_groups)
    return outputs


def test_remote_output_is_kept_as_the_same_object():
    remote = _remote("mailbox")
    outputs = _outputs({"mailbox": remote, "out_01": SimpleNamespace(is_remote=False, output_type="switch")})

    outputs._initialize_outputs(relay_pins=[], reload_config=True)

    assert outputs.get_output("mailbox") is remote
    assert outputs.get_output("out_01") is None


def test_remote_output_stays_in_its_interlock_group():
    remote = _remote("mailbox", ["lock1"])
    outputs = _outputs({"mailbox": remote})

    outputs._initialize_outputs(relay_pins=[], reload_config=True)

    assert remote in outputs._interlock_manager.groups["lock1"]


def test_first_start_has_nothing_to_keep():
    outputs = _outputs({})

    outputs._initialize_outputs(relay_pins=[], reload_config=False)

    assert outputs._outputs == {}
