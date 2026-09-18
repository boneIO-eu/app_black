"""Which addresses the panel's own HTTP server listens on.

The pentest finding is that the management interface answers in the clear on
0.0.0.0, and the recommendation is to limit it to 127.0.0.1 and reach it
through Caddy on 8443.

Applied literally that takes the device off the network entirely. Caddy runs in
a container and reaches the application through ``host.docker.internal``, which
Docker resolves to the host end of its own bridge — 172.17.0.1 on a boneIO
Black, not the loopback. Bound to 127.0.0.1 alone the proxy gets a refused
connection, 8443 answers 502, and a controller in a cabinet is reachable on no
port at all.

So "loopback only" has to mean loopback plus the bridge the proxy actually
arrives on, discovered on the device rather than written down here: the address
belongs to Docker and an operator can change it in daemon.json.
"""

from __future__ import annotations

import logging

_LOGGER = logging.getLogger(__name__)

#: Interfaces Docker gives the host on its own networks. The default bridge is
#: named exactly ``docker0`` and is where ``host-gateway`` points; ``br-<id>``
#: is a bridge created for a compose project.
_BRIDGE_PREFIXES = ("docker0", "br-")

LOOPBACK = "127.0.0.1"


class Exposure:
    """How much of the network the panel's own port answers on."""

    #: Every interface. What boneIO has always done, and what the finding is
    #: about: the login form, the tokens and the configuration in the clear on
    #: the LAN.
    ALL = "all"
    #: The loopback, plus whatever bridge the reverse proxy comes in on. The
    #: panel is then reachable over TLS on 8443, or through an SSH tunnel.
    PROXY = "proxy"


def docker_bridge_addresses() -> list[str]:
    """IPv4 addresses of the host's Docker bridges.

    Returns:
        Addresses, in a stable order, or an empty list when none can be found.
    """
    addresses: list[str] = []
    try:
        import psutil

        for name, addrs in psutil.net_if_addrs().items():
            if not name.startswith(_BRIDGE_PREFIXES):
                continue
            for addr in addrs:
                if getattr(addr, "family", None) is not None and addr.address:
                    # AF_INET only; psutil reports the family as an enum whose
                    # value is 2 on every platform this runs on.
                    if int(addr.family) == 2:
                        addresses.append(addr.address)
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Could not enumerate Docker bridges: %s", err)
    return sorted(set(addresses))


def binds_for(exposure: str, port: int) -> list[str]:
    """The ``host:port`` strings to hand to the server.

    Args:
        exposure: One of :class:`Exposure`.
        port: The port to listen on.

    Returns:
        Bind strings, never empty.
    """
    if exposure != Exposure.PROXY:
        return [f"0.0.0.0:{port}"]

    hosts = [LOOPBACK, *docker_bridge_addresses()]
    if len(hosts) == 1:
        # No bridge found. Binding the loopback alone would leave the panel
        # unreachable from anywhere but the device itself, so this says what
        # it is doing rather than quietly producing a dead controller.
        _LOGGER.warning(
            "web.expose is 'proxy' but no Docker bridge was found, so the "
            "panel will answer only on %s. Reach it over TLS on the proxy "
            "port, or with: ssh -L %d:%s:%d boneio@<device>",
            LOOPBACK, port, LOOPBACK, port,
        )
    else:
        _LOGGER.info(
            "Panel bound to %s — off the LAN, reachable through the proxy.",
            ", ".join(hosts),
        )
    return [f"{host}:{port}" for host in hosts]
