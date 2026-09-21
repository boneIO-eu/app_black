"""Stopping a cover must not freeze the event loop.

`Cover.stop()` waits for the movement thread to notice the stop event and then
de-energises both relays over I2C. Done inline in the coroutine that is half a
second of stopped event loop — and `toggle`, `toggle_open` and `toggle_close`
all call `stop()` first, so an ordinary button press paid for it. Nothing reads
GPIO while the loop is stopped, which is how a cover button ends up taking the
inputs down with it.
"""

from __future__ import annotations

import asyncio
import sys
import threading
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from boneio.components.cover.time_based import TimeBasedCover
from boneio.const import IDLE, OPENING


def _stopping_cover(join_delay: float) -> TimeBasedCover:
    """A cover whose movement thread takes `join_delay` seconds to finish.

    Only the attributes `stop()` touches are built; a real cover drags in MQTT,
    the event bus and the whole config stack.
    """
    cover = object.__new__(TimeBasedCover)
    cover._id = "cover_05"
    cover._position = 50.0
    cover._current_operation = OPENING
    cover._last_operation = OPENING
    cover._stop_event = threading.Event()
    cover._open_relay = MagicMock()
    cover._close_relay = MagicMock()
    # stop() fires these off as tasks; they must be awaitable.
    cover._open_relay.async_send_state = AsyncMock()
    cover._close_relay.async_send_state = AsyncMock()
    cover.send_state = MagicMock()

    def _spin() -> None:
        cover._stop_event.wait(timeout=5.0)
        # Keep the thread alive a little past the stop event, so join() really
        # has something to wait for.
        threading.Event().wait(join_delay)

    cover._movement_thread = threading.Thread(target=_spin, daemon=True)
    cover._movement_thread.start()
    return cover


class TestStopDoesNotBlockTheLoop:
    async def test_loop_keeps_running_during_stop(self):
        """A heartbeat must keep ticking while stop() waits on the thread."""
        cover = _stopping_cover(join_delay=0.3)
        ticks = 0
        running = True

        async def heartbeat():
            nonlocal ticks
            while running:
                ticks += 1
                await asyncio.sleep(0.01)

        beat = asyncio.create_task(heartbeat())
        await asyncio.sleep(0.02)
        before = ticks

        await cover.stop()

        running = False
        await beat

        # Inline, join(0.5) pinned the loop and the heartbeat could not advance.
        assert ticks - before >= 5, (
            f"loop was blocked during stop(): only {ticks - before} ticks"
        )

    async def test_relays_are_de_energised(self):
        """The behaviour itself is unchanged: both relays go off."""
        cover = _stopping_cover(join_delay=0.0)

        await cover.stop()

        cover._open_relay.turn_off.assert_called_once()
        cover._close_relay.turn_off.assert_called_once()
        assert cover._current_operation == IDLE

    async def test_relay_writes_happen_off_the_loop_thread(self):
        """The I2C writes must not run on the event loop thread."""
        cover = _stopping_cover(join_delay=0.0)
        loop_thread = threading.get_ident()
        seen: list[int] = []

        cover._open_relay.turn_off.side_effect = lambda: seen.append(
            threading.get_ident()
        )
        cover._close_relay.turn_off.side_effect = lambda: seen.append(
            threading.get_ident()
        )

        await cover.stop()

        assert seen and all(t != loop_thread for t in seen), (
            "relay writes ran on the event loop thread"
        )

    async def test_stop_is_a_noop_without_a_live_thread(self):
        """No movement in progress: nothing to halt, nothing touched."""
        cover = object.__new__(TimeBasedCover)
        cover._movement_thread = None
        cover._open_relay = MagicMock()
        cover._close_relay = MagicMock()

        await cover.stop()

        cover._open_relay.turn_off.assert_not_called()
