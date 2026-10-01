"""After a reload, Home Assistant's commands reach the controller that replaced the old one.

A reload rebuilds every controller under its old id, on the same command
topics. The subscription was skipped as already made, and the handler kept
the controller it was created with: from the first save of the irrigation
section on, every switch, button and number in Home Assistant drove the
stopped controller, until the next restart.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

_gpiod_mock = MagicMock()
for mod in ("gpiod", "gpiod.line", "gpiod.chip", "gpiod.edge_event"):
    sys.modules.setdefault(mod, _gpiod_mock)

from boneio.core.config.config_helper import ConfigHelper  # noqa: E402
from boneio.core.manager.irrigation import IrrigationManager  # noqa: E402
from boneio.core.manager.manager import Manager  # noqa: E402


def _config(*zones: str) -> list[dict]:
    return [
        {
            "id": "ogrod",
            "name": "Ogród",
            "zones": [{"id": z, "valve_id": f"OUT_{i:02d}"} for i, z in enumerate(zones, 1)],
        }
    ]


class _Bus:
    """The message bus as far as irrigation uses it: one listener per topic."""

    def __init__(self) -> None:
        self.listeners: dict[str, object] = {}
        self.subscribed: list[str] = []
        self.unsubscribed: list[str] = []
        self.send_message = MagicMock()

    async def subscribe_and_listen(self, topic, callback) -> None:
        self.subscribed.append(topic)
        self.listeners[topic] = callback

    async def unsubscribe_and_stop_listen(self, topic) -> None:
        self.unsubscribed.append(topic)
        del self.listeners[topic]

    async def command(self, topic: str, payload: str) -> None:
        await self.listeners[topic](topic, payload)


@pytest.fixture
def manager():
    config_helper = ConfigHelper(name="black", serial_override="blk0001")
    bus = _Bus()
    fake = SimpleNamespace(
        _config_helper=config_helper,
        config_helper=config_helper,
        outputs=MagicMock(),
        message_bus=bus,
        event_bus=MagicMock(),
        state_manager=MagicMock(get=lambda _section, _key, default: default),
        send_message=MagicMock(),
    )
    fake.publish_ha_discovery = lambda **kw: Manager.publish_ha_discovery(fake, **kw)
    return fake


async def _started(manager, config) -> IrrigationManager:
    irrigation = IrrigationManager(manager=manager, irrigation_config=config)
    await irrigation.start()
    return irrigation


async def _reload(manager, irrigation, config) -> None:
    manager._config_helper.get_config = lambda **_kw: {"irrigation": config}
    await irrigation.reload_irrigation()


async def test_a_command_after_a_reload_reaches_the_new_controller(manager):
    irrigation = await _started(manager, _config("trawnik"))
    old = irrigation._controllers["ogrod"]
    await _reload(manager, irrigation, _config("trawnik"))
    new = irrigation._controllers["ogrod"]
    assert new is not old
    old.handle_main_command = AsyncMock()
    new.handle_main_command = AsyncMock()

    await manager.message_bus.command(new._cmd_topic(), "ON")

    new.handle_main_command.assert_awaited_once_with("ON")
    old.handle_main_command.assert_not_awaited()


async def test_a_zone_command_after_a_reload_reaches_the_new_controller(manager):
    irrigation = await _started(manager, _config("trawnik"))
    await _reload(manager, irrigation, _config("trawnik"))
    new = irrigation._controllers["ogrod"]
    new.handle_zone_command = AsyncMock()

    await manager.message_bus.command(new._zone_cmd_topic("trawnik"), "open")

    new.handle_zone_command.assert_awaited_once_with("trawnik", "open")


async def test_a_reload_does_not_subscribe_a_topic_twice(manager):
    irrigation = await _started(manager, _config("trawnik"))
    before = list(manager.message_bus.subscribed)

    await _reload(manager, irrigation, _config("trawnik"))

    assert manager.message_bus.subscribed == before
    assert manager.message_bus.unsubscribed == []


async def test_a_removed_zone_stops_listening(manager):
    irrigation = await _started(manager, _config("trawnik", "grzadka"))
    zone_topic = irrigation._controllers["ogrod"]._zone_cmd_topic("grzadka")

    await _reload(manager, irrigation, _config("trawnik"))

    assert zone_topic in manager.message_bus.unsubscribed
    assert zone_topic not in manager.message_bus.listeners


async def test_a_removed_controller_stops_listening(manager):
    irrigation = await _started(manager, _config("trawnik"))
    topics = set(manager.message_bus.listeners)

    await _reload(manager, irrigation, [])

    assert set(manager.message_bus.unsubscribed) == topics
    assert manager.message_bus.listeners == {}
