"""INA226 reads the chip in a worker thread, not on the event loop.

Each measurement is a blocking I2C transfer behind the bus lock. A relay write
holding that lock would otherwise stall the loop — timers, the GPIO reader,
the event bus — for as long as the bus is busy. The factory tester now asks
for a fresh reading several times a second while it switches relays, which is
exactly when the bus is busiest.
"""

from __future__ import annotations

import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

from boneio.hardware.i2c.ina226 import INA226


class _Chip:
    """Driver stand-in that records which thread read it."""

    def __init__(self, current: float, fail: str | None = None) -> None:
        self._current = current
        self._fail = fail
        self.threads: list[threading.Thread] = []

    def _read(self, name: str, value: float) -> float:
        self.threads.append(threading.current_thread())
        if name == self._fail:
            raise OSError("bus timeout")
        return value

    @property
    def current(self) -> float:
        return self._read("current", self._current)

    @property
    def voltage(self) -> float:
        return self._read("voltage", 24.0)


class _Sensor:
    def __init__(self, sensor_id: str, unit: str) -> None:
        self.id = sensor_id
        self.name = sensor_id
        self.unit_of_measurement = unit
        self.raw_state: float | None = None
        self.state: float | None = None
        self.last_timestamp = 0.0

    def update(self, timestamp: float) -> None:
        self.state = self.raw_state
        self.last_timestamp = timestamp


def _monitor(chip: _Chip) -> INA226:
    monitor = object.__new__(INA226)
    monitor._ina = chip
    monitor._sensors = {
        "current": _Sensor("BoardCurrent", "A"),
        "voltage": _Sensor("BoardVoltage", "V"),
    }
    monitor.manager = SimpleNamespace(event_bus=MagicMock())
    return monitor


async def test_chip_is_read_off_the_event_loop():
    chip = _Chip(current=0.51)
    monitor = _monitor(chip)

    await monitor.async_update(timestamp=123.0)

    loop_thread = threading.current_thread()
    assert chip.threads, "the chip was never read"
    assert all(t is not loop_thread for t in chip.threads)
    assert monitor.sensors["current"].state == 0.51
    assert monitor.sensors["voltage"].state == 24.0
    assert monitor.manager.event_bus.trigger_event.call_count == 2


async def test_one_failed_measurement_does_not_cost_the_others():
    chip = _Chip(current=0.51, fail="voltage")
    monitor = _monitor(chip)

    await monitor.async_update(timestamp=123.0)

    assert monitor.sensors["current"].state == 0.51
    assert monitor.sensors["voltage"].state is None
