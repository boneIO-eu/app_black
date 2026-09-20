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
