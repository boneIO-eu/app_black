"""Tests for AsyncUpdater's initial_delay.

Regression cover for the startup stall: ``_refresh`` performed its first update
immediately, so any component doing network I/O in ``async_update`` sat on the
application's startup critical path.
"""

from __future__ import annotations

import asyncio

import pytest

from boneio.core.utils.async_updater import AsyncUpdater
from boneio.core.utils.timeperiod import TimePeriod


class FakeManager:
    """Minimal Manager stand-in that runs appended coroutines as tasks."""

    def __init__(self) -> None:
        self.tasks: list[asyncio.Task] = []

    def append_task(self, coro, name: str) -> None:
        self.tasks.append(asyncio.get_event_loop().create_task(coro(), name=name))

    async def cancel_all(self) -> None:
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)


class CountingUpdater(AsyncUpdater):
    """Records every async_update invocation."""

    def __init__(self, manager, **kwargs) -> None:
        self.id = "counting"
        self.calls = 0
        self.first_call_at: float | None = None
        super().__init__(manager=manager, **kwargs)

    async def async_update(self, timestamp: float) -> float | None:
        self.calls += 1
        if self.first_call_at is None:
            self.first_call_at = asyncio.get_running_loop().time()
        return None


@pytest.mark.asyncio
async def test_without_initial_delay_first_update_is_immediate() -> None:
    """Existing behaviour is preserved when initial_delay is not given."""
    manager = FakeManager()
    updater = CountingUpdater(manager, update_interval=TimePeriod(hours=1))

    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert updater.calls == 1
    await manager.cancel_all()


@pytest.mark.asyncio
async def test_initial_delay_defers_first_update() -> None:
    """With initial_delay set, nothing runs during startup."""
    manager = FakeManager()
    updater = CountingUpdater(
        manager,
        update_interval=TimePeriod(hours=1),
        initial_delay=TimePeriod(seconds=30),
    )

    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert updater.calls == 0, "first update must not run on the startup path"
    await manager.cancel_all()


@pytest.mark.asyncio
async def test_initial_delay_zero_behaves_like_no_delay() -> None:
    manager = FakeManager()
    updater = CountingUpdater(
        manager,
        update_interval=TimePeriod(hours=1),
        initial_delay=TimePeriod(seconds=0),
    )

    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert updater.calls == 1
    await manager.cancel_all()


@pytest.mark.asyncio
async def test_request_update_interrupts_initial_delay() -> None:
    """An explicit refresh (e.g. from the WebUI) must not wait out the delay."""
    manager = FakeManager()
    updater = CountingUpdater(
        manager,
        update_interval=TimePeriod(hours=1),
        initial_delay=TimePeriod(hours=1),
    )

    await asyncio.sleep(0)
    assert updater.calls == 0

    updater.request_update()
    # Yield enough for the wait_for to observe the event and the loop to advance.
    for _ in range(6):
        await asyncio.sleep(0)

    assert updater.calls == 1
    await manager.cancel_all()
