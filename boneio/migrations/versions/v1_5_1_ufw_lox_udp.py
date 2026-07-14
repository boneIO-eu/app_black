"""Open UFW firewall port for Loxone UDP communication.

When ``lox_udp`` is enabled in the BoneIO configuration, port 4445/udp
must be open so that the Loxone Miniserver can send commands to BoneIO.

Without this rule, the UFW DROP policy silently discards incoming UDP
datagrams even though ``tcpdump`` shows them arriving at the interface
(tcpdump captures packets before iptables filtering).
"""

from __future__ import annotations

from boneio.migrations.actions import MigrationAction, UfwAllow

VERSION = "1.5.1"
DESCRIPTION = "Open UFW port 4445/udp for Loxone UDP protocol"
REQUIRES_ROOT = True


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    return [
        UfwAllow(
            port=4445,
            proto="udp",
            comment="BoneIO Loxone UDP",
        ),
    ]
