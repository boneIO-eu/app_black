"""The on-demand power monitor read.

The factory tester switches a bank of relays and has to see the coil current
within a second or two. ``/sensors/loaded`` hands it the value from the last
scheduled poll, up to ``update_interval`` old, so good boards failed with a
delta of exactly zero. The refresh route must read the chip on the spot.
"""

from __future__ import annotations

from types import SimpleNamespace

from boneio.webui.routes import sensors as route


class _Sensor:
    def __init__(self, sensor_id: str, unit: str, state: float) -> None:
        self.id = sensor_id
        self.name = sensor_id
        self.unit_of_measurement = unit
        self.state = state


class _Monitor:
    """A power monitor whose next read reports ``next_current``."""

    def __init__(self, current: float) -> None:
        self.sensors = {
            "current": _Sensor("BoardCurrent", "A", current),
            "voltage": _Sensor("BoardVoltage", "V", 24.0),
        }
        self.next_current = current
        self.reads: list[float] = []

    async def async_update(self, timestamp: float) -> None:
        self.reads.append(timestamp)
        self.sensors["current"].state = self.next_current


class _Sensors:
    """A sensor manager with power monitors and nothing else."""

    def __init__(self, ina219, ina226) -> None:
        self._ina219 = list(ina219)
        self._ina226 = list(ina226)

    def get_ina219_sensors(self):
        return self._ina219

    def get_ina226_sensors(self):
        return self._ina226

    def __getattr__(self, name):
        # Every other get_*_sensors() listing is empty.
        if name.startswith("get_"):
            return lambda: []
        raise AttributeError(name)


def _manager(ina219=(), ina226=()):
    return SimpleNamespace(
        sensors=_Sensors(ina219, ina226),
        modbus=SimpleNamespace(get_all_coordinators=lambda: {}),
    )


async def test_refresh_reads_the_chip_instead_of_the_cache():
    monitor = _Monitor(current=0.170)
    monitor.next_current = 0.510  # sixteen coils just pulled in

    result = await route.refresh_power_monitor(manager=_manager(ina219=[monitor]))

    assert len(monitor.reads) == 1
    current = next(e for e in result["ina219"] if e["unit"] == "A")
    assert current["state"] == 0.510
    assert result["timestamp"] == monitor.reads[0]


async def test_refresh_covers_ina226_boards_under_the_same_key():
    """v1.x boards carry an INA226; the tester reads one list for both."""
    monitor = _Monitor(current=0.030)
    monitor.next_current = 0.130

    result = await route.refresh_power_monitor(manager=_manager(ina226=[monitor]))

    assert monitor.reads
    assert [e["state"] for e in result["ina219"] if e["unit"] == "A"] == [0.130]


async def test_refresh_without_a_power_monitor_returns_an_empty_list():
    result = await route.refresh_power_monitor(manager=_manager())

    assert result["ina219"] == []


async def test_loaded_still_reports_the_cached_value():
    """The plain listing must not start touching the bus on every GET."""
    monitor = _Monitor(current=0.170)
    monitor.next_current = 0.510

    result = await route.get_loaded_sensors(manager=_manager(ina219=[monitor]))

    assert monitor.reads == []
    assert [e["state"] for e in result["ina219"] if e["unit"] == "A"] == [0.170]
