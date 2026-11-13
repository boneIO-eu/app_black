"""A button is a one-shot trigger register: written, never read or published."""

from __future__ import annotations

import json
from types import SimpleNamespace

from boneio.core.config.config_helper import ConfigHelper
from boneio.modbus.entities import ModbusButton
from tests.unit.modbus.test_modbus_coils import _coordinator as _bare_coordinator


def _button(**extra) -> dict:
    return {
        "name": "DHW Disinfection",
        "address": 7,
        "write_address": 7,
        "entity_type": "button",
        "value_type": "U_WORD",
        **extra,
    }


def _coordinator(register_type: str = "coil"):
    config_helper = ConfigHelper(name="black", serial_override="blk0001")
    coordinator = _bare_coordinator(
        [{"base": 7, "length": 1, "register_type": register_type, "registers": [_button()]}]
    )
    coordinator._id = "pump"
    button = coordinator._modbus_entities[0]["dhwdisinfection"]
    button._config_helper = config_helper
    button._parent["id"] = "pump"
    return coordinator, button


async def test_button_press_writes_write_value_to_coil():
    coordinator, button = _coordinator()

    assert isinstance(button, ModbusButton)
    await button.press()

    coordinator._modbus.write_register.assert_awaited_once_with(
        unit=1, address=7, value=1, coil=True
    )


async def test_any_requested_value_still_presses_with_write_value():
    coordinator = _bare_coordinator(
        [{"base": 7, "length": 1, "register_type": "holding", "registers": [_button(write_value=5)]}]
    )
    button = coordinator._modbus_entities[0]["dhwdisinfection"]

    # Home Assistant and the panel send "1" whatever the register wants.
    await coordinator.write_register(value="1", entity=button)
    await button.write_value(0)

    assert [c.kwargs["value"] for c in coordinator._modbus.write_register.await_args_list] == [5, 5]
    assert all(c.kwargs["coil"] is False for c in coordinator._modbus.write_register.await_args_list)


def test_button_discovery_belongs_to_modbus_device():
    coordinator, button = _coordinator()

    msg = button.discovery_message()

    assert msg["device"]["identifiers"] == ["pump"]
    assert msg["command_topic"].endswith("/cmd/modbus/pump/set")
    assert json.loads(msg["payload_press"]) == {"device": "dhwdisinfection", "value": "1"}
    assert msg["availability"][0]["topic"].endswith("/modbus/pump/state")
    assert "state_topic" not in msg


async def test_button_has_no_state_in_block_payload():
    coordinator, button = _coordinator()
    values = SimpleNamespace(registers=[1])
    coordinator._polling_enabled = True
    coordinator._modbus.is_suspended = False
    coordinator._modbus.read_registers = _async(values)
    coordinator.check_availability = _async(None)
    coordinator._update_cycle_count = 0
    coordinator._failed_groups = set()
    coordinator._reported_groups = set()
    coordinator._optional_misses = {}
    coordinator._optional_last_try = {}
    coordinator._payload_online = "online"
    coordinator._update_interval = SimpleNamespace(total_in_seconds=60)

    await coordinator._poll(timestamp=1.0)

    (call,) = coordinator._message_bus.send_message.call_args_list
    assert call.kwargs["payload"] == {}
    assert button.state is None

    coordinator._message_bus.send_message.reset_mock()
    await button.press()
    coordinator._message_bus.send_message.assert_not_called()


def test_read_only_device_announces_no_buttons():
    coordinator, button = _coordinator()
    coordinator._read_only = True

    assert button not in list(coordinator._announced_entities())


def _async(result):
    async def call(*args, **kwargs):
        return result

    return call
