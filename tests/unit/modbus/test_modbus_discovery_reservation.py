"""A Modbus device's entities are this controller's before it first answers.

Discovery for a Modbus device goes out on its first successful read, which
may come long after startup, or never while it is unplugged. Until then its
topics were missing from the discovery cache, so the retained configs left
from the last run were removed as unused, and the device's entities dropped
out of Home Assistant every time it was slow or offline at startup.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from boneio.const import ID, MODEL, NAME
from boneio.core.config.config_helper import ConfigHelper
from boneio.modbus.coordinator import ModbusCoordinator
from boneio.modbus.entities.base import BaseEntity

SENSOR_TOPIC = "homeassistant/sensor/blk0001/meter_voltage/config"
POLLING_TOPIC = "homeassistant/switch/blk0001/meter_polling/config"


def _coordinator(config_helper: ConfigHelper) -> ModbusCoordinator:
    # Bypass __init__: it loads a device JSON and wires up the manager.
    coordinator = ModbusCoordinator.__new__(ModbusCoordinator)
    coordinator._id = "meter"
    coordinator._name = "Meter"
    coordinator._model = "sdm120"
    coordinator._area = None
    coordinator._db = {}
    coordinator._polling_enabled = True
    coordinator._message_bus = MagicMock()
    coordinator.manager = MagicMock(config_helper=config_helper)
    voltage = BaseEntity(
        name="Voltage",
        parent={ID: "meter", NAME: "Meter", MODEL: "sdm120"},
        message_bus=coordinator._message_bus,
        config_helper=config_helper,
    )
    coordinator._modbus_entities = [{"voltage": voltage}]
    coordinator._additional_entities = []
    return coordinator


def _sent(coordinator) -> list[str]:
    return [c.kwargs["topic"] for c in coordinator._message_bus.send_message.call_args_list]


def test_an_unanswered_device_keeps_its_topics_without_announcing_them():
    config_helper = ConfigHelper(name="black", serial_override="blk0001")
    coordinator = _coordinator(config_helper)

    coordinator._reserve_discovery_for_all_registers()

    assert config_helper.is_topic_in_autodiscovery(SENSOR_TOPIC)
    assert config_helper.is_topic_in_autodiscovery(POLLING_TOPIC)
    assert _sent(coordinator) == []
    # Home Assistant coming online is no reason to announce it either.
    assert list(config_helper.autodiscovery_msgs) == []


def test_once_the_device_answers_its_entities_are_resent_as_usual():
    config_helper = ConfigHelper(name="black", serial_override="blk0001")
    coordinator = _coordinator(config_helper)
    coordinator._reserve_discovery_for_all_registers()

    coordinator._send_discovery_for_all_registers()

    assert SENSOR_TOPIC in _sent(coordinator)
    assert POLLING_TOPIC in _sent(coordinator)
    resent = {msg["topic"] for msg in config_helper.autodiscovery_msgs}
    assert resent == {SENSOR_TOPIC, POLLING_TOPIC}


def test_reserving_again_keeps_what_was_announced():
    config_helper = ConfigHelper(name="black", serial_override="blk0001")
    coordinator = _coordinator(config_helper)
    coordinator._send_discovery_for_all_registers()

    coordinator._reserve_discovery_for_all_registers()

    resent = {msg["topic"] for msg in config_helper.autodiscovery_msgs}
    assert resent == {SENSOR_TOPIC, POLLING_TOPIC}
