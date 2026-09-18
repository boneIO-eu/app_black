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

import json
import logging
import ssl
import time
import urllib.error
import urllib.request

import psutil

from boneio.const import DEFAULT_PROXY_PORT

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


#: How long to wait for a Docker bridge to appear before giving up on it.
#:
#: boneIO deliberately does not start after docker.service — it drives relays,
#: and waiting for a container runtime to come up first is the wrong trade on a
#: controller. So on a cold boot the panel can be ready before dockerd has
#: created its bridge, and binding then would miss the address the proxy
#: arrives on. The web server already shows a loading page on this port while
#: it starts, so a short wait costs nothing visible.
BRIDGE_WAIT_SECONDS = 60.0
_BRIDGE_POLL_SECONDS = 2.0


def _wait_for_a_bridge(timeout: float) -> list[str]:
    """Poll for Docker bridges until one appears or the time runs out.

    Args:
        timeout: Seconds to wait in total.

    Returns:
        The addresses found, possibly empty.
    """
    deadline = time.monotonic() + timeout
    waited = False
    while True:
        found = docker_bridge_addresses()
        if found or time.monotonic() >= deadline:
            if waited and found:
                _LOGGER.info("Docker bridge appeared; binding the panel to it.")
            return found
        if not waited:
            _LOGGER.info(
                "Waiting up to %.0fs for a Docker bridge — the panel is behind "
                "the proxy and the proxy arrives on one.",
                timeout,
            )
            waited = True
        time.sleep(_BRIDGE_POLL_SECONDS)


def binds_for(exposure: str, port: int, wait: float = BRIDGE_WAIT_SECONDS) -> list[str]:
    """The ``host:port`` strings to hand to the server.

    Args:
        exposure: One of :class:`Exposure`.
        port: The port to listen on.
        wait: Seconds to wait for a Docker bridge, when one is needed.

    Returns:
        Bind strings, never empty.
    """
    if exposure != Exposure.PROXY:
        return [f"0.0.0.0:{port}"]

    hosts = [LOOPBACK, *_wait_for_a_bridge(wait)]
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


def proxy_is_serving(port: int = DEFAULT_PROXY_PORT, timeout: float = 5.0) -> tuple[bool, str]:
    """Whether the reverse proxy is answering for this device right now.

    Asked before the panel is taken off the LAN, because that change is only
    safe if there is something else to reach it through. It is not enough that
    a port is open: Caddy answers on 8443 whether or not it can reach the
    application behind it, and a 502 there would mean a controller that has
    just closed its own front door onto an empty corridor.

    So this asks the proxy for something only the application can answer, over
    the loopback, and looks at what comes back.

    Args:
        port: The port the proxy publishes HTTPS on.
        timeout: Seconds to allow.

    Returns:
        Whether it is serving, and a short reason when it is not.
    """
    # The certificate is the device's own, usually from Caddy's internal CA,
    # and this request never leaves the machine. What is being tested is
    # whether the proxy reaches the application, not who signed the key.
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    url = f"https://127.0.0.1:{port}/api/init"
    try:
        with urllib.request.urlopen(url, timeout=timeout, context=context) as response:
            if response.status != 200:
                return False, f"the proxy answered {response.status} on port {port}"
            body = json.loads(response.read(65536).decode("utf-8", "replace"))
    except urllib.error.HTTPError as err:
        return False, f"the proxy answered {err.code} on port {port}"
    except (urllib.error.URLError, OSError) as err:
        return False, f"nothing is serving HTTPS on port {port}: {err}"
    except (ValueError, json.JSONDecodeError):
        return False, f"port {port} answered with something that is not this panel"

    if "version" not in body:
        return False, f"port {port} is serving something else"
    return True, ""
