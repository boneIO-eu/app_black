"""The user chooses per entity where it shows; a definition only sets the default.

Visibility is about display. A hidden entity still takes writes, and its
``confirm`` flag reaches the panel.
"""

from __future__ import annotations

import logging

from boneio.modbus.coordinator import ModbusCoordinator
from tests.unit.modbus.test_modbus_coils import _coordinator as _bare_coordinator


def _stop(**extra) -> dict:
    return {
        "name": "Emergency stop",
        "address": 3,
        "write_address": 3,
        "entity_type": "writeable_binary_sensor_discrete",
        "value_type": "U_WORD",
        "payload_on": "1",
        "payload_off": "0",
        "hidden": True,
        "confirm": True,
        **extra,
    }


def _coordinator(visibility: dict | None = None, **stop) -> ModbusCoordinator:
    coordinator = _bare_coordinator(
        [{"base": 0, "length": 1, "register_type": "coil", "registers": [_stop(**stop)]}]
    )
    coordinator._entity_visibility = visibility or {}
    return coordinator


def _entity(coordinator):
    return coordinator._modbus_entities[0]["emergencystop"]


def _announced(coordinator) -> list:
    return list(coordinator._announced_entities())


def _panel_events(coordinator) -> list:
    return [c.args[0] for c in coordinator._event_bus.trigger_event.call_args_list]


def test_hidden_register_is_off_in_both_by_default():
    coordinator = _coordinator()
    entity = _entity(coordinator)

    assert not coordinator.visible(entity, "panel")
    assert not coordinator.visible(entity, "ha")
    assert _announced(coordinator) == []

    entity._state = 1
    coordinator._trigger_entity_events(entity)
    assert _panel_events(coordinator) == []


def test_config_shows_hidden_entity_in_ha_only():
    coordinator = _coordinator({"emergencystop": {"ha": True}})
    entity = _entity(coordinator)

    assert coordinator.visible(entity, "ha")
    assert not coordinator.visible(entity, "panel")
    assert _announced(coordinator) == [entity]


def test_config_hides_a_visible_entity():
    coordinator = _coordinator({"emergencystop": {"panel": False, "ha": False}}, hidden=False)

    assert not coordinator.visible(_entity(coordinator), "panel")
    assert _announced(coordinator) == []


def test_unknown_entity_in_visibility_is_ignored_with_warning(caplog):
    coordinator = _coordinator({"nonesuch": {"ha": False}})

    with caplog.at_level(logging.WARNING):
        coordinator._warn_unknown_visibility_entries()

    assert "nonesuch" in caplog.text
    assert coordinator.visible(_entity(coordinator), "ha") is False


def test_known_entity_in_visibility_does_not_warn(caplog):
    coordinator = _coordinator({"emergencystop": {"ha": True}})

    with caplog.at_level(logging.WARNING):
        coordinator._warn_unknown_visibility_entries()

    assert caplog.text == ""


async def test_hidden_entity_still_accepts_api_writes():
    coordinator = _coordinator()

    await coordinator.write_register(value="1", entity=_entity(coordinator))

    coordinator._modbus.write_register.assert_awaited_once()


def test_confirm_flag_reaches_ws_state():
    coordinator = _coordinator({"emergencystop": {"panel": True}})
    entity = _entity(coordinator)
    entity._state = 1

    coordinator._trigger_entity_events(entity)

    (event,) = _panel_events(coordinator)
    assert event.state.confirm is True


def test_derived_entity_inherits_hidden_and_confirm_from_its_source():
    coordinator = _coordinator()
    derived = _derived(coordinator, "emergencystop")

    assert not coordinator.visible(derived, "panel")
    assert coordinator.confirm_required(derived)

    coordinator._entity_visibility = {"stopmode": {"panel": True}}
    assert coordinator.visible(derived, "panel")
    assert not coordinator.visible(_entity(coordinator), "panel")


def test_entry_for_the_source_register_reaches_its_derived_entity():
    coordinator = _coordinator({"emergencystop": {"ha": True}})
    derived = _derived(coordinator, "emergencystop")

    assert coordinator.visible(derived, "ha")


def _derived(coordinator, source: str):
    from types import SimpleNamespace

    return SimpleNamespace(decoded_name="stopmode", source_sensor_decoded_name=source)
