"""An optional register block that a unit lacks is not a failure."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from pymodbus.pdu import ExceptionResponse

from boneio.modbus.coordinator import OPTIONAL_GIVE_UP, OPTIONAL_RETRY_S
from tests.unit.modbus.definitions import definition
from tests.unit.modbus.test_coordinator_exception_response import _coordinator

GOOD = MagicMock(registers=[1, 2])


def _two_blocks(read, optional: bool):
    coordinator = _coordinator([])
    coordinator._definition = definition(
        [
            {"base": 0, "length": 2, "registers": [], "optional": optional},
            {"base": 100, "length": 2, "registers": []},
        ]
    )
    coordinator._modbus_entities = [{"s0": MagicMock()}, {"s1": MagicMock()}]

    async def side_effect(unit, address, count, method):
        return read(address)

    coordinator._modbus.read_registers = AsyncMock(side_effect=side_effect)
    return coordinator


def _reads(coordinator, base):
    return [c for c in coordinator._modbus.read_registers.call_args_list if c.kwargs["address"] == base]


@pytest.mark.parametrize("miss", [None, ExceptionResponse(4, 2)])
async def test_optional_block_miss_does_not_back_off_or_fail(miss):
    coordinator = _two_blocks(lambda a: miss if a == 0 else GOOD, optional=True)

    interval = await coordinator.async_update(timestamp=1.0)

    assert interval == pytest.approx(60.0)
    assert coordinator.failing is False
    assert coordinator._failed_groups == set()
    coordinator._event_bus.trigger_event.assert_not_called()
    coordinator._update_sensor_and_derived.assert_called_once()
    assert coordinator._update_sensor_and_derived.call_args.kwargs["values"] is GOOD


async def test_optional_block_given_up_after_three_misses_is_retried_hourly():
    coordinator = _two_blocks(lambda a: None if a == 0 else GOOD, optional=True)

    for ts in range(OPTIONAL_GIVE_UP + 1):
        await coordinator.async_update(timestamp=float(ts))
    assert len(_reads(coordinator, 0)) == OPTIONAL_GIVE_UP
    assert len(_reads(coordinator, 100)) == OPTIONAL_GIVE_UP + 1

    await coordinator.async_update(timestamp=2.0 + OPTIONAL_RETRY_S - 1)
    assert len(_reads(coordinator, 0)) == OPTIONAL_GIVE_UP
    await coordinator.async_update(timestamp=2.0 + OPTIONAL_RETRY_S)
    assert len(_reads(coordinator, 0)) == OPTIONAL_GIVE_UP + 1


async def test_optional_block_that_answers_again_resets_its_misses():
    answers = iter([None, GOOD])
    coordinator = _two_blocks(lambda a: next(answers) if a == 0 else GOOD, optional=True)

    await coordinator.async_update(timestamp=1.0)
    assert coordinator._optional_misses == {0: 1}
    await coordinator.async_update(timestamp=2.0)
    assert coordinator._optional_misses == {}


async def test_regular_block_timeout_still_backs_off():
    coordinator = _two_blocks(lambda a: None if a == 0 else GOOD, optional=False)

    interval = await coordinator.async_update(timestamp=1.0)

    assert interval == pytest.approx(90.0)
    assert coordinator.failing is True


async def test_regular_block_refusal_still_marks_failing():
    coordinator = _two_blocks(lambda a: ExceptionResponse(4, 2) if a == 0 else GOOD, optional=False)

    await coordinator.async_update(timestamp=1.0)

    assert coordinator.failing is True
    assert coordinator._failed_groups == {0}
