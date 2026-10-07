"""The panel answers on the loopback at once and on docker0 once it is up.

Node-RED asks the panel through host.docker.internal, which is docker0, so the
second listener is needed; it must not run the application's startup twice, and
it must not hold up a shutdown while it is still waiting for Docker.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from boneio.webui import bind
from boneio.webui.web_server import WebServer, _without_lifespan


def test_the_second_server_does_not_run_the_app_startup_again():
    calls = []

    async def app(scope, receive, send):
        calls.append(scope["type"])

    sent = []

    async def receive():
        return {"type": "lifespan.startup"}

    async def send(message):
        sent.append(message["type"])
        raise asyncio.CancelledError  # end the loop after the first answer

    try:
        asyncio.run(_without_lifespan(app)({"type": "lifespan"}, receive, send))
    except asyncio.CancelledError:
        pass
    assert calls == []
    assert sent == ["lifespan.startup.complete"]


def _server() -> WebServer:
    server = WebServer.__new__(WebServer)
    server._port = 8090
    server._shutdown_event = asyncio.Event()
    server._hypercorn_config = SimpleNamespace(bind=["127.0.0.1:8090"])
    server.app = None
    return server


async def test_a_shutdown_while_waiting_for_docker_is_not_held_up(monkeypatch):
    """Docker disabled, or a restart in the first minutes of boot."""
    monkeypatch.setattr(bind, "_default_bridge_up", lambda: False)
    monkeypatch.setattr(bind, "_BRIDGE_POLL_SECONDS", 0.01)
    server = _server()
    task = asyncio.create_task(server._serve_late_bridge(server.app))
    await asyncio.sleep(0.05)
    server._shutdown_event.set()
    await asyncio.wait_for(task, timeout=1)


async def test_a_bridge_that_cannot_be_bound_leaves_the_panel_running(monkeypatch, caplog):
    monkeypatch.setattr(bind, "_default_bridge_up", lambda: True)
    monkeypatch.setattr(bind, "docker_bridge_addresses", lambda: ["172.17.0.1"])
    monkeypatch.setattr(bind, "usb_gadget_addresses", lambda: [])

    async def refuse(*args, **kwargs):
        raise OSError("address already in use")

    monkeypatch.setattr("hypercorn.asyncio.serve", refuse)
    server = _server()
    await asyncio.wait_for(server._serve_late_bridge(server.app), timeout=1)
    assert "address already in use" in caplog.text
