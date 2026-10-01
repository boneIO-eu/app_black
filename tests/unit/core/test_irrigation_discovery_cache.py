"""What irrigation takes out of Home Assistant also leaves the discovery cache.

The cache is what gets resent whenever Home Assistant comes online. The
cleanup of the old switch-type zones went through it with an empty payload,
so every resend cleared those topics again; a removed controller went out of
Home Assistant but stayed in the cache, to be announced again on the next
resend.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

_gpiod_mock = MagicMock()
for mod in ("gpiod", "gpiod.line", "gpiod.chip", "gpiod.edge_event"):
    sys.modules.setdefault(mod, _gpiod_mock)

from boneio.core.config.config_helper import ConfigHelper  # noqa: E402
from boneio.core.manager.irrigation import IrrigationManager  # noqa: E402
from boneio.core.manager.manager import Manager  # noqa: E402

PREFIX = "homeassistant"
SERIAL = "blk0001"
OLD_ZONE_SWITCH = f"{PREFIX}/switch/{SERIAL}/ogrod_zone_trawnik/config"
OLD_NEXT_RUN = f"{PREFIX}/sensor/{SERIAL}/ogrod_zone_trawnik_next_run/config"
VALVE = f"{PREFIX}/valve/{SERIAL}/ogrod_zone_trawnik/config"

CONFIG = [
    {
        "id": "ogrod",
        "name": "Ogród",
        "zones": [{"id": "trawnik", "valve_id": "OUT_01", "run_every_n": 2}],
    }
]


@pytest.fixture
def manager():
    config_helper = ConfigHelper(name="black", serial_override=SERIAL)
    fake = SimpleNamespace(
        _config_helper=config_helper,
        config_helper=config_helper,
        outputs=MagicMock(),
        message_bus=MagicMock(),
        event_bus=MagicMock(),
        # Nothing saved: every setting is what the configuration says.
        state_manager=MagicMock(get=lambda _section, _key, default: default),
        send_message=MagicMock(),
    )
    fake.publish_ha_discovery = lambda **kw: Manager.publish_ha_discovery(fake, **kw)
    return fake


async def _irrigation(manager) -> IrrigationManager:
    irrigation = IrrigationManager(manager=manager, irrigation_config=CONFIG)
    await irrigation.send_ha_autodiscovery()
    return irrigation


def _resent(manager) -> set[str]:
    return {msg["topic"] for msg in manager._config_helper.autodiscovery_msgs}


def _cleared(manager) -> list[str]:
    return [
        c.kwargs["topic"]
        for c in manager.send_message.call_args_list
        if not c.kwargs.get("payload")
    ]


async def test_the_old_zone_entities_are_cleared_but_not_kept_for_resending(manager):
    await _irrigation(manager)

    assert OLD_ZONE_SWITCH in _cleared(manager)
    assert OLD_NEXT_RUN in _cleared(manager)
    assert VALVE in _resent(manager)
    assert OLD_ZONE_SWITCH not in _resent(manager)
    assert OLD_NEXT_RUN not in _resent(manager)


async def test_a_removed_controller_takes_every_entity_it_announced(manager):
    irrigation = await _irrigation(manager)
    announced = _resent(manager)
    manager.send_message.reset_mock()

    irrigation._remove_discovery(irrigation._controllers["ogrod"])

    assert announced <= set(_cleared(manager))
    assert _resent(manager) == set()
