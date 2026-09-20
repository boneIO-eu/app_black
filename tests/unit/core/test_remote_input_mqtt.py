"""Tests for remote inputs carried over MQTT.

The schema advertised `remote_source: mqtt` long before anything implemented
it: the input was created and then nothing ever changed its state, which in
Home Assistant looks like a sensor stuck at "released" rather than a missing
feature. These cover the implementation and the refusal that replaced the
other half of that promise.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from boneio.components.input.remote.mqtt import MqttBinarySensorInput


def make_input(mode: str = "binary_sensor", inverted: bool = False, topic: str = "peer/input/in_01"):
    return MqttBinarySensorInput(
        device_id="peer",
        sensor_id="in_01",
        topic=topic,
        id="peer_in01",
        name="Peer IN 01",
        event_bus=MagicMock(),
        actions={},
        mode=mode,
        inverted=inverted,
    )


# ── reading a payload ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "payload",
    ["ON", "on", "true", "1", "pressed", "open", " ON ", '"ON"'],
)
def test_payloads_that_mean_on(payload):
    """Three vocabularies at once: boneIO says pressed, ESPHome says ON, and
    everything else says true."""
    assert MqttBinarySensorInput.parse_state(payload) is True


@pytest.mark.parametrize("payload", ["OFF", "off", "false", "0", "released", "closed"])
def test_payloads_that_mean_off(payload):
    assert MqttBinarySensorInput.parse_state(payload) is False


@pytest.mark.parametrize("payload", ["", "maybe", "17", "{}", None])
def test_a_payload_that_means_nothing_is_not_guessed_at(payload):
    """None, not False. A wrong guess here silently drives a relay."""
    assert MqttBinarySensorInput.parse_state(payload) is None


# ── binary sensor mode ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_state_message_moves_the_input():
    remote = make_input()
    seen: list = []
    remote.press_callback = lambda click_type, duration=None, start_time=None: seen.append(click_type)

    await remote.on_mqtt_message("peer/input/in_01", "pressed")
    assert seen == ["pressed"]
    assert remote.is_active is True

    await remote.on_mqtt_message("peer/input/in_01", "released")
    assert seen == ["pressed", "released"]
    assert remote.is_active is False


@pytest.mark.asyncio
async def test_inversion_is_applied():
    remote = make_input(inverted=True)
    seen: list = []
    remote.press_callback = lambda click_type, duration=None, start_time=None: seen.append(click_type)

    await remote.on_mqtt_message("peer/input/in_01", "ON")
    assert seen == ["released"]


@pytest.mark.asyncio
async def test_an_unreadable_payload_leaves_the_state_alone(caplog):
    remote = make_input()
    seen: list = []
    remote.press_callback = lambda click_type, duration=None, start_time=None: seen.append(click_type)

    with caplog.at_level("WARNING"):
        await remote.on_mqtt_message("peer/input/in_01", "banana")
    assert seen == []
    assert any("cannot read" in record.message for record in caplog.records)


# ── event mode ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_click_event_is_passed_through():
    """A boneIO event input publishes a click it has already classified. Feeding
    that through the local detector would try to re-derive it from a press this
    side never saw."""
    remote = make_input(mode="event")
    seen: list = []
    remote.press_callback = lambda click_type, duration=None, start_time=None: seen.append(click_type)

    await remote.on_mqtt_message("peer/input/in_01", '{"event_type": "double"}')
    assert seen == ["double"]


@pytest.mark.asyncio
async def test_a_click_event_in_binary_mode_is_ignored(caplog):
    remote = make_input(mode="binary_sensor")
    seen: list = []
    remote.press_callback = lambda click_type, duration=None, start_time=None: seen.append(click_type)

    with caplog.at_level("DEBUG"):
        await remote.on_mqtt_message("peer/input/in_01", '{"event_type": "single"}')
    assert seen == []


@pytest.mark.asyncio
async def test_malformed_json_falls_through_to_the_state_parser(caplog):
    """Not every payload starting with a brace is a click, and dropping the
    message outright would hide a device publishing something unexpected."""
    remote = make_input()
    with caplog.at_level("WARNING"):
        await remote.on_mqtt_message("peer/input/in_01", "{not json")
    assert remote.is_active is False
    assert any("cannot read" in record.message for record in caplog.records)


# ── the registrar ────────────────────────────────────────────────────────


def make_registrar(config):
    from boneio.core.manager.remote_input_registrar import RemoteInputRegistrar

    manager = MagicMock()
    manager.parse_actions.return_value = {}
    registrar = RemoteInputRegistrar(manager=manager)
    inputs: dict = {}
    devices = MagicMock()
    devices.get_device.return_value = MagicMock(spec=[])  # no ESPHome callback
    registrar.register_all(inputs, devices, config)
    return registrar, inputs


@pytest.mark.asyncio
async def test_an_mqtt_input_gets_the_peer_topic_by_default():
    """device_id is the peer's topic prefix, so mirroring another boneIO needs
    no topic at all."""
    registrar, inputs = make_registrar(
        [{"id": "peer_in01", "remote_source": "mqtt", "device_id": "blk_peer", "input_id": "in_01"}]
    )
    assert inputs["peer_in01"].topic == "blk_peer/input/in_01"
    assert len(registrar._mqtt_inputs) == 1


@pytest.mark.asyncio
async def test_an_explicit_topic_wins():
    _, inputs = make_registrar(
        [{
            "id": "door", "remote_source": "mqtt", "device_id": "esp",
            "input_id": "door", "topic": "esphome/door/state",
        }]
    )
    assert inputs["door"].topic == "esphome/door/state"


@pytest.mark.asyncio
async def test_an_unimplemented_source_is_refused_not_created(caplog):
    """Creating it would put an entity in Home Assistant that never updates,
    which reads as a wiring fault rather than a missing feature."""
    with caplog.at_level("ERROR"):
        _, inputs = make_registrar(
            [{"id": "can_in", "remote_source": "can", "device_id": "node1", "input_id": "in_01"}]
        )
    assert inputs == {}
    assert any("not implemented" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_start_subscribes_every_mqtt_input():
    registrar, _ = make_registrar(
        [{"id": "peer_in01", "remote_source": "mqtt", "device_id": "blk_peer", "input_id": "in_01"}]
    )
    subscribed: list = []

    async def subscribe(topic, handler):
        subscribed.append((topic, handler))

    registrar._manager.message_bus.subscribe_and_listen = subscribe
    await registrar.start()
    assert subscribed[0][0] == "blk_peer/input/in_01"


@pytest.mark.asyncio
async def test_stop_unsubscribes_so_a_reload_does_not_double_up():
    registrar, _ = make_registrar(
        [{"id": "peer_in01", "remote_source": "mqtt", "device_id": "blk_peer", "input_id": "in_01"}]
    )
    removed: list = []

    async def unsubscribe(topic):
        removed.append(topic)

    registrar._manager.message_bus.unsubscribe_and_stop_listen = unsubscribe
    await registrar.stop()
    assert removed == ["blk_peer/input/in_01"]
    assert registrar._mqtt_inputs == []


@pytest.mark.asyncio
async def test_one_failing_subscription_does_not_stop_the_others(caplog):
    registrar, _ = make_registrar([
        {"id": "a", "remote_source": "mqtt", "device_id": "p", "input_id": "in_01"},
        {"id": "b", "remote_source": "mqtt", "device_id": "p", "input_id": "in_02"},
    ])
    done: list = []

    async def subscribe(topic, handler):
        if topic.endswith("in_01"):
            raise RuntimeError("broker said no")
        done.append(topic)

    registrar._manager.message_bus.subscribe_and_listen = subscribe
    with caplog.at_level("ERROR"):
        await registrar.start()
    assert done == ["p/input/in_02"]
