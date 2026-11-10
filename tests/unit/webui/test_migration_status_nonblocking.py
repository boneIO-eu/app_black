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


async def test_apply_is_accepted_once_only_the_v2_helper_is_left():
    """1.6.6 removes the legacy helper; v2 alone must be enough to apply."""
    runner = SimpleNamespace(
        _helper_installed=lambda: False, _any_helper_available=lambda: True
    )
    manager = SimpleNamespace(migration_runner=runner)
    tasks = SimpleNamespace(add_task=lambda *args: None)
    result = await migrations.apply_migrations(tasks, manager)
    assert result["success"] is True


async def test_bootstrap_does_not_reinstall_the_legacy_helper_beside_v2():
    runner = SimpleNamespace(
        _helper_installed=lambda: False, _any_helper_available=lambda: True
    )
    manager = SimpleNamespace(migration_runner=runner)
    tasks = SimpleNamespace(add_task=lambda *args: None)
    result = await migrations.bootstrap_migration_helper(None, tasks, manager)
    assert result["message"] == "Helper already installed."
