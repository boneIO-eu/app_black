"""Tell the application who is really on the other end of a proxied request.

The panel is normally reached through Caddy, which runs in a container and
connects to the application from the Docker bridge. Every such request then
came "from" the proxy's address, so the per-IP login throttle put the whole
household in one bucket and the logs named the proxy for every sign-in.

Caddy says who it is forwarding for in ``X-Forwarded-For``, and this puts that
address where the rest of the application reads the client from. Only for a
request that arrives from the proxy, though: the panel's own port can also be
reachable from the LAN, and there anybody can send the header — honouring it
would let one guesser pose as a new address on every attempt and walk
straight past the per-IP throttle.

So the header counts only when the peer is the loopback or a Docker bridge
network on this controller. Of its list the right-most address is taken: that
is the one the proxy itself added, whatever the client wrote in front of it.
"""

from __future__ import annotations

import ipaddress
import logging
import time
from collections.abc import Callable

from boneio.webui.bind import docker_bridge_networks

_LOGGER = logging.getLogger(__name__)

# How long a list of bridge networks is trusted before it is read again. The
# bridges can appear after the application has started — boneIO does not wait
# for Docker at boot — so it cannot be read once for good.
_REFRESH_SECONDS = 60.0

_Network = ipaddress.IPv4Network | ipaddress.IPv6Network


class TrustedProxyMiddleware:
    """Replace the client address with the forwarded one, for the local proxy.

    Pure ASGI rather than BaseHTTPMiddleware, so it covers the WebSocket too
    and runs before everything that reads the client address.

    Args:
        app: The wrapped ASGI application.
        bridge_networks: Returns the Docker bridge networks; replaceable for
            tests.
    """

    def __init__(
        self,
        app,
        bridge_networks: Callable[[], list[_Network]] = docker_bridge_networks,
    ) -> None:
        self.app = app
        self._bridge_networks = bridge_networks
        self._networks: list[_Network] = []
        self._read_at = float("-inf")

    def _trusted(self, host: str) -> bool:
        """Whether a peer address is this controller's own proxy.

        Args:
            host: The peer address of the connection.

        Returns:
            True for the loopback and the Docker bridge networks.
        """
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            return False
        if address.is_loopback:
            return True
        now = time.monotonic()
        if now - self._read_at > _REFRESH_SECONDS:
            self._networks = self._bridge_networks()
            self._read_at = now
        return any(address in network for network in self._networks)

    async def __call__(self, scope, receive, send):
        """Rewrite ``scope["client"]`` for a request forwarded by the proxy."""
        if scope["type"] in ("http", "websocket"):
            client = scope.get("client")
            if client and self._trusted(client[0]):
                forwarded = forwarded_client(scope.get("headers") or [])
                if forwarded is not None:
                    scope = {**scope, "client": (forwarded, client[1])}
        await self.app(scope, receive, send)


def forwarded_client(headers: list[tuple[bytes, bytes]]) -> str | None:
    """The address the proxy forwarded for, from ``X-Forwarded-For``.

    Args:
        headers: Raw ASGI headers.

    Returns:
        The right-most well-formed address, or None when there is none.
    """
    values = [v for k, v in headers if k.lower() == b"x-forwarded-for"]
    if not values:
        return None
    # Several headers are one list, in order.
    entries = b",".join(values).decode("latin-1").split(",")
    candidate = entries[-1].strip()
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        _LOGGER.debug("Ignoring an X-Forwarded-For that is not an address: %r", candidate)
        return None
