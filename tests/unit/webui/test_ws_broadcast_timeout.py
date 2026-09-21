"""A WebSocket client that stops answering must not stop the controller.

Reported from the field on v1.5.4: clicking an input logged
``Detected SINGLE click`` but the output action never ran, and only a restart
brought it back. In the same journal, hypercorn logged
``OSError: [Errno 113] No route to host`` — a browser whose host had left the
network.

That is the whole mechanism. Nothing raises ``WebSocketDisconnect`` for a peer
that simply stopped being routable: the socket stays in ``active_connections``,
the kernel buffer fills, and ``writer.drain()`` inside hypercorn waits for as
long as TCP keeps retrying. Every entity event on the device is dispatched by
one worker task which awaits this broadcast, so the wait became everyone's —
inputs, outputs, covers and sensors all stopped, while the click detector
upstream carried on logging clicks that no longer did anything.
"""

from __future__ import annotations

import asyncio

import pytest
from starlette.websockets import WebSocketDisconnect

from boneio.webui.websocket_manager import WS_SEND_TIMEOUT, WebSocketManager


class FakeClient:
    """A websocket that can be healthy, hung, or already gone."""

    def __init__(self, behaviour: str = "ok") -> None:
        self.behaviour = behaviour
        self.sent: list[dict] = []
        self.closed = False
        self.application_state = None

    async def send_json(self, payload: dict) -> None:
        if self.behaviour == "hang":
            await asyncio.Event().wait()  # never completes
        if self.behaviour == "gone":
            raise WebSocketDisconnect()
        if self.behaviour == "boom":
            raise RuntimeError("socket exploded")
        self.sent.append(payload)

    async def close(self, code: int = 1000) -> None:
        self.closed = True


@pytest.fixture
def manager(monkeypatch):
    """A manager with a very short send timeout, so tests stay fast."""
    monkeypatch.setattr("boneio.webui.websocket_manager.WS_SEND_TIMEOUT", 0.2)
    return WebSocketManager()


class TestOneStuckClientDoesNotBlockTheRest:
    async def test_broadcast_returns_despite_a_hung_client(self, manager):
        """The broadcast must finish in about the timeout, not never."""
        hung = FakeClient("hang")
        manager.active_connections = [hung]

        start = asyncio.get_running_loop().time()
        await manager.broadcast({"hello": "world"})
        elapsed = asyncio.get_running_loop().time() - start

        assert elapsed < 2.0, f"broadcast hung for {elapsed:.2f}s"

    async def test_healthy_clients_still_get_the_frame(self, manager):
        """A stuck client must not cost the others their update."""
        hung = FakeClient("hang")
        good = FakeClient("ok")
        manager.active_connections = [hung, good]

        await manager.broadcast({"n": 1})

        assert good.sent == [{"n": 1}]

    async def test_the_stuck_client_is_dropped(self, manager):
        """Once it has timed out it must not be tried again forever."""
        hung = FakeClient("hang")
        good = FakeClient("ok")
        manager.active_connections = [hung, good]

        await manager.broadcast({"n": 1})

        assert hung not in manager.active_connections
        assert good in manager.active_connections

    async def test_many_stuck_clients_cost_one_timeout(self, manager):
        """Sends run concurrently: five dead clients, not five waits."""
        manager.active_connections = [FakeClient("hang") for _ in range(5)]

        start = asyncio.get_running_loop().time()
        await manager.broadcast({"n": 1})
        elapsed = asyncio.get_running_loop().time() - start

        assert elapsed < 1.0, f"timeouts ran in series: {elapsed:.2f}s"
        assert manager.active_connections == []


class TestOrdinaryFailuresStillHandled:
    async def test_disconnected_client_is_dropped(self, manager):
        good = FakeClient("ok")
        manager.active_connections = [FakeClient("gone"), good]

        await manager.broadcast({"n": 1})

        assert manager.active_connections == [good]

    async def test_raising_client_is_dropped_and_others_served(self, manager):
        good = FakeClient("ok")
        manager.active_connections = [FakeClient("boom"), good]

        await manager.broadcast({"n": 1})

        assert manager.active_connections == [good]
        assert good.sent == [{"n": 1}]

    async def test_no_clients_is_a_noop(self, manager):
        manager.active_connections = []
        await manager.broadcast({"n": 1})  # must not raise

    async def test_closing_manager_sends_nothing(self, manager):
        good = FakeClient("ok")
        manager.active_connections = [good]
        manager._closing = True

        await manager.broadcast({"n": 1})

        assert good.sent == []


class TestTheDefaultTimeoutIsSane:
    def test_timeout_is_bounded(self):
        """Long enough for a slow phone, short enough not to wedge the bus."""
        assert 1.0 <= WS_SEND_TIMEOUT <= 15.0
