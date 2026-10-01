"""An input reload must leave the HA discovery cache describing what HA has.

The MQTT client deletes every discovery topic it receives that is not in the
cache, and it receives its own publishes back from the broker. One save in the
panel reloads inputs twice (the ``event`` and ``binary_sensor`` sections both
map to ``reload_inputs``). When each reload wiped the cache, the second one
emptied it after the first had re-published every input, and the echo of those
publishes then removed all event entities from Home Assistant.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

mock_gpiod = MagicMock()
sys.modules.setdefault("gpiod", mock_gpiod)
sys.modules.setdefault("gpiod.line", mock_gpiod.line)

from boneio.components.input import GpioEventButton, GpioInputBinarySensor  # noqa: E402
from boneio.core.config.config_helper import ConfigHelper  # noqa: E402
from boneio.core.manager.inputs import InputManager  # noqa: E402


def _topic(ha_type: str, entity_id: str) -> str:
    return f"homeassistant/{ha_type}/blk0001/{entity_id}/config"


@pytest.fixture
def config_helper():
    return ConfigHelper(name="black", serial_override="blk0001")


@pytest.fixture
def manager(config_helper):
    def publish_ha_discovery(id, ha_type, payload):
        config_helper.add_autodiscovery_msg(topic=_topic(ha_type, id), ha_type=ha_type, payload=payload)

    return SimpleNamespace(
        _config_helper=config_helper,
        publish_ha_discovery=MagicMock(side_effect=publish_ha_discovery),
        send_message=MagicMock(),
        parse_actions=lambda pin, actions: actions,
        _event_bus=MagicMock(),
    )


def _existing(cls, input_id: str, name: str, *, show_in_ha: bool = True) -> MagicMock:
    device = MagicMock(spec=cls)
    device.id = input_id
    device._name = name
    device.area = None
    device._device_class = None
    device.device_class = None
    device.mqtt_sequences = {}
    device._mqtt_sequences = {}
    device.show_in_ha = show_in_ha
    if cls is GpioInputBinarySensor:
        device.update_inverted.return_value = False
    return device


def _reload(inputs: InputManager, config: dict) -> None:
    with patch.object(inputs._manager._config_helper, "get_config", return_value=config):
        inputs._configure_inputs(reload_config=True)


@pytest.fixture
def inputs(manager):
    im = InputManager.__new__(InputManager)
    im._manager = manager
    im._inputs = {
        "in_01": _existing(GpioEventButton, "in_01", "IN_01"),
        "in_48": _existing(GpioInputBinarySensor, "in_48", "IN_48"),
    }
    im._event_pins = []
    im._binary_pins = []
    for ha_type, entity_id in [
        ("event", "in_01"),
        ("binary_sensor", "in_48"),
        ("event", "security_event"),
        ("binary_sensor", "security_alert"),
        ("event", "oled_button"),
    ]:
        manager.publish_ha_discovery(id=entity_id, ha_type=ha_type, payload={"name": None})
    manager.publish_ha_discovery.reset_mock()
    return im


def _config(event_name: str = "IN_01", **event_extra) -> dict:
    return {
        "event": [{"pin": "P8_30", "boneio_input": "in_01", "name": event_name, **event_extra}],
        "binary_sensor": [{"pin": "P8_31", "boneio_input": "in_48", "name": "IN_48"}],
    }


def test_unchanged_inputs_stay_in_the_cache(inputs, config_helper):
    _reload(inputs, _config())

    assert config_helper.is_topic_in_autodiscovery(_topic("event", "in_01"))
    assert config_helper.is_topic_in_autodiscovery(_topic("binary_sensor", "in_48"))
    inputs._manager.publish_ha_discovery.assert_not_called()


def test_entities_that_are_not_inputs_survive_a_reload(inputs, config_helper):
    _reload(inputs, _config())

    assert config_helper.is_topic_in_autodiscovery(_topic("event", "security_event"))
    assert config_helper.is_topic_in_autodiscovery(_topic("binary_sensor", "security_alert"))
    assert config_helper.is_topic_in_autodiscovery(_topic("event", "oled_button"))


def test_second_reload_keeps_what_the_first_republished(inputs, config_helper):
    """The double reload from one panel save: first changes, second does not."""
    _reload(inputs, _config(event_name="Salon"))
    assert inputs._manager.publish_ha_discovery.call_count == 1

    inputs._inputs["in_01"]._name = "Salon"
    _reload(inputs, _config(event_name="Salon"))

    assert config_helper.is_topic_in_autodiscovery(_topic("event", "in_01"))


def test_hiding_an_input_removes_it_from_ha_and_the_cache(inputs, config_helper):
    _reload(inputs, _config(show_in_ha=False))

    topic = _topic("event", "in_01")
    assert not config_helper.is_topic_in_autodiscovery(topic)
    inputs._manager.send_message.assert_any_call(topic=topic, payload=None, retain=True)


def test_showing_a_hidden_input_publishes_it(inputs, config_helper):
    hidden = inputs._inputs["in_01"]
    hidden.show_in_ha = False
    config_helper.remove_autodiscovery_msg("event", _topic("event", "in_01"))

    _reload(inputs, _config())

    assert config_helper.is_topic_in_autodiscovery(_topic("event", "in_01"))


def test_still_hidden_input_is_not_removed_again(inputs):
    inputs._inputs["in_01"].show_in_ha = False

    _reload(inputs, _config(show_in_ha=False))

    inputs._manager.send_message.assert_not_called()
