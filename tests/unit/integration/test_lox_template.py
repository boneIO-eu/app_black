"""Tests for Modbus entries in the Lox Config template and command summary."""

from unittest.mock import MagicMock, patch

from boneio.integration import lox_template
from boneio.integration.lox_template import generate_lox_summary, generate_lox_template
from boneio.modbus.entities.sensor.binary import ModbusBinarySensor
from boneio.modbus.entities.sensor.numeric import ModbusNumericSensor
from boneio.modbus.entities.sensor.text import ModbusTextSensor

_PARENT = {"id": "sht20", "name": "SHT20", "model": "sht20"}


def _entity(cls, name, unit=None, **kwargs):
    return cls(
        name=name,
        parent=_PARENT,
        register_address=1,
        base_address=1,
        message_bus=MagicMock(),
        config_helper=MagicMock(),
        unit_of_measurement=unit,
        state_class=None,
        device_class=None,
        value_type="U_WORD",
        entity_category=None,
        filters=[],
        **kwargs,
    )


def _manager():
    coordinator = MagicMock()
    coordinator.name = "SHT20"
    coordinator.get_all_entities.return_value = [{
        "temperature": _entity(ModbusNumericSensor, "Temperature", unit="°C"),
        "alarm": _entity(ModbusBinarySensor, "Alarm"),
        "status": _entity(ModbusTextSensor, "Status", value_mapping={"0": "OK"}),
    }]
    coordinator.get_all_additional_entities.return_value = []

    manager = MagicMock()
    manager.config_helper.serial_number = "blk123"
    manager.config_helper.name = "boneIO"
    manager.config_helper.get_config.return_value = {"lox_udp": {"host": "10.0.0.5"}}
    manager.outputs.get_all_outputs.return_value = {}
    manager.outputs.get_all_output_groups.return_value = {}
    manager.covers.get_all_covers.return_value = {}
    manager.inputs = None
    manager.modbus.get_all_coordinators.return_value = {"sht20": coordinator}
    return manager


def test_template_lists_modbus_readings():
    xml = generate_lox_template(_manager())

    assert 'Check="sht20.online=\\v"' in xml
    assert 'Check="sht20.temperature=\\v"' in xml
    assert 'Unit="&lt;v.1&gt; °C"' in xml
    assert 'Check="sht20.alarm=\\v"' in xml
    # Text readings cannot be parsed by \v, so the template leaves them out
    assert "sht20.status" not in xml


def test_summary_lists_modbus_readings():
    summary = generate_lox_summary(_manager())
    formats = {m["entity"]: m["format"] for m in summary["status_messages"] if m["type"] == "modbus"}

    assert formats == {
        "sht20.online": "sht20.online=1|0",
        "sht20.temperature": "sht20.temperature=<number>",
        "sht20.alarm": "sht20.alarm=1|0",
        "sht20.status": "sht20.status=<text>",
    }
    assert summary["modbus_value_count"] == 3


def test_template_addresses_boneio_not_the_miniserver(monkeypatch):
    """lox_udp.host is the Miniserver; the template must point at boneIO."""
    monkeypatch.setattr(lox_template, "_boneio_ip", lambda host: "192.168.1.50")
    xml = generate_lox_template(_manager())

    assert 'Address="/dev/udp/192.168.1.50/4445"' in xml
    assert 'Address="192.168.1.50"' in xml
    assert "10.0.0.5" not in xml


def test_boneio_ip_uses_route_to_miniserver():
    assert lox_template._boneio_ip("127.0.0.1") == "127.0.0.1"


def test_boneio_ip_hostname_falls_back_to_ethernet():
    with patch("boneio.core.system.monitor.get_network_info", return_value={"ip": "192.168.1.60"}):
        assert lox_template._boneio_ip("miniserver.local") == "192.168.1.60"
    with patch("boneio.core.system.monitor.get_network_info", return_value={"ip": "none"}):
        assert lox_template._boneio_ip(None) == "0.0.0.0"
