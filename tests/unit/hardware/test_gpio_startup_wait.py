"""Requesting the GPIO input lines waits for udev instead of giving up at once.

On a first boot boneIO can reach /dev/gpiochip* before udev has handed it to
the gpio group. One failed request used to leave every input on the chip dead,
with nothing but an ERROR in the journal and no retry.
"""

from __future__ import annotations

import errno
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from boneio.hardware import udev_wait
from boneio.hardware.gpio.input import manager as manager_module
from boneio.hardware.gpio.input.manager import GpioInputDefinition, GpioManager


class _Clock:
    """Stands in for ``time``; the manager's sleep moves it forward."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.slept = 0.0

    def monotonic(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept += seconds
        self.now += seconds


@pytest.fixture(autouse=True)
def _fresh_budget():
    """The startup budget is process-wide; every test starts a new boot."""
    udev_wait.reset_startup_budget()
    yield
    udev_wait.reset_startup_budget()


@pytest.fixture
def clock(monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(udev_wait, "time", clock)
    return clock


@pytest.fixture
def gpiod(monkeypatch):
    fake = MagicMock()
    monkeypatch.setattr(manager_module, "gpiod", fake)
    return fake


@pytest.fixture
def manager(clock):
    gm = GpioManager(loop=MagicMock())
    gm._sleep = clock.sleep
    gm._cleanup_stale_requests = AsyncMock()
    gm._inputs.append(
        GpioInputDefinition(
            name="IN_01", pin="P8_07", chip=2, line=2, bias=MagicMock(), detector=MagicMock()
        )
    )
    return gm


def _denied() -> PermissionError:
    return PermissionError(errno.EACCES, "Permission denied", "/dev/gpiochip2")


def _always_denied(*args, **kwargs):
    raise _denied()


def _missing() -> FileNotFoundError:
    return FileNotFoundError(errno.ENOENT, "No such file or directory", "/dev/gpiochip2")


async def test_a_chip_udev_has_not_handed_over_yet_is_waited_for(manager, gpiod, clock, caplog):
    request = MagicMock()
    gpiod.request_lines.side_effect = [_missing(), _denied(), request]

    with caplog.at_level(logging.INFO, logger=manager_module.__name__):
        await manager.start()

    assert manager._requests == {2: request}
    assert gpiod.request_lines.call_count == 3
    assert clock.slept == pytest.approx(2.0)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "/dev/gpiochip2 not accessible yet" in warnings[0].getMessage()
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert any("accessible after" in r.getMessage() for r in caplog.records)


async def test_a_chip_that_never_becomes_usable_is_skipped_after_the_budget(
    manager, gpiod, clock, caplog
):
    gpiod.request_lines.side_effect = _always_denied

    with caplog.at_level(logging.WARNING, logger=manager_module.__name__):
        await manager.start()

    assert manager._requests == {}
    assert clock.slept == pytest.approx(udev_wait.STARTUP_WAIT_SECONDS)
    assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 1
    errors = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
    assert any("still not accessible after 60 s" in m for m in errors)
    assert any("Failed to request lines on chip 2" in m for m in errors)


async def test_busy_lines_fail_at_once(manager, gpiod, clock):
    gpiod.request_lines.side_effect = OSError(errno.EBUSY, "Device or resource busy")

    await manager.start()

    assert manager._requests == {}
    assert gpiod.request_lines.call_count == 1
    assert clock.slept == 0


async def test_the_i2c_wait_counts_against_the_chips(manager, gpiod, clock):
    """I2C and GPIO together must not wait past systemd's stop timeout."""
    bus = udev_wait.NodeWait("/dev/i2c-2", logging.getLogger("test"), clock=clock.monotonic)
    assert bus.retry(_denied()) is True
    await clock.sleep(45)  # the bus took 45 s to appear
    gpiod.request_lines.side_effect = _always_denied

    await manager.start()

    assert manager._requests == {}
    assert clock.slept == pytest.approx(udev_wait.STARTUP_WAIT_SECONDS)
