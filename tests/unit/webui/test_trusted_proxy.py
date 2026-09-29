"""The client address behind the local reverse proxy.

Caddy reaches the application from the Docker bridge, so without this every
proxied request came from the proxy's address. The header that fixes it is
also one anybody can send, so what these pin down is who is believed.
"""

from __future__ import annotations

import asyncio
import ipaddress

import pytest

from boneio.webui.middleware.proxy import TrustedProxyMiddleware, forwarded_client

BRIDGES = [ipaddress.IPv4Network("172.18.0.0/16")]


def _client_seen(peer: str, headers: list[tuple[bytes, bytes]], kind: str = "http"):
    seen = {}

    async def app(scope, receive, send):
        seen["client"] = scope.get("client")

    middleware = TrustedProxyMiddleware(app, bridge_networks=lambda: BRIDGES)
    scope = {"type": kind, "client": (peer, 51000), "headers": headers}
    asyncio.run(middleware(scope, None, None))
    return seen["client"][0]


XFF = [(b"x-forwarded-for", b"192.168.50.31")]


def test_the_proxy_on_the_bridge_is_believed():
    assert _client_seen("172.18.0.5", XFF) == "192.168.50.31"


def test_the_loopback_is_believed():
    assert _client_seen("127.0.0.1", XFF) == "192.168.50.31"
    assert _client_seen("::1", XFF) == "192.168.50.31"


def test_a_lan_client_sending_the_header_is_not():
    """Otherwise one guesser could pose as a new address on every attempt."""
    assert _client_seen("192.168.50.77", XFF) == "192.168.50.77"


def test_the_address_the_proxy_added_wins_over_what_the_client_wrote():
    spoofed = [(b"x-forwarded-for", b"10.9.9.9, 192.168.50.31")]
    assert _client_seen("172.18.0.5", spoofed) == "192.168.50.31"


def test_several_headers_read_as_one_list():
    headers = [(b"x-forwarded-for", b"10.9.9.9"), (b"X-Forwarded-For", b"192.168.50.31")]
    assert _client_seen("172.18.0.5", headers) == "192.168.50.31"


@pytest.mark.parametrize("value", [b"", b"unknown", b"192.168.50.31, not-an-ip", b"<script>"])
def test_a_header_that_is_not_an_address_changes_nothing(value):
    assert _client_seen("172.18.0.5", [(b"x-forwarded-for", value)]) == "172.18.0.5"


def test_no_header_changes_nothing():
    assert _client_seen("172.18.0.5", []) == "172.18.0.5"


def test_the_websocket_is_covered_too():
    assert _client_seen("172.18.0.5", XFF, kind="websocket") == "192.168.50.31"


def test_ipv6_clients_come_through():
    assert forwarded_client([(b"x-forwarded-for", b"fe80::1")]) == "fe80::1"


def test_the_bridges_are_read_again_once_they_appear(monkeypatch):
    """boneIO does not wait for Docker at boot, so the bridge can come later."""
    calls = {"n": 0}

    def bridges():
        calls["n"] += 1
        return [] if calls["n"] == 1 else BRIDGES

    seen = {}

    async def app(scope, receive, send):
        seen["client"] = scope["client"][0]

    middleware = TrustedProxyMiddleware(app, bridge_networks=bridges)
    scope = {"type": "http", "client": ("172.18.0.5", 1), "headers": XFF}
    asyncio.run(middleware(scope, None, None))
    assert seen["client"] == "172.18.0.5"

    clock = {"t": 1000.0}
    monkeypatch.setattr("boneio.webui.middleware.proxy.time.monotonic", lambda: clock["t"])
    middleware._read_at = 900.0  # more than the refresh interval ago
    asyncio.run(middleware(scope, None, None))
    assert seen["client"] == "192.168.50.31"
