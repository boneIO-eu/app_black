"""The first open of the I2C bus waits for udev instead of crashing at once."""

from __future__ import annotations

import errno
import logging

import pytest

from boneio.hardware import udev_wait
from boneio.hardware.i2c import bus as bus_module
from boneio.hardware.i2c.bus import SMBus2I2C


@pytest.fixture(autouse=True)
def _fresh_budget():
    """The startup budget is process-wide; every test starts a new boot."""
    udev_wait.reset_startup_budget()
    yield
    udev_wait.reset_startup_budget()


class _Clock:
    """Stands in for the ``time`` module: sleeping only moves the clock."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.slept = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept += seconds
        self.now += seconds


class _FakeSMBus:
    def __init__(self, bus_number: int) -> None:
        self.bus_number = bus_number

    def close(self) -> None:
        pass


def _flaky_smbus(failures: list[BaseException]):
    """An SMBus that raises each of ``failures`` in turn, then opens."""
    attempts = {"n": 0}

    def factory(bus_number: int):
        attempts["n"] += 1
        if failures:
            raise failures.pop(0)
        return _FakeSMBus(bus_number)

    return factory, attempts


@pytest.fixture
def clock(monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(bus_module, "time", clock)
    return clock


def _denied() -> PermissionError:
    return PermissionError(errno.EACCES, "Permission denied", "/dev/i2c-2")


def test_a_node_udev_has_not_handed_over_yet_is_waited_for(monkeypatch, clock, caplog):
    factory, attempts = _flaky_smbus([_denied(), _denied()])
    monkeypatch.setattr(bus_module, "SMBus", factory)

    with caplog.at_level(logging.INFO, logger=bus_module.__name__):
        i2c = SMBus2I2C(bus_number=2)

    assert isinstance(i2c._bus, _FakeSMBus)
    assert attempts["n"] == 3
    assert clock.slept == pytest.approx(2.0)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "/dev/i2c-2 not accessible yet" in warnings[0].getMessage()
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert any("accessible after" in r.getMessage() for r in caplog.records if r.levelno == logging.INFO)


def test_a_missing_node_is_waited_for_too(monkeypatch, clock):
    factory, attempts = _flaky_smbus([FileNotFoundError(errno.ENOENT, "No such file", "/dev/i2c-2")])
    monkeypatch.setattr(bus_module, "SMBus", factory)

    SMBus2I2C(bus_number=2)

    assert attempts["n"] == 2


def test_a_node_that_never_becomes_usable_fails_after_the_limit(monkeypatch, clock, caplog):
    def always_denied(bus_number: int):
        raise _denied()

    monkeypatch.setattr(bus_module, "SMBus", always_denied)

    with caplog.at_level(logging.WARNING, logger=bus_module.__name__), pytest.raises(PermissionError):
        SMBus2I2C(bus_number=2, startup_wait=30)

    assert clock.slept == pytest.approx(30.0)
    assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 1
    assert len([r for r in caplog.records if r.levelno == logging.ERROR]) == 1


def test_other_errors_fail_at_once(monkeypatch, clock):
    def broken(bus_number: int):
        raise OSError(errno.EIO, "Input/output error")

    monkeypatch.setattr(bus_module, "SMBus", broken)

    with pytest.raises(OSError, match="Input/output error"):
        SMBus2I2C(bus_number=2)

    assert clock.slept == 0


def test_no_wait_means_no_retry(monkeypatch, clock):
    factory, attempts = _flaky_smbus([_denied()])
    monkeypatch.setattr(bus_module, "SMBus", factory)

    with pytest.raises(PermissionError):
        SMBus2I2C(bus_number=2, startup_wait=0)

    assert attempts["n"] == 1
    assert clock.slept == 0


def test_a_reopen_at_runtime_does_not_wait(monkeypatch, clock):
    monkeypatch.setattr(bus_module, "SMBus", _FakeSMBus)
    i2c = SMBus2I2C(bus_number=2)
    i2c.close()

    def denied(bus_number: int):
        raise _denied()

    monkeypatch.setattr(bus_module, "SMBus", denied)

    assert i2c.try_lock() is False
    assert clock.slept == 0


def test_the_budget_is_shared_with_whatever_waited_before(monkeypatch, clock, caplog):
    """Time already spent waiting for another node counts against the bus."""
    other = udev_wait.NodeWait("/dev/gpiochip0", logging.getLogger("test"), clock=clock.monotonic)
    assert other.retry(_denied()) is True
    clock.sleep(50)  # the other node took 50 s

    def always_denied(bus_number: int):
        raise _denied()

    monkeypatch.setattr(bus_module, "SMBus", always_denied)

    with pytest.raises(PermissionError):
        SMBus2I2C(bus_number=2)

    assert clock.slept == pytest.approx(60.0)
