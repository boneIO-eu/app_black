"""The CPU sensor names what uses the processor, but only when it is busy.

A process scan costs about 300 ms of CPU on a BeagleBone, so an idle
controller must never pay for it.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import psutil
import pytest

from boneio.core.sensor import system
from boneio.core.sensor.system import CpuUsageSensor
from boneio.core.system import cpu_report
from boneio.core.system.cpu_report import CpuSnapshot, ProcessUsage

BUSY = CpuSnapshot(
    1_760_000_000.0,
    {},
    [
        ProcessUsage(1, "node", "nodered.service", 60.0),
        ProcessUsage(2, "python3", "boneio.service", 30.0),
        ProcessUsage(3, "mosquitto", "mosquitto.service", 5.0),
        ProcessUsage(4, "kworker/0:1", "kworker/0:1", 1.0),
    ],
)


class _Clock:
    now = 1000.0


@pytest.fixture
def sensor(monkeypatch):
    monkeypatch.setattr(system.time, "monotonic", lambda: _Clock.now)
    _Clock.now = 1000.0
    bus = MagicMock()
    made = CpuUsageSensor(manager=MagicMock(), message_bus=bus, topic_prefix="boneio")
    made.sent = lambda: bus.send_message.call_args.kwargs["payload"]
    return made


def _cpu(monkeypatch, percent):
    monkeypatch.setattr(psutil, "cpu_percent", lambda interval=None: percent)


def _scans(monkeypatch, result):
    calls = []

    def sample(max_age=None):
        calls.append(max_age)
        return result

    monkeypatch.setattr(cpu_report.SAMPLER, "sample", sample)
    return calls


async def test_below_threshold_no_scan_and_no_attributes(sensor, monkeypatch):
    _cpu(monkeypatch, 30.0)
    calls = _scans(monkeypatch, BUSY)
    await sensor.async_update(0.0)
    assert calls == []
    assert "top1_name" not in sensor.sent()


async def test_busy_publishes_top_three(sensor, monkeypatch):
    _cpu(monkeypatch, 100.0)
    _scans(monkeypatch, BUSY)
    await sensor.async_update(0.0)
    payload = sensor.sent()
    assert payload["top1_name"] == "nodered.service"
    assert payload["top1_percent"] == 60.0
    assert payload["top3_name"] == "mosquitto.service"
    assert "top4_name" not in payload
    assert payload["measured_at"].startswith("2025-10-09T")


async def test_first_busy_reading_without_baseline_publishes_nothing_extra(sensor, monkeypatch):
    _cpu(monkeypatch, 100.0)
    _scans(monkeypatch, None)
    await sensor.async_update(0.0)
    assert "top1_name" not in sensor.sent()


async def test_scan_at_most_once_a_minute(sensor, monkeypatch):
    _cpu(monkeypatch, 100.0)
    calls = _scans(monkeypatch, BUSY)
    await sensor.async_update(0.0)
    _Clock.now += 10
    await sensor.async_update(10.0)
    assert len(calls) == 1
    assert sensor.sent()["top1_name"] == "nodered.service"


async def test_a_baseline_does_not_wait_a_minute_for_the_real_scan(sensor, monkeypatch):
    _cpu(monkeypatch, 100.0)
    calls = _scans(monkeypatch, None)
    await sensor.async_update(0.0)
    _Clock.now += 10
    _scans(monkeypatch, BUSY)
    await sensor.async_update(10.0)
    assert sensor.sent()["top1_name"] == "nodered.service"
    assert len(calls) == 1


async def test_attributes_cleared_as_soon_as_cpu_drops(sensor, monkeypatch):
    _cpu(monkeypatch, 100.0)
    _scans(monkeypatch, BUSY)
    await sensor.async_update(0.0)
    _cpu(monkeypatch, 20.0)
    await sensor.async_update(10.0)
    assert "top1_name" not in sensor.sent()


async def test_the_scan_asks_for_a_recent_baseline(sensor, monkeypatch):
    _cpu(monkeypatch, 100.0)
    calls = _scans(monkeypatch, BUSY)
    await sensor.async_update(0.0)
    assert calls == [2 * system.CPU_SCAN_INTERVAL]


async def test_a_failing_scan_still_publishes_the_cpu(sensor, monkeypatch):
    _cpu(monkeypatch, 100.0)

    def broken(max_age=None):
        raise RuntimeError("no /proc")

    monkeypatch.setattr(cpu_report.SAMPLER, "sample", broken)
    await sensor.async_update(0.0)
    assert sensor.sent()["state"] == 100.0
