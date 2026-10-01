"""Retained discovery replayed at startup is judged only once startup is done.

Subscribing to the discovery wildcards makes the broker replay every retained
config at once, while most entities are not in the cache yet - the security
entities register during the initial discovery, remote inputs only after the
web stack is up. Removing whatever the cache lacks at that moment took those
entities out of Home Assistant on every start, to be published again a moment
later. These tests play the startup order through handle_messages.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("aiomqtt", reason="aiomqtt not installed in test environment")

from aiomqtt import Topic  # noqa: E402

from boneio.core.messaging.mqtt import MQTTClient  # noqa: E402

SERIAL = "blk265f49"
SECURITY_ALERT = f"homeassistant/binary_sensor/{SERIAL}/security_alert/config"
REMOTE_INPUT = f"homeassistant/event/{SERIAL}/boneio_input24_gen2_01_19e400_in_03/config"
STALE = f"homeassistant/switch/{SERIAL}/removed_long_ago/config"


class _Cache:
    """The discovery cache, as far as the cleanup asks about it."""

    def __init__(self) -> None:
        self.topics: set[str] = set()

    def register(self, topic: str) -> None:
        self.topics.add(topic)

    def __contains__(self, topic: str) -> bool:
        return topic in self.topics


@pytest.fixture
def cache():
    return _Cache()


@pytest.fixture
async def client(cache):
    helper = MagicMock()
    helper.ha_discovery = True
    helper.ha_discovery_prefix = "homeassistant"
    helper.ha_types = ["binary_sensor", "event", "switch"]
    helper.serial_number = SERIAL
    helper.subscribe_topic = "boneio/cmd/#"
    helper.topic_prefix = "boneio"
    helper.receive_boneio_autodiscovery = False
    helper.is_topic_in_autodiscovery.side_effect = cache.__contains__
    mqtt = MQTTClient(host="localhost", config_helper=helper, port=1883)
    mqtt.send_message = MagicMock()
    return mqtt


def _replay(*topics: str, payload: bytes = b'{"name": "x"}'):
    async def messages():
        for topic in topics:
            yield SimpleNamespace(topic=Topic(topic), payload=payload, retain=True)

    return messages()


async def _manager_callback(topic, payload):
    raise AssertionError(f"discovery topic {topic} reached the manager")


def _removed(client) -> list[str]:
    return [
        call.kwargs["topic"]
        for call in client.send_message.call_args_list
        if call.kwargs.get("payload") is None and call.kwargs.get("retain")
    ]


async def test_entities_registered_after_the_replay_are_not_removed(client, cache):
    # 1. Connect: the broker replays what it kept from the last run.
    await client.handle_messages(_replay(SECURITY_ALERT, REMOTE_INPUT), _manager_callback)
    assert _removed(client) == []

    # 2. Initial discovery, then remote inputs once the web stack is up.
    cache.register(SECURITY_ALERT)
    cache.register(REMOTE_INPUT)

    # 3. Startup has registered everything.
    client.release_discovery_cleanup()

    assert _removed(client) == []


async def test_a_stale_entity_is_removed_once_startup_is_done(client, cache):
    await client.handle_messages(_replay(SECURITY_ALERT, STALE), _manager_callback)
    cache.register(SECURITY_ALERT)
    assert _removed(client) == []

    client.release_discovery_cleanup()

    assert _removed(client) == [STALE]


async def test_after_startup_an_unknown_entity_is_removed_as_it_arrives(client):
    client.release_discovery_cleanup()

    await client.handle_messages(_replay(STALE), _manager_callback)

    assert _removed(client) == [STALE]


async def test_an_entity_removed_while_held_is_not_removed_again(client):
    await client.handle_messages(_replay(STALE), _manager_callback)
    # Someone else cleared it before startup finished.
    await client.handle_messages(_replay(STALE, payload=b""), _manager_callback)

    client.release_discovery_cleanup()

    assert _removed(client) == []


async def test_releasing_twice_removes_nothing_twice(client):
    await client.handle_messages(_replay(STALE), _manager_callback)

    client.release_discovery_cleanup()
    client.release_discovery_cleanup()

    assert _removed(client) == [STALE]
