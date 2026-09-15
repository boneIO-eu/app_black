"""Bound where device discovery is allowed to connect (F-15).

``discover-wled`` and ``discover-esphome`` took a host and a port and connected
to them. That made the controller three things it should not be: a port scanner
for its own loopback interface, a way to reach anything on the network from the
controller's address, and — because the upstream error was handed back verbatim
— a banner grabber. The report's proof reads an SSH version string out of an
HTTP error.

The guard is shaped by what the feature is actually for. A WLED or ESPHome node
lives on the local network, so private addresses stay allowed; blocking them
would leave nothing to discover. Everything with no legitimate reason to be a
discovery target is refused:

``loopback``
    The controller's own services. This is the port-scanning oracle from the
    report, and the only thing it can find is boneIO itself.
``link-local``
    Includes 169.254.169.254, the cloud metadata address — an SSRF target
    worth closing even on hardware that will never run in a cloud.
``global``
    A light strip is not on the public internet. Refusing it stops the
    controller being used to reach out from its own address.
``multicast, reserved, unspecified``
    Not endpoints.

Ports are checked against a short list per protocol, because a free choice of
port is what turns discovery into a scanner. Anything unusual can still be
added by hand; discovery is the convenience, not the only way in.
"""

from __future__ import annotations

import ipaddress
import logging
import socket

_LOGGER = logging.getLogger(__name__)

#: Ports a WLED node is plausibly served on. WLED's web server is HTTP.
WLED_PORTS = frozenset({80, 443, 8080})

#: The ESPHome native API port. ESPHome does not use another by convention.
ESPHOME_PORTS = frozenset({6053})


class DiscoveryTargetError(Exception):
    """Raised when a discovery target is not allowed.

    The message is deliberately the same for every reason. Saying which rule
    was hit would answer questions about the network the caller should be
    asking the network, not the controller.
    """


#: One message for every refusal — see :class:`DiscoveryTargetError`.
REFUSAL = (
    "That address cannot be used for discovery. Use the device's address on "
    "your local network."
)


def _resolve(host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Every address a host name resolves to.

    All of them are checked, not just the first: a name under the caller's
    control can resolve to one harmless address and one loopback address, and
    checking only the first would wave the pair through.

    Args:
        host: Host name or literal address.

    Returns:
        Resolved addresses.

    Raises:
        DiscoveryTargetError: If the name cannot be resolved.
    """
    try:
        return [ipaddress.ip_address(host.strip())]
    except ValueError:
        pass

    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError) as err:
        _LOGGER.info("Discovery target %r did not resolve: %s", host, err)
        raise DiscoveryTargetError(REFUSAL) from err

    addresses = []
    for info in infos:
        try:
            addresses.append(ipaddress.ip_address(info[4][0]))
        except ValueError:
            continue

    if not addresses:
        raise DiscoveryTargetError(REFUSAL)
    return addresses


def _is_allowed(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Whether one address may be a discovery target.

    Args:
        address: Resolved address.

    Returns:
        True for a private address that is not loopback or link-local.
    """
    if (
        address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        return False

    # IPv4-mapped IPv6 (::ffff:127.0.0.1) would otherwise slip past the checks
    # above, which report False for the wrapper while the address inside is
    # loopback.
    mapped = getattr(address, "ipv4_mapped", None)
    if mapped is not None:
        return _is_allowed(mapped)

    return address.is_private


def assert_target_allowed(host: str, port: int, allowed_ports: frozenset[int]) -> None:
    """Refuse a discovery target that is out of bounds.

    Args:
        host: Host name or address the caller asked for.
        port: TCP port the caller asked for.
        allowed_ports: Ports this protocol is served on.

    Raises:
        DiscoveryTargetError: If the target is not allowed. The message never
            says why, and never carries anything learned from the target.
    """
    if port not in allowed_ports:
        _LOGGER.warning(
            "Refused discovery to %s:%s — port not in %s",
            host,
            port,
            sorted(allowed_ports),
        )
        raise DiscoveryTargetError(REFUSAL)

    for address in _resolve(host):
        if not _is_allowed(address):
            _LOGGER.warning(
                "Refused discovery to %s (%s) — address is not a local device",
                host,
                address,
            )
            raise DiscoveryTargetError(REFUSAL)
