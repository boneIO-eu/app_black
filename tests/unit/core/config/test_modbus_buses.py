"""The Modbus bus list and which bus each device is on."""

from __future__ import annotations

import pytest

from boneio.core.config import models
from boneio.core.config.modbus_buses import (
    bus_change_errors,
    bus_reference_errors,
    device_bus,
    device_id,
    serial_device,
)


def test_bus_list_is_valid():
    assert models.validate("modbus", [{"id": "rs485", "port": "uart4"},
        {"id": "pompa", "port": "/dev/serial/by-id/usb-FTDI_FT232R-if00-port0", "parity": "E"}]) == []


@pytest.mark.parametrize("port", ["uart1", "/dev/serial/by-path/platform-usb-0:1:1.0-port0",
                                  "/dev/ttyUSB0", "/dev/ttyACM12"])
def test_port_in_pattern_accepted(port):
    assert models.validate("modbus", [{"id": "a", "port": port}]) == []


@pytest.mark.parametrize("port", ["/dev/ttyS1", "/dev/serial/by-id/..", "/etc/passwd", "uart9", "/dev/sda",
                                  "/dev/serial/by-id/a/b", "/dev/ttyUSB0\n"])
def test_port_outside_pattern_refused(port):
    assert models.validate("modbus", [{"id": "a", "port": port}])


@pytest.mark.parametrize("bus_id", ["RS485", "a-b", ""])
def test_bus_id_outside_pattern_refused(bus_id):
    assert models.validate("modbus", [{"id": bus_id, "port": "uart4"}])


def test_bus_defaults_are_todays():
    bus = models.load("modbus", [{"id": "a", "port": "uart4"}])[0]
    assert (bus["baudrate"], bus["stopbits"], bus["bytesize"], bus["parity"]) == (9600, 1, 8, "N")
    assert bus["timeout"].total_in_seconds == 1.5


def test_duplicate_bus_id_refused():
    assert models.validate("modbus", [{"id": "a", "port": "uart4"}, {"id": "a", "port": "/dev/ttyUSB0"}])


def test_duplicate_bus_port_refused():
    assert models.validate("modbus", [{"id": "a", "port": "uart4"}, {"id": "b", "port": "uart4"}])


def test_duplicate_resolved_device_ids_refused():
    errs = models.validate("modbus_devices", [{"address": 1, "model": "sdm630"},
        {"address": 1, "model": "sdm630", "bus": "pompa"}])
    assert any("id" in e for e in errs)


def test_device_bus_field():
    assert models.validate("modbus_devices", [{"address": 1, "model": "sdm630", "bus": "pompa"}]) == []
    assert models.validate("modbus_devices", [{"address": 1, "model": "sdm630", "bus": "Pompa"}])


def test_device_id_ignores_the_bus():
    assert device_id({"address": 1, "model": "SDM 630", "bus": "b"}) == "1_sdm_630"
    assert device_id({"id": "My Meter", "address": 1, "model": "m"}) == "mymeter"


def test_serial_device():
    assert serial_device("uart4") == "/dev/ttyS4"
    assert serial_device("/dev/ttyUSB0") == "/dev/ttyUSB0"


def test_device_bus_defaults_to_first():
    assert device_bus({"address": 1}, [{"id": "a"}, {"id": "b"}]) == "a"
    assert device_bus({"bus": "b"}, [{"id": "a"}, {"id": "b"}]) == "b"
    assert device_bus({}, []) is None


def test_bus_reference_errors():
    assert bus_reference_errors([{"id": "x", "address": 1, "model": "m", "bus": "nope"}], [{"id": "a"}])
    assert bus_reference_errors([{"address": 1, "model": "m", "bus": "a"}, {"address": 2, "model": "m"}],
                                [{"id": "a"}]) == []


def test_reorder_moves_implicit_devices():
    devs = [{"address": 1, "model": "m"}]
    assert bus_change_errors([{"id": "a"}, {"id": "b"}], [{"id": "b"}, {"id": "a"}], devs)
    assert bus_change_errors([{"id": "a"}], [{"id": "a"}, {"id": "b"}], devs) == []


def test_rename_or_delete_used_bus_refused():
    devs = [{"id": "meter", "address": 1, "model": "m", "bus": "b"}]
    errs = bus_change_errors([{"id": "a"}, {"id": "b"}], [{"id": "a"}], devs)
    assert errs and "meter" in errs[0]
    assert bus_change_errors([{"id": "a"}, {"id": "b"}], [{"id": "a"}, {"id": "c"}], devs)
    assert bus_change_errors([{"id": "a"}, {"id": "b"}], [{"id": "b"}, {"id": "a"}], devs) == []


def test_bus_change_lets_a_dangling_reference_be_fixed():
    devs = [{"address": 1, "model": "m", "bus": "c"}]
    assert bus_change_errors([{"id": "a"}], [{"id": "a"}, {"id": "c"}], devs) == []
    assert bus_change_errors([], [{"id": "a"}], [{"address": 1, "model": "m"}]) == []
