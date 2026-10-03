"""An input reload leaves alone the inputs the local sections do not own.

Remote inputs and the OLED button live in the same map as GPIO inputs. The
first reload after start counted them as deleted, dropped them from the map
and sent empty discovery for them, so saving any input took the remote
inputs' entities out of Home Assistant until the next restart.
"""

from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

mock_gpiod = MagicMock()
sys.modules.setdefault("gpiod", mock_gpiod)
sys.modules.setdefault("gpiod.line", mock_gpiod.line)

from boneio.components.input import GpioEventButton, RemoteInputBase  # noqa: E402
from boneio.core.manager.inputs import InputManager  # noqa: E402


def _device(cls, area=None):
    device = MagicMock(spec=cls)
    device.area = area
    return device


async def test_remote_inputs_and_the_oled_button_survive_an_input_reload(monkeypatch):
    remote = _device(RemoteInputBase, area="garden")
    oled = _device(GpioEventButton)
    local = _device(GpioEventButton)
    gone = _device(GpioEventButton)

    im = InputManager.__new__(InputManager)
    im._manager = SimpleNamespace(
        _config_helper=MagicMock(get_config=MagicMock(return_value={"event": [{"id": "in_01", "pin": "P8_7"}]})),
    )
    im._inputs = {"in_01": local, "in_02": gone, "abc": remote, "oled_button": oled}
    im._remove_input_ha_discovery = MagicMock()
    im._configure_inputs = MagicMock()
    im._broadcast_all_input_states = MagicMock()

    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    await im.reload_inputs()

    assert im._inputs == {"in_01": local, "abc": remote, "oled_button": oled}
    removed = [c.args[0] for c in im._remove_input_ha_discovery.call_args_list]
    assert removed == ["in_02"]
