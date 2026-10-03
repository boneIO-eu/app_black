"""Config reloads run one at a time.

A reload re-reads the file and rebuilds entity maps across awaits; two saves
clicked in quick succession used to interleave and leave inputs half-rebuilt.
"""

from __future__ import annotations

import asyncio
import sys
from unittest.mock import MagicMock

mock_gpiod = MagicMock()
sys.modules.setdefault("gpiod", mock_gpiod)
sys.modules.setdefault("gpiod.line", mock_gpiod.line)

from boneio.core.manager.manager import Manager  # noqa: E402


def test_concurrent_reloads_do_not_overlap():
    async def run():
        manager = Manager.__new__(Manager)
        manager._reload_lock = asyncio.Lock()
        running = 0
        peak = 0

        async def body(sections):
            nonlocal running, peak
            running += 1
            peak = max(peak, running)
            await asyncio.sleep(0.01)
            running -= 1
            return {"status": "success", "sections": sections}

        manager._reload_config_locked = body
        manager.inputs = MagicMock()

        async def reload_inputs():
            await body(["input"])

        manager.inputs.reload_inputs = reload_inputs

        results = await asyncio.gather(
            manager.reload_config(["event"]),
            manager.reload_config(["binary_sensor"]),
            manager.reload_inputs_serialized(),
        )
        return peak, results

    peak, results = asyncio.run(run())

    assert peak == 1
    assert results[0]["sections"] == ["event"]
    assert results[1]["sections"] == ["binary_sensor"]
