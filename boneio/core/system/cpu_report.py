"""Which processes use the CPU, named by the service they belong to.

The CPU sensor reports the whole system, so 100% on a single-core controller
only says that *something* holds the core. This module says what.

Three rules shape it.

**Our own deltas, never psutil's percent helpers.** ``psutil.cpu_percent()``
and ``cpu_times_percent()`` measure "since the previous call" in a module-wide
slot that the CPU sensor and the OLED already use; calling them here would
shorten the sensor's window. The breakdown is computed from ``cpu_times()``.

**A scan costs about 300 ms of CPU on a BeagleBone** (measured with 144
processes). Every caller runs it in a worker thread and the HA sensor only
scans when the CPU is already busy.

**No command lines.** They can carry passwords that are not in the
configuration, and the report ends up in a support bundle that leaves the
house. A process is its name, its pid and its cgroup — the cgroup is what turns
``node`` into Node-RED and ``python3`` into the right container.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from collections import defaultdict
from dataclasses import dataclass

import psutil

from boneio.core import containers

_LOGGER = logging.getLogger(__name__)

#: How long a container id → name map stays good. Asking costs a sudo call of
#: about two seconds, and containers are not renamed while they run.
CONTAINER_NAMES_TTL = 600

_DOCKER_SCOPE = re.compile(r"docker-([0-9a-f]{12,64})\.scope$")

#: (fetched at, {short id: name}), refreshed by :func:`_container_names`.
_container_cache: tuple[float, dict[str, str]] = (0.0, {})


@dataclass(frozen=True)
class ProcessUsage:
    """One process's share of the CPU between two samples."""

    pid: int
    name: str
    label: str
    percent: float


@dataclass(frozen=True)
class CpuSnapshot:
    """The CPU between two samples.

    Attributes:
        measured_at: Epoch seconds of the second sample.
        breakdown: Percent of the interval in ``user, system, iowait, irq,
            softirq, idle``; adds up to 100.
        processes: Processes that used any CPU, busiest first.
    """

    measured_at: float
    breakdown: dict[str, float]
    processes: list[ProcessUsage]


def label_from_cgroup(text: str, name: str) -> str:
    """Name a process by its systemd service or container, else by itself.

    Args:
        text: Contents of ``/proc/<pid>/cgroup`` (cgroup v2).
        name: The process name, used when the cgroup says nothing better.
    """
    for line in text.splitlines():
        path = line.rpartition(":")[2]
        last = path.rstrip("/").rpartition("/")[2]
        if last.endswith(".service"):
            return last
        docker = _DOCKER_SCOPE.match(last)
        if docker:
            return f"docker:{docker.group(1)[:12]}"
    return name


def top_labels(snapshot: CpuSnapshot, n: int = 3) -> list[tuple[str, float]]:
    """The *n* labels using the most CPU, processes of one service summed."""
    totals: dict[str, float] = defaultdict(float)
    for process in snapshot.processes:
        totals[process.label] += process.percent
    ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)
    return [(label, round(percent, 1)) for label, percent in ranked[:n]]


def looks_like_interrupts(snapshot: CpuSnapshot) -> bool:
    """Whether the CPU goes to interrupts rather than to programs.

    On this hardware that usually means a floating input or a flood on the
    network, which no process list will explain.
    """
    # ponytail: rough thresholds, tune them after the first real case.
    irq = snapshot.breakdown.get("irq", 0) + snapshot.breakdown.get("softirq", 0)
    if irq >= 30:
        return True
    if snapshot.processes:
        top = snapshot.processes[0].label
        return top.startswith(("ksoftirqd", "irq/"))
    return False


def _read_cgroup(pid: int) -> str:
    try:
        with open(f"/proc/{pid}/cgroup", encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return ""


def _container_names() -> dict[str, str]:
    """Short container id → name, from the helper, cached."""
    global _container_cache
    fetched, names = _container_cache
    if names and time.monotonic() - fetched < CONTAINER_NAMES_TTL:
        return names
    names = {}
    try:
        parsed = containers.containers().json()
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Could not list containers for the CPU report: %s", err)
        parsed = None
    if isinstance(parsed, dict):
        parsed = [parsed]
    for item in parsed or []:
        if isinstance(item, dict) and item.get("ID") and item.get("Names"):
            names[str(item["ID"])[:12]] = str(item["Names"])
    _container_cache = (time.monotonic(), names)
    return names


def _breakdown(before, after) -> dict[str, float]:
    delta = {field: getattr(after, field) - getattr(before, field) for field in after._fields}
    total = sum(delta.values()) or 1.0
    known = ("user", "nice", "system", "iowait", "irq", "softirq", "idle")
    rest = sum(value for field, value in delta.items() if field not in known)
    share = {
        "user": delta.get("user", 0) + delta.get("nice", 0),
        "system": delta.get("system", 0) + rest,
        "iowait": delta.get("iowait", 0),
        "irq": delta.get("irq", 0),
        "softirq": delta.get("softirq", 0),
        "idle": delta.get("idle", 0),
    }
    return {field: round(100 * value / total, 1) for field, value in share.items()}


class CpuSampler:
    """Remembers the previous sample so the next one can be a difference.

    Not thread-safe by itself; :meth:`sample` holds a lock because the panel,
    the HA sensor and the bundle share one instance.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._procs: dict[int, psutil.Process] = {}
        self._times = None

    def sample(self) -> CpuSnapshot | None:
        """Usage since the previous call; ``None`` on the first, which is a baseline.

        Blocks for the length of a process scan.
        """
        with self._lock:
            times = psutil.cpu_times()
            seen: dict[int, psutil.Process] = {}
            usage: list[ProcessUsage] = []
            for process in psutil.process_iter(["name"]):
                try:
                    known = self._procs.get(process.pid)
                    # psutil caches Process objects, but only a Process that
                    # was asked before can say what it used since.
                    current = known or process
                    percent = current.cpu_percent(None)
                    seen[process.pid] = current
                    if known is None or not percent:
                        continue
                    name = process.info.get("name") or str(process.pid)
                    label = label_from_cgroup(_read_cgroup(process.pid), name)
                    usage.append(ProcessUsage(process.pid, name, label, round(percent, 1)))
                except (psutil.NoSuchProcess, psutil.ZombieProcess, psutil.AccessDenied):
                    continue
            before, self._times, self._procs = self._times, times, seen
            if before is None:
                return None

        if any(p.label.startswith("docker:") for p in usage):
            names = _container_names()
            usage = [
                ProcessUsage(p.pid, p.name, names.get(p.label[7:], p.label), p.percent)
                if p.label.startswith("docker:")
                else p
                for p in usage
            ]
        usage.sort(key=lambda p: p.percent, reverse=True)
        return CpuSnapshot(time.time(), _breakdown(before, times), usage)

    def measure(self, interval: float = 1.0) -> CpuSnapshot:
        """A fresh measurement over *interval* seconds. Blocks."""
        self.sample()
        time.sleep(interval)
        snapshot = self.sample()
        assert snapshot is not None
        return snapshot


#: The one sampler the panel, the HA sensor and the bundle share.
SAMPLER = CpuSampler()
