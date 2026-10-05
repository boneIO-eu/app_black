"""The migration status does not hold the event loop while the helper selftest runs."""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

from boneio.webui.routes import migrations


async def test_the_status_runs_off_the_loop():
    def slow_status():
        time.sleep(0.3)  # stands in for sudo boneio-migrate-v2 --selftest
        return {"status": "ok"}

    manager = SimpleNamespace(migration_runner=SimpleNamespace(get_status_dict=slow_status))
    ticks = 0

    async def tick():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    ticker = asyncio.create_task(tick())
    assert await migrations.get_migration_status(manager) == {"status": "ok"}
    ticker.cancel()
    assert ticks > 10
