"""An exception response from a Modbus device is a failed read.

pymodbus 3.x gives ``ExceptionResponse`` an empty ``registers`` and the client
returns it as is (the modbus CLI prints its code). The coordinator took it for
data: the device went ONLINE and every sensor failed to decode an empty
payload, at ERROR, on every poll.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
from pymodbus.pdu import ExceptionResponse

from boneio.const import OFFLINE, ONLINE
from boneio.core.utils.timeperiod import TimePeriod
from boneio.modbus.coordinator import ModbusCoordinator

LOGGER_NAME = "boneio.modbus.coordinator"


def _coordinator(read_results: list, groups: int = 1) -> ModbusCoordinator:
    # Bypass __init__: it loads a device JSON and wires up the manager.
    coordinator = ModbusCoordinator.__new__(ModbusCoordinator)
    coordinator._id = "meter"
    coordinator._name = "Meter"
    coordinator._address = 10
    coordinator._polling_enabled = True
    coordinator._modbus = MagicMock(is_suspended=False)
    coordinator._modbus.read_registers = AsyncMock(side_effect=read_results)
    coordinator._update_interval = TimePeriod(seconds=60)
    coordinator._update_cycle_count = 0
    coordinator._db = {"registers_base": [{"base": 100 * i, "length": 2} for i in range(groups)]}
    coordinator._failed_groups = set()
    coordinator._reported_groups = set()
    coordinator._payload_online = OFFLINE
    coordinator._discovery_sent = True
    coordinator._message_bus = MagicMock()
    coordinator._send_topic = "boneio/modbus/meter"
    coordinator._modbus_entities = [{f"sensor{i}": MagicMock()} for i in range(groups)]
    coordinator.manager = MagicMock()
    coordinator.manager.config_helper.topic_prefix = "boneio"
    coordinator.check_availability = AsyncMock()
    coordinator._update_sensor_and_derived = MagicMock(return_value={})
    return coordinator


def _online_messages(coordinator: ModbusCoordinator) -> list:
    return [
        call
        for call in coordinator._message_bus.send_message.call_args_list
        if call.kwargs.get("payload") == ONLINE
    ]


async def test_an_exception_response_does_not_bring_the_device_online():
    coordinator = _coordinator([ExceptionResponse(4, 2)])

    interval = await coordinator.async_update(timestamp=1.0)

    assert coordinator._payload_online == OFFLINE
    assert _online_messages(coordinator) == []
    coordinator._update_sensor_and_derived.assert_not_called()
    assert 0 in coordinator._failed_groups
    # The device answered: no back-off, no offline payload.
    assert interval == pytest.approx(60.0)


async def test_repeated_exception_responses_warn_once_then_info(caplog):
    coordinator = _coordinator([ExceptionResponse(4, 2)] * 3)
    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)

    for ts in range(3):
        await coordinator.async_update(timestamp=float(ts))

    levels = [
        r.levelno
        for r in caplog.records
        if r.name == LOGGER_NAME and "refused register group 0" in r.getMessage()
    ]
    assert levels == [logging.WARNING, logging.INFO, logging.INFO]
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


async def test_a_good_read_after_exception_responses_recovers():
    good = MagicMock(registers=[1, 2])
    coordinator = _coordinator([ExceptionResponse(4, 2), good])

    await coordinator.async_update(timestamp=1.0)
    await coordinator.async_update(timestamp=2.0)

    assert coordinator._payload_online == ONLINE
    assert len(_online_messages(coordinator)) == 1
    assert coordinator._reported_groups == set()
    assert coordinator._failed_groups == set()
    coordinator._update_sensor_and_derived.assert_called_once()
    assert coordinator._update_sensor_and_derived.call_args.kwargs["values"] is good


async def test_one_refused_group_does_not_stop_the_others(caplog):
    """One unsupported register block must not take the whole device down."""
    good = MagicMock(registers=[1, 2])
    coordinator = _coordinator([ExceptionResponse(4, 2), good], groups=2)
    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)

    interval = await coordinator.async_update(timestamp=1.0)

    assert interval == pytest.approx(60.0)
    assert coordinator._payload_online == ONLINE
    assert len(_online_messages(coordinator)) == 1
    assert coordinator._failed_groups == {0}
    coordinator._update_sensor_and_derived.assert_called_once()
    assert coordinator._update_sensor_and_derived.call_args.kwargs["values"] is good
    warnings = [r for r in caplog.records if r.name == LOGGER_NAME and r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "refused register group 0 (base=0)" in warnings[0].getMessage()
