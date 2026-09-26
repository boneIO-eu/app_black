"""Unit tests for rate-limited Modbus failure logging.

A device that stops answering fails on every poll cycle. These check that the
first failure is a WARNING, repeats are INFO, the recovery is visible, and
that pymodbus's duplicate of the same timeout is dropped only when the
operator has not asked to see pymodbus.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest
from pymodbus.exceptions import ModbusIOException
from pymodbus.pdu import ExceptionResponse

from boneio.core.utils import logger as boneio_logger
from boneio.modbus.client import FailureLog, Modbus

LOGGER_NAME = "boneio.modbus.client"


def _levels(caplog) -> list[int]:
    return [r.levelno for r in caplog.records if r.name == LOGGER_NAME]


class TestFailureLog:
    """The tracker on its own."""

    @pytest.fixture
    def log(self):
        return FailureLog(logging.getLogger(LOGGER_NAME))

    def test_first_failure_warns_and_repeats_are_info(self, log, caplog):
        caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
        for _ in range(3):
            log.failed((10, 0), "Error reading registers from device %s", 10)
        assert _levels(caplog) == [logging.WARNING, logging.INFO, logging.INFO]
        assert "failed 3 times in a row" in caplog.records[-1].getMessage()

    def test_recovery_is_reported_and_rearms_the_warning(self, log, caplog):
        caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
        log.failed((10, 0), "fail")
        log.failed((10, 0), "fail")
        log.succeeded((10, 0), "Modbus device 10 at address 0")
        log.failed((10, 0), "fail")
        assert _levels(caplog) == [
            logging.WARNING,
            logging.INFO,
            logging.WARNING,
            logging.WARNING,
        ]
        assert (
            "Modbus device 10 at address 0 responding again after 2 failed attempt(s)"
            in caplog.records[2].getMessage()
        )

    def test_success_without_failure_is_silent(self, log, caplog):
        caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
        log.succeeded((10, 0), "Modbus device 10 at address 0")
        assert _levels(caplog) == []

    def test_keys_are_independent(self, log, caplog):
        """One misconfigured register must not silence another device."""
        caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
        log.failed((10, 0), "fail")
        log.failed((11, 0), "fail")
        log.failed((10, 4), "fail")
        assert _levels(caplog) == [logging.WARNING] * 3


class TestReadRegisters:
    """The client's read path uses the tracker per (unit, address)."""

    @pytest.fixture
    def modbus(self):
        # Bypass __init__: it opens a serial client and wants an event loop.
        client = Modbus.__new__(Modbus)
        client._uart = {"id": "/dev/ttyS4"}
        client._failures = FailureLog(logging.getLogger(LOGGER_NAME))
        client._client = MagicMock()
        client._client.connected = True
        return client

    def test_timeouts_warn_once_then_info_then_recover(self, modbus, caplog):
        caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
        read = modbus._client.read_input_registers
        read.side_effect = ModbusIOException("No response received after 2 retries")
        modbus.read_registers_blocking(unit=10, address=0)
        modbus.read_registers_blocking(unit=10, address=0)

        read.side_effect = None
        read.return_value = MagicMock(registers=[1, 2])
        assert modbus.read_registers_blocking(unit=10, address=0) is not None

        read.side_effect = ModbusIOException("No response received after 2 retries")
        modbus.read_registers_blocking(unit=10, address=0)

        levels = [lvl for lvl in _levels(caplog) if lvl > logging.DEBUG]
        assert levels == [
            logging.WARNING,
            logging.INFO,
            logging.WARNING,
            logging.WARNING,
        ]
        messages = [r.getMessage() for r in caplog.records if r.levelno > logging.DEBUG]
        assert "device 10 at address 0" in messages[0]
        assert "responding again after 2 failed attempt(s)" in messages[2]
        assert not any(r.levelno >= logging.ERROR for r in caplog.records)

    def test_an_exception_response_is_a_failure_of_that_register(self, modbus, caplog):
        caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
        modbus._client.read_input_registers.return_value = ExceptionResponse(4, 2)
        modbus.read_registers_blocking(unit=10, address=0)
        modbus.read_registers_blocking(unit=10, address=0)
        levels = [lvl for lvl in _levels(caplog) if lvl > logging.DEBUG]
        assert levels == [logging.WARNING, logging.INFO]


class TestPymodbusFilter:
    """pymodbus's own copy of a timeout is dropped unless asked for."""

    @pytest.fixture(autouse=True)
    def _clean(self):
        """configure_logger sets levels on shared loggers; put them back."""
        names = [
            "",
            "pymodbus",
            "pymodbus.client",
            boneio_logger.PYMODBUS_INTERNAL_LOGGER,
            "paho.mqtt.client",
            "hypercorn.access",
            "hypercorn.error",
        ]
        saved = {name: logging.getLogger(name).level for name in names}
        yield
        logging.getLogger(boneio_logger.PYMODBUS_INTERNAL_LOGGER).removeFilter(
            boneio_logger._PYMODBUS_NO_RESPONSE_FILTER
        )
        for name, level in saved.items():
            logging.getLogger(name).setLevel(level)

    @staticmethod
    def _filtered() -> bool:
        internal = logging.getLogger(boneio_logger.PYMODBUS_INTERNAL_LOGGER)
        return boneio_logger._PYMODBUS_NO_RESPONSE_FILTER in internal.filters

    def test_installed_by_default(self):
        boneio_logger.configure_logger(log_config={}, debug=0)
        assert self._filtered()

    def test_installed_once_across_reloads(self):
        boneio_logger.configure_logger(log_config={}, debug=0)
        boneio_logger.configure_logger(log_config={}, debug=0)
        internal = logging.getLogger(boneio_logger.PYMODBUS_INTERNAL_LOGGER)
        assert internal.filters.count(boneio_logger._PYMODBUS_NO_RESPONSE_FILTER) == 1

    @pytest.mark.parametrize("name", ["pymodbus", "pymodbus.logging"])
    def test_explicit_logs_entry_turns_it_off(self, name):
        boneio_logger.configure_logger(log_config={}, debug=0)
        boneio_logger.configure_logger(log_config={"logs": {name: "error"}}, debug=0)
        assert not self._filtered()

    def test_verbose_debug_turns_it_off(self):
        boneio_logger.configure_logger(log_config={}, debug=2)
        assert not self._filtered()

    def test_only_the_no_response_message_is_dropped(self):
        f = boneio_logger._PYMODBUS_NO_RESPONSE_FILTER

        def record(msg):
            return logging.LogRecord("pymodbus.logging", logging.ERROR, "", 0, msg, None, None)

        assert not f.filter(record("No response received after 2 retries, continue with next request"))
        assert f.filter(record("ERROR: No response received of the last requests, CLOSING CONNECTION."))
        assert f.filter(record("Frame check failed"))
