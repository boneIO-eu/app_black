"""Why boneIO itself uses the CPU: which thread, and where it spends it."""

from __future__ import annotations

import asyncio
import threading
from collections import namedtuple

import psutil

from boneio.core.system import cpu_why
from boneio.core.system.cpu_why import explain, hot_stacks, task_counts, thread_usage


def test_a_spinning_thread_is_the_hottest_and_its_stack_points_at_it():
    stop = threading.Event()

    def spin_here():
        while not stop.is_set():
            pass

    thread = threading.Thread(target=spin_here, name="spinner")
    thread.start()
    try:
        report = explain(0.3)
        assert report["hot_thread"] == "spinner"
        assert "spin_here" in report["stacks"][0]["stack"]
    finally:
        stop.set()
        thread.join()


def test_an_unknown_thread_has_no_stack():
    assert hot_stacks(native_id=999_999_999, samples=2, interval=0) == []


def test_unnamed_threads_are_shown_by_tid(monkeypatch):
    Thread = namedtuple("Thread", "id user_time system_time")
    calls = iter([[Thread(424242, 0.0, 0.0)], [Thread(424242, 0.5, 0.0)]])

    class FakeProcess:
        def threads(self):
            return next(calls)

    monkeypatch.setattr(psutil, "Process", FakeProcess)
    usage = thread_usage(0.0)
    assert usage[0].name == "tid 424242"
    assert usage[0].percent > 0


async def test_task_counts_groups_by_coroutine():
    async def waiter():
        await asyncio.sleep(10)

    tasks = [asyncio.create_task(waiter()) for _ in range(3)]
    try:
        assert task_counts()[waiter.__qualname__] == 3
    finally:
        for task in tasks:
            task.cancel()


def test_nothing_busy_means_no_stack(monkeypatch):
    monkeypatch.setattr(cpu_why, "thread_usage", lambda interval=1.0: [])
    report = explain(0.0)
    assert report == {"threads": [], "hot_thread": None, "stacks": []}
