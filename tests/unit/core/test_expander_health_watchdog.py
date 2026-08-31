"""The watchdog loop that keeps MCP23017 expanders driving their outputs.

Without it, an expander reset back to all-inputs stays dead until boneIO is
restarted: every write still succeeds, so nothing else in the stack notices.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from boneio.core.manager.outputs import OutputManager


def _bare_output_manager(mcps: dict) -> OutputManager:
    """Only the attributes the watchdog loop touches."""
    manager = object.__new__(OutputManager)
    manager._mcp = mcps
    return manager


async def _run_one_pass(manager: OutputManager, monkeypatch) -> None:
    """Let the watchdog complete exactly one sweep, then stop it.

    The loop is intentionally infinite, so the second sleep (the interval at the
    bottom of the loop) is what we cancel on.
    """
    calls = {"sleeps": 0}

    async def fake_sleep(_seconds: float) -> None:
        calls["sleeps"] += 1
        if calls["sleeps"] >= 2:  # 1 = initial delay, 2 = end of first sweep
            raise asyncio.CancelledError
        return None

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    with pytest.raises(asyncio.CancelledError):
        await manager._expander_health_watchdog()


@pytest.mark.asyncio
async def test_watchdog_checks_every_expander(monkeypatch):
    left, right = MagicMock(), MagicMock()
    left.health_check.return_value = False
    right.health_check.return_value = False
    manager = _bare_output_manager({"mcp_left": left, "mcp_right": right})

    await _run_one_pass(manager, monkeypatch)

    left.health_check.assert_called_once()
    right.health_check.assert_called_once()


@pytest.mark.asyncio
async def test_watchdog_reports_a_repair(monkeypatch, caplog):
    broken = MagicMock()
    broken.health_check.return_value = True
    broken.address = 0x24
    manager = _bare_output_manager({"mcp_right": broken})

    with caplog.at_level(logging.WARNING):
        await _run_one_pass(manager, monkeypatch)

    assert "mcp_right" in caplog.text
    assert "0x24" in caplog.text


@pytest.mark.asyncio
async def test_one_failing_expander_does_not_stop_the_sweep(monkeypatch, caplog):
    """A raising health_check must not kill the task or skip the other chips."""
    exploding, healthy = MagicMock(), MagicMock()
    exploding.health_check.side_effect = OSError("bus gone")
    healthy.health_check.return_value = False
    manager = _bare_output_manager({"mcp_left": exploding, "mcp_right": healthy})

    with caplog.at_level(logging.ERROR):
        await _run_one_pass(manager, monkeypatch)

    healthy.health_check.assert_called_once()
    assert "bus gone" in caplog.text
