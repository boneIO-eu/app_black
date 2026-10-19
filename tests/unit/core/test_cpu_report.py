"""What uses the CPU: processes named by the service they belong to."""

from __future__ import annotations

import psutil
import pytest

from boneio.core import containers
from boneio.core.system import cpu_report
from boneio.core.system.cpu_report import (
    CpuSampler,
    CpuSnapshot,
    ProcessUsage,
    label_from_cgroup,
    looks_like_interrupts,
    top_labels,
)

DOCKER_ID = "a" * 64


@pytest.fixture(autouse=True)
def _no_container_names(monkeypatch):
    """Never ask the real helper; a cached map would leak between tests."""
    monkeypatch.setattr(cpu_report, "_container_cache", (0.0, {}))
    monkeypatch.setattr(
        containers, "containers", lambda timeout=30: containers.Result(1, "", "denied", True)
    )


@pytest.mark.parametrize(
    "text,name,expected",
    [
        ("0::/system.slice/mosquitto.service\n", "mosquitto", "mosquitto.service"),
        (f"0::/system.slice/docker-{DOCKER_ID}.scope\n", "node", "docker:" + "a" * 12),
        ("0::/user.slice/user-1000.slice/session-3.scope\n", "bash", "bash"),
        ("0::/\n", "ksoftirqd/0", "ksoftirqd/0"),
        ("0::/init.scope\n", "systemd", "systemd"),
    ],
)
def test_label_from_cgroup(text, name, expected):
    assert label_from_cgroup(text, name) == expected


def test_top_labels_sums_processes_of_one_service():
    snap = CpuSnapshot(
        0.0,
        {},
        [
            ProcessUsage(1, "node", "nodered.service", 40.0),
            ProcessUsage(2, "node", "nodered.service", 20.0),
            ProcessUsage(3, "python3", "boneio.service", 30.0),
        ],
    )
    assert top_labels(snap, 2) == [("nodered.service", 60.0), ("boneio.service", 30.0)]


def test_interrupts_when_softirq_dominates():
    snap = CpuSnapshot(
        0.0, {"user": 5, "system": 5, "iowait": 0, "irq": 10, "softirq": 70, "idle": 10}, []
    )
    assert looks_like_interrupts(snap)


def test_interrupts_when_kernel_irq_thread_on_top():
    snap = CpuSnapshot(
        0.0,
        {"user": 10, "system": 80, "iowait": 0, "irq": 0, "softirq": 0, "idle": 10},
        [ProcessUsage(9, "irq/45-gpio", "irq/45-gpio", 75.0)],
    )
    assert looks_like_interrupts(snap)


def test_not_interrupts_for_a_busy_program():
    snap = CpuSnapshot(
        0.0,
        {"user": 90, "system": 5, "iowait": 0, "irq": 0, "softirq": 1, "idle": 4},
        [ProcessUsage(1, "node", "nodered.service", 90.0)],
    )
    assert not looks_like_interrupts(snap)


def test_first_sample_is_only_a_baseline():
    assert CpuSampler().sample() is None


def test_measure_returns_a_breakdown_that_adds_up():
    snap = CpuSampler().measure(0.2)
    assert set(snap.breakdown) == {"user", "system", "iowait", "irq", "softirq", "idle"}
    assert 99.0 <= sum(snap.breakdown.values()) <= 101.0


class _FakeProcess:
    def __init__(self, pid, name, percent=None, error=None):
        self.pid = pid
        self.info = {"name": name}
        self._percent = percent
        self._error = error

    def cpu_percent(self, interval=None):
        if self._error:
            raise self._error
        return self._percent


def test_a_process_that_vanishes_is_skipped(monkeypatch):
    healthy = _FakeProcess(1, "node", 50.0)
    gone = _FakeProcess(2, "ghost", error=psutil.NoSuchProcess(2))
    monkeypatch.setattr(psutil, "process_iter", lambda attrs=None: iter([healthy, gone]))
    monkeypatch.setattr(cpu_report, "_read_cgroup", lambda pid: "0::/\n")
    sampler = CpuSampler()
    sampler.sample()
    snap = sampler.sample()
    assert [p.name for p in snap.processes] == ["node"]


def test_container_label_falls_back_when_docker_cannot_be_asked(monkeypatch):
    proc = _FakeProcess(7, "node", 80.0)
    monkeypatch.setattr(psutil, "process_iter", lambda attrs=None: iter([proc]))
    monkeypatch.setattr(
        cpu_report, "_read_cgroup", lambda pid: f"0::/system.slice/docker-{DOCKER_ID}.scope\n"
    )
    sampler = CpuSampler()
    sampler.sample()
    snap = sampler.sample()
    assert snap.processes[0].label == "docker:" + "a" * 12


def test_container_label_uses_the_container_name(monkeypatch):
    proc = _FakeProcess(7, "node", 80.0)
    monkeypatch.setattr(psutil, "process_iter", lambda attrs=None: iter([proc]))
    monkeypatch.setattr(
        cpu_report, "_read_cgroup", lambda pid: f"0::/system.slice/docker-{DOCKER_ID}.scope\n"
    )
    listing = '{"ID":"aaaaaaaaaaaa","Names":"nodered"}\n{"ID":"bbbbbbbbbbbb","Names":"caddy"}\n'
    monkeypatch.setattr(
        containers, "containers", lambda timeout=30: containers.Result(0, listing, "", True)
    )
    sampler = CpuSampler()
    sampler.sample()
    snap = sampler.sample()
    assert snap.processes[0].label == "nodered"
