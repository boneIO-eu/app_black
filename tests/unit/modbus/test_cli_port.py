"""`boneio modbus --port` accepts a UART key or a USB adapter path."""

import sys

import pytest

from boneio.bonecli import get_arguments


def _parse(monkeypatch, *flags):
    monkeypatch.setattr(
        sys, "argv", ["boneio", "modbus", "--baudrate", "9600", *flags, "get",
         "--register-address", "1", "--register-type", "input", "--value-type", "U_WORD"]
    )
    return get_arguments()


@pytest.mark.parametrize("flag", ["--port", "--uart"])
@pytest.mark.parametrize("value", ["/dev/ttyUSB0", "uart4"])
def test_port_and_uart_are_one_option(monkeypatch, flag, value):
    assert _parse(monkeypatch, flag, value).port == value


@pytest.mark.parametrize("value", ["/etc/passwd", "uart9", "/dev/ttyUSB0\n"])
def test_invalid_port_rejected(monkeypatch, value):
    with pytest.raises(SystemExit):
        _parse(monkeypatch, "--port", value)
