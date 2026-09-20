"""Tests for virtual switches — an on/off flag with no relay behind it.

The point of one is to be read by a condition, so the tests that matter are
about the state being right: what it comes up as after a restart, that Home
Assistant can set it, and that a condition sees the same value the panel does.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from boneio.components.virtual_switch import VirtualSwitch
from boneio.core.manager.action_conditions import (
    precompile_conditions,
    should_execute_action,
)
from boneio.core.manager.virtual_switches import VirtualSwitchManager


class FakeStateManager:
    """The bits of StateManager a virtual switch touches."""

    def __init__(self, initial: dict | None = None) -> None:
        self.saved: dict[str, dict] = initial or {}

    def get(self, attr_type: str, attr: str, default_value=None):
        return self.saved.get(attr_type, {}).get(attr, default_value)

    def save_attribute(self, attr_type: str, attribute: str, value) -> None:
        self.saved.setdefault(attr_type, {})[attribute] = value


@pytest.fixture
def manager():
    fake = MagicMock()
    fake.published: list[tuple[str, dict, bool]] = []
    fake._message_bus.send_message = lambda topic, payload, retain=False: fake.published.append(
        (topic, payload, retain)
    )
    fake.events: list = []
    fake._event_bus.trigger_event = lambda event: fake.events.append(event)
    fake._topic_prefix = "boneio/blk123"
    fake._state_manager = FakeStateManager()
    return fake


def build(manager, config) -> VirtualSwitchManager:
    return VirtualSwitchManager(manager=manager, config=config)


# ── coming up ────────────────────────────────────────────────────────────


def test_a_switch_starts_off_by_default(manager):
    switches = build(manager, [{"id": "evening", "restore_state": True, "initial": False}])
    assert switches.get("evening").is_active is False


def test_initial_decides_when_there_is_nothing_to_restore(manager):
    switches = build(manager, [{"id": "evening", "restore_state": True, "initial": True}])
    assert switches.get("evening").is_active is True


def test_a_saved_state_is_restored(manager):
    """A controller that forgot every mode on each reboot would be worse than
    one with no modes at all."""
    manager._state_manager = FakeStateManager({"virtual_switch": {"evening": True}})
    switches = build(manager, [{"id": "evening", "restore_state": True, "initial": False}])
    assert switches.get("evening").is_active is True


def test_restore_state_off_ignores_what_was_saved(manager):
    manager._state_manager = FakeStateManager({"virtual_switch": {"evening": True}})
    switches = build(manager, [{"id": "evening", "restore_state": False, "initial": False}])
    assert switches.get("evening").is_active is False


def test_a_duplicate_id_is_refused(manager, caplog):
    with caplog.at_level("ERROR"):
        switches = build(manager, [{"id": "evening"}, {"id": "evening"}])
    assert len(switches.all()) == 1
    assert any("Duplicate" in record.message for record in caplog.records)


def test_a_switch_without_an_id_is_skipped(manager):
    assert build(manager, [{"name": "nameless"}]).all() == []


# ── switching ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_turning_on_publishes_a_retained_state(manager):
    """Retained, because Home Assistant restarting must not lose which mode the
    house is in."""
    switch = build(manager, [{"id": "evening"}]).get("evening")
    await switch.async_turn_on()

    topic, payload, retain = manager.published[-1]
    assert topic == "boneio/blk123/virtual_switch/evening"
    assert payload == {"state": "ON"}
    assert retain is True


@pytest.mark.asyncio
async def test_toggling_flips_the_state(manager):
    switch = build(manager, [{"id": "evening"}]).get("evening")
    await switch.async_toggle()
    assert switch.is_active is True
    await switch.async_toggle()
    assert switch.is_active is False


@pytest.mark.asyncio
async def test_the_state_is_persisted(manager):
    switch = build(manager, [{"id": "evening", "restore_state": True}]).get("evening")
    await switch.async_turn_on()
    assert manager._state_manager.saved["virtual_switch"]["evening"] is True
    await switch.async_turn_off()
    assert manager._state_manager.saved["virtual_switch"]["evening"] is False


@pytest.mark.asyncio
async def test_nothing_is_persisted_when_restore_is_off(manager):
    switch = build(manager, [{"id": "evening", "restore_state": False}]).get("evening")
    await switch.async_turn_on()
    assert manager._state_manager.saved == {}


@pytest.mark.asyncio
async def test_the_panel_is_told(manager):
    switch = build(manager, [{"id": "evening", "name": "Evening mode"}]).get("evening")
    await switch.async_turn_on()

    event = manager.events[-1]
    assert event.state.id == "evening"
    assert event.state.state == "ON"
    # The discriminator the panel groups on — it travels the output channel
    # because to a viewer it is the same shape of thing.
    assert event.state.type == "virtual_switch"
    assert event.state.pin is None


@pytest.mark.asyncio
async def test_a_failing_state_file_does_not_break_the_switch(manager, caplog):
    """A flag that cannot be written down still works until the next reboot."""
    switch = build(manager, [{"id": "evening"}]).get("evening")

    def boom(*args, **kwargs):
        raise OSError("read-only filesystem")

    manager._state_manager.save_attribute = boom
    with caplog.at_level("ERROR"):
        await switch.async_turn_on()
    assert switch.is_active is True
    assert any("Could not save state" in record.message for record in caplog.records)


# ── read by a condition ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_condition_reads_the_switch(manager):
    """The whole reason the thing exists."""
    switches = build(manager, [{"id": "evening"}])
    resolver = lambda entity_type, entity_id: (  # noqa: E731
        switches.get(entity_id) if entity_type == "virtual_switch" else None
    )
    compiled = precompile_conditions(
        {
            "condition": {
                "type": "state",
                "entity": "virtual_switch",
                "entity_id": "evening",
                "state": "is_on",
            }
        }
    )
    from datetime import datetime

    now = datetime.now().astimezone()
    assert should_execute_action(compiled, now, resolver) is False

    await switches.get("evening").async_turn_on()
    assert should_execute_action(compiled, now, resolver) is True


@pytest.mark.asyncio
async def test_is_off_reads_the_other_way(manager):
    switches = build(manager, [{"id": "evening"}])
    resolver = lambda entity_type, entity_id: switches.get(entity_id)  # noqa: E731
    compiled = precompile_conditions(
        {
            "condition": {
                "type": "state",
                "entity": "virtual_switch",
                "entity_id": "evening",
                "state": "is_off",
            }
        }
    )
    from datetime import datetime

    now = datetime.now().astimezone()
    assert should_execute_action(compiled, now, resolver) is True
    await switches.get("evening").async_turn_on()
    assert should_execute_action(compiled, now, resolver) is False


# ── reload ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reload_keeps_the_state_of_a_surviving_switch(manager):
    """Saving an unrelated part of the configuration must not silently turn off
    the mode the house is running on."""
    switches = build(manager, [{"id": "evening"}, {"id": "holiday"}])
    await switches.get("evening").async_turn_on()

    await switches.reload([{"id": "evening"}, {"id": "holiday"}, {"id": "guest"}])
    assert switches.get("evening").is_active is True
    assert switches.get("holiday").is_active is False
    assert switches.get("guest") is not None


@pytest.mark.asyncio
async def test_a_removed_switch_is_gone(manager):
    switches = build(manager, [{"id": "evening"}, {"id": "holiday"}])
    await switches.reload([{"id": "evening"}])
    assert switches.get("holiday") is None
    assert len(switches.all()) == 1


# ── Home Assistant ───────────────────────────────────────────────────────


def test_the_discovery_message_is_a_switch(manager):
    from boneio.integration.homeassistant import ha_switch_availabilty_message

    helper = MagicMock()
    helper.topic_prefix = "boneio/blk123"
    helper.name = "Black"
    helper.device_type = "32x10a"
    helper.cloud_registration = False
    helper.serial_number = "blk123"
    helper.real_serial = "blk123"
    helper.is_web_active = False
    helper.network_info = {}
    helper.areas = {}
    helper.ha_child_devices = False
    helper.get_area_name.return_value = None

    msg = ha_switch_availabilty_message(
        id="evening", name="Evening mode", config_helper=helper, device_type="virtual_switch"
    )
    # Settable from Home Assistant — a binary_sensor would be read-only, which
    # is the whole difference.
    assert msg["command_topic"] == "boneio/blk123/cmd/virtual_switch/evening/set"
    assert msg["state_topic"] == "boneio/blk123/virtual_switch/evening"
    assert msg["payload_on"] == "ON"
    assert msg["payload_off"] == "OFF"


def test_a_hidden_switch_is_not_announced(manager):
    switches = build(manager, [{"id": "secret", "show_in_ha": False}])
    manager.publish_ha_discovery = MagicMock()
    switches.publish_discovery()
    manager.publish_ha_discovery.assert_not_called()


# ── reaching the panel ───────────────────────────────────────────────────


def test_a_connecting_panel_is_told_about_them(manager):
    """Retained MQTT covers Home Assistant; the panel gets its state over a
    WebSocket, and a switch missing from that burst would be invisible until
    someone happened to flip it."""
    import asyncio

    from starlette.websockets import WebSocketState

    from boneio.webui.app import send_initial_states

    manager._startup_complete = True
    manager.inputs.get_inputs_list.return_value = []
    manager.outputs.get_all_outputs.return_value = {}
    manager.outputs.get_all_output_groups.return_value = {}
    manager.covers.get_all_covers.return_value = {}
    manager.virtual_switches = build(manager, [{"id": "evening", "name": "Evening mode"}])

    sent: list[dict] = []
    websocket = MagicMock()
    websocket.application_state = WebSocketState.CONNECTED

    async def send_json(payload):
        sent.append(payload)

    websocket.send_json = send_json

    assert asyncio.run(send_initial_states(websocket, manager)) is True
    switches = [p for p in sent if p.get("state", {}).get("type") == "virtual_switch"]
    assert len(switches) == 1
    assert switches[0]["state"]["id"] == "evening"
    assert switches[0]["state"]["pin"] is None


# ── actions on change ────────────────────────────────────────────────────


def build_with_actions(manager, config, runner=None):
    """A manager stub whose parse_actions passes the lists through."""
    manager.parse_actions = lambda pin, actions: {k: list(v) for k, v in actions.items()}
    manager.execute_actions = runner or (lambda actions, **kw: asyncio.sleep(0))
    return VirtualSwitchManager(manager=manager, config=config)


ON_ACTION = {"action": "mqtt", "topic": "t/on", "action_mqtt_msg": "go"}
OFF_ACTION = {"action": "mqtt", "topic": "t/off", "action_mqtt_msg": "stop"}


@pytest.fixture
def ran(manager):
    calls: list[list] = []

    async def runner(actions, **kwargs):
        calls.append(list(actions))

    manager.ran = calls
    return runner


@pytest.mark.asyncio
async def test_turning_on_runs_the_on_actions(manager, ran):
    switches = build_with_actions(
        manager,
        [{"id": "away", "actions": {"on_turn_on": [ON_ACTION], "on_turn_off": [OFF_ACTION]}}],
        ran,
    )
    await switches.get("away").async_turn_on()
    assert manager.ran == [[ON_ACTION]]


@pytest.mark.asyncio
async def test_turning_off_runs_the_off_actions(manager, ran):
    switches = build_with_actions(
        manager,
        [{"id": "away", "actions": {"on_turn_on": [ON_ACTION], "on_turn_off": [OFF_ACTION]}}],
        ran,
    )
    await switches.get("away").async_turn_on()
    await switches.get("away").async_turn_off()
    assert manager.ran == [[ON_ACTION], [OFF_ACTION]]


@pytest.mark.asyncio
async def test_setting_the_same_state_again_runs_nothing(manager, ran):
    """The reconnect republish sets every switch to the state it already has.
    Running actions there would re-fire the house on every broker restart."""
    switches = build_with_actions(manager, [{"id": "away", "actions": {"on_turn_on": [ON_ACTION]}}], ran)
    switch = switches.get("away")

    await switch.async_turn_on()
    assert len(manager.ran) == 1

    await switch.async_send_state()
    await switch.async_turn_on()
    assert len(manager.ran) == 1


@pytest.mark.asyncio
async def test_a_restored_state_does_not_run_actions(manager, ran):
    """Coming back from a power cut must not act on the house."""
    manager._state_manager = FakeStateManager({"virtual_switch": {"away": True}})
    switches = build_with_actions(
        manager, [{"id": "away", "restore_state": True, "actions": {"on_turn_on": [ON_ACTION]}}], ran
    )
    assert switches.get("away").is_active is True
    assert manager.ran == []


@pytest.mark.asyncio
async def test_a_switch_without_actions_still_switches(manager, ran):
    switches = build_with_actions(manager, [{"id": "away"}], ran)
    await switches.get("away").async_turn_on()
    assert switches.get("away").is_active is True
    assert manager.ran == []


@pytest.mark.asyncio
async def test_a_failing_action_does_not_wedge_the_flag(manager, caplog):
    async def boom(actions, **kwargs):
        raise RuntimeError("output on fire")

    switches = build_with_actions(manager, [{"id": "away", "actions": {"on_turn_on": [ON_ACTION]}}], boom)
    with caplog.at_level("ERROR"):
        await switches.get("away").async_turn_on()
    assert switches.get("away").is_active is True
    assert any("actions failed" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_a_loop_between_switches_is_broken(manager, caplog):
    """A toggles B on both edges, B toggles A on both edges. Every step is a
    real change, so nothing else stops it — without the guard this recurses
    until the stack gives out."""
    switches: VirtualSwitchManager | None = None

    async def runner(actions, **kwargs):
        # Stand in for the real dispatcher: every action toggles the other one.
        for action in actions:
            await switches.get(action["boneio_virtual_switch"]).async_toggle()

    def toggling(target: str) -> dict:
        both = [{"action": "virtual_switch", "boneio_virtual_switch": target}]
        return {"on_turn_on": list(both), "on_turn_off": list(both)}

    switches = build_with_actions(
        manager,
        [
            {"id": "a", "actions": toggling("b")},
            {"id": "b", "actions": toggling("a")},
        ],
        runner,
    )

    with caplog.at_level("ERROR"):
        await switches.get("a").async_turn_on()  # must return, not recurse

    assert any("a loop between switches" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_actions_are_parsed_after_every_switch_exists(manager, ran):
    """An action may target a switch defined further down the list, so parsing
    has to wait until all of them are built."""
    switches = build_with_actions(
        manager,
        [
            {"id": "first", "actions": {"on_turn_on": [{"action": "virtual_switch", "boneio_virtual_switch": "second"}]}},
            {"id": "second"},
        ],
        ran,
    )
    assert switches.get("first").actions["on_turn_on"][0]["boneio_virtual_switch"] == "second"


@pytest.mark.asyncio
async def test_a_reload_does_not_re_run_the_actions(manager, ran):
    """Saving the Virtual Switches page rebuilds every switch and hands each
    new one the state its predecessor held. That is a handover, not somebody
    flipping the switch: renaming one switch must not replay the scenes of
    every other one."""
    config = [{"id": "away", "actions": {"on_turn_on": [ON_ACTION], "on_turn_off": [OFF_ACTION]}}]
    switches = build_with_actions(manager, config, ran)
    await switches.get("away").async_turn_on()
    assert len(manager.ran) == 1

    # Same section, one field edited elsewhere.
    await switches.reload([{**config[0], "name": "Away mode"}])

    assert switches.get("away").is_active is True
    assert len(manager.ran) == 1


@pytest.mark.asyncio
async def test_republishing_does_not_re_run_the_actions(manager, ran):
    """republish_states runs after every broker reconnect."""
    switches = build_with_actions(
        manager,
        [{"id": "away", "actions": {"on_turn_on": [ON_ACTION]}}],
        ran,
    )
    await switches.get("away").async_turn_on()
    assert len(manager.ran) == 1

    await switches.republish_states()

    assert len(manager.ran) == 1
