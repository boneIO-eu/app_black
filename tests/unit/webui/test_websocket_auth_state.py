"""Whether a socket needs a token is decided per connection, not at boot.

A controller ships with no account, so the server starts believing no token is
needed. Somebody finishes the first-run wizard and from that moment the client
knows better: /api/init says auth is required, and the client offers its token
as a WebSocket subprotocol. A server still holding the boot-time answer accepts
without agreeing to a subprotocol, the browser fails the handshake, and it does
so on every reconnect.

The visible result is a panel with no outputs, no inputs and no sensors — the
socket is the only thing that carries them — for the whole life of the process.
"""

from __future__ import annotations

import asyncio

import pytest

from boneio.webui.websocket_manager import WebSocketManager


class _Socket:
    """Enough of a WebSocket to watch what the manager does to it."""

    def __init__(self, protocols: str | None = None):
        self.headers = {"sec-websocket-protocol": protocols} if protocols else {}
        self.accepted_with: str | None | object = "not accepted"
        self.closed: tuple[int, str] | None = None

    async def accept(self, subprotocol: str | None = None):
        self.accepted_with = subprotocol

    async def close(self, code: int = 1000, reason: str = ""):
        self.closed = (code, reason)


TOKEN_PROTOCOL = "token.abc.def.ghi"


def test_an_unclaimed_device_needs_no_token():
    manager = WebSocketManager(auth_required=lambda: False)
    assert manager.auth_required is False


def test_the_answer_follows_the_device():
    """The regression.

    Same manager, same process: the device gains an account and the next
    connection has to be treated differently from the last.
    """
    claimed = False
    manager = WebSocketManager(auth_required=lambda: claimed)
    assert manager.auth_required is False

    claimed = True
    assert manager.auth_required is True, "still answering with the boot-time value"


def test_a_plain_boolean_still_works():
    """Tests and callers that pass a fixed answer keep working."""
    assert WebSocketManager(auth_required=True).auth_required is True
    assert WebSocketManager(auth_required=False).auth_required is False


def test_an_unreadable_auth_state_requires_a_token():
    """A socket carries every entity on the device, so this fails closed."""

    def broken():
        raise RuntimeError("account store is unreadable")

    assert WebSocketManager(auth_required=broken).auth_required is True


def test_the_token_subprotocol_is_agreed_to(monkeypatch):
    """What the browser is waiting for.

    Offering a subprotocol and getting none back is a failed handshake, which
    is what the panel showed as WebSocket close 1006 over and over.
    """
    manager = WebSocketManager(auth_required=lambda: True)
    monkeypatch.setattr(manager, "_verify_token", lambda ws: _true())
    socket = _Socket(protocols=TOKEN_PROTOCOL)

    assert asyncio.run(manager.connect(socket)) is True
    assert socket.accepted_with == TOKEN_PROTOCOL


def test_a_device_claimed_after_boot_still_agrees_to_it(monkeypatch):
    """The whole bug, end to end."""
    claimed = False
    manager = WebSocketManager(auth_required=lambda: claimed)
    monkeypatch.setattr(manager, "_verify_token", lambda ws: _true())

    claimed = True
    socket = _Socket(protocols=TOKEN_PROTOCOL)
    assert asyncio.run(manager.connect(socket)) is True
    assert socket.accepted_with == TOKEN_PROTOCOL, (
        "accepted without the subprotocol the client offered — the browser "
        "fails this handshake and the panel gets no entities"
    )


def test_a_bad_token_is_refused(monkeypatch):
    manager = WebSocketManager(auth_required=lambda: True)
    monkeypatch.setattr(manager, "_verify_token", lambda ws: _false())
    socket = _Socket(protocols=TOKEN_PROTOCOL)

    assert asyncio.run(manager.connect(socket)) is False
    assert socket.closed == (4001, "Authentication failed")


async def _true() -> bool:
    return True


async def _false() -> bool:
    return False


def test_an_unclaimed_device_accepts_without_a_token(monkeypatch):
    """The other half, and the one a careless fix breaks.

    Reading the callable as a plain truthiness test rather than calling it
    makes every device look claimed — a function object is always truthy — so
    a freshly flashed controller would demand a token nobody can have yet, and
    the wizard would come up with no socket at all.
    """
    asked = []
    manager = WebSocketManager(auth_required=lambda: False)
    monkeypatch.setattr(
        manager, "_verify_token", lambda ws: asked.append(ws) or _false()
    )
    socket = _Socket()

    assert asyncio.run(manager.connect(socket)) is True
    assert socket.accepted_with is None, "negotiated a subprotocol nobody offered"
    assert socket.closed is None
    assert asked == [], "asked for a token on a device that has no accounts"
