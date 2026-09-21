"""Regression tests for the event bus worker outliving a bad listener.

Every input, output, cover and sensor event on a controller is dispatched by a
single worker task. A listener that raised ``CancelledError`` used to end that
task: ``CancelledError`` is a ``BaseException``, so it passed straight through
the ``except Exception`` handlers, and a task that ends that way is recorded as
merely *cancelled* — no traceback, nothing logged, nothing watching it.

From that point the queue kept filling and nobody drained it. On the controller
that looks like every input going dead at once, with nothing in the log to say
why, until the service is restarted.

A websocket send whose connection task is torn down underneath it raises
exactly this, and the websocket broadcast is registered as a global listener
for all six event types.
"""

from __future__ import annotations

import asyncio

import pytest

from boneio.core.events.bus import EventBus
from boneio.models import InputState
from boneio.models.events import InputEvent


def _input_event(entity_id: str) -> InputEvent:
    """Build a minimal InputEvent for dispatch."""
    return InputEvent(
        entity_id=entity_id,
        click_type="single",
        duration=None,
        state=InputState(
            name=entity_id,
            pin="P8_34",
            state="single",
            type="input",
            timestamp=0.0,
            boneio_input="",
            area=None,
        ),
    )


@pytest.fixture
async def bus():
    """A started EventBus, stopped on teardown."""
    bus = EventBus(loop=asyncio.get_running_loop())
    await bus.start()
    yield bus
    await bus.stop()


class TestWorkerSurvivesCancelledListener:
    async def test_worker_keeps_running(self, bus):
        """A listener raising CancelledError must not end the worker."""

        async def exploding(_event):
            raise asyncio.CancelledError

        bus.add_event_listener(
            event_type="input", entity_id="", listener_id="bad", target=exploding
        )

        bus.trigger_event(_input_event("in1"))
        await asyncio.sleep(0.05)

        assert not bus._worker_task.done(), "the worker died on a cancelled listener"

    async def test_later_events_are_still_delivered(self, bus):
        """The queue must keep draining after a listener is cancelled."""
        seen: list[str] = []

        async def exploding(_event):
            raise asyncio.CancelledError

        async def good(event):
            seen.append(event.entity_id)

        bus.add_event_listener(
            event_type="input", entity_id="", listener_id="bad", target=exploding
        )
        bus.add_event_listener(
            event_type="input", entity_id="", listener_id="good", target=good
        )

        bus.trigger_event(_input_event("in1"))
        bus.trigger_event(_input_event("in2"))
        await asyncio.sleep(0.05)

        assert seen == ["in1", "in2"]

    async def test_one_bad_listener_does_not_block_the_others(self, bus):
        """The surviving listeners still run for the very event that failed."""
        seen: list[str] = []

        async def exploding(_event):
            raise asyncio.CancelledError

        async def good(event):
            seen.append(event.entity_id)

        # 'bad' sorts before 'good', so it is dispatched first.
        bus.add_event_listener(
            event_type="input", entity_id="", listener_id="bad", target=exploding
        )
        bus.add_event_listener(
            event_type="input", entity_id="", listener_id="good", target=good
        )

        bus.trigger_event(_input_event("in1"))
        await asyncio.sleep(0.05)

        assert seen == ["in1"]

    async def test_ordinary_exceptions_still_contained(self, bus):
        """The pre-existing behaviour for normal errors is unchanged."""
        seen: list[str] = []

        async def exploding(_event):
            raise RuntimeError("boom")

        async def good(event):
            seen.append(event.entity_id)

        bus.add_event_listener(
            event_type="input", entity_id="", listener_id="bad", target=exploding
        )
        bus.add_event_listener(
            event_type="input", entity_id="", listener_id="good", target=good
        )

        bus.trigger_event(_input_event("in1"))
        await asyncio.sleep(0.05)

        assert seen == ["in1"]
        assert not bus._worker_task.done()


class TestStallIsReported:
    """A dispatcher that stops moving must say so in the journal."""

    async def test_no_warning_while_healthy(self, bus, caplog):
        bus._dispatch_started_at = None
        with caplog.at_level("ERROR"):
            bus._check_dispatch_stall()
        assert "waiting" not in caplog.text

    async def test_no_warning_before_the_threshold(self, bus, caplog):
        import time as _t

        bus._dispatch_started_at = _t.monotonic() - 1.0
        bus._dispatch_listener = "ws_input_global (input)"
        with caplog.at_level("ERROR"):
            bus._check_dispatch_stall()
        assert "waiting" not in caplog.text

    async def test_warns_once_when_stuck(self, bus, caplog):
        import time as _t

        bus._dispatch_started_at = _t.monotonic() - 60.0
        bus._dispatch_listener = "ws_input_global (input)"

        with caplog.at_level("ERROR"):
            bus._check_dispatch_stall()
            bus._check_dispatch_stall()

        assert caplog.text.count("Event bus has been waiting") == 1
        assert "ws_input_global (input)" in caplog.text

    async def test_listener_is_named_during_dispatch(self, bus):
        """The warning can only name a listener if dispatch records it."""
        seen: list[str] = []

        async def slow(_event):
            seen.append(bus._dispatch_listener)

        bus.add_event_listener(
            event_type="input", entity_id="", listener_id="ws_input_global", target=slow
        )
        bus.trigger_event(_input_event("in1"))
        await asyncio.sleep(0.05)

        assert seen == ["ws_input_global (input)"]
